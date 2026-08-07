#!/usr/bin/env python3
"""Deploy files via SFTP and run SSH commands."""
import sys
import os
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)

def sftp_upload(files):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    sftp = client.open_sftp()
    for local, remote in files:
        print(f"Uploading {local} -> {remote}")
        sftp.put(local, remote)
        print(f"  OK")
    sftp.close()
    client.close()

def run(cmd, timeout=300):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    client.close()
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    return rc

if __name__ == "__main__":
    # Step 1: SFTP upload
    files = [
        (r"c:\Users\1\VSKS_CRM\backend\app\models\contractor.py",
         "/opt/vsks-crm/backend/app/models/contractor.py"),
        (r"c:\Users\1\VSKS_CRM\backend\app\schemas\schemas.py",
         "/opt/vsks-crm/backend/app/schemas/schemas.py"),
        (r"c:\Users\1\VSKS_CRM\backend\app\models\subsidy_contractor_override.py",
         "/opt/vsks-crm/backend/app/models/subsidy_contractor_override.py"),
        (r"c:\Users\1\VSKS_CRM\frontend\src\views\SubsidiesView.vue",
         "/opt/vsks-crm/frontend/src/views/SubsidiesView.vue"),
        (r"c:\Users\1\VSKS_CRM\frontend\src\views\ContractorsView.vue",
         "/opt/vsks-crm/frontend/src/views/ContractorsView.vue"),
    ]
    print("=== SFTP Upload ===")
    sftp_upload(files)

    # Step 2: copy check_schema.py
    rc = run("docker cp /opt/vsks-crm/backend/check_schema.py vsks-crm-backend-1:/app/check_schema.py")
    print(f"Exit code: {rc}")

    # Step 3: apply schema
    rc = run("docker exec vsks-crm-backend-1 python /app/check_schema.py --apply")
    print(f"Exit code: {rc}")

    # Step 4: restart backend
    rc = run("docker restart vsks-crm-backend-1")
    print(f"Exit code: {rc}")

    # Step 5: wait 5 seconds
    print("\nWaiting 5 seconds...")
    time.sleep(5)

    # Step 6: check logs
    rc = run("docker logs vsks-crm-backend-1 --tail 5")
    print(f"Exit code: {rc}")

    # Step 7: build and restart frontend
    rc = run("cd /opt/vsks-crm && docker compose build frontend && docker compose up -d --force-recreate frontend", timeout=600)
    print(f"Exit code: {rc}")

    # Step 8: confirm frontend running
    rc = run("docker ps --filter name=vsks-crm-frontend-1 --format '{{.Names}} {{.Status}}'")
    print(f"Exit code: {rc}")

    print("\n=== Deploy complete ===")
