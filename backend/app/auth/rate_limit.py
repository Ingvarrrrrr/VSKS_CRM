"""In-memory rate limiter for POST /api/auth/login.

Простой dict IP -> deque(timestamps), без Redis/внешних зависимостей —
масштаб задачи (один эндпоинт, один процесс) не оправдывает тяжёлую
зависимость.

IP и X-Forwarded-For
---------------------
backend/Dockerfile запускает uvicorn с `--proxy-headers
--forwarded-allow-ips='*'`. Это значит uvicorn САМ разбирает
X-Forwarded-For от прокси (в docker-compose nginx — единственный, кто
достаёт backend по сети) и подменяет `request.client.host` на реальный IP
клиента ДО того, как ASGI-приложение его увидит. Поэтому здесь читается
только `request.client.host` — самостоятельный разбор X-Forwarded-For был
бы двойной (и небезопасной, т.к. `forwarded-allow-ips='*'` доверяет ЛЮБОМУ
входящему соединению) подменой.

Реплики и масштаб лимита
------------------------
backend_a и backend_b (docker-compose.yml) — раздельные процессы с
раздельной памятью, общего счётчика между ними нет. При round-robin через
nginx upstream лимит фактически удваивается (до ~20 попыток/60с на IP).
Это принято как приемлемый компромисс — see PR/task description.

Почему не HTTPException
-----------------------
backend/app/errors.py регистрирует общий `@app.exception_handler(HTTPException)`
(единый формат ошибок на всё приложение — code/message/details/correlation_id,
см. Rule №6 «один источник истины»), который строит ответ как
`JSONResponse(status_code=exc.status_code, content=payload)` — БЕЗ
`headers=exc.headers`. Значит `raise HTTPException(..., headers={...})` из
любого места приложения сейчас теряет кастомные заголовки молча (никто
раньше на это не напарывался, т.к. до этой правки ни один HTTPException в
проекте headers не выставлял). Чтобы Retry-After гарантированно дошёл до
клиента и не пришлось трогать общий error-handler (не в scope этой
задачи), check_login_rate_limit() возвращает готовый JSONResponse вместо
исключения — роутер возвращает его напрямую, в обход exception-handler'а.
"""

from collections import defaultdict, deque
from time import monotonic
from typing import Deque, Dict, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 60.0

# module-level state: живёт, пока жив процесс backend_a/backend_b
_attempts: Dict[str, Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(dq: Deque[float], now: float) -> None:
    while dq and now - dq[0] > WINDOW_SECONDS:
        dq.popleft()


def resolve_client_ip(request: Request) -> str:
    return _client_ip(request)


def rate_limit_response(ip: str) -> Optional[JSONResponse]:
    """Return a ready 429 JSONResponse (with Retry-After) if `ip` is over
    the limit, else None. Does not mutate state — safe to call repeatedly."""
    now = monotonic()
    dq = _attempts[ip]
    _prune(dq, now)
    if len(dq) >= MAX_ATTEMPTS:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Слишком много попыток входа. Повторите через минуту."},
            headers={"Retry-After": str(int(WINDOW_SECONDS))},
        )
    return None


def record_failed_login(ip: str) -> None:
    _attempts[ip].append(monotonic())


def reset_login_rate_limit(ip: str) -> None:
    _attempts.pop(ip, None)
