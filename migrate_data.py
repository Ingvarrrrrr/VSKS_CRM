#!/usr/bin/env python3
"""Migrate data from local dump to production DB via SSH."""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)

def run(cmd, timeout=120):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    client.close()
    return out, err, rc

def upload_file(local_path, remote_path):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    sftp = client.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    client.close()

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"

    if action == "cmd":
        cmd = " ".join(sys.argv[2:])
        out, err, rc = run(cmd, timeout=300)
        if out: print(out, end="")
        if err: print(err, end="", file=sys.stderr)
        sys.exit(rc)

    elif action == "list-tables":
        out, err, rc = run(
            'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c '
            '"SELECT tablename FROM pg_tables WHERE schemaname=\'public\' ORDER BY tablename;"'
        )
        print(out)
        if err: print(err, file=sys.stderr)

    elif action == "truncate":
        # Get all tables
        out, err, rc = run(
            'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -t -c '
            '"SELECT tablename FROM pg_tables WHERE schemaname=\'public\';"'
        )
        tables = [t.strip() for t in out.strip().split('\n') if t.strip()]
        print(f"Found {len(tables)} tables: {tables}")

        # Truncate all tables with CASCADE
        table_list = ', '.join(tables)
        out, err, rc = run(
            f'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c '
            f'"TRUNCATE {table_list} CASCADE;"'
        )
        print(f"TRUNCATE result: {out.strip()}")
        if err: print(err, file=sys.stderr)

    elif action == "upload":
        local_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/vsks_data_clean.sql"
        remote_path = "/tmp/vsks_data_clean.sql"
        print(f"Uploading {local_path} -> {remote_path}...")
        upload_file(local_path, remote_path)
        print("Upload done.")

    elif action == "import":
        print("Importing data from /tmp/vsks_data_clean.sql...")
        out, err, rc = run(
            'docker cp /tmp/vsks_data_clean.sql vsks-crm-db-1:/tmp/vsks_data_clean.sql && '
            'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/vsks_data_clean.sql 2>&1 | tail -50',
            timeout=300
        )
        print(out)
        if err: print(err, file=sys.stderr)

    elif action == "counts":
        tables = ["users", "subsidies", "products", "contractors", "purchases",
                   "purchase_items", "feo_categories", "contracts", "payments",
                   "platform_publications", "subsidy_approvers", "organizations",
                   "responsible_persons", "purchase_files"]
        for t in tables:
            out, err, rc = run(
                f'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -t -c "SELECT count(*) FROM {t};"'
            )
            count = out.strip()
            print(f"  {t}: {count}")

    elif action == "fix-sequences":
        # Get all tables with serial/identity columns
        out, err, rc = run(
            'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -t -c "'
            "SELECT table_name, column_name, pg_get_serial_sequence(table_name, column_name) "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND column_default LIKE 'nextval%' "
            "ORDER BY table_name;"
            '"'
        )
        print("Fixing sequences...")
        for line in out.strip().split('\n'):
            if '|' not in line:
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 3 or not parts[2]:
                continue
            table, col, seq = parts[0], parts[1], parts[2]
            fix_cmd = (
                f"SELECT setval('{seq}', COALESCE((SELECT MAX({col}) FROM {table}), 1));"
            )
            out2, err2, rc2 = run(
                f'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -t -c "{fix_cmd}"'
            )
            print(f"  {seq} -> {out2.strip()}")
        print("Sequences fixed.")

    elif action == "status":
        out, err, rc = run("docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vsks")
        print(out)

    else:
        print(f"Unknown action: {action}")
        print("Usage: migrate_data.py [list-tables|truncate|upload|import|counts|fix-sequences|status|cmd ...]")
