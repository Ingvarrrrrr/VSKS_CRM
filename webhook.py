#!/usr/bin/env python3
import subprocess, json, hmac, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

SECRET = "vsks-autodeploy-secret-2026"

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy/vsks-crm":
            self.send_response(404); self.end_headers(); return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sig = self.headers.get("X-Hub-Signature-256", "")
        exp = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, exp):
            self.send_response(403); self.end_headers(); return
        data = json.loads(body)
        if data.get("ref") == "refs/heads/claude":
            subprocess.Popen(
                ["/bin/bash", "/opt/vsks-crm/autodeploy.sh"],
                stdout=open("/var/log/vsks-deploy.log", "a"),
                stderr=subprocess.STDOUT
            )
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass  # suppress access logs

HTTPServer(("0.0.0.0", 9000), H).serve_forever()
