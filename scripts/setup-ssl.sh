#!/usr/bin/env bash
# Phase 30-07: первый выпуск SSL-сертификата Let's Encrypt
# для gaaala.duckdns.org через DNS-01 challenge (DuckDNS API).
#
# Запускать ОДИН РАЗ на проде после первого деплоя с обновлённым nginx.conf
# и docker-compose.yml. Renewal дальше идёт автоматически в certbot-контейнере.
#
# Prerequisites:
#   1. /opt/vsks-crm/.env содержит:  DUCKDNS_TOKEN=<твой_токен>
#   2. gaaala.duckdns.org резолвится в IP сервера
#   3. docker compose pull && docker compose up -d  (выкатились новые services)
#
# Использование (на сервере):
#   cd /opt/vsks-crm
#   bash scripts/setup-ssl.sh
#
# Опционально, для теста на Let's Encrypt staging (не лимитируется):
#   bash scripts/setup-ssl.sh --staging

set -euo pipefail

DOMAIN="gaaala.duckdns.org"
EMAIL="2964241@gmail.com"
STAGING_FLAG=""

if [ "${1:-}" = "--staging" ]; then
  STAGING_FLAG="--staging"
  echo "→ Режим: STAGING (тестовый CA, не реальный сертификат)"
fi

if [ -z "${DUCKDNS_TOKEN:-}" ]; then
  if [ -f .env ]; then
    set -a; . .env; set +a
  fi
fi

if [ -z "${DUCKDNS_TOKEN:-}" ]; then
  echo "ERROR: DUCKDNS_TOKEN не задан. Положи в .env или экспортни."
  exit 1
fi

echo "→ Проверка DNS: $DOMAIN"
RESOLVED=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || true)
EXPECTED=$(curl -s ifconfig.me || echo "unknown")
echo "   $DOMAIN → $RESOLVED (текущий IP сервера: $EXPECTED)"

if [ "$RESOLVED" != "$EXPECTED" ] && [ "$EXPECTED" != "unknown" ]; then
  echo "WARNING: $DOMAIN указывает на $RESOLVED, а сервер на $EXPECTED."
  echo "         Обнови A-запись: curl 'https://www.duckdns.org/update?domains=gaaala&token=\$DUCKDNS_TOKEN&ip='"
  echo "         (пустой ip = auto-detect по IP откуда запрос)"
  echo "         Прервать? [y/N]"
  read -r ans
  [ "$ans" = "y" ] && exit 1
fi

echo "→ Запуск certbot certonly через DNS-01 challenge..."

docker compose run --rm \
  -e DUCKDNS_TOKEN="$DUCKDNS_TOKEN" \
  --entrypoint certbot \
  certbot certonly \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --authenticator dns-duckdns \
    --dns-duckdns-token "$DUCKDNS_TOKEN" \
    --dns-duckdns-propagation-seconds 60 \
    -d "$DOMAIN" \
    $STAGING_FLAG

echo "→ Сертификат выпущен. Перезагружаю nginx..."
docker compose exec nginx nginx -s reload

echo ""
echo "✓ Готово. Проверь:"
echo "   curl -I https://$DOMAIN"
echo "   openssl s_client -connect $DOMAIN:443 -servername $DOMAIN </dev/null 2>/dev/null | openssl x509 -noout -dates"
echo ""
echo "Renewal автоматический в certbot-контейнере (каждые 12 часов проверка)."
