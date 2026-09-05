"""Точка входа FastAPI-приложения VSKS CRM (uvicorn app.main:app).

Перенесено из app/__init__.py при разрезании монолитного файла (2483
строки) на модули (Правило №5 — модульность кода). Собирает воедино:
  - app.startup.lifespan            — фоновые задачи + идемпотентные миграции/сиды
  - app.errors.register_error_handlers — 3 глобальных exception handler'а
  - app.routes.register_routes         — все APIRouter'ы, порядок сохранён 1:1
"""
import uuid

from fastapi import FastAPI, Request

# Импорты моделей ниже НЕ используются напрямую в этом файле — они нужны
# ТОЛЬКО чтобы зарегистрировать соответствующие таблицы в Base.metadata
# (см. app/__init__.py до разрезания, комментарии "ensure table is
# registered" сохранены как есть).
from app.models import platform_publication  # ensure table is registered
from app.models import subsidy_allocation    # ensure purchase_subsidy_allocations table is created
from app.models import contract_subsidy      # ensure contract_subsidies table is created
from app.models import org_section_config    # ensure org_section_configs table is created
from app.models.task import TaskAssignee, TelegramMessageMap  # ensure tables created
from app.models.task_decline import TaskConsentDecline  # ensure task_consent_declines table is created
from app.models.manager_department import ManagerDepartment  # ensure manager_departments table is created
from app.models.org_billing import OrgBillingPaid  # ensure org_billing_paid table is created
from app.models.purchase_comment import PurchaseComment  # ensure purchase_comments table is created
from app.models import bank_statement  # ensure bank_statement_imports / bank_payments tables registered
from app.models.entity_change import EntityChange, EntityFieldSeen  # ensure entity_changes / entity_field_seen tables registered

from app.startup import lifespan
from app.errors import register_error_handlers
from app.routes import register_routes

app = FastAPI(title="VSKS CRM API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


register_error_handlers(app)
register_routes(app)
