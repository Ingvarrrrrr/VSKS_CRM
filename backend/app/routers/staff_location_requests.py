"""
API разовых запросов местоположения через мессенджер — владелец (организация
спасателей), 2026-09.

Только HTTP-слой: валидация входа, права, сборка ответа. Бизнес-логика — в
app/services/staff_location_requests.py (создание/ответ/отмена запроса,
отправка в Telegram/MAX). Модель — app/models/staff_location_request.py.

Права: staff.location.view — тот же ключ, что у app/routers/staff_location.py
(«диспетчер видит чужое местоположение» и «диспетчер просит чужое
местоположение» — одно и то же полномочие, отдельного права не заводим).
Видимость по организациям — переиспользуем _check_staff_visibility оттуда же
(не дублируем логику org-границы).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import _has_key_in_any_org
from app.models.user import User
from app.models.organization import Organization
from app.models.staff_location import StaffLocationPoint
from app.models.staff_location_request import StaffLocationRequest
from app.routers.staff_location import _check_staff_visibility, _LOCATION_VIEW_ACTION
from app.schemas.staff_location import (
    LocationRequestCreateIn, LocationRequestOut, LocationPointOut, RosterEntryOut,
    LocationRequestRespondIn,
)
from app.services.staff_location_requests import (
    create_request, cancel_request, decline_request, effective_status,
    record_location_response,
)
from app.services.push_sender import get_user_ids_with_subscription

router = APIRouter(prefix="/api/staff-location", tags=["staff-location-requests"])

log = logging.getLogger(__name__)


async def _require_view_permission(current_user: User, db: AsyncSession) -> None:
    if current_user.role in ("superadmin", "account_owner"):
        return
    if not await _has_key_in_any_org(current_user, db, _LOCATION_VIEW_ACTION):
        raise HTTPException(
            status_code=403,
            detail="Нет права «Просмотр местоположения сотрудников» — обратитесь к администратору организации.",
        )


def _to_out(
    req: StaffLocationRequest,
    requester_name: Optional[str] = None,
    point: Optional[StaffLocationPoint] = None,
) -> LocationRequestOut:
    return LocationRequestOut(
        id=req.id,
        requested_by_id=req.requested_by_id,
        requested_by_name=requester_name,
        user_id=req.user_id,
        status=effective_status(req),
        channels_sent=req.channels_sent,
        created_at=req.created_at,
        expires_at=req.expires_at,
        responded_at=req.responded_at,
        point=LocationPointOut.model_validate(point) if point else None,
    )


@router.post("/requests", response_model=LocationRequestOut)
async def create_location_request(
    body: LocationRequestCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кнопка «Запросить местоположение» у конкретного сотрудника."""
    await _require_view_permission(current_user, db)

    target = await db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if target.id != current_user.id:
        await _check_staff_visibility(target, current_user, db)

    req = await create_request(db, current_user, target)
    await db.commit()
    await db.refresh(req)
    return _to_out(req, requester_name=current_user.full_name or current_user.username)


@router.get("/requests", response_model=List[LocationRequestOut])
async def list_location_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Запросы по сотрудникам своих организаций (не только созданные мной —
    чтобы разные диспетчеры видели друг у друга, что запрос уже отправлен и
    не спамили сотрудника повторно)."""
    await _require_view_permission(current_user, db)

    q = select(StaffLocationRequest, User).join(User, User.id == StaffLocationRequest.user_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    q = q.order_by(StaffLocationRequest.created_at.desc()).limit(200)
    rows = (await db.execute(q)).all()
    if not rows:
        return []

    point_ids = [r.point_id for (r, _u) in rows if r.point_id]
    points = {}
    if point_ids:
        prows = (await db.execute(
            select(StaffLocationPoint).where(StaffLocationPoint.id.in_(point_ids))
        )).scalars().all()
        points = {p.id: p for p in prows}

    requester_ids = {r.requested_by_id for (r, _u) in rows}
    requesters = {}
    if requester_ids:
        urows = (await db.execute(
            select(User.id, User.full_name, User.username).where(User.id.in_(requester_ids))
        )).all()
        requesters = {row.id: (row.full_name or row.username) for row in urows}

    changed = False
    out = []
    for req, _u in rows:
        if effective_status(req) == "expired" and req.status != "expired":
            req.status = "expired"
            changed = True
        out.append(_to_out(
            req,
            requester_name=requesters.get(req.requested_by_id),
            point=points.get(req.point_id),
        ))
    if changed:
        await db.commit()
    return out


@router.post("/requests/{request_id}/cancel", response_model=LocationRequestOut)
async def cancel_location_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(StaffLocationRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    if req.requested_by_id != current_user.id and current_user.role not in ("superadmin", "account_owner"):
        raise HTTPException(status_code=403, detail="Отменить можно только запрос, который создали вы сами.")
    if effective_status(req) != "sent":
        raise HTTPException(status_code=400, detail="Запрос уже не активен (получен ответ, истёк или уже отменён) — отменять нечего.")

    await cancel_request(db, req)
    await db.commit()
    await db.refresh(req)
    return _to_out(req)


@router.get("/roster", response_model=List[RosterEntryOut])
async def list_roster(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Все сотрудники своих организаций + привязка мессенджеров + последний
    запрос — данные для панели «Запросить местоположение» на карте «Где люди».
    Показывает и тех, у кого мессенджер не привязан (can_request=False),
    задание п.3 — «не прятать молча»."""
    await _require_view_permission(current_user, db)

    q = select(User).where(User.id != current_user.id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    users = (await db.execute(q)).scalars().all()
    if not users:
        return []

    org_ids_in_use = {u.org_id for u in users if u.org_id}
    org_names = {}
    if org_ids_in_use:
        org_rows = (await db.execute(
            select(Organization.id, Organization.name).where(Organization.id.in_(org_ids_in_use))
        )).all()
        org_names = {r.id: r.name for r in org_rows}

    user_ids = [u.id for u in users]
    all_reqs = (await db.execute(
        select(StaffLocationRequest)
        .where(StaffLocationRequest.user_id.in_(user_ids))
        .order_by(StaffLocationRequest.user_id, StaffLocationRequest.created_at.desc())
    )).scalars().all()
    latest_by_user: dict[int, StaffLocationRequest] = {}
    for r in all_reqs:
        if r.user_id not in latest_by_user:
            latest_by_user[r.user_id] = r

    point_ids = [r.point_id for r in latest_by_user.values() if r.point_id]
    points = {}
    if point_ids:
        prows = (await db.execute(
            select(StaffLocationPoint).where(StaffLocationPoint.id.in_(point_ids))
        )).scalars().all()
        points = {p.id: p for p in prows}

    # 2026-09: push — основной канал, показываем диспетчеру наравне с
    # Telegram/MAX (задание п.5 — "дойдёт ли запрос"), одним batch-запросом.
    push_user_ids = await get_user_ids_with_subscription(db, user_ids)

    out = []
    for u in users:
        tg = bool(getattr(u, "telegram_id", None))
        mx = bool(getattr(u, "max_chat_id", None))
        push = u.id in push_user_ids
        req = latest_by_user.get(u.id)
        out.append(RosterEntryOut(
            user_id=u.id,
            full_name=u.full_name or u.username,
            org_id=u.org_id,
            org_name=org_names.get(u.org_id) if u.org_id else None,
            has_push=push,
            has_telegram=tg,
            has_max=mx,
            can_request=(push or tg or mx),
            latest_request=_to_out(req, point=points.get(req.point_id)) if req else None,
        ))
    out.sort(key=lambda r: (r.full_name or "").lower())
    return out


# ─────────── Экран подтверждения на телефоне сотрудника (push-клик) ────────
# Задание владельца п.2/п.3 (2026-09): по клику на push открывается
# экран подтверждения в самом приложении — тут endpoints для НЕГО САМОГО
# (не для диспетчера, поэтому БЕЗ staff.location.view — это его собственные
# данные, тот же принцип, что у /staff-location/mine/last в staff_location.py).


async def _load_own_request(request_id: int, current_user: User, db: AsyncSession) -> StaffLocationRequest:
    req = await db.get(StaffLocationRequest, request_id)
    if not req or req.user_id != current_user.id:
        # 404, не 403 — не подтверждаем даже факт существования чужого запроса.
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return req


@router.get("/requests/{request_id}/self", response_model=LocationRequestOut)
async def get_own_location_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Данные для экрана подтверждения — сотрудник открывает СВОЙ запрос
    (обычно по клику на push)."""
    req = await _load_own_request(request_id, current_user, db)
    if effective_status(req) == "expired" and req.status != "expired":
        req.status = "expired"
        await db.commit()
        await db.refresh(req)
    requester = await db.get(User, req.requested_by_id)
    return _to_out(req, requester_name=(requester.full_name or requester.username) if requester else None)


@router.post("/requests/{request_id}/respond", response_model=LocationRequestOut)
async def respond_own_location_request(
    request_id: int,
    body: LocationRequestRespondIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кнопка «Отправить моё местоположение» на экране подтверждения.

    Пишет точку тем же путём, что и ответ из Telegram (record_location_response
    — минуя проверку активной смены), с source='webapp', отличающим канал
    ответа от 'telegram'/'browser' на карте (задание п.3)."""
    req = await _load_own_request(request_id, current_user, db)
    computed = effective_status(req)
    if computed != "sent":
        if computed == "expired" and req.status != "expired":
            req.status = "expired"
            await db.commit()  # фиксируем ленивую пометку "истёк"
        raise HTTPException(
            status_code=400,
            detail="Запрос уже не активен (истёк, отменён или ответ уже принят) — обновите страницу.",
        )
    await record_location_response(
        db, req, lat=body.lat, lon=body.lon, accuracy_m=body.accuracy_m, source="webapp",
    )
    await db.commit()
    await db.refresh(req)
    log.info("staff_location_request id=%s answered via webapp by user_id=%s", req.id, current_user.id)
    return _to_out(req)


@router.post("/requests/{request_id}/decline", response_model=LocationRequestOut)
async def decline_own_location_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кнопка «Отказаться» на экране подтверждения — фиксирует явный отказ,
    чтобы диспетчер видел разницу между «не увидел» и «отказался» (задание)."""
    req = await _load_own_request(request_id, current_user, db)
    computed = effective_status(req)
    if computed != "sent":
        if computed == "expired" and req.status != "expired":
            req.status = "expired"
            await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Запрос уже не активен — отказаться уже нельзя.",
        )
    await decline_request(db, req)
    await db.commit()
    await db.refresh(req)
    log.info("staff_location_request id=%s declined by user_id=%s", req.id, current_user.id)
    return _to_out(req)
