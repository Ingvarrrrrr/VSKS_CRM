#!/bin/bash
cd /opt/vsks-crm
git checkout -f claude && git clean -fd && git pull origin claude
docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py
docker exec vsks-crm-backend-1 python /app/check_schema.py --apply 2>&1 || true
docker restart vsks-crm-backend-1 && sleep 8
docker compose build frontend 2>&1 | tail -5
docker compose up -d frontend
echo "Deploy complete: $(date)" >> /var/log/vsks-deploy.log

# --- One-time NEMAKH bootstrap ---
# Clones nemakh-deploy and starts its own independent webhook on port 9001.
# After this runs once, NEMAKH manages itself via its own autodeploy.sh.
if [ ! -d /opt/nemakh ]; then
    echo "=== Bootstrapping NEMAKH: $(date) ===" >> /var/log/vsks-deploy.log
    GH_TOKEN=$(git -C /opt/vsks-crm remote get-url origin | sed -n 's|https://\([^@]*\)@.*|\1|p')
    if [ -n "$GH_TOKEN" ]; then
        mkdir -p /opt/nemakh
        cd /opt/nemakh
        git clone "https://${GH_TOKEN}@github.com/Ingvarrrrrr/nemakh-deploy.git" .
        git clone "https://${GH_TOKEN}@github.com/Ingvarrrrrr/nemakh-web.git"
        # Build web client
        if [ -d nemakh-web ]; then
            cd nemakh-web && npm install && npm run build:prod && cd ..
        fi
        # First run with DB init
        RESET_DB=true docker compose up -d
        sleep 20
        # Init MinIO bucket
        docker exec nemakh-minio mc alias set local http://localhost:9000 nemakh nemakh_secret || true
        docker exec nemakh-minio mc mb local/nemakh-media --ignore-existing || true
        docker exec nemakh-minio mc anonymous set download local/nemakh-media || true
        # Restart without RESET_DB
        docker compose down && docker compose up -d
        # Start NEMAKH's own webhook listener (port 9001, independent of CRM)
        nohup python3 /opt/nemakh/webhook.py >> /var/log/nemakh-webhook.log 2>&1 &
        echo "=== NEMAKH bootstrap complete: $(date) ===" >> /var/log/vsks-deploy.log
        cd /opt/vsks-crm
    else
        echo "=== NEMAKH bootstrap FAILED: no GH_TOKEN ===" >> /var/log/vsks-deploy.log
    fi
fi
