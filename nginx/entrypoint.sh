#!/bin/sh
# Phase 30-07: Self-signed placeholder для gaaala.duckdns.org
# Phase 30-xx: adminer.gaaala.duckdns.org basic-auth файл из env
# Запускается через /docker-entrypoint.d/ ДО старта nginx.

set -e

DOMAIN="gaaala.duckdns.org"
LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"

# Установить openssl если его нет (alpine: уже есть) — нужен и для
# self-signed placeholder, и для htpasswd-хеша ниже.
command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl

# ── Self-signed placeholder ──────────────────────────────────────────
# Если LE-сертификата нет — создаём snake-oil чтобы nginx не падал на
# старте. После запуска setup-ssl.sh реальный cert от Let's Encrypt
# заменит этот.
if [ -f "${LIVE_DIR}/fullchain.pem" ] && [ -f "${LIVE_DIR}/privkey.pem" ]; then
  echo "[entrypoint] Cert уже существует: ${LIVE_DIR}/fullchain.pem"
else
  echo "[entrypoint] LE cert не найден, генерирую self-signed placeholder..."

  mkdir -p "${LIVE_DIR}"

  openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
    -keyout "${LIVE_DIR}/privkey.pem" \
    -out "${LIVE_DIR}/fullchain.pem" \
    -subj "/CN=${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN}" 2>/dev/null

  chmod 644 "${LIVE_DIR}/fullchain.pem"
  chmod 600 "${LIVE_DIR}/privkey.pem"

  echo "[entrypoint] Self-signed placeholder создан. Запусти scripts/setup-ssl.sh для реального LE cert."
fi

# ── Adminer basic-auth ───────────────────────────────────────────────
# Файл /etc/nginx/secrets/adminer.htpasswd собирается из переменной
# окружения ADMINER_HTPASSWD (docker-compose.yml → .env), а не из
# бинд-маунта — абсолютный хостовый путь ломал бы стек на любой другой
# машине (docker создал бы там каталог вместо файла, если его нет).
# Пустая переменная (например .env без строки ADMINER_HTPASSWD, как на
# машине разработчика) — не ошибка: пишем заведомо неподходящий хеш со
# случайным паролем, чтобы vhost честно отдавал 401, а не 500.
SECRETS_DIR="/etc/nginx/secrets"
HTPASSWD_FILE="${SECRETS_DIR}/adminer.htpasswd"
mkdir -p "${SECRETS_DIR}"

if [ -n "${ADMINER_HTPASSWD:-}" ]; then
  echo "[entrypoint] ADMINER_HTPASSWD задан, записываю ${HTPASSWD_FILE}"
  printf '%s\n' "${ADMINER_HTPASSWD}" > "${HTPASSWD_FILE}"
else
  echo "[entrypoint] ADMINER_HTPASSWD пуст — adminer будет честно отдавать 401 (неподходящий хеш)"
  RANDOM_PW=$(openssl rand -hex 20)
  echo "disabled:$(openssl passwd -apr1 "${RANDOM_PW}")" > "${HTPASSWD_FILE}"
fi
chmod 644 "${HTPASSWD_FILE}"
