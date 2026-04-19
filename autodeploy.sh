#!/bin/bash
set -u  # fail on unset vars; keep going on non-zero so one step can't dead-lock the rest
LOG=/var/log/vsks-deploy.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "===== $(ts) deploy start =====" >> "$LOG"

cd /opt/vsks-crm || { echo "[$(ts)] cd /opt/vsks-crm FAILED" >> "$LOG"; exit 1; }

# Track webhook.py hash before pull so we know whether to restart the webhook service
WEBHOOK_HASH_BEFORE=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)

git checkout -f claude >> "$LOG" 2>&1
git clean -fd >> "$LOG" 2>&1
git pull origin claude >> "$LOG" 2>&1

WEBHOOK_HASH_AFTER=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)

# Rebuild & restart backend (picks up code + model changes)
docker compose build backend >> "$LOG" 2>&1
docker compose up -d backend >> "$LOG" 2>&1
sleep 8
# Apply any new columns via check_schema.py
docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py >> "$LOG" 2>&1
docker exec vsks-crm-backend-1 python /app/check_schema.py --apply >> "$LOG" 2>&1 || true

# Rebuild & restart frontend
docker compose build frontend >> "$LOG" 2>&1
docker compose up -d frontend >> "$LOG" 2>&1

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
