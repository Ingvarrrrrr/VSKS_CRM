#!/bin/bash
set -u  # fail on unset vars; keep going on non-zero so one step can't dead-lock the rest
LOG=/var/log/vsks-deploy.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "===== $(ts) deploy start =====" >> "$LOG"

cd /opt/vsks-crm || { echo "[$(ts)] cd /opt/vsks-crm FAILED" >> "$LOG"; exit 1; }

# Track webhook.py hash before pull so we know whether to restart the webhook service
WEBHOOK_HASH_BEFORE=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)
# Track nginx config + docker-compose hash. nginx был отдельный TODO (websocket
# config-изменения не доходили до прода, т.к. autodeploy не пересобирал nginx).
# Rebuild ТОЛЬКО если nginx/* или docker-compose.yml поменялись — не хотим
# прерывать активные сессии браузера на каждом backend-only push.
NGINX_HASH_BEFORE=$(cat nginx/nginx.conf docker-compose.yml 2>/dev/null | sha256sum | cut -d' ' -f1)

git checkout -f claude >> "$LOG" 2>&1
git clean -fd >> "$LOG" 2>&1
git pull origin claude >> "$LOG" 2>&1

WEBHOOK_HASH_AFTER=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)
NGINX_HASH_AFTER=$(cat nginx/nginx.conf docker-compose.yml 2>/dev/null | sha256sum | cut -d' ' -f1)

# Rebuild backend image (picks up code + model changes)
docker compose build backend >> "$LOG" 2>&1

# Apply schema migrations BEFORE starting backend container.
# Reason: if a migration adds a column, SQLAlchemy first request will
# crash with UndefinedColumn → backend Exited → docker exec fails →
# `|| true` swallows the error → site stays 502.
# Use `docker compose run --rm` to spawn an ephemeral container on the
# fresh image, apply schema, then exit. Only after that we start the
# long-running backend container.
echo "[$(ts)] applying schema migrations (pre-start)" >> "$LOG"
docker compose run --rm --no-deps backend python /app/check_schema.py --apply >> "$LOG" 2>&1 || \
    echo "[$(ts)] WARN: check_schema.py --apply failed (see above)" >> "$LOG"

# Now safe to start backend
docker compose up -d backend >> "$LOG" 2>&1
sleep 8

# Rebuild & restart frontend
docker compose build frontend >> "$LOG" 2>&1
docker compose up -d frontend >> "$LOG" 2>&1

# Conditional nginx rebuild — только если nginx.conf или docker-compose.yml изменились.
# Это закрывает старый TODO от 2026-04-05: websocket-fix в nginx.conf не применялся
# на проде, т.к. autodeploy не трогал nginx-контейнер. Теперь ws/cache/proxy-tweaks
# доходят, но мы не дёргаем nginx без нужды.
if [ "$NGINX_HASH_BEFORE" != "$NGINX_HASH_AFTER" ]; then
    echo "[$(ts)] nginx config changed; rebuilding & restarting nginx" >> "$LOG"
    docker compose build nginx >> "$LOG" 2>&1
    docker compose up -d --force-recreate nginx >> "$LOG" 2>&1
fi

docker image prune -f >> "$LOG" 2>&1

# Always restart the webhook service at the end of a deploy. Two reasons:
#  (1) picks up any webhook.py changes (see WEBHOOK_HASH_BEFORE/AFTER above);
#  (2) clears any transient hang in the long-lived Python process — the root
#      cause of the 2026-04-19 outage was a stuck accept loop that `systemctl
#      status` reported as "active running" but that silently dropped every
#      connection. Cheaper to always restart than to run a separate healthcheck.
# Scheduled in the background with a 2s delay so the currently-running handler
# can finish responding to GitHub before we replace ourselves.
if [ "$WEBHOOK_HASH_BEFORE" != "$WEBHOOK_HASH_AFTER" ]; then
    echo "[$(ts)] webhook.py changed; restarting vsks-deploy.service" >> "$LOG"
else
    echo "[$(ts)] restarting vsks-deploy.service (routine hang prevention)" >> "$LOG"
fi
( sleep 2 && systemctl restart vsks-deploy.service ) &

echo "[$(ts)] deploy complete" >> "$LOG"
