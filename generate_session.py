"""
generate_session.py
Rode este script UMA VEZ no seu computador para gerar a StringSession do Telegram.
A string gerada vai para o secret TELEGRAM_SESSION_STRING no GitHub.

Uso:
    pip install telethon
    python generate_session.py
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("=" * 55)
    print("  Gerador de StringSession — Telegram Price Monitor")
    print("=" * 55)
    print()
    print("Você vai precisar de:")
    print("  • API_ID e API_HASH de https://my.telegram.org")
    print("  • Seu número de telefone (com DDI, ex: +5521...)")
    print()

    api_id   = int(input("API ID  : ").strip())
    api_hash = input("API Hash: ").strip()

    print()
    print("Conectando ao Telegram...")

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print()
        print("✅ Autenticado com sucesso!")
        print()
        print("=" * 55)
        print("  SUA STRING DE SESSÃO (copie tudo abaixo):")
        print("=" * 55)
        print()
        print(client.session.save())
        print()
        print("=" * 55)
        print("Guarde essa string como secret TELEGRAM_SESSION_STRING no GitHub.")
        print("NÃO compartilhe com ninguém — dá acesso total à sua conta.")


asyncio.run(main())
