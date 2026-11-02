"""Скользящая сессия для httpOnly-cookie `gala_session`.

Проблема (29.10.2026): токен живёт settings.ACCESS_TOKEN_EXPIRE_MINUTES
(30 дней) С МОМЕНТА ВХОДА, без продления — активный пользователь,
заходящий каждый день, всё равно вылетает ровно через 30 дней после
логина. Нужно: 30 дней с последней активности.

Правило №6 (один показатель — один источник истины): это единственное
место, решающее, когда и как переиздать cookie-токен. app/auth/jwt.py
(get_current_user) вызывает maybe_queue_renewal() СРАЗУ ПОСЛЕ успешной
проверки подписи/exp/token_version — здесь эта проверка НЕ повторяется,
функция полностью доверяет payload, который ей передали.

Почему middleware, а не Response в самом роутере
--------------------------------------------------
get_current_user — dependency, у него нет доступа к объекту Response,
который в итоге уйдёт клиенту (а для StreamingResponse/FileResponse его
вообще не существует в теле роутера). Поэтому dependency только
ОТКЛАДЫВАЕТ решение в request.state, а SessionRenewMiddleware — уже
снаружи, после call_next(), когда Response типа всегда есть — ставит
Set-Cookie тем же хелпером set_session_cookie (app/auth/session_cookie.py,
Правило №6 — параметры cookie не дублируются второй раз здесь).

Только cookie-путь
-------------------
Bearer-клиенты (API-клиенты, тесты, Swagger) не продлеваются — у них нет
cookie, которую можно "скользить"; они получают новый токен обычным
логином/рефрешем на их стороне.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.session_cookie import SESSION_COOKIE_NAME, set_session_cookie
from app.config import settings

# Продлеваем не на каждый запрос (лишний Set-Cookie на каждый API-вызов),
# а когда токену от выдачи больше суток — пока пользователь не молчит
# дольше 30 дней, это не играет роли.
RENEW_IF_OLDER_THAN = timedelta(days=1)


def _token_age(payload: dict) -> timedelta:
    """Возраст токена с момента выдачи. claim "iat" — основной источник;
    если его нет (токен выпущен до этой задачи, старый формат без iat) —
    восстанавливаем момент выдачи из exp минус срок жизни токена."""
    now = datetime.now(timezone.utc)
    iat = payload.get("iat")
    if iat is not None:
        issued = datetime.fromtimestamp(float(iat), tz=timezone.utc)
        return now - issued
    exp = payload.get("exp")
    if exp is not None:
        issued = datetime.fromtimestamp(float(exp), tz=timezone.utc) - timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        return now - issued
    # Ни iat, ни exp — посчитать нечем; считаем «старым», чтобы продлить
    # (безопаснее продлить лишний раз, чем молча выкинуть активного юзера).
    return RENEW_IF_OLDER_THAN


def maybe_queue_renewal(request: Request, payload: dict, used_cookie: bool) -> None:
    """Если токен пришёл через cookie и ему от выдачи больше суток — кладёт
    переизданный токен в request.state.gala_session_renewed, откуда его
    забирает SessionRenewMiddleware и ставит в Set-Cookie исходящего ответа.

    Подпись/exp/token_version уже проверены вызывающим (get_current_user) —
    здесь это НЕ повторяется (Правило №6 — одна проверка, не две).
    """
    if not used_cookie:
        return
    if _token_age(payload) < RENEW_IF_OLDER_THAN:
        return
    from app.auth.jwt import create_access_token  # lazy: jwt.py импортирует этот модуль, избегаем circular import

    # Новый токен — те же claims (sub/role/org_id/org_ids/tv и т.п.), кроме
    # exp/iat — их create_access_token проставит заново от текущего момента.
    data = {k: v for k, v in payload.items() if k not in ("exp", "iat")}
    new_token = create_access_token(data)
    request.state.gala_session_renewed = new_token


class SessionRenewMiddleware(BaseHTTPMiddleware):
    """Ставит Set-Cookie gala_session на исходящий ответ, если
    get_current_user решил продлить сессию (maybe_queue_renewal выше).
    Работает для ЛЮБОГО типа ответа, включая StreamingResponse/FileResponse —
    это и есть причина делать это middleware'ом, а не правкой в роутерах.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        new_token: Optional[str] = getattr(request.state, "gala_session_renewed", None)
        if not new_token:
            return response
        # Некоторые роутеры (login/switch-org/select-orgs/session-from-token
        # в app/routers/auth.py) САМИ ставят свежую cookie этим же ответом —
        # не затирать её менее актуальным продлением сверху. logout не
        # зависит от get_current_user, поэтому в него это состояние не
        # попадает вовсе — его Set-Cookie (снятие cookie) ничем не рискует.
        existing = response.headers.getlist("set-cookie") if hasattr(response.headers, "getlist") else []
        if any(SESSION_COOKIE_NAME in cookie_header for cookie_header in existing):
            return response
        set_session_cookie(response, new_token, request)
        return response
