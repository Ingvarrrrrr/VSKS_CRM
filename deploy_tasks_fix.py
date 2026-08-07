#!/usr/bin/env python3
"""Deploy: fix tasks visibility + ProductsView performance."""
import sys, os, time, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
PORT = 22
USER = "root"
PASS = os.environ.get("REMOTE_PASS")
if not PASS:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)
REMOTE_BASE = "/opt/vsks-crm"
LOCAL_BASE = r"C:\Users\1\VSKS_CRM"

FILES_TO_UPLOAD = [
    (r"backend\app\routers\tasks.py",       "backend/app/routers/tasks.py"),
    (r"frontend\src\views\MyTasksView.vue", "frontend/src/views/MyTasksView.vue"),
    (r"frontend\src\views\ProductsView.vue","frontend/src/views/ProductsView.vue"),
]

DEPLOY_SCRIPT = r"""
set -e
echo "=== restart backend ==="
docker restart vsks-crm-backend-1
sleep 6
docker logs vsks-crm-backend-1 --tail 4 2>&1

echo "=== build+start frontend ==="
cd /opt/vsks-crm && docker compose build frontend 2>&1 | tail -8
docker compose up -d frontend 2>&1 | tail -5

echo "=== DONE ==="
"""

def run():
    sock = socket.create_connection((HOST, PORT), timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=USER, password=PASS)

    sftp = paramiko.SFTPClient.from_transport(transport)
    for local_rel, remote_rel in FILES_TO_UPLOAD:
        local_path = os.path.join(LOCAL_BASE, local_rel)
        remote_path = f"{REMOTE_BASE}/{remote_rel}"
        print(f"  upload: {local_rel}")
        sftp.put(local_path, remote_path)
    sftp.close()
    print("Files uploaded.")

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
    print("🚀 Deploy: tasks fix + products perf")
    rc = run()
    print("\n✅ Done!" if rc == 0 else f"\n❌ rc={rc}")
    sys.exit(rc)
