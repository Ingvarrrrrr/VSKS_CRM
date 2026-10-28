"""JWT-авторизация и низкоуровневые HTTP-вызовы Росэлторг.Бизнес API.

Выделено из publications_roseltorg_client.py (ПРАВИЛО №5 — модульность: тот
файл рос сразу тремя ответственностями — авторизация, сборка позиций,
оркестрация черновика; теперь это три отдельных модуля в app/services/roseltorg/).

Авторизация и базовый URL — живьём проверены владельцем (см. задание), не
менять: тело {"grant_type":"integration","token":"<токен БЕЗ Bearer>",
"platform":"b2b","client":"b2b"} → JWT; к API — Authorization: Bearer <jwt>.
"""
import asyncio
import json
import os
import urllib.request
import urllib.error
import uuid

from app.services.publications_status import _make_ssl_ctx

# Запасной токен из окружения — используется, если у публикующего
# пользователя нет личной учётной записи площадки (user_platform_credentials,
# platform='roseltorg'). Личный токен приоритетнее (см. client.py).
ROSELTORG_TOKEN = os.getenv("ROSELTORG_TOKEN", "")

ROSELTORG_AUTH_URL = "https://lk.roseltorg.ru/api/app/api/auth-integration/v1/auth"

ROSELTORG_BASE_URL = "https://business.roseltorg.ru/integration/v1"

# Шаблоны процедур на площадке (GET /templates, сверено владельцем живьём
# 28.10.2026): только эти два используются «Положением о закупке» организации —
# 10 (продажа) и 11 (мультивалютная) и 12 (продажа недвижимости) НЕ подходят
# для закупки товаров/услуг и не предлагаются пользователю.
ROSELTORG_TEMPLATE_IDS = {
    "request_quotations": 8,   # Процедура по закупке с выбором победителя
    "request_proposals":  9,   # Процедура по закупке без выбора победителя (анализ рынка)
}


class RoseltorgAuthError(Exception):
    pass


def rb_ok(result: dict | None, status: int) -> bool:
    """Площадка возвращает HTTP 200 c "success": false при бизнес-ошибке
    (проверено живьём владельцем на черновике 303879) — HTTP-код одного
    недостаточно, success проверяем явно (отсутствие ключа — считаем успехом,
    как было у ответов без этого поля, напр. documents)."""
    if status not in (200, 201):
        return False
    if result is None:
        return True
    return result.get("success") is not False


def rb_error_text(result: dict | None) -> str:
    """Текст ошибки площадки — resp["errors"] (dict или list) по-русски как
    есть, иначе _error/сырой ответ."""
    if not result:
        return "пустой ответ площадки"
    errors = result.get("errors")
    if errors:
        if isinstance(errors, dict):
            return "; ".join(f"{k}: {v}" for k, v in errors.items())
        if isinstance(errors, list):
            return "; ".join(str(e) for e in errors)
        return str(errors)
    if result.get("_error"):
        return str(result["_error"])[:300]
    return str(result)[:300]


async def get_roseltorg_jwt(token: str) -> str:
    """Обменивает интеграционный токен на JWT (двухшаговая авторизация v2.0)."""
    if not token:
        raise RoseltorgAuthError("Токен Росэлторг не задан")
    body = json.dumps({
        "grant_type": "integration",
        "token": token,
        "platform": "b2b",
        "client": "b2b",
    }).encode("utf-8")
    req = urllib.request.Request(
        ROSELTORG_AUTH_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "VSKS-CRM/1.0"},
    )
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
        )
        data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        raise RoseltorgAuthError(f"HTTP {e.code}: {text[:300]}") from e
    token_val = data.get("access_token")
    if not token_val:
        raise RoseltorgAuthError(f"В ответе авторизации нет access_token: {str(data)[:200]}")
    return token_val


async def rb_call(jwt: str, url: str, body: dict | None = None, method: str = "POST"):
    """JSON-вызов к Росэлторг.Бизнес API с JWT. Возвращает (parsed_json, http_status)."""
    data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "User-Agent": "VSKS-CRM/1.0",
        },
    )
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
        )
        raw = resp.read().decode("utf-8")
        return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
        parsed["_error"] = text
        parsed["_code"] = e.code
        return parsed, e.code


async def rb_call_multipart(jwt: str, url: str, file_name: str, file_bytes: bytes, field_name: str = "file"):
    """multipart/form-data вызов (загрузка документа) — у JSON rb_call своей
    поддержки multipart нет (urllib не умеет сам), поэтому собираем тело
    вручную. Используется только для POST /notices/{id}/documents.
    """
    boundary = uuid.uuid4().hex
    body = bytearray()

    def _add_field_header(name: str, filename: str | None = None, content_type: str | None = None):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        if filename:
            body.extend(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            body.extend(f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n".encode("utf-8"))
        else:
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))

    _add_field_header(field_name, filename=file_name, content_type="application/octet-stream")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url, data=bytes(body), method="POST",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "VSKS-CRM/1.0",
        },
    )
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=60, context=_make_ssl_ctx())
        )
        raw = resp.read().decode("utf-8")
        return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        return {"_error": text, "_code": e.code}, e.code
