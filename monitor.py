"""
Telegram Price Monitor - Tempo Real
Conecta ao Telegram e escuta mensagens instantaneamente via eventos.
Sem polling — notificação assim que a mensagem chega no grupo.

Envio de alertas via WhatsApp usando o serviço local whatsapp-sender
(Baileys, self-hosted, sem custo de terceiros).

Aviso de queda: se a sessão do WhatsApp cair, o monitor avisa pelo próprio
Telegram (lembrete nas "Mensagens salvas", que gera notificação) e guarda lá
as promoções que não conseguiu entregar. Se for a sessão do Telegram que
cair, o aviso vai pelo WhatsApp.
"""

import asyncio
import json
import logging
import os
import time
import urllib.request
from datetime import timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── Configurações sensíveis via .env ───────────────────────────────────────
API_ID         = int(os.environ["TELEGRAM_API_ID"])
API_HASH       = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
WHATSAPP_SENDER_URL = os.environ.get("WHATSAPP_SENDER_URL", "http://127.0.0.1:3300/send")
WHATSAPP_STATUS_URL = os.environ.get(
    "WHATSAPP_STATUS_URL", WHATSAPP_SENDER_URL.rsplit("/", 1)[0] + "/status"
)

# ─── Aviso de queda de sessão ───────────────────────────────────────────────
CHECK_INTERVAL   = int(os.environ.get("WA_CHECK_INTERVAL", "300"))    # s entre verificações
FAILS_TO_ALERT   = int(os.environ.get("WA_FAILS_TO_ALERT", "2"))      # falhas seguidas antes de avisar
REALERT_INTERVAL = int(os.environ.get("WA_REALERT_INTERVAL", "86400"))  # s entre lembretes enquanto fora do ar
REMINDER_DELAY   = 70  # s; mensagem agendada nas Mensagens salvas vira lembrete com notificação
TG_ALERT_MARKER  = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".telegram_down_alerted")

# ─── Configurações editáveis via config.json ────────────────────────────────
_config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_config_path, encoding="utf-8") as _f:
    _config = json.load(_f)

GROUPS   = [g.strip() for g in _config["groups"] if g.strip()]
KEYWORDS = [k.strip().lower() for k in _config["keywords"] if k.strip()]

log.info(f"Grupos: {GROUPS}")
log.info(f"Keywords: {KEYWORDS}")


# ─── WhatsApp via whatsapp-sender local (Baileys) ───────────────────────────

def send_whatsapp(text: str) -> bool:
    """Envia pelo whatsapp-sender. Retorna True se a mensagem saiu."""
    try:
        payload = json.dumps({"message": text}).encode("utf-8")
        req = urllib.request.Request(
            WHATSAPP_SENDER_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                log.info("WhatsApp enviado via whatsapp-sender.")
                return True
            log.error(f"whatsapp-sender retornou erro: {result.get('error')}")
    except Exception as e:
        log.error(f"Erro ao enviar WhatsApp (whatsapp-sender indisponível?): {e}")
    return False


def whatsapp_status() -> tuple[bool, str]:
    """Consulta o /status do whatsapp-sender. Retorna (conectado, motivo)."""
    try:
        with urllib.request.urlopen(WHATSAPP_STATUS_URL, timeout=10) as resp:
            st = json.loads(resp.read().decode())
    except Exception as e:
        return False, f"serviço whatsapp-sender não responde ({e})"
    if st.get("connected"):
        return True, "conectado"
    if st.get("loggedOut"):
        return False, "sessão encerrada pelo WhatsApp (logout) — é preciso parear de novo"
    last = st.get("lastDisconnect") or {}
    detalhe = f" (último erro: {last.get('statusCode')} {last.get('message')})" if last else ""
    return False, "WhatsApp desconectado" + detalhe


def format_alert(group_name: str, msg_text: str) -> str:
    preview = msg_text[:400] + ("..." if len(msg_text) > 400 else "")
    return (
        f"🔔 *PROMOÇÃO DETECTADA!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Grupo: {group_name}\n\n"
        f"{preview}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 Keywords: {', '.join(KEYWORDS)}"
    )


# ─── Monitor em tempo real ───────────────────────────────────────────────────

async def notify_telegram(client, text: str) -> None:
    """Avisa o dono pelo Telegram, nas Mensagens salvas.

    Mensagem comum para si mesmo não notifica; mensagem AGENDADA nas Mensagens
    salvas vira lembrete e notifica. Se o agendamento falhar, envia direto.
    """
    try:
        await client.send_message("me", text, schedule=timedelta(seconds=REMINDER_DELAY))
        log.info("Aviso agendado nas Mensagens salvas do Telegram (lembrete).")
    except Exception as e:
        log.error(f"Falha ao agendar aviso no Telegram ({e}); enviando direto.")
        try:
            await client.send_message("me", text)
        except Exception as e2:
            log.error(f"Falha ao enviar aviso no Telegram: {e2}")


class WhatsAppWatchdog:
    """Vigia a sessão do WhatsApp e avisa pelo Telegram quando ela cai/volta."""

    def __init__(self, client):
        self.client = client
        self.fails = 0          # verificações seguidas com falha
        self.alerted_at = 0.0   # quando o último aviso de queda foi enviado (0 = sem queda avisada)
        self.lock = asyncio.Lock()

    async def check(self, immediate: bool = False) -> None:
        """immediate=True: um envio real acabou de falhar, não espera a 2ª verificação."""
        async with self.lock:
            ok, reason = await asyncio.to_thread(whatsapp_status)
            now = time.time()
            if ok:
                if self.alerted_at:
                    await notify_telegram(
                        self.client,
                        "✅ Monitor de preços: o WhatsApp voltou a funcionar. Alertas normalizados.",
                    )
                self.fails = 0
                self.alerted_at = 0.0
                return

            self.fails += 1
            log.warning(f"WhatsApp fora do ar ({self.fails}x seguidas): {reason}")
            if not immediate and self.fails < FAILS_TO_ALERT:
                return  # pode ser só uma reconexão rápida
            if self.alerted_at and now - self.alerted_at < REALERT_INTERVAL:
                return  # já avisou há pouco
            primeiro = not self.alerted_at
            self.alerted_at = now
            await notify_telegram(
                self.client,
                ("⚠️ Monitor de preços: o WhatsApp parou de enviar alertas.\n"
                 if primeiro else
                 "⚠️ Monitor de preços: o WhatsApp CONTINUA sem enviar alertas.\n")
                + f"Motivo: {reason}\n\n"
                "Enquanto isso, as promoções detectadas ficam guardadas aqui nas "
                "Mensagens salvas. Para voltar: parear o WhatsApp de novo na VM.",
            )

    async def run(self) -> None:
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            try:
                await self.check()
            except Exception as e:
                log.error(f"Erro no watchdog do WhatsApp: {e}")


def alert_telegram_session_lost() -> None:
    """Sessão do Telegram inválida: avisa pelo WhatsApp, no máximo 1x a cada 24h
    (o systemd reinicia o serviço a cada 30s, então é preciso limitar)."""
    try:
        if time.time() - os.path.getmtime(TG_ALERT_MARKER) < REALERT_INTERVAL:
            return
    except OSError:
        pass
    if send_whatsapp(
        "⚠️ *Monitor de preços parado*\n"
        "A sessão do Telegram foi encerrada e o monitor não consegue mais ler os grupos.\n"
        "É preciso gerar uma nova TELEGRAM_SESSION_STRING (generate_session.py) "
        "e atualizar o .env na VM."
    ):
        with open(TG_ALERT_MARKER, "w") as f:
            f.write(str(time.time()))


async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        log.error("Sessão do Telegram inválida ou revogada. Encerrando.")
        await asyncio.to_thread(alert_telegram_session_lost)
        await client.disconnect()
        raise SystemExit(1)
    try:
        os.remove(TG_ALERT_MARKER)  # sessão ok: libera um novo aviso se cair de novo
    except OSError:
        pass
    log.info("Conectado ao Telegram.")

    # Resolve grupos para entidades
    group_entities = []
    for group_ref in GROUPS:
        try:
            entity = await client.get_entity(group_ref)
            group_entities.append(entity)
            log.info(f"✅ Monitorando: {getattr(entity, 'title', group_ref)}")
        except Exception as e:
            log.error(f"⚠️ Grupo '{group_ref}' inacessível: {e}")

    if not group_entities:
        log.error("Nenhum grupo válido. Encerrando.")
        return

    watchdog = WhatsAppWatchdog(client)

    # Escuta mensagens em tempo real
    @client.on(events.NewMessage(chats=group_entities))
    async def handler(event):
        if not event.text:
            return
        if any(kw in event.text.lower() for kw in KEYWORDS):
            group_name = getattr(event.chat, "title", "Grupo desconhecido")
            log.info(f"✅ Match em '{group_name}': {event.text[:80]}")
            alert = format_alert(group_name, event.text)
            if await asyncio.to_thread(send_whatsapp, alert):
                return
            # WhatsApp falhou: não perde a promoção e dispara o aviso de queda
            try:
                await client.send_message(
                    "me", alert + "\n\n(não entregue no WhatsApp — sessão fora do ar)"
                )
            except Exception as e:
                log.error(f"Falha ao guardar alerta no Telegram: {e}")
            await watchdog.check(immediate=True)

    watchdog_task = asyncio.create_task(watchdog.run())
    log.info("🟢 Monitor ativo. Aguardando mensagens em tempo real...")
    try:
        await client.run_until_disconnected()
    finally:
        watchdog_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
