#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/3] Checking Node/NPM versions"
node -v
npm -v

echo "[2/3] Installing frontend dependencies via default npm settings"
if npm install; then
  echo "Dependencies installed successfully with default npm settings."
  exit 0
fi

echo "Default npm install failed. Trying fallback without proxy environment variables..."

echo "[3/3] Retrying install with proxy env vars removed"
if env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u npm_config_http_proxy -u npm_config_https_proxy npm install; then
  echo "Dependencies installed successfully without proxy env vars."
  exit 0
fi

cat <<'MSG'
ERROR: Could not install frontend dependencies.
Possible reasons:
- Corporate/security policy blocks access to npm registry.
- Proxy settings in environment are invalid or unavailable.

What to do next:
1) Configure an internal allowed npm mirror:
   npm config set registry <your-internal-registry>
2) Or provide working proxy values for npm:
   export npm_config_http_proxy=http://<proxy-host>:<port>
   export npm_config_https_proxy=http://<proxy-host>:<port>
3) Retry:
   ./scripts/install_deps.sh
MSG

exit 1
