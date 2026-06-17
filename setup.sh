#!/bin/bash
# setup.sh
# Roda UMA VEZ na VM do Oracle Cloud para configurar o ambiente.
# Uso: bash setup.sh SEU_USUARIO/price-monitor

set -e

REPO=${1:-"SEU_USUARIO/price-monitor"}
REPO_URL="https://github.com/${REPO}.git"
INSTALL_DIR="$HOME/telegram-price-monitor"

echo "========================================"
echo "  Telegram Price Monitor — Setup VM"
echo "========================================"
echo ""

echo "📦 Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

echo "💾 Configurando swap (essencial com 1GB de RAM)..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✅ Swap de 2GB criado e ativado."
else
    echo "✅ Swap já existe, pulando."
fi

echo "🐍 Instalando Python e Git..."
sudo apt install -y python3 python3-pip python3-venv git

echo "📁 Clonando repositório..."
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "🔧 Criando ambiente virtual..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install telethon

echo ""
echo "========================================"
echo "  ✅ Setup concluído!"
echo "========================================"
echo ""
free -h
echo ""
echo "Próximos passos:"
echo ""
echo "1. Crie o arquivo de variáveis de ambiente:"
echo "   nano $INSTALL_DIR/.env"
echo ""
echo "   Cole o seguinte conteúdo (com seus valores reais):"
echo "   ─────────────────────────────────────────"
echo "   TELEGRAM_API_ID=seu_api_id"
echo "   TELEGRAM_API_HASH=seu_api_hash"
echo "   TELEGRAM_SESSION_STRING=sua_session_string"
echo "   CALLMEBOT_PHONE=5521999999999"
echo "   CALLMEBOT_APIKEY=sua_apikey"
echo "   ─────────────────────────────────────────"
echo ""
echo "2. Instale e ative o serviço:"
echo "   sudo cp $INSTALL_DIR/telegram-monitor.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable telegram-monitor"
echo "   sudo systemctl start telegram-monitor"
echo ""
echo "3. Verifique se está rodando:"
echo "   sudo systemctl status telegram-monitor"
echo ""
echo "4. Acompanhe os logs em tempo real:"
echo "   sudo journalctl -u telegram-monitor -f"
