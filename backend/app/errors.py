"""Глобальные exception handler'ы + сохранение инцидентов в SystemIncident.

Перенесено из app/__init__.py при разрезании монолитного файла на модули
(Правило №5). Логика не менялась. `_save_incident` определена ДО хендлеров,
которые её вызывают (в исходнике было наоборот — определение после места
использования допустимо в Python благодаря позднему связыванию внутри тела
функции, но здесь для читаемости порядок изменён на строго последовательный).
"""
import traceback
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.database import async_session

# Плановые позиции ФЭО (FeoPlannedItemCreate, app/schemas/schemas.py) — жалоба
# владельца 2026-09-04: пустая «Цена за единицу» отвечала сырым «Поле "unit_price":
# ожидается число», человек не обязан знать имя поля бэкенда.
field_labels = {
    "subsidy_id": "Субсидия", "contractor_id": "Контрагент", "item_type": "Тип",
    "item_name": "Наименование", "status": "Статус", "date": "Дата",
    "contract_date": "Дата договора", "delivery_date": "Дата поставки",
    "execution_term": "Срок исполнения", "nmck": "НМЦК", "contract_price": "Цена договора",
    "planned_total_price": "Плановая сумма", "payment_amount": "Сумма оплаты",
    "number": "Номер", "subject": "Предмет", "max_amount": "Максимальная сумма",
    # wishes (заявки)
    "title": "Название", "category": "Категория", "description": "Описание",
    "quantity": "Количество", "unit": "Ед. изм.", "estimated_price": "Ориент. цена",
    "link": "Ссылка", "priority": "Приоритет", "desired_date": "Желаемая дата",
    "last_name": "Фамилия", "first_name": "Имя", "middle_name": "Отчество",
    "justification": "Обоснование", "org_id": "Организация",
    "assigned_to": "Ответственный", "event_id": "Мероприятие",
    "execution_deadline": "Срок исполнения",
    "unit_price": "Цена за единицу", "amount": "Сумма", "name": "Наименование",
    "feo_category_id": "Категория ФЭО", "months_count": "Количество месяцев",
    "monthly_amount": "Сумма в месяц", "planned_date": "Плановая дата",
    "monthly_start_date": "Дата начала выплат",
}


async def _save_incident(request: Request, message: str, details: str,
                         code: str, correlation_id: str):
    try:
        from app.models.system_incident import SystemIncident
        user_id = getattr(getattr(request, "state", None), "user_id", None)
        async with async_session() as session:
            session.add(SystemIncident(
                message=message, details=details, code=code,
                correlation_id=correlation_id,
                path=request.url.path, method=request.method,
                user_id=user_id,
            ))
            await session.commit()
    except Exception:
        pass


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Convert pydantic 422 errors into human-readable Russian messages."""
        correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
        errors = []
        fields = []  # для фронта: подсветка/стрелочка к проблемному полю
        for err in exc.errors():
            loc = [str(l) for l in err.get("loc", []) if l != "body"]
            field = loc[-1] if loc else "?"
            label = field_labels.get(field, field)
            fields.append({"field": field, "label": label})
            msg = err.get("msg", "")
            # Translate common pydantic messages
            if "required" in msg.lower():
                errors.append(f"Поле «{label}» обязательно для заполнения")
            elif "valid" in msg.lower() and "date" in msg.lower():
                errors.append(f"Поле «{label}»: неверный формат даты")
            elif "valid" in msg.lower() and ("decimal" in msg.lower() or "number" in msg.lower()):
                errors.append(f"Поле «{label}»: ожидается число")
            elif "valid" in msg.lower() and "integer" in msg.lower():
                errors.append(f"Поле «{label}»: ожидается целое число")
            else:
                errors.append(f"Поле «{label}»: {msg}")
        message = "; ".join(errors) if errors else "Проверьте правильность заполнения формы"
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": message,
                "fields": fields,  # [{field, label}] — фронт подсвечивает поля
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
        # Phase 23.2: support structured dict-detail (e.g. TEMPLATE_RENDER_ERROR with hint).
        # Если HTTPException(detail=<dict>) — пробрасываем поля dict'а в payload (code из dict
        # перекрывает HTTP_<status>, message/details берутся из dict). Иначе fallback на старое поведение.
        if isinstance(exc.detail, dict):
            payload = {
                "code": exc.detail.get("code") or f"HTTP_{exc.status_code}",
                "message": exc.detail.get("message") or "Ошибка запроса",
                "details": exc.detail,
                "correlation_id": correlation_id,
            }
        else:
            payload = {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail if isinstance(exc.detail, str) else "Ошибка запроса",
                "details": None,
                "correlation_id": correlation_id,
            }
        if exc.status_code >= 500:
            await _save_incident(request, payload["message"], repr(exc.detail),
                                 payload["code"], correlation_id)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        await _save_incident(request, "Внутренняя ошибка сервера", details,
                             "INTERNAL_ERROR", correlation_id)
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка сервера",
                "details": details,
                "correlation_id": correlation_id,
            },
        )
