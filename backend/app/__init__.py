import asyncio
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .routers import (
    auth, users, contractors, contracts, purchases, payments,
    feo_categories, dashboard, subsidies, products, purchase_files,
    documents, publications, subsidy_approvers, responsible_persons,
    commercial_requests, suppliers, purchase_events, user_hierarchy,
    system_incidents, organizations, reports, events, purchase_approvals,
    tasks, departments, delivery_addresses, hierarchy, billing,
    wishes, purchase_export, purchase_items_import, purchase_members,
    permissions as permissions_router,
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


@asynccontextmanager
async def lifespan(app_: FastAPI):
    task = asyncio.create_task(_deadline_reminder_loop())
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
                            if s >= 3 and s > best_score:
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

    yield
    task.cancel()
    try:
        await task
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
        "phase": "26-BB",
        "git_sha": git_sha,
        "schema": schema_status,
        "features": [
            "auto-recompute-on-get-advance",
            "structured-document-errors",
            "receipt-as-file-in-acceptance-docs",
            "contractor-inheritance-purchase-to-items",
            "per-receipt-contractor-mapping",
            "fuzzy-match-legacy-items",
        ],
    }
