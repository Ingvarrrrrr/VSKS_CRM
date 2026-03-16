#!/usr/bin/env python3
"""Test signature API endpoints."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import paramiko, json

HOST = "85.239.53.155"
USER = "root"
PASSWORD = "gGUW6H@i#s5NrZ"

def ssh(cmd, timeout=15):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    client.close()
    return out, err

# Get token
out, _ = ssh("""curl -s -X POST http://localhost/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'""")
token = json.loads(out)['access_token']
print("Token OK:", token[:30], "...")

# Test GET signature
out, _ = ssh(f"""curl -s http://localhost/api/users/me/signature \
  -H 'Authorization: Bearer {token}'""")
print("GET /me/signature:", out)

# Test PUT signature (tiny 1x1 px PNG base64)
tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
out, _ = ssh(f"""curl -s -X PUT http://localhost/api/users/me/signature \
  -H 'Authorization: Bearer {token}' \
  -H 'Content-Type: application/json' \
  -d '{{"signature": "{tiny_png}"}}'""")
print("PUT /me/signature:", out)

# Test GET after save
out, _ = ssh(f"""curl -s http://localhost/api/users/me/signature \
  -H 'Authorization: Bearer {token}'""")
data = json.loads(out)
print("GET after save: signature present =", bool(data.get('signature')))

# Test DELETE
out, _ = ssh(f"""curl -s -X DELETE http://localhost/api/users/me/signature \
  -H 'Authorization: Bearer {token}'""")
print("DELETE /me/signature:", out)
