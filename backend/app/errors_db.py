"""app/errors_db.py — общий обработчик БД-ошибок мусорного ввода, которые
раньше падали в app.errors.unhandled_exception_handler как голые 500
(ПРАВИЛО №6 — одна точка классификации вместо try/except в каждом роутере).

Повод: поведенческий фаззинг (tests/behavior/REPORT.md, находка С4) нашёл
~55 операций, отвечающих 500 вместо честного 4xx на мусорном id/параметре:
  - OverflowError('value out of int32 range')      — id > 2^31 в пути/параметре
    (asyncpg заворачивает его в собственный DataError ДО того, как долетит
    сюда — см. .schemathesis/.../crashes/DELETE_api_departments_*.json)
  - asyncpg.exceptions.ForeignKeyViolationError      — несуществующий id в теле
  - asyncpg.exceptions.NumericValueOutOfRangeError    — слишком большое число
  - asyncpg.exceptions.DataError / InvalidTextRepresentationError — "invalid
    input syntax"
  - asyncpg.exceptions.InvalidRowCountInLimitClauseError — "LIMIT/OFFSET must
    not be negative" (та же семья мусорного ввода — найдено ДОПОЛНИТЕЛЬНО при
    проверке фикса: limit=-467629 на /api/legal/requests и /api/system-incidents/,
    роутеры валидируют верхнюю границу limit (le=...), но не нижнюю — тот же
    класс бага, что ИСХОДНЫЙ chat.py:821, просто другие роутеры)
  - ГОЛЫЙ builtin OverflowError БЕЗ похода в БД — напр.
    vehicles_dashboard_fines.py:249 `timedelta(days=period_days)` падает
    раньше, чем запрос доходит до asyncpg, если period_days вылезает за
    ±999999999 дней (та же находка при проверке — симптом тот же класс
    "int32-переполнение", просто сработавший в Python, а не в БД).
  - asyncpg.exceptions.StringDataRightTruncationError — "value too long for
    type varchar(N)" (найдено ДОПОЛНИТЕЛЬНО при проверке: POST /api/suppliers/
    с длинным `kpp` — роутер не валидирует длину поля).

Основной канал — sqlalchemy.exc.DBAPIError (или его подкласс IntegrityError/
DataError/InternalError — все наследуют DBAPIError), ОДИН регистрируемый
здесь handler на DBAPIError перехватывает их все; ВТОРОЙ handler здесь же —
на голый builtin OverflowError (для случая, когда переполнение происходит
до похода в БД, см. выше) — переиспользует ТУ ЖЕ _classify, не вторую
формулу (ПРАВИЛО №6). Starlette выбирает handler по MRO исключения, так что
более специфичные DBAPIError/OverflowError матчатся раньше общего `Exception`
из app/errors.py, порядок регистрации не важен.

UniqueViolation — НЕ второй механизм: в роутерах/сервисах уже есть локальные
try/except IntegrityError (bank_statements.py, fuel_logs.py, products.py,
subsidies.py, vehicle_odometer.py, services/purchase_payments.py,
services/payment_lookup.py) — они перехватывают исключение раньше, чем оно
дойдёт до глобального обработчика, этот модуль их не трогает и не
переопределяет. Если IntegrityError всё же долетит сюда НЕЗАПЛАНИРОВАННО
(т.е. это необработанная локально UniqueViolation) — по заданию отдаём 409.

Rollback: НЕ требует отдельного кода — `app.database.get_db` открывает
сессию через `async with async_session() as session:`; когда роут поднимает
исключение, FastAPI закрывает dependency-generator ДО того, как исключение
долетает до любого exception_handler (в т.ч. до app.errors.
unhandled_exception_handler, который ловил эти же ошибки раньше) — `__aexit__`
сессии закрывает соединение, которое пул откатывает при возврате. Это тот же
путь, что был у catch-all `Exception` handler, поведение не меняется.

Формат ответа — {code, message, correlation_id}, тот же, что отдают
app.errors.http_exception_handler/validation_exception_handler
(ApiErrorDialog.vue на фронте читает code/message одинаково для всех 4xx)."""
import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)


def _classify(exc: Exception) -> tuple[int, str, str] | None:
    """Возвращает (status_code, code, message) для известных классов
    БД-ошибок/переполнений мусорного ввода, или None — тогда решает catch-all
    `Exception` handler (как и раньше, 500 + запись в SystemIncident).

    `exc` — либо sqlalchemy.exc.DBAPIError (читаем `.orig`, текст исходной
    asyncpg-ошибки), либо голый builtin OverflowError (читаем str(exc)
    напрямую — у него нет `.orig`)."""
    # Голый builtin OverflowError (а не DBAPIError с asyncpg-эксцепшеном
    # внутри .orig) — ЛЮБОЙ такой, независимо от текста сообщения: текст
    # различается ("...must have magnitude <= 999999999" vs "Python int too
    # large to convert to C int" — оба видены при проверке на
    # vehicles_dashboard_fines.py), но тип исключения сам по себе уже
    # достаточно специфичен (register_db_error_handlers регистрирует этот
    # handler ТОЛЬКО на OverflowError, см. ниже).
    if isinstance(exc, OverflowError):
        return 422, "INVALID_PARAM_VALUE", "Неверное значение параметра"

    orig = getattr(exc, "orig", None)
    text = str(orig) if orig is not None else str(exc)
    low = text.lower()

    # Порядок важен: сообщение о int32-переполнении само содержит "out of
    # range", поэтому проверяем конкретные случаи ДО общего numeric-overflow.
    if "foreignkeyviolationerror" in low or "violates foreign key constraint" in low:
        field = None
        m = re.search(r'column "([^"]+)"', text) or re.search(r'constraint "([^"]+)"', text)
        if m:
            field = m.group(1)
        message = "Указанный объект не найден" + (f" (поле «{field}»)" if field else "")
        return 422, "FK_NOT_FOUND", message

    if "limit must not be negative" in low or "offset must not be negative" in low or \
       "invalidrowcountinlimitclause" in low:
        return 422, "INVALID_PARAM_VALUE", "Неверное значение параметра (отрицательное значение limit/offset)"

    if "overflowerror" in low or "int32 range" in low or "invalid input for query argument" in low \
       or "must have magnitude" in low:
        return 422, "INVALID_PARAM_VALUE", "Неверное значение параметра"

    if "numericvalueoutofrange" in low or "numeric field overflow" in low:
        return 422, "NUMBER_TOO_LARGE", "Слишком большое число"

    if "stringdatarighttruncation" in low or "value too long for type" in low:
        # Найдено при проверке фикса (POST /api/suppliers/ с kpp длиннее
        # varchar(9)) — тот же класс мусорного ввода, что остальные здесь:
        # роутер не валидирует длину поля, Postgres падает первым.
        return 422, "INVALID_PARAM_VALUE", "Слишком длинное значение поля"

    if "invalid input syntax" in low or "invalidtextrepresentation" in low or "dataerror" in low:
        return 422, "INVALID_PARAM_VALUE", "Неверное значение параметра"

    if "uniqueviolation" in low or "duplicate key value violates unique constraint" in low:
        # Сюда долетают ТОЛЬКО UniqueViolation без локального try/except —
        # для уже обработанных (см. докстринг выше) этот handler не вызовется.
        return 409, "ALREADY_EXISTS", "Запись с такими данными уже существует"

    return None


async def _handle(request: Request, exc: Exception) -> JSONResponse:
    """Общее тело обоих handler'ов ниже (DBAPIError и голый OverflowError) —
    ОДНА точка сборки ответа, не копия (ПРАВИЛО №6)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    classified = _classify(exc)
    if classified is None:
        # Неизвестный случай — не глушим под 4xx: тот же результат, что
        # раньше отдавал catch-all `Exception` handler (500 + трейс +
        # SystemIncident) — переиспользуем ЕГО логику сохранения инцидента
        # (app.errors._save_incident), а не заводим вторую (ПРАВИЛО №6).
        # Внутри exception_handler raise не долетит до других handler'ов
        # Starlette, поэтому строим тот же ответ сами.
        import traceback as _traceback
        from app.errors import _save_incident
        details = "".join(_traceback.format_exception(type(exc), exc, exc.__traceback__))
        await _save_incident(request, "Внутренняя ошибка сервера", details,
                             "INTERNAL_ERROR", correlation_id)
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка сервера",
                # Трейсбек — только в SystemIncident, клиенту не отдаём
                # (аудит безопасности 2026-10-20, как в app.errors).
                "details": None,
                "correlation_id": correlation_id,
            },
        )
    status_code, code, message = classified
    logger.warning(
        "db_error_handler: %s %s -> %s %s (correlation_id=%s)",
        request.method, request.url.path, status_code, code, correlation_id,
    )
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "correlation_id": correlation_id},
    )


def register_db_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DBAPIError)
    async def db_error_handler(request: Request, exc: DBAPIError):
        return await _handle(request, exc)

    @app.exception_handler(OverflowError)
    async def overflow_error_handler(request: Request, exc: OverflowError):
        # Переполнение ДО похода в БД (напр. datetime.timedelta(days=...)) —
        # см. докстринг модуля. Та же _classify/_handle, не вторая формула.
        return await _handle(request, exc)
