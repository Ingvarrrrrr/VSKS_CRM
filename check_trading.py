#!/usr/bin/env python3
"""Check trading bot status via authenticated API."""
import paramiko, os, sys, time, socket, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)

def connect():
    for attempt in range(5):
        try:
            sock = socket.create_connection((HOST, 22), timeout=60)
            t = paramiko.Transport(sock)
            t.banner_timeout = 60
            t.start_client(timeout=60)
            t.auth_password("root", PASSWORD)
            return t
        except Exception as e:
            print(f"Attempt {attempt+1}: {e}")
            time.sleep(5)
    raise Exception("Failed")

def run(t, cmd):
    ch = t.open_session(timeout=30)
    ch.settimeout(60)
    ch.exec_command(cmd)
    out = b""
    while True:
        try:
            d = ch.recv(65536)
            if not d: break
            out += d
        except socket.timeout:
            break
    ch.close()
    return out.decode(errors="replace")

t = connect()

# Login
login_resp = run(t, 'curl -s -X POST http://localhost:8002/api/login -d "username=admin&password=1213141516"')
print("Login response:", login_resp[:200])
try:
    token = json.loads(login_resp)["access_token"]
except:
    print("Cannot login!")
    t.close()
    sys.exit(1)

print(f"Token: {token[:20]}...")

# Status
status = run(t, f'curl -s http://localhost:8002/api/status -H "Authorization: Bearer {token}"')
print("\n=== STATUS ===")
print(status[:500])

# Positions
positions = run(t, f'curl -s http://localhost:8002/api/positions -H "Authorization: Bearer {token}"')
print("\n=== POSITIONS ===")
print(positions[:1000])

# Settings
settings = run(t, f'curl -s http://localhost:8002/api/settings -H "Authorization: Bearer {token}"')
print("\n=== SETTINGS ===")
print(settings[:500])

# Logs
logs = run(t, f'curl -s http://localhost:8002/api/logs -H "Authorization: Bearer {token}"')
print("\n=== RECENT LOGS (last 500 chars) ===")
print(logs[-500:] if len(logs) > 500 else logs)

# Check docker internal trader state
print("\n=== DOCKER TRADER STATE ===")
state = run(t, 'docker exec trading-bot python3 -c "import sys; sys.path.insert(0, chr(47)+chr(97)+chr(112)+chr(112)); from app.trader import trading_api; print(trading_api.is_running, trading_api.trader)"')
print(state)

t.close()
