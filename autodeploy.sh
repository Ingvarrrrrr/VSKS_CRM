#!/bin/bash
cd /opt/vsks-crm
git checkout -f claude && git clean -fd && git pull origin claude
docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py
docker exec vsks-crm-backend-1 python /app/check_schema.py --apply 2>&1 || true
docker restart vsks-crm-backend-1 && sleep 8
docker compose build frontend 2>&1 | tail -5
docker compose up -d frontend
echo "Deploy complete: $(date)" >> /var/log/vsks-deploy.log
