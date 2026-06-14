"""
Telegram Price Monitor
Monitora grupos do Telegram por palavras-chave e envia alertas via WhatsApp (CallMeBot).
"""

import asyncio
import json
import os
import urllib.request
import urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession

# ─── Configurações sensíveis via secrets do GitHub ──────────────────────────
API_ID         = int(os.environ["TELEGRAM_API_ID"])
API_HASH       = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
WA_PHONE       = os.environ["CALLMEBOT_PHONE"]           # ex: 5521999999999
WA_APIKEY      = os.environ["CALLMEBOT_APIKEY"]
GIST_ID        = os.environ["GIST_ID"]
GH_PAT         = os.environ["GH_PAT"]                    # Personal Access Token com escopo gist

# ─── Configurações editáveis via config.json no repositório ─────────────────
_config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_config_path, encoding="utf-8") as _f:
    _config = json.load(_f)

GROUPS   = [g.strip() for g in _config["groups"] if g.strip()]
KEYWORDS = [k.strip().lower() for k in _config["keywords"] if k.strip()]
GIST_FILENAME = "tg_monitor_state.json"


# ─── Gist (estado persistente) ──────────────────────────────────────────────

def _gist_request(method: str, payload: dict | None = None) -> dict:
    url = f"https://api.github.com/gists/{GIST_ID}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"token {GH_PAT}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def load_state() -> dict:
    """Carrega o estado (último ID visto por grupo) do Gist."""
    try:
        gist = _gist_request("GET")
        files = gist.get("files", {})
        if GIST_FILENAME in files:
            return json.loads(files[GIST_FILENAME]["content"])
    except Exception as e:
        print(f"[state] Erro ao carregar estado: {e}")
    return {}


def save_state(state: dict) -> None:
    """Salva o estado atualizado no Gist."""
    try:
        _gist_request("PATCH", {
            "files": {GIST_FILENAME: {"content": json.dumps(state, indent=2)}}
        })
    except Exception as e:
        print(f"[state] Erro ao salvar estado: {e}")


# ─── Notificação WhatsApp via CallMeBot ─────────────────────────────────────

def send_whatsapp(text: str) -> None:
    encoded = urllib.parse.quote(text)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WA_PHONE}&text={encoded}&apikey={WA_APIKEY}"
    )
    try:
        with urllib.request.urlopen(url) as resp:
            status = resp.read().decode()
            print(f"[whatsapp] Resposta CallMeBot: {status[:100]}")
    except Exception as e:
        print(f"[whatsapp] Erro ao enviar mensagem: {e}")


def format_alert(group_name: str, msg_text: str, msg_id: int) -> str:
    preview = msg_text[:400] + ("..." if len(msg_text) > 400 else "")
    return (
        f"🔔 *PROMOÇÃO DETECTADA!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Grupo: {group_name}\n\n"
        f"{preview}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 Keywords: {', '.join(KEYWORDS)}"
    )


# ─── Monitoramento principal ────────────────────────────────────────────────

async def monitor():
    state = load_state()
    new_state = dict(state)
    total_alerts = 0

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        for group_ref in GROUPS:
            print(f"[monitor] Verificando: {group_ref}")
            try:
                entity = await client.get_entity(group_ref)
                group_id = str(entity.id)
                group_name = getattr(entity, "title", group_ref)
                last_id = state.get(group_id)  # None = primeira execução

                # Busca as últimas 50 mensagens
                messages = await client.get_messages(entity, limit=50)

                if not messages:
                    continue

                # Primeira execução: inicializa o estado sem enviar alertas
                if last_id is None:
                    new_state[group_id] = messages[0].id
                    print(f"[monitor] '{group_name}' inicializado (ID mais recente: {messages[0].id})")
                    continue

                # Filtra apenas mensagens novas com texto
                new_msgs = [m for m in messages if m.id > last_id and m.text]

                if new_msgs:
                    # Atualiza o estado para o ID mais recente
                    new_state[group_id] = messages[0].id

                # Verifica keywords (da mais antiga para a mais nova)
                for msg in reversed(new_msgs):
                    if any(kw in msg.text.lower() for kw in KEYWORDS):
                        print(f"[monitor] ✅ Match em '{group_name}' (ID {msg.id})")
                        alert_text = format_alert(group_name, msg.text, msg.id)
                        send_whatsapp(alert_text)
                        total_alerts += 1
                        # Pausa entre envios pra respeitar rate limit do CallMeBot
                        await asyncio.sleep(3)

            except Exception as e:
                print(f"[monitor] ⚠️ Erro no grupo '{group_ref}': {e}")

    save_state(new_state)
    print(f"[monitor] Concluído. {total_alerts} alerta(s) enviado(s).")


if __name__ == "__main__":
    asyncio.run(monitor())
