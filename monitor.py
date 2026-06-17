"""
Telegram Price Monitor - Tempo Real
Conecta ao Telegram e escuta mensagens instantaneamente via eventos.
Sem polling — notificação assim que a mensagem chega no grupo.
"""

import asyncio
import json
import logging
import os
import urllib.request
import urllib.parse
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
WA_PHONE       = os.environ["CALLMEBOT_PHONE"]
WA_APIKEY      = os.environ["CALLMEBOT_APIKEY"]

# ─── Configurações editáveis via config.json ────────────────────────────────
_config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_config_path, encoding="utf-8") as _f:
    _config = json.load(_f)

GROUPS   = [g.strip() for g in _config["groups"] if g.strip()]
KEYWORDS = [k.strip().lower() for k in _config["keywords"] if k.strip()]

log.info(f"Grupos: {GROUPS}")
log.info(f"Keywords: {KEYWORDS}")


# ─── WhatsApp via CallMeBot ──────────────────────────────────────────────────

def send_whatsapp(text: str) -> None:
    encoded = urllib.parse.quote(text)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WA_PHONE}&text={encoded}&apikey={WA_APIKEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            status = resp.read().decode()
            log.info(f"WhatsApp enviado. Resposta: {status[:80]}")
    except Exception as e:
        log.error(f"Erro ao enviar WhatsApp: {e}")


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
