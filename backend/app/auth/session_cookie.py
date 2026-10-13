"""HttpOnly-cookie сессия (gala_session) — единственное место, где JWT
кладётся в cookie и снимается оттуда.

Перенос JWT из localStorage (читался фронтом ~128 раз, крался бы любой
XSS) в HttpOnly-cookie, 2026-10-13. Правило №6: один источник истины на
имя cookie / правила set-cookie — set_session_cookie/clear_session_cookie,
никто больше не формирует Set-Cookie для сессии напрямую.

Secure-флаг
-----------
Стенд работает и на http://localhost:8079 (без TLS) — там Secure cookie
браузер молча не поставит вовсе. Secure включаем только когда запрос
пришёл по https: либо request.url.scheme == 'https' (прямое TLS-соединение
uvicorn — в докере такого нет), либо заголовок X-Forwarded-Proto == 'https'
(прод — внешний nginx терминирует TLS и форвардит на backend по http).
"""

from fastapi import Request
from fastapi.responses import Response

from app.config import settings

SESSION_COOKIE_NAME = "gala_session"


def _is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return forwarded_proto.split(",")[0].strip().lower() == "https"


def set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def get_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)
