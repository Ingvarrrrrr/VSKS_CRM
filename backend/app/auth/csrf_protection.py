"""CSRF-защита для cookie-аутентифицированных запросов.

Правило №6: одно место проверки источника запроса. До переноса JWT в
httpOnly-cookie (2026-10-13) CSRF не требовался — токен в заголовке
Authorization не шлётся браузером автоматически, значит чужой сайт не мог
его подставить. Cookie браузер шлёт САМ на любой запрос к нашему домену
(включая с чужой страницы) — значит небезопасные методы (создают/меняют/
удаляют данные) обязаны проверять, что запрос пришёл со своего же сайта.

Правило: небезопасный метод (POST/PUT/PATCH/DELETE), аутентифицированный
ИМЕННО cookie (без валидного Bearer в Authorization) — обязан иметь
Origin (или Referer, если Origin нет — некоторые браузеры/расширения его
не шлют) с хостом, совпадающим с хостом запроса. Запросы без cookie вовсе
(вебхуки типа /deploy, внешние колбэки, логин) и запросы с валидным Bearer
(API-клиенты, тесты) не затрагиваются — CSRF для них не имеет смысла.
"""

from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.auth.session_cookie import SESSION_COOKIE_NAME
# Правило №6: формальная проверка «похоже на JWT» (три непустых сегмента,
# не "null"/"undefined"/пусто) — ОДНА реализация в app/auth/jwt.py,
# используется и здесь, и в get_current_user. Не копировать её сюда заново.
from app.auth.jwt import _is_well_formed_jwt

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _has_valid_bearer(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    return _is_well_formed_jwt(auth[7:].strip())


def _strip_port(host: str) -> str:
    # nginx форвардит Host через `$host` (nginx/nginx.conf, deploy/edge/nginx.conf)
    # — эта переменная НЕ несёт порт даже когда клиент стучался на :8079/:443 с
    # явным портом в URL. Origin/Referer браузера, наоборот, порт несёт. Без
    # нормализации локальный стенд (http://localhost:8079) никогда не проходил
    # бы собственный же Origin — сравниваем только имя хоста, порт из обоих
    # сторон отбрасываем.
    return host.rsplit(":", 1)[0] if ":" in host and not host.startswith("[") else host


def _request_host(request: Request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        raw = forwarded_host.split(",")[0].strip().lower()
    else:
        raw = (request.headers.get("host") or request.url.netloc or "").lower()
    return _strip_port(raw)


def _origin_host(origin_or_referer: str) -> str:
    try:
        parsed = urlparse(origin_or_referer)
        return _strip_port((parsed.netloc or "").lower())
    except Exception:
        return ""


class CsrfProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS:
            has_session_cookie = bool(request.cookies.get(SESSION_COOKIE_NAME))
            if has_session_cookie and not _has_valid_bearer(request):
                source = request.headers.get("origin") or request.headers.get("referer") or ""
                source_host = _origin_host(source)
                if not source_host or source_host != _request_host(request):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Запрос отклонён: неизвестный источник запроса"},
                    )
        return await call_next(request)
