"""152-ФЗ: согласие на обработку персональных данных + обращения субъектов ПДн.

IP клиента — переиспользует подход backend/app/auth/rate_limit.py (см. его
docstring, раздел «IP и X-Forwarded-For»): backend/Dockerfile запускает
uvicorn с `--proxy-headers --forwarded-allow-ips='*'`, поэтому uvicorn САМ
разбирает X-Forwarded-For от nginx и подменяет `request.client.host` на
реальный IP клиента ещё до ASGI-приложения. Самостоятельный разбор заголовка
здесь был бы двойной и небезопасной подменой (то же предупреждение, что и в
rate_limit.py). ВАЖНО: backend/app/routers/purchase_approvals.py содержит
свою собственную (более старую) реализацию `_client_ip`, которая ЧИТАЕТ
X-Forwarded-For напрямую — по факту это разошедшийся с rate_limit.py способ
получения IP (Правило №6 уже нарушено ДО этой задачи). Чинить
purchase_approvals.py вне периметра этой задачи; здесь взят задокументированный
и более обоснованный вариант (rate_limit.py), а не скопирован второй.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.models.user_consent import (
    PersonalDataRequest,
    PersonalDataRequestStatus,
    PersonalDataRequestType,
    UserConsent,
)
from app.services.legal_constants import get_response_due_at

router = APIRouter(prefix="/api/legal", tags=["legal"])


def client_ip(request: Request) -> str:
    """См. docstring модуля — единственный корректный способ в проекте."""
    return request.client.host if request.client else "unknown"


class PersonalDataRequestCreate(BaseModel):
    request_type: str
    message: str
    reply_contact: Optional[str] = None
    requester_name: Optional[str] = None


def _consent_out(c: UserConsent) -> dict:
    return {
        "id": c.id,
        "document_version": c.document_version,
        "documents": c.documents,
        "accepted_at": c.accepted_at.isoformat() if c.accepted_at else None,
        "source": c.source,
        "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
        "withdrawal_reason": c.withdrawal_reason,
    }


def _request_out(r: PersonalDataRequest) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "requester_name": r.requester_name,
        "reply_contact": r.reply_contact,
        "request_type": r.request_type,
        "message": r.message,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "response_due_at": r.response_due_at.isoformat() if r.response_due_at else None,
        "status": r.status,
        "answered_at": r.answered_at.isoformat() if r.answered_at else None,
        "response_text": r.response_text,
        "handled_by_user_id": r.handled_by_user_id,
    }


@router.get("/my-consents")
async def my_consents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """История согласий текущего пользователя."""
    rows = (
        await db.execute(
            select(UserConsent)
            .where(UserConsent.user_id == current_user.id)
            .order_by(desc(UserConsent.accepted_at))
        )
    ).scalars().all()
    return [_consent_out(c) for c in rows]


@router.post("/request", status_code=201)
async def create_personal_data_request(
    data: PersonalDataRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Регистрация обращения субъекта ПДн. НЕ выполняет удаление/исправление/
    отзыв автоматически — только фиксирует обращение; решение и ответ
    (в т.ч. фактическое уничтожение/исправление данных) выполняет оператор
    вручную по итогам рассмотрения, вне этого запроса."""
    if data.request_type not in PersonalDataRequestType.ALL:
        raise HTTPException(
            400,
            f"Неизвестный тип обращения: {data.request_type!r}. "
            f"Допустимые значения: {', '.join(PersonalDataRequestType.ALL)}",
        )
    if not data.message or not data.message.strip():
        raise HTTPException(400, "Текст обращения не может быть пустым")

    reply_contact = (data.reply_contact or current_user.email or "").strip()
    if not reply_contact:
        raise HTTPException(
            400,
            "Укажите контакт для ответа (email или телефон) — у вашей учётной "
            "записи не указан email",
        )

    # response_due_at считается здесь и ТОЛЬКО здесь (Правило №6) —
    # см. app/services/legal_constants.get_response_due_at(). received_at
    # фиксируется в Python (а не полагается на server_default), чтобы срок
    # был посчитан от той же даты, что попадёт в БД.
    received_at = datetime.now(timezone.utc)
    req = PersonalDataRequest(
        user_id=current_user.id,
        requester_name=data.requester_name or current_user.full_name,
        reply_contact=reply_contact,
        request_type=data.request_type,
        message=data.message.strip(),
        received_at=received_at,
        response_due_at=get_response_due_at(received_at, data.request_type),
        status=PersonalDataRequestStatus.NEW,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return _request_out(req)


@router.get("/requests")
async def list_personal_data_requests(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    # Уровень админа АККАУНТА, не орги: обращение субъекта ПДн — сквозной
    # compliance-процесс на весь аккаунт (может вовсе не иметь org_id), а
    # org_admin управляет только своей организацией — решение: НЕ пускать
    # org_admin, чтобы не создавать иллюзию видимости чужих обращений/её
    # отсутствия по организационному признаку, которого у обращения нет.
    # Тот же кортеж ролей, что уже применяется в organizations.py для
    # аккаунт-уровневых операций (create/delete organization).
    _admin=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    """Список обращений субъектов ПДн — только для администраторов аккаунта."""
    rows = (
        await db.execute(
            select(PersonalDataRequest)
            .order_by(desc(PersonalDataRequest.received_at))
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return [_request_out(r) for r in rows]
