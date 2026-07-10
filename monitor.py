"""
Telegram Price Monitor - Tempo Real
Conecta ao Telegram e escuta mensagens instantaneamente via eventos.
Sem polling — notificação assim que a mensagem chega no grupo.

Envio de alertas via WhatsApp usando o serviço local whatsapp-sender
(Baileys, self-hosted, sem custo de terceiros).
"""

import asyncio
import json
import logging
import os
import urllib.request
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

# ─── Configurações editáveis via config.json ────────────────────────────────
_config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_config_path, encoding="utf-8") as _f:
    _config = json.load(_f)

GROUPS   = [g.strip() for g in _config["groups"] if g.strip()]
KEYWORDS = [k.strip().lower() for k in _config["keywords"] if k.strip()]

log.info(f"Grupos: {GROUPS}")
log.info(f"Keywords: {KEYWORDS}")


# ─── WhatsApp via whatsapp-sender local (Baileys) ───────────────────────────

def send_whatsapp(text: str) -> None:
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
            else:
                log.error(f"whatsapp-sender retornou erro: {result.get('error')}")
    except Exception as e:
        log.error(f"Erro ao enviar WhatsApp (whatsapp-sender indisponível?): {e}")


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

async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
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

    # Escuta mensagens em tempo real
    @client.on(events.NewMessage(chats=group_entities))
    async def handler(event):
        if not event.text:
            return
        if any(kw in event.text.lower() for kw in KEYWORDS):
            group_name = getattr(event.chat, "title", "Grupo desconhecido")
            log.info(f"✅ Match em '{group_name}': {event.text[:80]}")
            send_whatsapp(format_alert(group_name, event.text))

    log.info("🟢 Monitor ativo. Aguardando mensagens em tempo real...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
