#!/usr/bin/env python3
"""Deploy: task change tracking + notification fixes."""
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
    # (local_path, remote_path)
    ("backend/app/models/task_change.py",   f"{REMOTE_BASE}/backend/app/models/task_change.py"),
    ("backend/app/models/__init__.py",       f"{REMOTE_BASE}/backend/app/models/__init__.py"),
    ("backend/app/schemas/schemas.py",       f"{REMOTE_BASE}/backend/app/schemas/schemas.py"),
    ("backend/app/routers/tasks.py",         f"{REMOTE_BASE}/backend/app/routers/tasks.py"),
    ("backend/app/notifications.py",         f"{REMOTE_BASE}/backend/app/notifications.py"),
    ("backend/check_schema.py",              f"{REMOTE_BASE}/backend/check_schema.py"),
]

FRONTEND_FILE = (
    "frontend/src/views/MyTasksView.vue",
    f"{REMOTE_BASE}/frontend/src/views/MyTasksView.vue",
)

BACKEND_CMDS = r"""
set -e
echo "=== create new tables ==="
docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c "
CREATE TABLE IF NOT EXISTS task_changes (
  id SERIAL PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  field_name VARCHAR(50) NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  changed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  changed_by_name VARCHAR(200)
);
CREATE INDEX IF NOT EXISTS ix_task_changes_task_id ON task_changes(task_id);

CREATE TABLE IF NOT EXISTS task_field_seen (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  field_name VARCHAR(50) NOT NULL,
  dismissed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, task_id, field_name)
);
" 2>&1

echo "=== restart backend ==="
docker restart vsks-crm-backend-1
sleep 8
docker logs vsks-crm-backend-1 --tail 8 2>&1
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
            while channel.recv_ready():
                print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
            break
        else:
            time.sleep(0.1)
    rc = channel.recv_exit_status()
    channel.close()
    return rc


def main():
    print("🚀 Connecting...")
    sock = socket.create_connection((HOST, PORT), timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=USER, password=PASSWORD)

    # Upload backend files
    print("📤 Uploading backend files...")
    sftp = transport.open_sftp_client()
    for local_rel, remote_path in FILES_TO_UPLOAD:
        local_path = os.path.join(LOCAL_BASE, local_rel).replace("\\", "/")
        print(f"  {local_rel} → {remote_path}")
        sftp.put(local_path, remote_path)

    # Upload frontend file
    local_rel, remote_path = FRONTEND_FILE
    local_path = os.path.join(LOCAL_BASE, local_rel).replace("\\", "/")
    print(f"  {local_rel} → {remote_path}")
    sftp.put(local_path, remote_path)
    sftp.close()

    # Run backend commands
    print("\n🔧 Running backend deploy...")
    rc = run_cmd(transport, BACKEND_CMDS)
    if rc != 0:
        print(f"❌ Backend deploy failed (rc={rc})")
        transport.close(); sock.close()
        return rc

    # Build frontend
    print("\n🎨 Building frontend...")
    rc = run_cmd(transport, FRONTEND_CMDS, timeout=600)

    transport.close()
    sock.close()
    return rc


if __name__ == "__main__":
    rc = main()
    print("\n✅ Done!" if rc == 0 else f"\n❌ rc={rc}")
    sys.exit(rc)
