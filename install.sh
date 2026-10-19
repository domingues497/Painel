#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Painel de infraestrutura Zabbix — instalação/atualização automática no Ubuntu.
#
# Baixa o projeto do GitHub, cria o ambiente Python, grava o serviço systemd
# e sobe o servidor (Uvicorn). Pode ser executado várias vezes: na primeira vez
# clona o repositório; nas seguintes apenas atualiza o código e reinicia.
#
# Uso:  sudo bash install.sh
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_URL="https://github.com/domingues497/Painel.git"
APP_DIR="/opt/painel"
SERVICE_NAME="painel"
SERVICE_USER="painel"
HOST="0.0.0.0"
PORT="8000"

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute como root: sudo bash install.sh" >&2
  exit 1
fi

echo "==> 1/6 Instalando dependências do sistema"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git python3 python3-venv python3-pip
else
  echo "   Aviso: apt não encontrado. Garanta git, python3-venv e python3-pip instalados." >&2
fi

echo "==> 2/6 Preparando usuário de serviço (${SERVICE_USER})"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> 3/6 Obtendo o código em ${APP_DIR}"
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$SERVICE_USER" git -C "$APP_DIR" fetch --all --prune
  sudo -u "$SERVICE_USER" git -C "$APP_DIR" pull --ff-only
else
  mkdir -p "$APP_DIR"
  GIT_TERMINAL_PROMPT=0 git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

echo "==> 4/6 Criando ambiente virtual e instalando dependências Python"
sudo -u "$SERVICE_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> 5/6 Configurando o arquivo .env"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "   .env criado. Edite ZABBIX_URL e ZABBIX_TOKEN em ${APP_DIR}/.env"
fi
chown "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "==> 6/6 Registrando e iniciando o serviço systemd"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Painel de infraestrutura Zabbix (FastAPI/Uvicorn)
After=network.target

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
ExecStart=${APP_DIR}/.venv/bin/uvicorn app:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

IP_TEXT="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "=========================================================="
echo " Painel instalado e em execução."
echo "   URL:     http://${IP_TEXT:-<IP_DO_SERVIDOR>}:${PORT}"
echo "   .env:    ${APP_DIR}/.env   (edite e rode: systemctl restart ${SERVICE_NAME})"
echo "   Status:  systemctl status ${SERVICE_NAME}"
echo "   Logs:    journalctl -u ${SERVICE_NAME} -f"
echo "=========================================================="
