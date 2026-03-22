"""Deploy task-purchase linking feature to server."""
import sys, os, time, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = "85.239.53.155"
PORT = 22
USER = "root"
PASS = "gGUW6H@i#s5NrZ"
REMOTE_BASE = "/opt/vsks-crm"
LOCAL_BASE = r"C:\Users\1\VSKS_CRM"

FILES_TO_UPLOAD = [
    (r"backend\app\models\task.py", "backend/app/models/task.py"),
    (r"backend\app\schemas\schemas.py", "backend/app/schemas/schemas.py"),
    (r"backend\app\routers\tasks.py", "backend/app/routers/tasks.py"),
    (r"backend\app\routers\purchases.py", "backend/app/routers/purchases.py"),
    (r"backend\app\notifications.py", "backend/app/notifications.py"),
    (r"frontend\src\views\CreateOrderView.vue", "frontend/src/views/CreateOrderView.vue"),
    (r"frontend\src\views\MyTasksView.vue", "frontend/src/views/MyTasksView.vue"),
    (r"backend\check_schema.py", "backend/check_schema.py"),
]

DEPLOY_SCRIPT = r"""
set -e
echo "=== 1. Add purchase_id column to tasks table ==="
docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c "
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS purchase_id INTEGER REFERENCES purchases(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_purchase_id ON tasks(purchase_id);
" 2>&1

echo "=== 2. copy check_schema into container ==="
docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py
docker exec vsks-crm-backend-1 python /app/check_schema.py --apply 2>&1

echo "=== 3. restart backend ==="
docker restart vsks-crm-backend-1
sleep 8
docker logs vsks-crm-backend-1 --tail 8 2>&1

echo "=== 4. build frontend ==="
cd /opt/vsks-crm && docker compose build frontend 2>&1 | tail -15

echo "=== 5. up frontend ==="
docker compose up -d frontend 2>&1

echo "=== 6. final backend check ==="
docker logs vsks-crm-backend-1 --tail 5 2>&1

echo "=== DONE ==="
"""

def upload_files(sftp):
    for local_rel, remote_rel in FILES_TO_UPLOAD:
        local_path = os.path.join(LOCAL_BASE, local_rel)
        remote_path = f"{REMOTE_BASE}/{remote_rel}"
        print(f"  Uploading: {local_rel}")
        sftp.put(local_path, remote_path)
    print("All files uploaded.")

def run_deploy(transport):
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
    return channel.recv_exit_status()

def main():
    sock = socket.create_connection((HOST, PORT), timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=USER, password=PASS)

    print("=== Step 1: Upload files via SFTP ===")
    sftp = paramiko.SFTPClient.from_transport(transport)
    upload_files(sftp)
    sftp.close()

    print("\n=== Step 2: Run deploy script on server ===")
    rc = run_deploy(transport)

    transport.close()
    sock.close()

    if rc == 0:
        print("\nDeploy successful!")
    else:
        print(f"\nDeploy finished with rc={rc}")
    return rc

if __name__ == "__main__":
    sys.exit(main())
