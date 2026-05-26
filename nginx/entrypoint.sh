#!/bin/sh
# Phase 30-07: Self-signed placeholder для gaaala.duckdns.org
# Запускается через /docker-entrypoint.d/ ДО старта nginx.
# Если LE-сертификата нет — создаём snake-oil чтобы nginx не падал на старте.
# После запуска setup-ssl.sh реальный cert от Let's Encrypt заменит этот.

set -e

DOMAIN="gaaala.duckdns.org"
LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"

if [ -f "${LIVE_DIR}/fullchain.pem" ] && [ -f "${LIVE_DIR}/privkey.pem" ]; then
  echo "[entrypoint] Cert уже существует: ${LIVE_DIR}/fullchain.pem"
  exit 0
fi

echo "[entrypoint] LE cert не найден, генерирую self-signed placeholder..."

# Установить openssl если его нет (alpine: уже есть)
command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl

mkdir -p "${LIVE_DIR}"

openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
  -keyout "${LIVE_DIR}/privkey.pem" \
  -out "${LIVE_DIR}/fullchain.pem" \
  -subj "/CN=${DOMAIN}" \
  -addext "subjectAltName=DNS:${DOMAIN}" 2>/dev/null

chmod 644 "${LIVE_DIR}/fullchain.pem"
chmod 600 "${LIVE_DIR}/privkey.pem"

echo "[entrypoint] Self-signed placeholder создан. Запусти scripts/setup-ssl.sh для реального LE cert."
