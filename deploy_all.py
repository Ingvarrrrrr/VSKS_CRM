#!/usr/bin/env python3
"""Full deploy in one SSH session, no retries."""
import sys, os, time, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = "85.239.53.155"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS", "gGUW6H@i#s5NrZ")

DEPLOY_SCRIPT = r"""
set -e
echo "=== 1. check_schema ==="
docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py
docker exec vsks-crm-backend-1 python /app/check_schema.py --apply 2>&1

echo "=== 2. FK CASCADE ==="
docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c "ALTER TABLE commercial_requests DROP CONSTRAINT IF EXISTS commercial_requests_purchase_id_fkey; ALTER TABLE commercial_requests ADD CONSTRAINT commercial_requests_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE;" || true

echo "=== 3. pip install ==="
docker exec vsks-crm-backend-1 pip install "pdfplumber>=0.10.0" "python-docx>=1.1.0" 2>&1 | tail -3

echo "=== 4. restart backend ==="
docker restart vsks-crm-backend-1
sleep 8
docker logs vsks-crm-backend-1 --tail 5 2>&1

echo "=== 5. build+deploy frontend ==="
cd /opt/vsks-crm && docker compose build frontend 2>&1 | tail -10
docker compose up -d frontend 2>&1

echo "=== DONE ==="
"""

def run():
    sock = socket.create_connection((HOST, PORT), timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=USER, password=PASSWORD)
    channel = transport.open_session()
    channel.get_pty()
    channel.settimeout(600)
    channel.exec_command(DEPLOY_SCRIPT)
    while True:
        if channel.recv_ready():
            print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
        elif channel.recv_stderr_ready():
            print(channel.recv_stderr(4096).decode(errors="replace"), end="", flush=True)
        elif channel.exit_status_ready():
            while channel.recv_ready():
                print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
            break
        else:
            time.sleep(0.1)
    rc = channel.recv_exit_status()
    channel.close(); transport.close(); sock.close()
    return rc

if __name__ == "__main__":
    print("🚀 VSKS CRM Deploy")
    rc = run()
    print("\n✅ Done!" if rc == 0 else f"\n❌ rc={rc}")
    sys.exit(rc)
