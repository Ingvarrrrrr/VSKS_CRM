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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.user_consent import (
    PersonalDataRequest,
    PersonalDataRequestStatus,
    PersonalDataRequestType,
    UserConsent,
)
from app.services.consent_status import (
    orgs_requiring_poruchenie,
    pd_consent_required,
    poruchenie_required,
)
from app.services.legal_constants import (
    PD_CONSENT_DOCUMENTS,
    PD_CONSENT_VERSION,
    PORUCHENIE_DOCUMENTS,
    PORUCHENIE_VERSION,
    get_response_due_at,
)

router = APIRouter(prefix="/api/legal", tags=["legal"])

# 152-ФЗ: отказ принять «за чужую организацию» — то же сообщение везде,
# где могло бы возникнуть (сейчас только здесь, ПРАВИЛО №6: одна константа,
# а не копия текста при появлении второго места).
PORUCHENIE_NOT_OWNER_MESSAGE = (
    "Условия поручения обработки персональных данных может принять только "
    "владелец организации"
)


class ConsentAcceptRequest(BaseModel):
    kind: str  # 'pd' | 'poruchenie'
    accepted: bool
    org_id: Optional[int] = None  # совместимость со старым фронтом (одна org)
    org_ids: Optional[List[int]] = None  # новый фронт: ВСЕ org одним запросом


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


@router.get("/consent-status")
async def consent_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Единственное место, откуда фронт узнаёт, нужно ли показать гейт
    согласия после входа (router/index.ts beforeEach → useConsentGate.ts).
    Решение считает backend/app/services/consent_status.py — сервер не верит
    тому, что скажет фронт, версии берёт из своей сборки legal_generated.py.

    poruchenie_required: true только для ДЕЙСТВИТЕЛЬНОГО владельца
    организации (Organization.owner_user_id == current_user.id) — не для
    любого account_owner/admin (см. feedback_permission_check_vs_candidate_pool
    — тот же класс ошибки: право/обязанность должны идти по владению, а не
    по роли). Владелец НЕСКОЛЬКИХ организаций без поручения видит и
    отмечает ВСЕ сразу (poruchenie_orgs) одним экраном — раньше отдавалась
    только первая по id, и владелец проходил гейт по кругу (жалоба
    владельца 2026-10-14). poruchenie_org (единственное число) — старое
    поле, оставлено для обратной совместимости с закешированным фронтом:
    первый элемент poruchenie_orgs или null.
    """
    pd_required = await pd_consent_required(db, current_user.id)
    pending_orgs = await orgs_requiring_poruchenie(db, current_user.id)
    poruchenie_orgs = [{"id": org.id, "name": org.name} for org in pending_orgs]

    return {
        "pd_consent_required": pd_required,
        "poruchenie_required": bool(poruchenie_orgs),
        "poruchenie_orgs": poruchenie_orgs,
        "poruchenie_org": poruchenie_orgs[0] if poruchenie_orgs else None,
        "pd_version": PD_CONSENT_VERSION,
        "poruchenie_version": PORUCHENIE_VERSION,
    }


@router.post("/consent", status_code=201)
async def accept_consent(
    data: ConsentAcceptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Приём согласия ВНЕ регистрации (гейт после входа, ConsentRequiredView.vue).
    document_version всегда СЕРВЕРНАЯ текущая версия (PD_CONSENT_VERSION /
    PORUCHENIE_VERSION) — тело запроса её не диктует (ПРАВИЛО №6, та же
    версия, что строит сам consent-status).

    kind='poruchenie' принимает org_ids (новый фронт — все организации
    владельца сразу) или старый одиночный org_id (обратная совместимость).
    Требование «все сразу»: пока хоть одна организация из
    orgs_requiring_poruchenie() не отмечена — 400 с перечислением
    неотмеченных названий; одна запись UserConsent на организацию, все в
    одной транзакции (ПРАВИЛО №6 — тот же источник правды, что и
    consent-status, не считаем список заново по-другому)."""
    if not data.accepted:
        raise HTTPException(400, "Согласие не отмечено")

    if data.kind == "pd":
        consent = UserConsent(
            user_id=current_user.id,
            org_id=None,
            email=current_user.email or "",
            document_version=PD_CONSENT_VERSION,
            documents=list(PD_CONSENT_DOCUMENTS),
            ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            source="login",
        )
        db.add(consent)
        await db.commit()
        await db.refresh(consent)
        return _consent_out(consent)

    if data.kind != "poruchenie":
        raise HTTPException(400, f"Неизвестный тип согласия: {data.kind!r}")

    # org_ids (не None, пусть и пустой список) — новый фронт, явно работающий
    # со ВСЕМ списком сразу (ConsentRequiredView.vue). Голый org_id без
    # org_ids — старый фронт/клиент (см. e2e/helpers.ts::acceptConsentIfShown):
    # принимает организации ПО ОДНОЙ за вызов, поэтому для него требование
    # «все сразу» не включается — иначе старый клиент, шлющий по одному
    # org_id за раз, получал бы 400 на каждый, кроме последнего.
    is_all_at_once = data.org_ids is not None
    submitted_ids = set(data.org_ids or [])
    if data.org_id:
        submitted_ids.add(data.org_id)
    if not submitted_ids:
        raise HTTPException(400, "Не указана организация")

    pending_orgs = await orgs_requiring_poruchenie(db, current_user.id)
    pending_by_id = {org.id: org for org in pending_orgs}

    # Чужая организация в списке — 403 с названием (а не тихое игнорирование):
    # проверяем ПРИНАДЛЕЖНОСТЬ (owner_user_id), не попадание в pending —
    # иначе уже принятая своя организация, повторно отмеченная на фронте,
    # ошибочно выглядела бы «чужой».
    submitted_orgs = (
        await db.execute(select(Organization).where(Organization.id.in_(submitted_ids)))
    ).scalars().all()
    submitted_by_id = {org.id: org for org in submitted_orgs}
    foreign_ids = [
        oid for oid in submitted_ids
        if submitted_by_id.get(oid) is None or submitted_by_id[oid].owner_user_id != current_user.id
    ]
    if foreign_ids:
        names = [
            submitted_by_id[oid].name if oid in submitted_by_id else f"#{oid}"
            for oid in foreign_ids
        ]
        raise HTTPException(
            403,
            f"{PORUCHENIE_NOT_OWNER_MESSAGE}: {', '.join(f'«{n}»' for n in names)}",
        )

    if is_all_at_once:
        missing_ids = set(pending_by_id) - submitted_ids
        if missing_ids:
            missing_names = [pending_by_id[oid].name for oid in missing_ids]
            raise HTTPException(
                400,
                "Отметьте все организации, владельцем которых вы являетесь: "
                + ", ".join(f"«{n}»" for n in missing_names),
            )

    created: list[UserConsent] = []
    for org_id in submitted_ids:
        consent = UserConsent(
            user_id=current_user.id,
            org_id=org_id,
            email=current_user.email or "",
            document_version=PORUCHENIE_VERSION,
            documents=list(PORUCHENIE_DOCUMENTS),
            ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            source="login",
        )
        db.add(consent)
        created.append(consent)
    await db.commit()
    for consent in created:
        await db.refresh(consent)
    return [_consent_out(c) for c in created]
