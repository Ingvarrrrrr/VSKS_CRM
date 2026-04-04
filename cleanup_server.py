#!/usr/bin/env python3
"""Clean up server: remove FruitShop, junk projects, docker prune, caches, logs."""
import paramiko, os, sys, time, socket
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = "85.239.53.155"
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS", "gGUW6H@i#s5NrZ")

def connect():
    for attempt in range(10):
        try:
            sock = socket.create_connection((HOST, 22), timeout=60)
            t = paramiko.Transport(sock)
            t.banner_timeout = 60
            t.start_client(timeout=60)
            t.auth_password(USER, PASSWORD)
            return t
        except Exception as e:
            print(f"  Connect attempt {attempt+1}: {e}")
            time.sleep(5)
    raise Exception("Failed to connect after 10 attempts")

def run(t, cmd, timeout=120):
    ch = t.open_session(timeout=30)
    ch.settimeout(timeout)
    ch.exec_command(cmd)
    out = b""
    while True:
        try:
            d = ch.recv(65536)
            if not d:
                break
            out += d
        except socket.timeout:
            break
    ch.close()
    return out.decode(errors="replace")

# Connect
print("Connecting...")
t = connect()
print("Connected!\n")

# Step 0: Check before
print("=== BEFORE ===")
print(run(t, "df -h / | tail -1"))

# Step 1: Stop and remove FruitShop
print("\n=== STEP 1: Remove FruitShop ===")
print(run(t, "pm2 stop all 2>&1; pm2 delete all 2>&1; echo PM2_DONE"))
print(run(t, "rm -rf /opt/fruits /root/Fruits && echo FRUITS_REMOVED"))

# Step 2: Remove junk projects
print("\n=== STEP 2: Remove junk projects ===")
print(run(t, "rm -rf /opt/Undercooked- /opt/GTA2 /opt/opengta2 /opt/freedroid.tar.gz && echo JUNK_REMOVED"))

# Step 3: Docker prune
print("\n=== STEP 3: Docker prune ===")
print(run(t, "docker system prune -a --volumes -f 2>&1", timeout=180))

# Step 4: Clear caches
print("\n=== STEP 4: Clear caches ===")
print(run(t, "rm -rf /root/.npm/_cacache /root/.local/share/pip && echo CACHES_CLEARED"))

# Step 5: Rotate logs
print("\n=== STEP 5: Rotate logs ===")
print(run(t, "truncate -s 0 /var/log/*.log 2>/dev/null; journalctl --vacuum-size=100M 2>&1; pm2 flush 2>&1; echo LOGS_DONE"))

# Verify
print("\n=== AFTER ===")
print(run(t, "df -h / | tail -1"))
print(run(t, "uptime"))
print(run(t, "docker ps --format 'table {{.Names}}\t{{.Status}}'"))
print(run(t, "pm2 list 2>&1"))

t.close()
print("\nDone!")
