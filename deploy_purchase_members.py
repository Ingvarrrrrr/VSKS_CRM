#!/usr/bin/env python3
"""Deploy: purchase discussion members UX fix."""
import sys, os, time, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
PORT = 22
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)
REMOTE_BASE = "/opt/vsks-crm"
LOCAL_BASE = os.path.dirname(os.path.abspath(__file__))

FILES_TO_UPLOAD = [
    ("backend/app/routers/purchases.py", f"{REMOTE_BASE}/backend/app/routers/purchases.py"),
    ("frontend/src/views/CreateOrderView.vue", f"{REMOTE_BASE}/frontend/src/views/CreateOrderView.vue"),
]

BACKEND_CMDS = r"""
set -e
echo "=== restart backend ==="
docker restart vsks-crm-backend-1
sleep 6
docker logs vsks-crm-backend-1 --tail 5 2>&1
echo "=== backend done ==="
"""

FRONTEND_CMDS = r"""
set -e
echo "=== build frontend ==="
cd /opt/vsks-crm && docker compose build frontend 2>&1 | tail -15
docker compose up -d frontend 2>&1
echo "=== frontend done ==="
"""

def run_cmd(transport, cmd, timeout=300):
    channel = transport.open_session()
    channel.get_pty()
    channel.settimeout(timeout)
    channel.exec_command(cmd)
    while True:
        if channel.recv_ready():
            print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
        elif channel.recv_stderr_ready():
            print(channel.recv_stderr(4096).decode(errors="replace"), end="", flush=True)
        elif channel.exit_status_ready():
            # drain
            while channel.recv_ready():
                print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
            break
        else:
            time.sleep(0.1)
    return channel.recv_exit_status()

def run():
    sock = socket.create_connection((HOST, PORT), timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=USER, password=PASSWORD)

    # Upload files
    sftp = paramiko.SFTPClient.from_transport(transport)
    for local_rel, remote in FILES_TO_UPLOAD:
        local = os.path.join(LOCAL_BASE, local_rel)
        print(f"Upload: {local_rel} -> {remote}")
        sftp.put(local, remote)
    sftp.close()
    print("=== files uploaded ===")

    run_cmd(transport, BACKEND_CMDS, timeout=120)
    run_cmd(transport, FRONTEND_CMDS, timeout=600)

    transport.close()
    print("\n=== DEPLOY COMPLETE ===")

if __name__ == "__main__":
    run()
