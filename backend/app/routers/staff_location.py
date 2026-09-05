"""
Отслеживание местоположения сотрудников — владелец (организация спасателей), 2026-09.

Контекст: аварийная безопасность, не круглосуточный трекинг. Сотрудник сам
включает передачу кнопкой «Я на смене» и сам выключает. Согласия сотрудников
владелец берёт на себя вне системы.

ТОЛЬКО BACKEND — мобильный интерфейс/карта заказываются отдельно.

Права (см. app/__init__.py, блок "Phase: staff.location.view permission seed",
по образцу Phase 29 vehicle.* сидов):
  - staff.location.view — видеть местоположение ЧУЖИХ сотрудников (в своих
    организациях). Granted по умолчанию: superadmin/account_owner/admin/org_admin.
    Explicit False: manager/employee (владелец решил — управленцы НЕ входят
    в дефолт, право отдельное от общих ролей).
  - Свою собственную позицию и смену видно ВСЕГДА, без этого права.

Видимость чужих данных — тот же принцип, что в vehicles.py (_visibility_q /
get_org_filter): организационная граница пользователя + explicit action-key.

ПЕРСОНАЛЬНЫЕ ДАННЫЕ: координаты нигде не логируются (см. функции ниже — в
logging.* только счётчики и user_id, никогда lat/lon). Выдача чужих точек
закрыта правом + организационной границей (см. _check_staff_visibility).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func as sa_func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import _has_key_in_any_org
from app.models.user import User
from app.models.organization import Organization
from app.models.staff_shift import StaffShift
from app.models.staff_location import StaffLocationPoint
from app.models.staff_location_request import StaffLocationRequest
from app.schemas.staff_location import (
    ShiftOut, LocationBatchIn, LocationBatchResult, LocationPointOut, OnShiftUserOut,
)

router = APIRouter(prefix="/api/staff-location", tags=["staff-location"])

log = logging.getLogger(__name__)

_LOCATION_VIEW_ACTION = "staff.location.view"
_MAX_POINT_AGE = timedelta(hours=24)  # точки старше суток игнорируются (задание п.3)
_RETENTION_DAYS = 30


def _ensure_utc(dt: datetime) -> datetime:
    """Naive datetime -> считаем UTC (устройства могут прислать без offset)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_active_shift(db: AsyncSession, user_id: int) -> Optional[StaffShift]:
    return (await db.execute(
        select(StaffShift).where(StaffShift.user_id == user_id, StaffShift.is_active == True)  # noqa: E712
    )).scalar_one_or_none()


async def _check_staff_visibility(target: User, current_user: User, db: AsyncSession) -> None:
    """403 с понятной причиной, если current_user не может смотреть чужие данные target.

    Тот же принцип, что vehicles.py::_check_vehicle_visibility: явное право
    (action key, хотя бы в одной орге) + организационная граница (get_org_filter).
    Свой собственный user_id сюда не попадает — вызывающий код обязан проверить
    это раньше и пропустить self без вызова этой функции.
    """
    if current_user.role in ("superadmin", "account_owner"):
        return
    if not await _has_key_in_any_org(current_user, db, _LOCATION_VIEW_ACTION):
        raise HTTPException(
            status_code=403,
            detail="Нет права «Просмотр местоположения сотрудников» — обратитесь к администратору организации.",
        )
    org_ids = get_org_filter(current_user)
    if org_ids is not None and target.org_id not in org_ids:
        raise HTTPException(
            status_code=403,
            detail="Этот сотрудник состоит в организации, к которой у вас нет доступа.",
        )


async def cleanup_old_location_points(db: AsyncSession) -> int:
    """Удаляет точки местоположения старше 30 дней (задание п.5).

    Вызывается: (1) в фоновом asyncio-цикле при старте приложения
    (app/__init__.py::_staff_location_cleanup_loop — раз в сутки, по образцу
    уже существующих периодических циклов типа _waybill_overdue_loop), и
    (2) лениво при обращении к API этого роутера (см. вызовы ниже) — на
    случай, если процесс держится дольше суток без перезапуска между чистками
    не страшно, это просто дополнительная подстраховка, а не замена циклу.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
    res = await db.execute(
        delete(StaffLocationPoint).where(StaffLocationPoint.recorded_at < cutoff)
    )
    await db.commit()
    deleted = res.rowcount or 0
    if deleted:
        log.info("staff_location cleanup: удалено записей старше %s дней: %d", _RETENTION_DAYS, deleted)
    return deleted


# ─────────────────────────── Смена ──────────────────────────────────────────

@router.post("/shift/start", response_model=ShiftOut)
async def start_shift(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кнопка «Я на смене» — включить передачу местоположения.

    Идемпотентно: повторное нажатие при уже активной смене возвращает
    существующую смену, а не создаёт вторую и не падает ошибкой.
    """
    existing = await _get_active_shift(db, current_user.id)
    if existing:
        return ShiftOut.model_validate(existing)

    shift = StaffShift(user_id=current_user.id, is_active=True)
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    return ShiftOut.model_validate(shift)


@router.post("/shift/end", response_model=ShiftOut)
async def end_shift(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кнопка «Я на смене» (повторное нажатие) — выключить передачу местоположения."""
    shift = await _get_active_shift(db, current_user.id)
    if not shift:
        raise HTTPException(status_code=400, detail="Смена не была начата — нечего завершать.")

    shift.is_active = False
    shift.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(shift)
    return ShiftOut.model_validate(shift)


@router.get("/shift/me", response_model=Optional[ShiftOut])
async def get_my_shift(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Своё состояние смены — доступно всегда, без права staff.location.view."""
    shift = await _get_active_shift(db, current_user.id)
    return ShiftOut.model_validate(shift) if shift else None


# ─────────────────────────── Приём координат ────────────────────────────────

@router.post("/points", response_model=LocationBatchResult)
async def submit_points(
    body: LocationBatchIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Пакетный приём координат текущего пользователя.

    Пакетом — потому что мобильное приложение копит точки при потере связи и
    досылает их разом. Требует активную смену (иначе 400 по-русски, задание
    п.3 — не молчать). Точки старше суток игнорируются. Дубли по времени
    (user_id, recorded_at) не создают новых строк (ON CONFLICT DO NOTHING).

    ПЕРСОНАЛЬНЫЕ ДАННЫЕ: ничего из body (координаты) не попадает в логи — см.
    log.info ниже, там только числа-счётчики.
    """
    shift = await _get_active_shift(db, current_user.id)
    if not shift:
        raise HTTPException(
            status_code=400,
            detail="Координаты не приняты: смена не активна. Нажмите «Я на смене», прежде чем отправлять местоположение.",
        )

    now = datetime.now(timezone.utc)
    cutoff_old = now - _MAX_POINT_AGE

    ignored_old = 0
    rows_by_ts: dict[datetime, dict] = {}  # де-дуп ВНУТРИ пакета по recorded_at
    for p in body.points:
        recorded = _ensure_utc(p.recorded_at)
        if recorded < cutoff_old:
            ignored_old += 1
            continue
        rows_by_ts[recorded] = {
            "user_id": current_user.id,
            "lat": p.lat,
            "lon": p.lon,
            "accuracy_m": p.accuracy_m,
            "recorded_at": recorded,
            "source": (p.source or "browser")[:20],
        }

    accepted = 0
    ignored_duplicate = 0
    rows = list(rows_by_ts.values())
    if rows:
        stmt = pg_insert(StaffLocationPoint).values(rows).on_conflict_do_nothing(
            constraint="uq_staff_location_user_recorded"
        ).returning(StaffLocationPoint.id)
        res = await db.execute(stmt)
        accepted = len(res.fetchall())
        ignored_duplicate = len(rows) - accepted
        await db.commit()

    log.info(
        "staff_location.points user_id=%s accepted=%d ignored_old=%d ignored_duplicate=%d",
        current_user.id, accepted, ignored_old, ignored_duplicate,
    )

    # Ленивая подстраховка автоочистки (см. cleanup_old_location_points) —
    # реальный периодический цикл живёт в app/__init__.py.
    try:
        await cleanup_old_location_points(db)
    except Exception as exc:
        log.warning("staff_location lazy cleanup skipped (non-fatal): %s", exc)

    return LocationBatchResult(
        accepted=accepted, ignored_old=ignored_old, ignored_duplicate=ignored_duplicate,
    )


# ─────────────────────────── Своя позиция ───────────────────────────────────

@router.get("/mine/last", response_model=Optional[LocationPointOut])
async def get_my_last_point(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Своя последняя точка — доступна всегда, без права staff.location.view."""
    point = (await db.execute(
        select(StaffLocationPoint)
        .where(StaffLocationPoint.user_id == current_user.id)
        .order_by(StaffLocationPoint.recorded_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    return LocationPointOut.model_validate(point) if point else None


# ─────────────────────────── Диспетчер: кто на смене ────────────────────────

@router.get("/on-shift", response_model=List[OnShiftUserOut])
async def list_on_shift(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кто сейчас на смене + последняя точка каждого — для диспетчера/руководителя.

    Требует staff.location.view. Видимость ограничена своими организациями
    (get_org_filter), тот же принцип, что list_vehicles в vehicles.py.

    2026-09 (запрос местоположения через мессенджер): в список ДОБАВЛЯЮТСЯ
    сотрудники БЕЗ активной смены, если они за последние _MAX_POINT_AGE (24ч)
    ответили на разовый запрос местоположения (staff_location_request.py) —
    задание явно требует, чтобы такая точка попадала на карту «Где люди»,
    даже когда смена не включена. Отмечены via_request=True, shift_started_at
    не заполняется (у них не было смены — нечего показывать).
    """
    if current_user.role not in ("superadmin", "account_owner"):
        if not await _has_key_in_any_org(current_user, db, _LOCATION_VIEW_ACTION):
            raise HTTPException(
                status_code=403,
                detail="Нет права «Просмотр местоположения сотрудников» — обратитесь к администратору организации.",
            )

    q = (
        select(StaffShift, User)
        .join(User, User.id == StaffShift.user_id)
        .where(StaffShift.is_active == True)  # noqa: E712
    )
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))

    rows = (await db.execute(q)).all()
    shift_user_ids = {u.id for (_shift, u) in rows}

    # ── Разовые ответы на запрос без активной смены ──────────────────────────
    one_off_cutoff = datetime.now(timezone.utc) - _MAX_POINT_AGE
    one_off_q = (
        select(StaffLocationRequest, StaffLocationPoint, User)
        .join(StaffLocationPoint, StaffLocationPoint.id == StaffLocationRequest.point_id)
        .join(User, User.id == StaffLocationRequest.user_id)
        .where(
            StaffLocationRequest.status == "answered",
            StaffLocationPoint.recorded_at >= one_off_cutoff,
        )
        .order_by(StaffLocationRequest.user_id, StaffLocationRequest.responded_at.desc())
    )
    if org_ids is not None:
        one_off_q = one_off_q.where(User.org_id.in_(org_ids))
    one_off_rows = (await db.execute(one_off_q)).all()
    # Одна (самая свежая) запись на пользователя, и только если сейчас не на смене.
    one_off_by_user: dict[int, tuple] = {}
    for _req, point, u in one_off_rows:
        if u.id in shift_user_ids or u.id in one_off_by_user:
            continue
        one_off_by_user[u.id] = (point, u)

    if not rows and not one_off_by_user:
        return []

    user_ids = list(shift_user_ids) + list(one_off_by_user.keys())

    # Последняя точка каждого сотрудника НА СМЕНЕ — DISTINCT ON (user_id)
    # ORDER BY user_id, recorded_at DESC (postgres-специфично, обслуживается
    # индексом ix_staff_location_points_user_recorded).
    last_points: dict[int, StaffLocationPoint] = {}
    if shift_user_ids:
        last_points_q = (
            select(StaffLocationPoint)
            .where(StaffLocationPoint.user_id.in_(shift_user_ids))
            .distinct(StaffLocationPoint.user_id)
            .order_by(StaffLocationPoint.user_id, StaffLocationPoint.recorded_at.desc())
        )
        last_points = {p.user_id: p for p in (await db.execute(last_points_q)).scalars().all()}

    all_users = {u.id: u for (_shift, u) in rows}
    for _pt, u in one_off_by_user.values():
        all_users[u.id] = u

    org_ids_in_use = {u.org_id for u in all_users.values() if u.org_id}
    org_names: dict[int, str] = {}
    if org_ids_in_use:
        org_rows = (await db.execute(
            select(Organization.id, Organization.name).where(Organization.id.in_(org_ids_in_use))
        )).all()
        org_names = {r.id: r.name for r in org_rows}

    out = []
    for shift, u in rows:
        point = last_points.get(u.id)
        out.append(OnShiftUserOut(
            user_id=u.id,
            full_name=u.full_name or u.username,
            org_id=u.org_id,
            org_name=org_names.get(u.org_id) if u.org_id else None,
            shift_started_at=shift.started_at,
            last_point=LocationPointOut.model_validate(point) if point else None,
            via_request=False,
        ))
    for uid, (point, u) in one_off_by_user.items():
        out.append(OnShiftUserOut(
            user_id=u.id,
            full_name=u.full_name or u.username,
            org_id=u.org_id,
            org_name=org_names.get(u.org_id) if u.org_id else None,
            shift_started_at=None,
            last_point=LocationPointOut.model_validate(point),
            via_request=True,
        ))
    out.sort(key=lambda r: (r.full_name or "").lower())
    return out


# ─────────────────────────── Трек за период ─────────────────────────────────

@router.get("/track/{user_id}", response_model=List[LocationPointOut])
async def get_track(
    user_id: int,
    date_from: Optional[datetime] = Query(None, description="Начало периода (ISO, включительно)"),
    date_to: Optional[datetime] = Query(None, description="Конец периода (ISO, включительно)"),
    limit: int = Query(2000, ge=1, le=10000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Трек одного сотрудника за период — для разбора происшествия.

    Собственный трек (user_id == self) доступен ВСЕГДА без права
    staff.location.view (задание п.6 — сотрудник видит, что о нём собрано).
    Чужой трек требует право + организационную границу.
    """
    if user_id == current_user.id:
        target = current_user
    else:
        target = await db.get(User, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        await _check_staff_visibility(target, current_user, db)

    q = select(StaffLocationPoint).where(StaffLocationPoint.user_id == user_id)
    if date_from:
        q = q.where(StaffLocationPoint.recorded_at >= _ensure_utc(date_from))
    if date_to:
        q = q.where(StaffLocationPoint.recorded_at <= _ensure_utc(date_to))
    q = q.order_by(StaffLocationPoint.recorded_at.asc()).limit(limit)

    points = (await db.execute(q)).scalars().all()
    return [LocationPointOut.model_validate(p) for p in points]
