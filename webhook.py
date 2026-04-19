#!/usr/bin/env python3
"""
VSKS CRM autodeploy webhook.

- ThreadingHTTPServer so one slow request never blocks the accept queue (the
  previous HTTPServer version would hang indefinitely after certain exceptions
  and leave the socket LISTEN-but-unresponsive).
- Per-connection socket timeout so a stuck client can't park a worker forever.
- /healthz endpoint for liveness probes (GET, no auth).
- Structured logging to stdout (captured by systemd-journald).
- autodeploy.sh is spawned detached; we never wait for it.
"""
import hashlib
import hmac
import json
import logging
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn

SECRET = "vsks-autodeploy-secret-2026"
DEPLOY_SCRIPT = "/opt/vsks-crm/autodeploy.sh"
LOG_PATH = "/var/log/vsks-deploy.log"
LISTEN = ("0.0.0.0", 9000)
REQUEST_TIMEOUT_SEC = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("vsks-webhook")


class Handler(BaseHTTPRequestHandler):
    timeout = REQUEST_TIMEOUT_SEC

    def log_message(self, fmt, *args):  # redirect default access log to our logger
        log.info("%s - %s", self.address_string(), fmt % args)

    def _reply(self, code: int, body: bytes = b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/healthz", "/deploy/healthz"):
            self._reply(200, b"ok\n")
            return
        self._reply(404)

    def do_POST(self):
        if self.path != "/deploy/vsks-crm":
            self._reply(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            sig = self.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                log.warning("rejected: HMAC mismatch from %s", self.address_string())
                self._reply(403)
                return
            try:
                data = json.loads(body or b"{}")
            except json.JSONDecodeError:
                log.warning("rejected: bad JSON from %s", self.address_string())
                self._reply(400)
                return
            ref = data.get("ref")
            if ref == "refs/heads/claude":
                log.info("dispatching deploy for %s", ref)
                # Detached — never wait. Own stdout so systemd journal doesn't hold pipes open.
                subprocess.Popen(
                    ["/bin/bash", DEPLOY_SCRIPT],
                    stdout=open(LOG_PATH, "a"),
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
            else:
                log.info("ignored ref=%s", ref)
            self._reply(200, b"ok\n")
        except Exception as exc:  # never let a handler exception freeze the server
            log.exception("handler error: %s", exc)
            try:
                self._reply(500)
            except Exception:
                pass


def main():
    server = ThreadingHTTPServer(LISTEN, Handler)
    server.daemon_threads = True
    log.info("webhook listening on %s:%d", *LISTEN)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutdown requested")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
