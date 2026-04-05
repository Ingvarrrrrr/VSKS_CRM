#!/usr/bin/env python3
import subprocess, json, hmac, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

ROUTES = {
    "/deploy/vsks-crm": {
        "secret": "vsks-autodeploy-secret-2026",
        "ref": "refs/heads/claude",
        "script": "/opt/vsks-crm/autodeploy.sh",
        "log": "/var/log/vsks-deploy.log",
    },
    "/deploy/nemakh": {
        "secret": "nemakh-autodeploy-secret-2026",
        "ref": "refs/heads/main",
        "script": "/opt/nemakh/autodeploy.sh",
        "log": "/var/log/nemakh-deploy.log",
    },
}

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        route = ROUTES.get(self.path)
        if not route:
            self.send_response(404); self.end_headers(); return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sig = self.headers.get("X-Hub-Signature-256", "")
        exp = "sha256=" + hmac.new(route["secret"].encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, exp):
            self.send_response(403); self.end_headers(); return
        data = json.loads(body)
        if data.get("ref") == route["ref"]:
            subprocess.Popen(
                ["/bin/bash", route["script"]],
                stdout=open(route["log"], "a"),
                stderr=subprocess.STDOUT,
            )
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass

HTTPServer(("0.0.0.0", 9000), H).serve_forever()
