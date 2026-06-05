"""Apple Configuration Profile (.mobileconfig) for iOS one-tap PWA install.

GET /api/install.mobileconfig returns a signed/unsigned Web Clip profile that
iOS Safari can install through Settings → Profile Downloaded → Install.
End-user UX:
  1. Tap "Установить" on the in-app banner
  2. Safari prompts: "Open in Settings"
  3. Settings → Profile Downloaded → Install (passcode prompt)
  4. Web Clip icon appears on home screen — opens app in standalone mode

Profile is unsigned, so iOS shows a "Not signed" warning. To remove the
warning, sign with an Apple Developer cert (out of scope here).
"""
import base64
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid5, NAMESPACE_URL

from fastapi import APIRouter, Request
from fastapi.responses import Response


router = APIRouter(tags=["install"])

# Icon: try frontend public dir (bind-mount in dev) or local copy in backend.
_HERE = Path(__file__).resolve()
_CANDIDATES = [
    _HERE.parent.parent / "static" / "pwa-192x192.png",
    Path("/app/frontend_public/pwa-192x192.png"),
    Path("/app/static/pwa-192x192.png"),
]


def _icon_b64() -> str:
    for p in _CANDIDATES:
        if p.exists():
            try:
                return base64.b64encode(p.read_bytes()).decode("ascii")
            except Exception:
                continue
    return ""


def _stable_uuid(seed: str) -> str:
    """Deterministic UUID so re-installing the profile updates rather than
    duplicating the Web Clip icon."""
    return str(uuid5(NAMESPACE_URL, seed)).upper()


@router.get("/install.mobileconfig")
async def get_mobileconfig(request: Request, base: str | None = None):
    # Resolve target URL. За nginx бэкенд НЕ получает публичный хост (Host=localhost:80,
    # X-Forwarded-* не прокидываются) → раньше webclip вёл на http://localhost:80/ и
    # ярлык на iPhone был мёртвый. Фронт шлёт ?base=<origin> — это самый надёжный
    # источник публичного адреса (это собственный origin пользователя).
    candidate = (
        base
        or os.getenv("BASE_URL")
        or request.headers.get("x-forwarded-host")
        and f"{request.headers.get('x-forwarded-proto') or 'https'}://{request.headers.get('x-forwarded-host')}"
        or request.headers.get("host")
        and f"{request.url.scheme}://{request.headers.get('host')}"
        or "https://localhost"
    )
    parsed = urlparse(candidate)
    # Защита: принимаем только http/https с непустым хостом, иначе fallback.
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        parsed = urlparse(os.getenv("BASE_URL") or "https://localhost")
    domain = parsed.netloc
    target = f"{parsed.scheme}://{parsed.netloc}/"

    icon_b64 = _icon_b64()
    icon_block = f"<key>Icon</key>\n        <data>{icon_b64}</data>\n        <key>PrecomposedIcon</key>\n        <true/>\n        " if icon_b64 else ""

    webclip_uuid = _stable_uuid(f"{domain}/webclip")
    profile_uuid = _stable_uuid(f"{domain}/profile")

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
        <key>FullScreen</key>
        <true/>
        <key>IgnoreManifestScope</key>
        <true/>
        {icon_block}<key>IsRemovable</key>
        <true/>
        <key>Label</key>
        <string>GALA</string>
        <key>PayloadDescription</key>
        <string>Web Clip для GALA</string>
        <key>PayloadDisplayName</key>
        <string>GALA</string>
        <key>PayloadIdentifier</key>
        <string>ru.gala.crm.webclip</string>
        <key>PayloadOrganization</key>
        <string>GALA</string>
        <key>PayloadType</key>
        <string>com.apple.webClip.managed</string>
        <key>PayloadUUID</key>
        <string>{webclip_uuid}</string>
        <key>PayloadVersion</key>
        <integer>1</integer>
        <key>URL</key>
        <string>{target}</string>
        </dict>
    </array>
    <key>PayloadDescription</key>
    <string>Установит ярлык GALA на главный экран iPhone</string>
    <key>PayloadDisplayName</key>
    <string>GALA</string>
    <key>PayloadIdentifier</key>
    <string>ru.gala.crm.profile</string>
    <key>PayloadOrganization</key>
    <string>GALA</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{profile_uuid}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
"""
    return Response(
        content=plist,
        media_type="application/x-apple-aspen-config",
        headers={
            "Content-Disposition": 'attachment; filename="GALA.mobileconfig"',
            "Cache-Control": "no-store",
        },
    )
