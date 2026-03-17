import traceback
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .routers import (
    auth, users, contractors, contracts, purchases, payments,
    feo_categories, dashboard, subsidies, products, purchase_files,
    documents, publications, subsidy_approvers, responsible_persons,
    commercial_requests, suppliers, purchase_events, user_hierarchy,
    system_incidents, organizations, reports, events, purchase_approvals,
    tasks, departments, delivery_addresses, hierarchy,
)
from .routers import org_config
from .routers import feo_planned_items
from .routers import settings as settings_router
from .models import platform_publication  # ensure table is registered
from .models import org_section_config    # ensure org_section_configs table is created
from .models.task import TaskAssignee     # ensure task_assignees table is created
from .models.manager_department import ManagerDepartment  # ensure manager_departments table is created
from .routers.documents import guide_router as documents_guide_router
from .database import async_session

app = FastAPI(title="VSKS CRM API", version="1.0.0")


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


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
app.include_router(tasks.router)
app.include_router(departments.router)
app.include_router(delivery_addresses.router)
app.include_router(org_config.router)
app.include_router(hierarchy.router)
