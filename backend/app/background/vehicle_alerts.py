"""Phase 29 D-17 — ежедневное создание Task'ов за 30 дней до просрочки
(ОСАГО, ТО, ВУ/медсправка водителей и внешних водителей).

Перенесено 1:1 из app/__init__.py (_create_vehicle_alert_tasks,
_vehicle_alerts_task_creator) при разрезании монолитного файла на модули
(Правило №5). Логика не менялась.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.database import async_session


async def _create_vehicle_alert_tasks(db) -> None:
    """Phase 29 D-17 — создаёт Task'и за 30 дней до просрочки.
    Идемпотентность через system_tag '[VEHICLE:{id}:{TYPE}]'.
    """
    from datetime import timedelta
    from sqlalchemy import select
    from app.models.vehicle import Vehicle
    from app.models.user import User
    from app.models.external_driver import ExternalDriver
    from app.models.task import Task, TaskStatus

    log = logging.getLogger(__name__)

    # Resolve system user (admin id=1); fallback None (skip if missing)
    admin_user = await db.get(User, 1)
    if admin_user is None:
        log.warning("vehicle_alerts: admin user id=1 not found — skipping cycle")
        return
    SYSTEM_USER_ID = admin_user.id

    today = datetime.now(timezone.utc).date()
    threshold_30 = today + timedelta(days=30)
    lookback_7 = today - timedelta(days=7)

    OPEN_STATUSES = [TaskStatus.todo, TaskStatus.in_progress, TaskStatus.review]

    created_count = 0

    # ── 1. OSAGO expiry (30 дней) ─────────────────────────────────────────────
    vehicles_osago = (await db.execute(
        select(Vehicle).where(
            Vehicle.state.notin_(["destroyed", "utilized"]),
            Vehicle.insurance_until.isnot(None),
            Vehicle.insurance_until <= threshold_30,
            Vehicle.insurance_until > lookback_7,
        )
    )).scalars().all()
    for v in vehicles_osago:
        tag = f"[VEHICLE:{v.id}:OSAGO_EXPIRY]"
        exists = (await db.execute(
            select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
        )).scalar_one_or_none()
        if not exists:
            # Автоблок (2026-09): гос. номер необязателен — заголовок/описание задачи
            # не должны показывать "None", если у машины его нет (опознаём по VIN).
            _v_ident = v.plate or v.vin or f"ТС #{v.id}"
            db.add(Task(
                title=f"Продлить ОСАГО {_v_ident}",
                description=(
                    f"ОСАГО на {v.brand or ''} {v.model or ''} ({_v_ident}) "
                    f"истекает {v.insurance_until.isoformat()}"
                ),
                category="Автотранспорт",
                system_tag=tag,
                due_date=datetime(v.insurance_until.year, v.insurance_until.month, v.insurance_until.day, tzinfo=timezone.utc),
                status=TaskStatus.todo,
                created_by_id=SYSTEM_USER_ID,
                org_id=v.owner_org_id,
            ))
            created_count += 1

    # ── 2. ТО предупреждение (<1000 км до ТО) ────────────────────────────────
    vehicles_to = (await db.execute(
        select(Vehicle).where(
            Vehicle.state.notin_(["destroyed", "utilized"]),
            Vehicle.next_to_km.isnot(None),
            Vehicle.current_odometer_km.isnot(None),
            (Vehicle.next_to_km - Vehicle.current_odometer_km) < 1000,
            (Vehicle.next_to_km - Vehicle.current_odometer_km) > -10000,
        )
    )).scalars().all()
    for v in vehicles_to:
        tag = f"[VEHICLE:{v.id}:TO_SOON]"
        exists = (await db.execute(
            select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
        )).scalar_one_or_none()
        if not exists:
            km_left = (v.next_to_km or 0) - (v.current_odometer_km or 0)
            due = today + timedelta(days=14)
            _v_ident = v.plate or v.vin or f"ТС #{v.id}"
            db.add(Task(
                title=f"Пройти ТО {_v_ident}",
                description=(
                    f"ТО для {v.brand or ''} {v.model or ''} ({_v_ident}) "
                    f"через {km_left} км (next_to_km={v.next_to_km}, текущий пробег={v.current_odometer_km})"
                ),
                category="Автотранспорт",
                system_tag=tag,
                due_date=datetime(due.year, due.month, due.day, tzinfo=timezone.utc),
                status=TaskStatus.todo,
                created_by_id=SYSTEM_USER_ID,
                org_id=v.owner_org_id,
            ))
            created_count += 1

    # ── 3. Водители (User.can_drive=True) — ВУ и медсправка ─────────────────
    drivers = (await db.execute(
        select(User).where(User.can_drive == True)  # noqa: E712
    )).scalars().all()
    for u in drivers:
        # LICENSE_EXPIRY
        if (
            u.license_expires_at is not None
            and u.license_expires_at <= threshold_30
            and u.license_expires_at > lookback_7
        ):
            tag = f"[DRIVER:{u.id}:LICENSE_EXPIRY]"
            exists = (await db.execute(
                select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
            )).scalar_one_or_none()
            if not exists:
                due = u.license_expires_at
                db.add(Task(
                    title=f"Обновить ВУ — {u.full_name}",
                    description=(
                        f"ВУ водителя {u.full_name} истекает {due.isoformat()}"
                    ),
                    category="Автотранспорт",
                    system_tag=tag,
                    due_date=datetime(due.year, due.month, due.day, tzinfo=timezone.utc),
                    status=TaskStatus.todo,
                    created_by_id=SYSTEM_USER_ID,
                    assigned_user_id=u.id,
                ))
                created_count += 1

        # MED_CERT_EXPIRY
        if (
            u.medical_cert_expires_at is not None
            and u.medical_cert_expires_at <= threshold_30
            and u.medical_cert_expires_at > lookback_7
        ):
            tag = f"[DRIVER:{u.id}:MED_CERT_EXPIRY]"
            exists = (await db.execute(
                select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
            )).scalar_one_or_none()
            if not exists:
                due = u.medical_cert_expires_at
                db.add(Task(
                    title=f"Обновить медсправку — {u.full_name}",
                    description=(
                        f"Медсправка водителя {u.full_name} истекает {due.isoformat()}"
                    ),
                    category="Автотранспорт",
                    system_tag=tag,
                    due_date=datetime(due.year, due.month, due.day, tzinfo=timezone.utc),
                    status=TaskStatus.todo,
                    created_by_id=SYSTEM_USER_ID,
                    assigned_user_id=u.id,
                ))
                created_count += 1

    # ── 4. Внешние водители (ExternalDriver) — ВУ и медсправка ──────────────
    ext_drivers = (await db.execute(select(ExternalDriver))).scalars().all()
    for ed in ext_drivers:
        # LICENSE_EXPIRY
        if (
            ed.license_expires_at is not None
            and ed.license_expires_at <= threshold_30
            and ed.license_expires_at > lookback_7
        ):
            tag = f"[EXT_DRIVER:{ed.id}:LICENSE_EXPIRY]"
            exists = (await db.execute(
                select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
            )).scalar_one_or_none()
            if not exists:
                due = ed.license_expires_at
                name = getattr(ed, 'full_name', None) or f"ExternalDriver#{ed.id}"
                db.add(Task(
                    title=f"Обновить ВУ — {name}",
                    description=(
                        f"ВУ внешнего водителя {name} истекает {due.isoformat()}"
                    ),
                    category="Автотранспорт",
                    system_tag=tag,
                    due_date=datetime(due.year, due.month, due.day, tzinfo=timezone.utc),
                    status=TaskStatus.todo,
                    created_by_id=SYSTEM_USER_ID,
                ))
                created_count += 1

        # MED_CERT_EXPIRY
        if (
            getattr(ed, 'medical_cert_expires_at', None) is not None
            and ed.medical_cert_expires_at <= threshold_30
            and ed.medical_cert_expires_at > lookback_7
        ):
            tag = f"[EXT_DRIVER:{ed.id}:MED_CERT_EXPIRY]"
            exists = (await db.execute(
                select(Task).where(Task.system_tag == tag, Task.status.in_(OPEN_STATUSES))
            )).scalar_one_or_none()
            if not exists:
                due = ed.medical_cert_expires_at
                name = getattr(ed, 'full_name', None) or f"ExternalDriver#{ed.id}"
                db.add(Task(
                    title=f"Обновить медсправку — {name}",
                    description=(
                        f"Медсправка внешнего водителя {name} истекает {due.isoformat()}"
                    ),
                    category="Автотранспорт",
                    system_tag=tag,
                    due_date=datetime(due.year, due.month, due.day, tzinfo=timezone.utc),
                    status=TaskStatus.todo,
                    created_by_id=SYSTEM_USER_ID,
                ))
                created_count += 1

    await db.commit()
    log.info(
        "vehicle_alerts: created %d task(s) "
        "(vehicles_osago=%d, vehicles_to=%d, drivers=%d, ext_drivers=%d)",
        created_count,
        len(vehicles_osago), len(vehicles_to), len(drivers), len(ext_drivers),
    )


async def _vehicle_alerts_task_creator():
    """Phase 29 D-17 — создаёт Task'и за 30 дней до просрочки.
    Идемпотентность через system_tag '[VEHICLE:{id}:{TYPE}]'.
    Запускается раз в сутки в lifespan."""
    log = logging.getLogger(__name__)
    while True:
        try:
            async with async_session() as db:
                await _create_vehicle_alert_tasks(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("vehicle_alerts: cycle failed: %s", exc)
        await asyncio.sleep(86400)  # 24h
