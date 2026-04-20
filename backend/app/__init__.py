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
)
from .routers import org_config
from .routers import purchase_transitions
from .routers import feo_planned_items
from .routers import telegram_webhook
from .routers import settings as settings_router
from .routers import chat as chat_router
from .routers import push as push_router
from .models import platform_publication  # ensure table is registered
from .models import subsidy_allocation    # ensure purchase_subsidy_allocations table is created
from .models import contract_subsidy      # ensure contract_subsidies table is created
from .models import org_section_config    # ensure org_section_configs table is created
from .models.task import TaskAssignee, TelegramMessageMap  # ensure tables created
from .models.task_decline import TaskConsentDecline  # ensure task_consent_declines table is created
from .models.manager_department import ManagerDepartment  # ensure manager_departments table is created
from .models.org_billing import OrgBillingPaid  # ensure org_billing_paid table is created
from .models.purchase_comment import PurchaseComment  # ensure purchase_comments table is created
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
app.include_router(purchases.router)
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
app.include_router(tasks.router)
from .routers import task_comments
app.include_router(task_comments.router)
from .routers import task_badges
app.include_router(task_badges.router)
from .routers import task_delegation
app.include_router(task_delegation.router)
app.include_router(departments.router)
app.include_router(delivery_addresses.router)
app.include_router(org_config.router)
app.include_router(hierarchy.router)
app.include_router(billing.router)
app.include_router(telegram_webhook.router)
app.include_router(chat_router.router)    # REST: /api/chat/...
app.include_router(chat_router.ws_router)  # WS: /api/ws/chat
app.include_router(wishes.router)
app.include_router(push_router.router)
