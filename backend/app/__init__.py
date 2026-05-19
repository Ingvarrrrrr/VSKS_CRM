import asyncio
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .auth.jwt import get_current_user

from .routers import (
    auth, users, contractors, contracts, purchases, payments,
    feo_categories, dashboard, subsidies, products, purchase_files,
    documents, publications, subsidy_approvers, responsible_persons,
    commercial_requests, suppliers, purchase_events, user_hierarchy,
    system_incidents, organizations, reports, events, purchase_approvals,
    tasks, departments, delivery_addresses, hierarchy, billing,
    wishes, purchase_export, purchase_items_import, purchase_members,
    permissions as permissions_router,
    staff_directory,
)
from .routers import wish_documents
from .routers import user_addresses as user_addresses_router
from .routers import org_config
from .routers import purchase_transitions
from .routers import feo_planned_items
from .routers import telegram_webhook
from .routers import settings as settings_router
from .routers import chat as chat_router
from .routers import push as push_router
from .routers import purchase_receipts
from .routers import install as install_router
from .routers import analytics as analytics_router
from .routers import report_configs as report_configs_router
from .routers import vehicles_dashboard, vehicles, vehicle_attachments, repair_attachments
from .routers import vehicle_repairs, vehicle_odometer, fuel_logs, trips
from .routers import external_drivers
from .routers import vehicles_import as vehicles_import_router
from .models import platform_publication  # ensure table is registered
from .models import subsidy_allocation    # ensure purchase_subsidy_allocations table is created
from .models import contract_subsidy      # ensure contract_subsidies table is created
from .models import org_section_config    # ensure org_section_configs table is created
from .models.task import TaskAssignee, TelegramMessageMap  # ensure tables created
from .models.task_decline import TaskConsentDecline  # ensure task_consent_declines table is created
from .models.manager_department import ManagerDepartment  # ensure manager_departments table is created
from .models.org_billing import OrgBillingPaid  # ensure org_billing_paid table is created
from .models.purchase_comment import PurchaseComment  # ensure purchase_comments table is created
from .models import bank_statement  # ensure bank_statement_imports / bank_payments tables registered
from .routers.documents import guide_router as documents_guide_router
from .database import async_session


async def _deadline_reminder_loop():
    """Ежедневно в 09:00 UTC шлёт напоминания о задачах и закупках."""
    import logging
    from sqlalchemy import select
    from .models.task import Task, TaskAssignee, TaskStatus
    from .models.user import User
    from .models.purchase import Purchase
    from .models.purchase_event import PurchaseMember
    from .models.purchase_approval import PurchaseApproval
    from .notifications import notify_deadline_soon, notify_purchase_deadline

    log = logging.getLogger(__name__)
    while True:
        try:
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= next_run:
                from datetime import timedelta
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())

            async with async_session() as db:
                today = datetime.now(timezone.utc).date()

                # ── 1. Task deadlines (0, 1, 3 дня) ──
                result = await db.execute(
                    select(Task).where(
                        Task.status.in_([TaskStatus.todo, TaskStatus.in_progress]),
                        Task.due_date.isnot(None),
                    )
                )
                for task in result.scalars().all():
                    due_date = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
                    days_left = (due_date - today).days
                    if days_left not in (0, 1, 3):
                        continue
                    assignees_result = await db.execute(
                        select(TaskAssignee).where(
                            TaskAssignee.task_id == task.id,
                            TaskAssignee.consent_pending == False,  # noqa: E712
                        )
                    )
                    for ta in assignees_result.scalars().all():
                        user = await db.get(User, ta.user_id)
                        if user:
                            await notify_deadline_soon(task, user, days_left)

                # ── 2. Purchase execution_term deadlines (0, 1, 3 дня) ──
                active_statuses = ("confirmed", "work_in_progress", "contracted")
                purch_result = await db.execute(
                    select(Purchase).where(
                        Purchase.status.in_(active_statuses),
                        Purchase.execution_term.isnot(None),
                    )
                )
                for p in purch_result.scalars().all():
                    days_left = (p.execution_term - today).days
                    if days_left not in (0, 1, 3, -1, -3):
                        continue
                    # Notify assigned user + members
                    notified = set()
                    if p.assigned_user_id:
                        u = await db.get(User, p.assigned_user_id)
                        if u:
                            await notify_purchase_deadline(p, u, days_left, "execution_term")
                            notified.add(p.assigned_user_id)
                    members = (await db.execute(
                        select(PurchaseMember).where(PurchaseMember.purchase_id == p.id)
                    )).scalars().all()
                    for m in members:
                        if m.user_id not in notified:
                            u = await db.get(User, m.user_id)
                            if u:
                                await notify_purchase_deadline(p, u, days_left, "execution_term")

                # ── 3. Payment overdue: delivered >5 days ago, not paid ──
                delivered_result = await db.execute(
                    select(Purchase).where(
                        Purchase.status == "delivered",
                        Purchase.delivery_date.isnot(None),
                    )
                )
                for p in delivered_result.scalars().all():
                    days_since = (today - p.delivery_date).days
                    if days_since < 5 or days_since % 5 != 0:  # remind every 5 days
                        continue
                    notified = set()
                    if p.assigned_user_id:
                        u = await db.get(User, p.assigned_user_id)
                        if u:
                            await notify_purchase_deadline(p, u, days_since, "payment_overdue")
                            notified.add(p.assigned_user_id)
                    members = (await db.execute(
                        select(PurchaseMember).where(PurchaseMember.purchase_id == p.id)
                    )).scalars().all()
                    for m in members:
                        if m.user_id not in notified:
                            u = await db.get(User, m.user_id)
                            if u:
                                await notify_purchase_deadline(p, u, days_since, "payment_overdue")

                # ── 4. Approval deadline overdue ──
                overdue_approvals = (await db.execute(
                    select(PurchaseApproval).where(
                        PurchaseApproval.status == "pending",
                        PurchaseApproval.approval_deadline.isnot(None),
                        PurchaseApproval.approval_deadline < today,
                    )
                )).scalars().all()
                for appr in overdue_approvals:
                    days_overdue = (today - appr.approval_deadline).days
                    if days_overdue not in (1, 3, 7):  # remind at 1, 3, 7 days overdue
                        continue
                    if appr.user_id:
                        u = await db.get(User, appr.user_id)
                        p = await db.get(Purchase, appr.purchase_id)
                        if u and p:
                            await notify_purchase_deadline(p, u, days_overdue, "approval_overdue")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).warning(f"Deadline reminder error: {e}")
            await asyncio.sleep(3600)


async def _create_vehicle_alert_tasks(db) -> None:
    """Phase 29 D-17 — создаёт Task'и за 30 дней до просрочки.
    Идемпотентность через system_tag '[VEHICLE:{id}:{TYPE}]'.
    """
    import logging
    from datetime import timedelta
    from sqlalchemy import select
    from .models.vehicle import Vehicle
    from .models.user import User
    from .models.external_driver import ExternalDriver
    from .models.task import Task, TaskStatus

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
            db.add(Task(
                title=f"Продлить ОСАГО {v.plate}",
                description=(
                    f"ОСАГО на {v.brand or ''} {v.model or ''} ({v.plate}) "
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
            db.add(Task(
                title=f"Пройти ТО {v.plate}",
                description=(
                    f"ТО для {v.brand or ''} {v.model or ''} ({v.plate}) "
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
    import logging
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


@asynccontextmanager
async def lifespan(app_: FastAPI):
    task = asyncio.create_task(_deadline_reminder_loop())
    # Phase 29 D-17: daily vehicle expiry alerts
    try:
        task_vehicle_alerts = asyncio.create_task(_vehicle_alerts_task_creator())
    except Exception as _e_va:
        import logging as _lg_va
        _lg_va.getLogger(__name__).warning(f"vehicle_alerts task start skipped (non-fatal): {_e_va}")
        task_vehicle_alerts = None
    # Start Telegram bot polling for reply-to-comment routing
    from .routers.telegram_webhook import start_polling as _start_tg_polling
    _start_tg_polling()

    # Phase 22: idempotent ALTER для subsidies — добавить basis_doc_number/date
    from .database import ensure_phase22_columns as _ensure_p22
    await _ensure_p22()

    # Phase 22: idempotent ALTER для bank_payments — заменить старый UniqueConstraint на source_row_hash
    try:
        from sqlalchemy import text
        from .database import engine
        async with engine.begin() as conn:
            # Дропаем старый natural-key UniqueConstraint (если есть на проде из старых ревертов)
            await conn.execute(text("ALTER TABLE bank_payments DROP CONSTRAINT IF EXISTS uq_bank_payment_natural"))
            # Добавляем колонку source_row_hash если не существует
            await conn.execute(text("ALTER TABLE bank_payments ADD COLUMN IF NOT EXISTS source_row_hash VARCHAR(64)"))
            # Создаём partial unique index (WHERE IS NOT NULL — legacy NULL записи не дедуплицируются)
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_bank_payment_source_row_hash "
                "ON bank_payments (source_row_hash) WHERE source_row_hash IS NOT NULL"
            ))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 22 hash migration skipped (non-fatal): {e}")

    # Phase 22: backfill source_row_hash для legacy записей + удаление дубликатов
    try:
        from sqlalchemy import select as _sel, text as _text
        from .models.bank_statement import BankPayment
        from .services.bank_statement_parser import compute_row_hash

        async with async_session() as db:
            # 1. Заполнить hash для legacy записей с NULL
            q = await db.execute(_sel(BankPayment).where(BankPayment.source_row_hash.is_(None)))
            legacy = q.scalars().all()
            backfilled = 0
            for bp in legacy:
                if bp.raw_json:
                    try:
                        bp.source_row_hash = compute_row_hash(bp.raw_json)
                        backfilled += 1
                    except Exception:
                        pass
            if backfilled:
                await db.commit()

            # 2. Удалить дубликаты — оставляем MIN(id) на каждый hash
            await db.execute(_text("""
                DELETE FROM bank_payments
                WHERE id NOT IN (
                    SELECT MIN(id) FROM bank_payments
                    WHERE source_row_hash IS NOT NULL
                    GROUP BY source_row_hash
                )
                AND source_row_hash IS NOT NULL
            """))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 22 hash backfill skipped (non-fatal): {e}")

    # Phase 22: idempotent seed для tab payment_registry + 3 actions
    try:
        from sqlalchemy import select as _sel
        from .models.permission import PermissionTab, PermissionAction, RolePermission
        async with async_session() as db:
            # 1. Tab
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'payment_registry'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='payment_registry', title='Реестр платежей'))
            # 2. Actions
            for action_key, description in [
                ('payment.import', 'Импорт банковских выписок'),
                ('payment.confirm', 'Подтверждение матча платежа'),
                ('payment.unbind', 'Откат подтверждения платежа'),
            ]:
                ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == action_key))
                if not ex.scalar_one_or_none():
                    db.add(PermissionAction(action_key=action_key, description=description))
            await db.commit()
            # 3. Role permissions (granted=True)
            # tab payment_registry — все 5 ролей (superadmin/admin/org_admin/manager/employee)
            # action payment.import — admin, manager, superadmin
            # action payment.confirm — admin, manager, org_admin, superadmin
            # action payment.unbind — admin, superadmin
            ROLE_PERMS = [
                ('superadmin', 'payment_registry'), ('admin', 'payment_registry'),
                ('org_admin', 'payment_registry'), ('manager', 'payment_registry'),
                ('employee', 'payment_registry'),
                ('superadmin', 'payment.import'), ('admin', 'payment.import'), ('manager', 'payment.import'),
                ('superadmin', 'payment.confirm'), ('admin', 'payment.confirm'),
                ('manager', 'payment.confirm'), ('org_admin', 'payment.confirm'),
                ('superadmin', 'payment.unbind'), ('admin', 'payment.unbind'),
            ]
            for role_name, key in ROLE_PERMS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == key,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=key, granted=True))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 22 permission seed skipped (non-fatal): {e}")

    # Phase 29: vehicles tab + 6 actions (idempotent permission seed)
    try:
        from sqlalchemy import select as _sel29
        from .models.permission import PermissionTab as _PT29, PermissionAction as _PA29, RolePermission as _RP29
        async with async_session() as db:
            # 1. Tab
            ex = await db.execute(_sel29(_PT29).where(_PT29.tab_key == 'vehicles'))
            if not ex.scalar_one_or_none():
                db.add(_PT29(tab_key='vehicles', title='Имущество'))
            await db.commit()
            # 2. Actions
            for _ak29, _desc29 in [
                ('vehicle.edit',           'Редактирование карточки ТС'),
                ('vehicle.delete',         'Удаление ТС'),
                ('vehicle.import',         'Импорт Excel реестра ТС'),
                ('vehicle.odometer.write', 'Ввод пробега'),
                ('vehicle.repair.write',   'Добавление ремонтов'),
                ('vehicle.trip.create',    'Создание путевых листов'),
            ]:
                ex = await db.execute(_sel29(_PA29).where(_PA29.action_key == _ak29))
                if not ex.scalar_one_or_none():
                    db.add(_PA29(action_key=_ak29, description=_desc29))
            await db.commit()
            # 3. Role defaults
            # (key, role_name, granted)
            # viewer role — tab visibility only, no actions
            _ROLE_PERMS_29 = [
                # tab visibility: superadmin/account_owner/admin/org_admin/manager/employee/viewer
                *[('vehicles', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee', 'viewer']],
                # vehicle.edit: admin+ yes; manager yes; employee explicit no
                *[('vehicle.edit', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.edit', 'employee', False),
                # vehicle.delete: admin+ only
                *[('vehicle.delete', r, True) for r in ['superadmin', 'account_owner', 'admin']],
                *[('vehicle.delete', r, False) for r in ['org_admin', 'manager', 'employee']],
                # vehicle.import: admin/org_admin yes; manager/employee explicit no
                *[('vehicle.import', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin']],
                *[('vehicle.import', r, False) for r in ['manager', 'employee']],
                # vehicle.odometer.write: all active roles yes
                *[('vehicle.odometer.write', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee']],
                # vehicle.repair.write: admin/manager yes; employee explicit no
                *[('vehicle.repair.write', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.repair.write', 'employee', False),
                # vehicle.trip.create: admin/manager yes; employee explicit no
                *[('vehicle.trip.create', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.trip.create', 'employee', False),
            ]
            for _key29, _role29, _granted29 in _ROLE_PERMS_29:
                ex = await db.execute(_sel29(_RP29).where(
                    _RP29.role_name == _role29,
                    _RP29.key == _key29,
                ))
                if not ex.scalar_one_or_none():
                    db.add(_RP29(role_name=_role29, key=_key29, granted=_granted29))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 29 permission seed skipped (non-fatal): {e}")

    # Phase 26-QQ: idempotent dedup контрагентов по ИНН + UNIQUE constraint.
    # Объединяет дубли (одинаковый INN), перевешивает FK на keep_id (MIN id),
    # удаляет дубли. Затем создаёт partial unique index чтобы новые дубли не появлялись.
    try:
        from sqlalchemy import text as _text
        from .database import engine as _engine
        async with _engine.begin() as conn:
            # 1. Find duplicate groups
            groups = (await conn.execute(_text("""
                SELECT TRIM(inn) AS norm_inn, ARRAY_AGG(id ORDER BY id) AS ids, COUNT(*) AS n
                FROM contractors
                WHERE inn IS NOT NULL AND TRIM(inn) != ''
                GROUP BY TRIM(inn)
                HAVING COUNT(*) > 1
            """))).all()

            if len(groups) > 200:
                import logging
                logging.getLogger(__name__).warning(
                    f"Phase 26-QQ contractor dedup: {len(groups)} duplicate groups — too many, skip auto-merge"
                )
            elif groups:
                # FK columns referencing contractors.id (вычислено grep'ом моделей)
                FK_TABLES = [
                    ("bank_payments", "matched_contractor_id"),
                    ("commercial_requests", "contractor_id"),
                    ("contracts", "contractor_id"),
                    ("organizations", "contractor_id"),
                    ("purchases", "contractor_id"),
                    ("purchase_items", "contractor_id"),
                    ("subsidies", "contractor_id"),
                    ("subsidy_contractor_overrides", "contractor_id"),
                ]
                total_merged = 0
                for row in groups:
                    norm_inn, ids, n = row.norm_inn, list(row.ids), row.n
                    keep_id = ids[0]
                    dup_ids = ids[1:]
                    # Rewire FK для каждой dup-таблицы
                    for tbl, col in FK_TABLES:
                        try:
                            await conn.execute(_text(
                                f"UPDATE {tbl} SET {col} = :keep WHERE {col} = ANY(:dups)"
                            ), {"keep": keep_id, "dups": dup_ids})
                        except Exception as inner_e:
                            import logging
                            logging.getLogger(__name__).warning(
                                f"Phase 26-QQ rewire {tbl}.{col} failed (table may not exist): {inner_e}"
                            )
                    # Merge пустых полей в keep (берём заполнения из дублей)
                    await conn.execute(_text("""
                        UPDATE contractors keep SET
                            name = COALESCE(NULLIF(keep.name, ''), dup.name),
                            kpp = COALESCE(NULLIF(keep.kpp, ''), dup.kpp),
                            ogrn = COALESCE(NULLIF(keep.ogrn, ''), dup.ogrn),
                            address = COALESCE(NULLIF(keep.address, ''), dup.address),
                            phone = COALESCE(NULLIF(keep.phone, ''), dup.phone),
                            email = COALESCE(NULLIF(keep.email, ''), dup.email),
                            signatory = COALESCE(NULLIF(keep.signatory, ''), dup.signatory)
                        FROM contractors dup
                        WHERE keep.id = :keep AND dup.id = ANY(:dups)
                    """), {"keep": keep_id, "dups": dup_ids})
                    # Удалить дубли
                    await conn.execute(_text(
                        "DELETE FROM contractors WHERE id = ANY(:dups)"
                    ), {"dups": dup_ids})
                    total_merged += len(dup_ids)
                import logging
                logging.getLogger(__name__).info(
                    f"Phase 26-QQ dedup: merged {total_merged} duplicate contractors across {len(groups)} INN groups"
                )

            # 2. Partial unique index — предотвращает новые дубли при race condition.
            #    Phase 26-OO defense in create_contractor — это второй уровень защиты.
            await conn.execute(_text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_contractors_inn_unique
                ON contractors (TRIM(inn))
                WHERE inn IS NOT NULL AND TRIM(inn) != ''
            """))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 26-QQ contractor dedup skipped (non-fatal): {e}")

    # Phase 26-DD: FK contract_items.source_item_id → SET NULL ON DELETE.
    # Раньше RESTRICT — update_purchase delete-then-insert ломал FK от contract_items,
    # которые ссылались на старые purchase_items.
    try:
        from sqlalchemy import text as _text
        from .database import engine as _engine
        async with _engine.begin() as conn:
            await conn.execute(_text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.referential_constraints
                        WHERE constraint_name = 'contract_items_source_item_id_fkey'
                          AND delete_rule != 'SET NULL'
                    ) THEN
                        ALTER TABLE contract_items
                            DROP CONSTRAINT contract_items_source_item_id_fkey;
                        ALTER TABLE contract_items
                            ADD CONSTRAINT contract_items_source_item_id_fkey
                            FOREIGN KEY (source_item_id) REFERENCES purchase_items(id)
                            ON DELETE SET NULL;
                    END IF;
                END $$;
            """))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 26-DD FK ALTER skipped (non-fatal): {e}")

    # Phase 28 → Phase 26-Y: idempotent seed для action 'documents.view_all_in_org'
    # (без него руководители без отдела не видят документы своей org → Цыганов кейс).
    try:
        from sqlalchemy import select as _sel
        from .models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'documents.view_all_in_org'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Видеть все документы организации без фильтра по ответственному исполнителю',
                ))
                await db.commit()
            # Role defaults — true для SaaS+admin+org_admin, false для manager/employee
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', True), ('org_admin', True),
                ('manager', False), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 26-Y view_all action seed skipped (non-fatal): {e}")

    # Phase 26-Q: idempotent seed для нового tab advance_reports.create
    # (отделяем «создание авансового отчёта» от «реестра авансовых отчётов»)
    try:
        from sqlalchemy import select as _sel
        from .models.permission import PermissionTab, RolePermission
        async with async_session() as db:
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'advance_reports.create'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='advance_reports.create', title='Авансовый отчёт (создание)'))
                await db.commit()
            # Role permissions: разрешено всем ролям, кому был разрешён advance_reports
            ALL_ADV_ROLES = ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee']
            for role_name in ALL_ADV_ROLES:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == 'advance_reports.create',
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key='advance_reports.create', granted=True))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 26-Q permission seed skipped (non-fatal): {e}")

    # Phase 27.4-10: idempotent seed для action 'purchase.status_change'
    # Дефолт: admin/manager/account_owner/superadmin=TRUE; employee=FALSE.
    # Управляет возможностью двигать статусы закупок в Канбане и через /transition.
    try:
        from sqlalchemy import select as _sel
        from .models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'purchase.status_change'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Изменение статуса закупки',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', True), ('org_admin', True),
                ('manager', True), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 27.4-10 purchase.status_change seed skipped (non-fatal): {e}")

    # Phase 18: idempotent seed для tab 'staff_directory' (all 5 roles)
    try:
        from sqlalchemy import select as _sel
        from .models.permission import PermissionTab, RolePermission
        async with async_session() as db:
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'staff_directory'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='staff_directory', title='Справочник сотрудников'))
                await db.commit()
            ALL_SD_ROLES = ['superadmin', 'admin', 'org_admin', 'manager', 'employee']
            for role_name in ALL_SD_ROLES:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == 'staff_directory',
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key='staff_directory', granted=True))
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Phase 18 staff_directory tab seed skipped (non-fatal): {e}")

    # Phase 22 RESTORE: backfill typed-fields для legacy bank_payments c payment_date IS NULL
    # Идемпотентно — skip если все строки уже типизированы. Запускается на каждом старте.
    try:
        from sqlalchemy import select as _sel, func as _func
        from .models.bank_statement import BankPayment
        from .services.bank_statement_parser import reparse_bank_payment_typed
        async with async_session() as db:
            null_count = (await db.execute(
                _sel(_func.count()).select_from(BankPayment).where(BankPayment.payment_date.is_(None))
            )).scalar() or 0
            if null_count > 0:
                q = await db.execute(_sel(BankPayment).where(BankPayment.payment_date.is_(None)))
                rows = q.scalars().all()
                fixed = 0
                for bp in rows:
                    if not bp.raw_json:
                        continue
                    reparse_bank_payment_typed(bp)
                    if bp.payment_date is not None or bp.purpose_text is not None:
                        fixed += 1
                if fixed:
                    await db.commit()
                import logging as _lg
                _lg.getLogger(__name__).info(
                    f"Phase 22 backfill: {fixed}/{null_count} bank_payments re-typed from raw_json"
                )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 22 bank_payments backfill skipped (non-fatal): {e}")

    # Phase 27.1: contract_items table + idempotent backfill (non-fatal pattern из Phase 22)
    try:
        from check_schema import _ensure_contract_items_table, _backfill_contract_items_from_purchase_items
        from .database import engine as _engine
        async with _engine.begin() as conn:
            await _ensure_contract_items_table(conn)
            backfilled = await _backfill_contract_items_from_purchase_items(conn)
            if backfilled:
                import logging as _lg
                _lg.getLogger(__name__).info(
                    f"Phase 27.1 backfill: {backfilled} contract_items inserted from legacy purchase_items"
                )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            f"Phase 27.1 contract_items setup skipped (non-fatal): {e}"
        )

    # Phase 26-BB: purchase_items.receipt_id column + FK
    try:
        from check_schema import _ensure_purchase_items_receipt_id
        from .database import engine as _engine
        async with _engine.begin() as conn:
            await _ensure_purchase_items_receipt_id(conn)
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-BB receipt_id column setup skipped (non-fatal): {e}")

    # Phase 26-mmm: sync denorm-полей purchases ← contracts при старте.
    # Чинит исторические рассинхронизации (contract_number/date/contractor_id
    # из соседних контрактов после ручных правок до Phase 26-j-1, когда
    # _sync_purchase_from_contract либо не вызывался, либо не копировал
    # contractor_id — это явно наблюдалось в проде: purchase #802 имел
    # contract_number='51802 ОП/КОР' но contract_date='27.05.2021' от
    # соседнего договора 110677/КОР, в реестре «Контрагент» = пусто).
    # Идемпотентно: вызывает _sync_purchase_from_contract который перезаписывает
    # только если значения отличаются от contract.*. Non-fatal (Phase 22 pattern).
    try:
        from sqlalchemy import select as _sel
        from .database import async_session as _async_session
        from .models.purchase import Purchase as _Purchase
        from .routers.purchases import _sync_purchase_from_contract as _sync_pc
        async with _async_session() as _db:
            _rows = (await _db.execute(
                _sel(_Purchase).where(_Purchase.contract_id.is_not(None))
            )).scalars().all()
            _updated = 0
            for _p in _rows:
                _before = (_p.contract_number, _p.contract_date, _p.purchase_contract_type, _p.contractor_id)
                await _sync_pc(_p, _db)
                _after = (_p.contract_number, _p.contract_date, _p.purchase_contract_type, _p.contractor_id)
                if _before != _after:
                    _updated += 1
            if _updated:
                await _db.commit()
            import logging as _lg
            _lg.getLogger(__name__).info(
                f"Phase 26-mmm backfill: {_updated}/{len(_rows)} purchases sync'нуты из contracts"
            )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            f"Phase 26-mmm purchase←contract sync skipped (non-fatal): {e}"
        )

    # Phase 26-ooo: дедуп existing acceptance_docs[] от исторических дублей.
    # Видимый симптом: «Документ 1: Чек 83287 5034» + «Документ 2: Чек 83287 5034»
    # одно и то же. Источник: legacy записи без receipt_id + auto-add с
    # receipt_id давали 2 строки на один чек. Phase 26-ooo backend-фикс
    # усилил дедуп при auto-add, но исторические дубли уже в БД.
    # Идемпотентно: убирает дубли по ключу (type, number, amount).
    try:
        from sqlalchemy import select as _sel
        from sqlalchemy.orm.attributes import flag_modified as _flag_mod
        from .database import async_session as _async_session
        from .models.purchase import Purchase as _Purchase
        async with _async_session() as _db:
            _q = await _db.execute(
                _sel(_Purchase).where(_Purchase.acceptance_docs.is_not(None))
            )
            _purchases = _q.scalars().all()
            _dedup_total = 0
            for _p in _purchases:
                _docs = list(_p.acceptance_docs or [])
                if len(_docs) <= 1:
                    continue
                _seen = set()
                _kept = []
                for _d in _docs:
                    _key = (
                        _d.get("type") or "",
                        str(_d.get("number") or ""),
                        round(float(_d.get("amount") or 0), 2),
                    )
                    if _key in _seen and _key[1] != "":
                        # дубликат — пропускаем, но если у дубля есть file_id
                        # и в kept[i] нет — переносим
                        if _d.get("file_id"):
                            for _k in _kept:
                                _kk = (
                                    _k.get("type") or "",
                                    str(_k.get("number") or ""),
                                    round(float(_k.get("amount") or 0), 2),
                                )
                                if _kk == _key and not _k.get("file_id"):
                                    _k["file_id"] = _d.get("file_id")
                                    break
                        continue
                    _seen.add(_key)
                    _kept.append(_d)
                if len(_kept) != len(_docs):
                    _p.acceptance_docs = _kept
                    _flag_mod(_p, "acceptance_docs")
                    _dedup_total += len(_docs) - len(_kept)
            if _dedup_total:
                await _db.commit()
            import logging as _lg
            _lg.getLogger(__name__).info(
                f"Phase 26-ooo acceptance_docs dedup: removed {_dedup_total} duplicates across {len(_purchases)} purchases"
            )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            f"Phase 26-ooo acceptance_docs dedup skipped (non-fatal): {e}"
        )

    # Phase 24 RESTORE: backfill contract_date/number для advance purchases
    # с receipts но без основания. Идемпотентно — skip если 0 строк нуждаются.
    try:
        from sqlalchemy import select as _sel, or_
        from .models.purchase import Purchase as _Purchase
        from .models.purchase_receipt import PurchaseReceipt as _PurchaseReceipt
        async with async_session() as db:
            q = await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    or_(_Purchase.contract_date.is_(None), _Purchase.contract_number.is_(None))
                )
            )
            advances = q.scalars().all()
            fixed = 0
            for p in advances:
                rq = await db.execute(
                    _sel(_PurchaseReceipt)
                    .where(_PurchaseReceipt.purchase_id == p.id)
                    .order_by(_PurchaseReceipt.receipt_datetime.asc())
                    .limit(1)
                )
                receipt = rq.scalar_one_or_none()
                if not receipt:
                    continue
                changed = False
                if receipt.receipt_datetime and not p.contract_date:
                    rd = receipt.receipt_datetime
                    p.contract_date = rd.date() if hasattr(rd, 'date') else rd
                    changed = True
                if receipt.fiscal_document_number and not p.contract_number:
                    p.contract_number = str(receipt.fiscal_document_number)
                    changed = True
                if changed:
                    fixed += 1
            if fixed:
                await db.commit()
                import logging as _lg
                _lg.getLogger(__name__).info(
                    f"Phase 24 backfill: {fixed} advance purchases получили contract_date/number из receipts"
                )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 24 advance backfill skipped (non-fatal): {e}")

    # Phase 26-U-3: idempotent ALTER для purchase_items.vat_rate + purchases.vat_mode
    try:
        from sqlalchemy import text as _text2
        from .database import engine as _engine2
        async with _engine2.begin() as conn:
            await conn.execute(_text2(
                "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS vat_rate VARCHAR(20)"
            ))
            await conn.execute(_text2(
                "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS vat_mode VARCHAR(20) DEFAULT 'uniform'"
            ))
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-U-3 vat columns skipped (non-fatal): {e}")

    # Phase 26-YY: idempotent ALTER — purchases.recompute_snapshot_hash (SHA-1 гейт
    # auto-recompute из purchase_receipts._recompute_from_receipts_core).
    try:
        from sqlalchemy import text as _text3
        from .database import engine as _engine3
        async with _engine3.begin() as conn:
            await conn.execute(_text3(
                "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS recompute_snapshot_hash VARCHAR(64)"
            ))
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-YY snapshot_hash column skipped (non-fatal): {e}")

    # Phase 26-BBB: backfill purchases.registry_number для записей без него.
    # Формат «РЕЕ-{year}-{id:05d}» — тот же что и для новых (purchases.py auto-gen,
    # ~стр. 590-592). В модели Purchase нет created_at → year берётся из NOW().
    try:
        from sqlalchemy import text as _text_bbb
        from .database import engine as _engine_bbb
        async with _engine_bbb.begin() as conn:
            await conn.execute(_text_bbb("""
                UPDATE purchases
                SET registry_number = 'РЕЕ-' || EXTRACT(YEAR FROM NOW())::int || '-' || LPAD(id::text, 5, '0')
                WHERE registry_number IS NULL OR registry_number = ''
            """))
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-BBB registry_number backfill skipped (non-fatal): {e}")

    # Phase 26-CC: propagate purchase.contractor_id → items.contractor_id для advance.
    # Если на уровне закупки контрагент проставлен вручную, items без contractor_id
    # должны его наследовать. Самый дешёвый backfill — без чтения raw_json.
    try:
        from sqlalchemy import select as _sel
        from .models.purchase import Purchase as _Purchase
        from .models.purchase_item import PurchaseItem as _PI
        from .models.contractor import Contractor as _Ctr
        async with async_session() as db:
            advances_with_c = (await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    _Purchase.contractor_id.is_not(None),
                )
            )).scalars().all()
            propagated_total = 0
            for p in advances_with_c:
                c_row = await db.get(_Ctr, p.contractor_id)
                if not c_row:
                    continue
                null_items = (await db.execute(
                    _sel(_PI).where(
                        _PI.purchase_id == p.id,
                        _PI.contractor_id.is_(None),
                    )
                )).scalars().all()
                for it in null_items:
                    it.contractor_id = c_row.id
                    it.contractor_inn = c_row.inn
                    it.contractor_name = c_row.name
                    propagated_total += 1
            if propagated_total:
                await db.commit()
                import logging as _lg
                _lg.getLogger(__name__).info(f"Phase 26-CC propagated: {propagated_total} items inherited contractor from purchase")
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-CC propagate skipped (non-fatal): {e}")

    # Phase 26-BB: per-receipt привязка через fuzzy match по 4 полям
    # (name + quantity + unit_price + total_price)
    try:
        from sqlalchemy import select as _sel
        from .models.purchase import Purchase as _Purchase
        from .models.purchase_item import PurchaseItem as _PI
        from .models.purchase_receipt import PurchaseReceipt as _PR
        from .models.contractor import Contractor as _Ctr
        from app.routers.purchase_receipts import _items_match_score as _fuzzy
        from app.routers.purchase_receipts import _extract_items as _ext_items
        async with async_session() as db:
            advances = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            linked_total = 0
            for (pid,) in advances:
                unlinked = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.receipt_id.is_(None))
                )).scalars().all()
                if not unlinked:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid)
                )).scalars().all()
                if not receipts:
                    continue
                for it in unlinked:
                    best_r = None
                    best_score = 0
                    for r in receipts:
                        items_list = _ext_items(r.raw_json or {})
                        for ri in items_list:
                            s = _fuzzy(it, ri)
                            if s >= 2 and s > best_score:
                                best_score = s
                                best_r = r
                    if best_r:
                        it.receipt_id = best_r.id
                        if best_r.seller_inn:
                            c_row = (await db.execute(
                                _sel(_Ctr).where(_Ctr.inn == best_r.seller_inn)
                            )).scalar_one_or_none()
                            if not c_row:
                                c_row = _Ctr(inn=best_r.seller_inn, name=best_r.seller_name or f"ИНН {best_r.seller_inn}")
                                db.add(c_row)
                                await db.flush()
                            it.contractor_id = c_row.id
                            it.contractor_inn = best_r.seller_inn
                            it.contractor_name = best_r.seller_name
                        linked_total += 1
            if linked_total:
                await db.commit()
                import logging as _lg
                _lg.getLogger(__name__).info(f"Phase 26-BB backfill: {linked_total} purchase_items linked to receipts via fuzzy")
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-BB backfill skipped (non-fatal): {e}")

    # Phase 26-W: backfill PurchaseItem.contractor_id для авансовых закупок,
    # где контрагент создан из чека, но item.contractor_id остался NULL
    # (deploy до Phase 26-V не заполнял contractor_id из seller_inn чека).
    try:
        from sqlalchemy import select as _sel, update as _upd
        from .models.purchase import Purchase as _Purchase
        from .models.purchase_item import PurchaseItem as _PI
        from .models.purchase_receipt import PurchaseReceipt as _PR
        from .models.contractor import Contractor as _Ctr
        async with async_session() as db:
            # Находим все advance-закупки с item.contractor_id IS NULL
            q = await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )
            advance_ids = [row[0] for row in q.all()]
            backfilled = 0
            for pid in advance_ids:
                # Получаем seller_inn из первого по дате PurchaseReceipt
                rq = await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc()).limit(1)
                )
                receipt = rq.scalar_one_or_none()
                if not receipt or not receipt.seller_inn:
                    continue
                # Resolve contractor по ИНН (или создаём)
                cq = await db.execute(
                    _sel(_Ctr).where(_Ctr.inn == receipt.seller_inn)
                )
                contractor = cq.scalar_one_or_none()
                if not contractor:
                    contractor = _Ctr(
                        inn=receipt.seller_inn,
                        name=receipt.seller_name or f"ИНН {receipt.seller_inn}",
                    )
                    db.add(contractor)
                    await db.flush()
                # Update PurchaseItem (only NULL ones)
                res = await db.execute(
                    _upd(_PI).where(
                        _PI.purchase_id == pid,
                        _PI.contractor_id.is_(None),
                    ).values(
                        contractor_id=contractor.id,
                        contractor_inn=receipt.seller_inn,
                        contractor_name=receipt.seller_name,
                    )
                )
                backfilled += res.rowcount or 0
            if backfilled:
                await db.commit()
                import logging as _lg
                _lg.getLogger(__name__).info(
                    f"Phase 26-W backfill: {backfilled} purchase_items got contractor_id from receipts"
                )
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"Phase 26-W backfill skipped (non-fatal): {e}")

    # Phase 29: vehicles fleet tables + ALTER purchases/users/tasks
    try:
        from check_schema import (
            _ensure_external_drivers_table, _ensure_vehicles_table,
            _ensure_vehicle_attachments_table, _ensure_vehicle_repairs_table,
            _ensure_repair_attachments_table, _ensure_vehicle_field_history_table,
            _ensure_vehicle_odometer_table, _ensure_fuel_logs_table,
            _ensure_trips_table, _ensure_purchases_vehicle_id,
            _ensure_users_driver_columns, _ensure_tasks_system_tag,
        )
        from .database import engine as _engine_p29
        async with _engine_p29.begin() as conn:
            for fn in [
                _ensure_external_drivers_table, _ensure_vehicles_table,
                _ensure_vehicle_attachments_table, _ensure_vehicle_repairs_table,
                _ensure_repair_attachments_table, _ensure_vehicle_field_history_table,
                _ensure_vehicle_odometer_table, _ensure_fuel_logs_table,
                _ensure_trips_table, _ensure_purchases_vehicle_id,
                _ensure_users_driver_columns, _ensure_tasks_system_tag,
            ]:
                try:
                    await fn(conn)
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"Phase 29 schema {fn.__name__} skipped: {e}"
                    )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 29 schema bootstrap failed (non-fatal): {e}"
        )

    # Phase 29-08: smoke-render trip templates (Lesson 2026-05-18 — catches Jinja TemplateSyntaxError at boot)
    # ZERO {% tr %} in templates (Lesson 2026-05-15). Non-fatal: log error, do NOT crash.
    try:
        from docxtpl import DocxTemplate as _DocxTpl29
        _fake_trip_ctx = {
            # 29-08 base keys
            'vehicle_plate': 'A001AA77', 'driver_full_name': 'Тест Тестов',
            'date': '01.01.2026', 'odometer_start': '1000', 'odometer_finish': '1100',
            'org_name': 'ВСКС', 'route_from': 'Москва', 'route_to': 'Тула',
            'vehicle_brand_model': 'Test Auto', 'fuel_type': 'AI-92',
            'driver_license_series': '77 ОТ', 'driver_license_number': '123456',
            'driver_license_categories': 'B', 'driver_license_issued_at': '01.01.2020',
            'driver_license_expires_at': '01.01.2030', 'delta_km': '100',
            'fuel_remaining_start': '30', 'fuel_remaining_finish': '25', 'fuel_issued_l': '10',
            'initiator_full_name': 'Иванов', 'initiator_position': 'Менеджер',
            'trip_number': 'VSKS-00001', 'trip_date': '01.01.2026',
            'cargo_name': '', 'cargo_weight_t': '', 'loading_point': '', 'unloading_point': '',
            'cargo_count': '', 'route': 'Москва → Тула', 'vehicle_color': 'белый', 'mileage': '100',
            'fuel_brand': 'AI-92', 'fuel_start': '30', 'fuel_finish': '25', 'customer_text': '',
            'plate': 'A001AA77',
            # 29-20 extended keys
            'vehicle_brand': 'Test', 'vehicle_model': 'Auto', 'vehicle_type_label': 'Легковой автомобиль',
            'vehicle_load_capacity': '', 'date_dmy': '01.01.2026', 'odometer_diff': '100',
            'fuel_added': '10', 'fuel_norm': '', 'fuel_season': 'зимняя', 'fuel_used_calc': '',
            'org_address': 'Москва', 'customer_org_name': 'ВСКС', 'customer_org_address': 'Москва',
            'purpose': '', 'task_description': '',
        }
        _tpl_dir29 = os.path.join(os.path.dirname(__file__), '..', 'templates')
        for _tpl_name29 in ['trip_light.docx', 'trip_truck.docx', 'trip_special.docx']:
            try:
                _tpl_path29 = os.path.join(_tpl_dir29, _tpl_name29)
                if os.path.exists(_tpl_path29):
                    _DocxTpl29(_tpl_path29).render(_fake_trip_ctx)
                    logging.getLogger(__name__).info(f"Phase 29 trip template smoke-render OK: {_tpl_name29}")
                else:
                    logging.getLogger(__name__).warning(f"Phase 29 trip template not found (skip smoke): {_tpl_name29}")
            except Exception as _e29:
                logging.getLogger(__name__).error(
                    f"Phase 29 trip template smoke-render FAILED {_tpl_name29}: {_e29}"
                )
    except Exception as _e29_outer:
        logging.getLogger(__name__).warning(f"Phase 29 smoke-render block failed (non-fatal): {_e29_outer}")

    # Phase 29-11: seed vehicles from xlsx Голичкова (idempotent — ON CONFLICT plate DO NOTHING)
    try:
        from .services.vehicles_seed import seed_vehicles_from_xlsx as _seed_vehicles
        async with async_session() as _db29:
            _vresult = await _seed_vehicles(_db29)
        logging.getLogger(__name__).info(f"Phase 29 vehicles_seed: {_vresult}")
    except Exception as _e29_seed:
        logging.getLogger(__name__).warning(f"Phase 29 vehicles_seed skipped (non-fatal): {_e29_seed}")

    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if task_vehicle_alerts is not None:
        task_vehicle_alerts.cancel()
        try:
            await task_vehicle_alerts
        except asyncio.CancelledError:
            pass


app = FastAPI(title="VSKS CRM API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert pydantic 422 errors into human-readable Russian messages."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    field_labels = {
        "subsidy_id": "Субсидия", "contractor_id": "Контрагент", "item_type": "Тип",
        "item_name": "Наименование", "status": "Статус", "date": "Дата",
        "contract_date": "Дата договора", "delivery_date": "Дата поставки",
        "execution_term": "Срок исполнения", "nmck": "НМЦК", "contract_price": "Цена договора",
        "planned_total_price": "Плановая сумма", "payment_amount": "Сумма оплаты",
        "number": "Номер", "subject": "Предмет", "max_amount": "Максимальная сумма",
    }
    errors = []
    for err in exc.errors():
        loc = [str(l) for l in err.get("loc", []) if l != "body"]
        field = loc[-1] if loc else "?"
        label = field_labels.get(field, field)
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
    message = "; ".join(errors) if errors else "Ошибка валидации данных"
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": message,
            "details": str(exc.errors()),
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


async def _save_incident(request: Request, message: str, details: str,
                         code: str, correlation_id: str):
    try:
        from .models.system_incident import SystemIncident
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


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(staff_directory.router)
app.include_router(contractors.router)
app.include_router(contracts.router)
# Phase 27.1: contract_items MUST be registered BEFORE purchases.router
# because purchases has catch-all /{purchase_id} that would intercept /contract-items
from .routers import contract_items as contract_items_router
app.include_router(contract_items_router.router)
app.include_router(purchases.router)
app.include_router(purchase_receipts.router)
app.include_router(install_router.router, prefix="/api")
# bank_statements MUST be registered BEFORE payments.router:
# /imports and /registry/{id}/... must resolve before payments' catch-all /{pid}
from .routers import bank_statements
app.include_router(bank_statements.router)
app.include_router(payments.router)
app.include_router(feo_categories.router)
app.include_router(feo_planned_items.router)
app.include_router(settings_router.router)
app.include_router(dashboard.router)
app.include_router(subsidies.router)
app.include_router(products.router)
app.include_router(purchase_files.router)
app.include_router(documents.router)
app.include_router(documents_guide_router)
app.include_router(publications.router)
app.include_router(subsidy_approvers.router)
app.include_router(responsible_persons.router)
app.include_router(commercial_requests.router)
app.include_router(suppliers.router)
app.include_router(purchase_events.router)
app.include_router(user_hierarchy.router)
app.include_router(system_incidents.router)
app.include_router(organizations.router)
app.include_router(reports.router)
app.include_router(events.router)
app.include_router(purchase_approvals.router)
app.include_router(purchase_export.router)
app.include_router(purchase_items_import.router)
app.include_router(purchase_members.router)
app.include_router(purchase_transitions.router)
# Специфичные суб-роутеры /api/tasks/* регистрируются ДО tasks.router,
# иначе catch-all `/{task_id}` ловит `/badges`, `/pending-consent`, `/report/*`
from .routers import task_badges, task_delegation, task_reports, task_comments
app.include_router(task_badges.router)
app.include_router(task_delegation.router)
app.include_router(task_reports.router)
app.include_router(task_comments.router)
app.include_router(tasks.router)
app.include_router(departments.router)
app.include_router(delivery_addresses.router)
app.include_router(org_config.router)
app.include_router(hierarchy.router)
app.include_router(billing.router)
app.include_router(telegram_webhook.router)
app.include_router(chat_router.router)    # REST: /api/chat/...
app.include_router(chat_router.ws_router)  # WS: /api/ws/chat
# Specific sub-router /api/wishes/*/documents/* registered BEFORE wishes.router
# so the specific path resolves before the catch-all /{wish_id} in wishes.router
# (same ordering principle as task_badges/task_delegation before tasks.router, commit 3d37cf9)
app.include_router(wish_documents.router)
app.include_router(wishes.router)
app.include_router(push_router.router)
app.include_router(permissions_router.router)
app.include_router(user_addresses_router.router)
app.include_router(analytics_router.router)
app.include_router(report_configs_router.router)

# Phase 29: vehicle fleet routers
# vehicles_dashboard (/api/vehicles-dashboard) и external_drivers.drivers_router (/api/drivers)
# регистрируются ПЕРЕД vehicles.router (/api/vehicles/{vehicle_id:int}) — Gotcha 2026-04-20 FastAPI routing
app.include_router(vehicles_dashboard.router)          # /api/vehicles-dashboard
app.include_router(external_drivers.drivers_router)    # /api/drivers/available
app.include_router(external_drivers.router)            # /api/external-drivers
app.include_router(vehicles_import_router.router)      # /api/vehicles-import (BEFORE vehicles catch-all)
app.include_router(vehicles.router)                    # /api/vehicles (catch-all /{vehicle_id:int})
app.include_router(vehicle_attachments.router)         # /api/vehicle-attachments
app.include_router(repair_attachments.router)          # /api/repair-attachments
app.include_router(vehicle_repairs.router)             # /api/vehicle-repairs
app.include_router(vehicle_odometer.router)            # /api/vehicle-odometer
app.include_router(fuel_logs.router)                   # /api/fuel-logs
app.include_router(trips.router)                       # /api/trips


@app.get("/api/diag/version")
async def diag_version():
    """Phase 26-BB: маркер фазы + git sha + runtime checks (колонка, backfill)."""
    import os as _os, subprocess as _sp
    from sqlalchemy import text as _text
    git_sha = "unknown"
    try:
        git_sha = _sp.check_output(
            ['git', '-C', _os.path.dirname(__file__) + '/../..', 'rev-parse', '--short', 'HEAD'],
            stderr=_sp.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        pass

    # Runtime DB checks
    schema_status = {"purchase_items.receipt_id": "unknown", "linked_count": 0, "advance_purchases": 0, "advance_null_contractor_items": 0}
    try:
        async with async_session() as db:
            col_q = await db.execute(_text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='purchase_items' AND column_name='receipt_id'
                LIMIT 1
            """))
            schema_status["purchase_items.receipt_id"] = "present" if col_q.scalar() else "MISSING"
            if schema_status["purchase_items.receipt_id"] == "present":
                cnt_q = await db.execute(_text("SELECT COUNT(*) FROM purchase_items WHERE receipt_id IS NOT NULL"))
                schema_status["linked_count"] = int(cnt_q.scalar() or 0)
            advances_q = await db.execute(_text("""
                SELECT COUNT(*) FROM purchases WHERE purchase_method='advance'
            """))
            schema_status["advance_purchases"] = int(advances_q.scalar() or 0)
            null_c_q = await db.execute(_text("""
                SELECT COUNT(*) FROM purchase_items pi
                JOIN purchases p ON p.id = pi.purchase_id
                WHERE p.purchase_method='advance' AND pi.contractor_id IS NULL
            """))
            schema_status["advance_null_contractor_items"] = int(null_c_q.scalar() or 0)
    except Exception as e:
        schema_status["error"] = str(e)[:200]

    return {
        "phase": "26-DD",
        "git_sha": git_sha,
        "schema": schema_status,
        "features": [
            "auto-recompute-on-get-advance",
            "structured-document-errors",
            "receipt-as-file-in-acceptance-docs",
            "contractor-inheritance-purchase-to-items",
            "per-receipt-contractor-mapping",
            "fuzzy-match-legacy-items",
            "propagate-purchase-contractor-to-items",
            "force-backfill-endpoint",
            "diag-purchase-endpoint",
        ],
    }


@app.post("/api/diag/run-backfills")
async def diag_run_backfills(current_user=Depends(get_current_user)):
    """Принудительный запуск всех backfill'ов (admin/superadmin only).
    Returns per-stage counts."""
    if current_user.role not in ('admin', 'superadmin'):
        raise HTTPException(403, "Только admin/superadmin")

    from sqlalchemy import select as _sel
    from .models.purchase import Purchase as _Purchase
    from .models.purchase_item import PurchaseItem as _PI
    from .models.purchase_receipt import PurchaseReceipt as _PR
    from .models.contractor import Contractor as _Ctr
    from app.routers.purchase_receipts import _items_match_score as _fuzzy, _extract_items as _ext

    result = {"propagated_from_purchase": 0, "linked_by_fuzzy": 0, "filled_first_receipt": 0, "errors": []}

    async with async_session() as db:
        # Stage A: propagate purchase.contractor_id → items
        try:
            advances_with_c = (await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    _Purchase.contractor_id.is_not(None),
                )
            )).scalars().all()
            for p in advances_with_c:
                c_row = await db.get(_Ctr, p.contractor_id)
                if not c_row:
                    continue
                null_items = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == p.id, _PI.contractor_id.is_(None))
                )).scalars().all()
                for it in null_items:
                    it.contractor_id = c_row.id
                    it.contractor_inn = c_row.inn
                    it.contractor_name = c_row.name
                    result["propagated_from_purchase"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_A: {str(e)[:200]}")

        # Stage B: fuzzy match unlinked items с raw_json
        try:
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            for (pid,) in advances_ids:
                unlinked = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.receipt_id.is_(None))
                )).scalars().all()
                if not unlinked:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid)
                )).scalars().all()
                if not receipts:
                    continue
                for it in unlinked:
                    best_r = None
                    best_score = 0
                    for r in receipts:
                        for ri in _ext(r.raw_json):
                            s = _fuzzy(it, ri)
                            if s >= 2 and s > best_score:
                                best_score = s
                                best_r = r
                    if best_r:
                        it.receipt_id = best_r.id
                        if best_r.seller_inn:
                            c_row = (await db.execute(
                                _sel(_Ctr).where(_Ctr.inn == best_r.seller_inn)
                            )).scalar_one_or_none()
                            if not c_row:
                                c_row = _Ctr(inn=best_r.seller_inn, name=best_r.seller_name or f"ИНН {best_r.seller_inn}")
                                db.add(c_row)
                                await db.flush()
                            it.contractor_id = c_row.id
                            it.contractor_inn = best_r.seller_inn
                            it.contractor_name = best_r.seller_name
                        result["linked_by_fuzzy"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_B: {str(e)[:200]}")

        # Stage C: fallback — для NULL items с одним чеком в закупке, заполнить от него
        try:
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            for (pid,) in advances_ids:
                null_items = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.contractor_id.is_(None))
                )).scalars().all()
                if not null_items:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
                )).scalars().all()
                if not receipts:
                    continue
                # Стратегия: если 1 чек — все NULL ← него; если несколько — НЕ трогать
                if len(receipts) == 1:
                    r = receipts[0]
                    if not r.seller_inn:
                        continue
                    c_row = (await db.execute(
                        _sel(_Ctr).where(_Ctr.inn == r.seller_inn)
                    )).scalar_one_or_none()
                    if not c_row:
                        c_row = _Ctr(inn=r.seller_inn, name=r.seller_name or f"ИНН {r.seller_inn}")
                        db.add(c_row)
                        await db.flush()
                    for it in null_items:
                        it.contractor_id = c_row.id
                        it.contractor_inn = r.seller_inn
                        it.contractor_name = r.seller_name
                        result["filled_first_receipt"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_C: {str(e)[:200]}")

        # Stage D: для каждой advance закупки прогнать _recompute_from_receipts_core —
        # создаёт PurchaseItem из raw_json если items отсутствуют, плюс per-receipt mapping.
        try:
            from app.routers.purchase_receipts import _recompute_from_receipts_core
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            d_autocreated = 0
            for (pid_,) in advances_ids:
                res = await _recompute_from_receipts_core(pid_, db)
                d_autocreated += int(res.get("items_autocreated") or 0)
            result["items_autocreated_from_raw_json"] = d_autocreated
        except Exception as e:
            result["errors"].append(f"stage_D: {str(e)[:200]}")

    return result


@app.get("/api/diag/advance-overview")
async def diag_advance_overview(current_user=Depends(get_current_user)):
    """Overview всех advance закупок: pid, registry_number, items в purchase_items vs contract_items,
    receipts_count, contractor. Чтобы найти где реально лежат данные."""
    from sqlalchemy import select as _sel, func as _func, text as _text
    from .models.purchase import Purchase as _Purchase
    from .models.purchase_item import PurchaseItem as _PI
    from .models.purchase_receipt import PurchaseReceipt as _PR

    async with async_session() as db:
        advances = (await db.execute(
            _sel(_Purchase).where(_Purchase.purchase_method == 'advance').order_by(_Purchase.id.desc())
        )).scalars().all()
        rows = []
        for p in advances:
            pi_count = (await db.execute(
                _sel(_func.count(_PI.id)).where(_PI.purchase_id == p.id)
            )).scalar() or 0
            r_count = (await db.execute(
                _sel(_func.count(_PR.id)).where(_PR.purchase_id == p.id)
            )).scalar() or 0
            # contract_items count через raw SQL — модель может быть в другом месте
            try:
                ci_count = (await db.execute(
                    _text("SELECT COUNT(*) FROM contract_items WHERE purchase_id = :pid"),
                    {"pid": p.id}
                )).scalar() or 0
            except Exception:
                ci_count = -1  # таблицы нет
            rows.append({
                "id": p.id,
                "registry_number": p.registry_number,
                "purchase_number": p.purchase_number,
                "purchase_method": p.purchase_method,
                "contractor_id": p.contractor_id,
                "purchase_items_count": pi_count,
                "contract_items_count": ci_count,
                "receipts_count": r_count,
            })
        # Также — все PurchaseReceipt и их purchase_id (где реально лежат чеки)
        all_receipts = (await db.execute(
            _sel(_PR.id, _PR.purchase_id, _PR.seller_inn, _PR.seller_name, _PR.total_sum)
            .order_by(_PR.id.desc()).limit(30)
        )).all()
        receipts_summary = [
            {"id": r.id, "purchase_id": r.purchase_id, "seller_inn": r.seller_inn,
             "seller_name": (r.seller_name or "")[:60], "total": float(r.total_sum or 0)}
            for r in all_receipts
        ]
        return {"advances": rows, "recent_receipts": receipts_summary}


@app.post("/api/diag/recompute/{pid}")
async def diag_recompute_single(pid: int, current_user=Depends(get_current_user)):
    """Phase 26-DD: ручной recompute одной закупки доступен ЛЮБОЙ авторизованной роли,
    с подробным отчётом включая sample raw_json. Для отладки 575/582 без admin токена."""
    from sqlalchemy import select as _sel
    from .models.purchase import Purchase as _Purchase
    from .models.purchase_item import PurchaseItem as _PI
    from .models.purchase_receipt import PurchaseReceipt as _PR
    from app.routers.purchase_receipts import (
        _recompute_from_receipts_core, _extract_items
    )
    import json as _json

    async with async_session() as db:
        p = await db.get(_Purchase, pid)
        if not p:
            raise HTTPException(404, "Закупка не найдена")
        # Snapshot ДО
        items_before = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid)
        )).scalars().all()
        receipts = (await db.execute(
            _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
        )).scalars().all()
        before = {
            "items_count": len(items_before),
            "items_with_contractor": sum(1 for i in items_before if i.contractor_id),
            "items_with_receipt_id": sum(1 for i in items_before if i.receipt_id),
            "receipts_count": len(receipts),
            "receipts_raw_items_count": [len(_extract_items(r.raw_json or {})) for r in receipts],
            "purchase_contractor_id": p.contractor_id,
        }
        # Sample raw_json первого чека (truncated)
        sample = None
        if receipts:
            r0 = receipts[0]
            raw_str = _json.dumps(r0.raw_json or {}, ensure_ascii=False)[:1500]
            sample = {
                "receipt_id": r0.id,
                "seller_inn": r0.seller_inn,
                "seller_name": r0.seller_name,
                "raw_json_truncated": raw_str,
                "extracted_items": _extract_items(r0.raw_json or {})[:5],
            }
        # Запуск
        result = await _recompute_from_receipts_core(pid, db)
        # Snapshot ПОСЛЕ
        items_after = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid)
        )).scalars().all()
        # Phase 26-FF: per-item info + contractor resolvability
        from .models.contractor import Contractor as _Ctr
        items_detail = []
        for it in items_after:
            c_resolvable = False
            c_inn = None
            c_name = None
            if it.contractor_id:
                c_row = await db.get(_Ctr, it.contractor_id)
                if c_row:
                    c_resolvable = True
                    c_inn = c_row.inn
                    c_name = c_row.name
            items_detail.append({
                "item_id": it.id,
                "name": (it.item_name or "")[:60],
                "contractor_id": it.contractor_id,
                "contractor_inn_in_item": it.contractor_inn,
                "contractor_name_in_item": (it.contractor_name or "")[:60] if it.contractor_name else None,
                "receipt_id": it.receipt_id,
                "contractor_resolvable_in_db": c_resolvable,
                "contractor_inn_resolved": c_inn,
                "contractor_name_resolved": (c_name or "")[:60] if c_name else None,
            })
        after = {
            "items_count": len(items_after),
            "items_with_contractor": sum(1 for i in items_after if i.contractor_id),
            "items_with_receipt_id": sum(1 for i in items_after if i.receipt_id),
            "items_detail": items_detail,
        }
        return {
            "ok": True,
            "before": before,
            "recompute_result": result,
            "after": after,
            "sample_receipt": sample,
        }


@app.get("/api/diag/purchase/{pid}")
async def diag_purchase(pid: int, current_user=Depends(get_current_user)):
    """Sample данных о закупке для диагностики backfills (admin/superadmin only)."""
    if current_user.role not in ('admin', 'superadmin'):
        raise HTTPException(403, "Только admin/superadmin")

    from sqlalchemy import select as _sel
    from .models.purchase import Purchase as _Purchase
    from .models.purchase_item import PurchaseItem as _PI
    from .models.purchase_receipt import PurchaseReceipt as _PR
    from .models.contractor import Contractor as _Ctr
    import json as _json

    async with async_session() as db:
        p = await db.get(_Purchase, pid)
        if not p:
            raise HTTPException(404, "Закупка не найдена")
        items = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid).order_by(_PI.id.asc())
        )).scalars().all()
        receipts = (await db.execute(
            _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
        )).scalars().all()

        # Resolve contractor inn for purchase
        purchase_contractor_inn = None
        if p.contractor_id:
            c = await db.get(_Ctr, p.contractor_id)
            if c:
                purchase_contractor_inn = c.inn

        items_out = [{
            "id": it.id,
            "item_name": it.item_name,
            "qty": float(it.quantity or 0),
            "unit_price": float(it.unit_price or 0),
            "total_price": float(it.total_price or 0),
            "contractor_id": it.contractor_id,
            "contractor_inn": it.contractor_inn,
            "receipt_id": it.receipt_id,
        } for it in items]

        receipts_out = []
        for r in receipts:
            raw_str = _json.dumps(r.raw_json or {}, ensure_ascii=False)[:2000] if r.raw_json else None
            receipts_out.append({
                "id": r.id,
                "seller_inn": r.seller_inn,
                "seller_name": r.seller_name,
                "total_sum": float(r.total_sum or 0),
                "raw_json_truncated": raw_str,
            })

        return {
            "purchase_id": pid,
            "purchase_contractor_id": p.contractor_id,
            "purchase_contractor_inn": purchase_contractor_inn,
            "items": items_out,
            "receipts": receipts_out,
        }
