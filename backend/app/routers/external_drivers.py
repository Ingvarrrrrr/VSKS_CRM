"""
External (hired) drivers CRUD + /api/drivers/available union endpoint.

Plan 29-09, Phase 29 «Имущество → Автотранспорт».
Decisions covered: D-04, D-15.

Endpoints (external_drivers router, prefix=/api/external-drivers):
  GET    /api/external-drivers               — list (search, org_id filter, pagination)
  POST   /api/external-drivers               — create
  GET    /api/external-drivers/{id}          — detail
  PATCH  /api/external-drivers/{id}          — partial update
  DELETE /api/external-drivers/{id}          — hard delete (409 if used in trips)

Endpoints (drivers_router, prefix=/api/drivers):
  GET    /api/drivers/available              — union User(can_drive=true) ∪ ExternalDriver

Registration in __init__.py done in separate commit (per plan constraint).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from typing import Any, List, Optional

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, require_action
from app.models.user import User
from app.models.external_driver import ExternalDriver

router = APIRouter(prefix="/api/external-drivers", tags=["vehicles"])
drivers_router = APIRouter(prefix="/api/drivers", tags=["vehicles"])

# ─────────────────────────── Field classification ───────────────────────────

_DATE_FIELDS = {
    "license_issued_at",
    "license_expires_at",
    "medical_cert_expires_at",
}

_PATCHABLE_FIELDS = {
    "full_name", "phone",
    "license_series", "license_number", "license_categories",
    "license_issued_at", "license_expires_at", "medical_cert_expires_at",
    "org_id", "notes",
}


# ─────────────────────────── Helpers ────────────────────────────────────────

def _coerce_patch_value(field: str, value: Any) -> Any:
    """Convert ISO string to date for DATE columns; empty string → None."""
    if value == "" or value is None:
        return None
    if field in _DATE_FIELDS and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    return value


def _visibility_q(user: User):
    """Base query with org visibility filter for ExternalDriver."""
    q = select(ExternalDriver)
    org_ids = get_org_filter(user)
    if org_ids is not None:
        q = q.where(
            or_(
                ExternalDriver.org_id.in_(org_ids),
                ExternalDriver.org_id.is_(None),
            )
        )
    return q


# ─────────────────────────── GET /api/external-drivers ──────────────────────

@router.get("", response_model=dict)
async def list_external_drivers(
    q: Optional[str] = Query(None, description="Search by full_name or license_number"),
    org_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """GET /api/external-drivers — paginated list."""
    base = _visibility_q(current_user)

    if org_id is not None:
        base = base.where(ExternalDriver.org_id == org_id)

    if q:
        pattern = f"%{q}%"
        base = base.where(
            or_(
                ExternalDriver.full_name.ilike(pattern),
                ExternalDriver.license_number.ilike(pattern),
                ExternalDriver.phone.ilike(pattern),
            )
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = base.order_by(ExternalDriver.full_name).limit(limit).offset(offset)
    items = (await db.execute(items_q)).scalars().all()

    return {
        "items": [_driver_out(d) for d in items],
        "total": total,
    }


# ─────────────────────────── POST /api/external-drivers ─────────────────────

@router.post("", response_model=dict, status_code=201)
async def create_external_driver(
    data: dict,
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    """POST /api/external-drivers — create a new external driver record."""
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        raise HTTPException(400, {"code": "FULL_NAME_REQUIRED", "detail": "full_name обязателен"})

    driver = ExternalDriver(
        full_name=full_name,
        phone=data.get("phone"),
        license_series=data.get("license_series"),
        license_number=data.get("license_number"),
        license_categories=data.get("license_categories"),
        license_issued_at=_coerce_patch_value("license_issued_at", data.get("license_issued_at")),
        license_expires_at=_coerce_patch_value("license_expires_at", data.get("license_expires_at")),
        medical_cert_expires_at=_coerce_patch_value("medical_cert_expires_at", data.get("medical_cert_expires_at")),
        org_id=data.get("org_id"),
        notes=data.get("notes"),
        created_by_id=current_user.id,
    )
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return _driver_out(driver)


# ─────────────────────────── GET /api/external-drivers/{id} ─────────────────

@router.get("/{driver_id}", response_model=dict)
async def get_external_driver(
    driver_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """GET /api/external-drivers/{id} — detail."""
    driver = await db.get(ExternalDriver, driver_id)
    if not driver:
        raise HTTPException(404, {"code": "NOT_FOUND", "detail": "Водитель не найден"})
    _check_visibility(driver, current_user)
    return _driver_out(driver)


# ─────────────────────────── PATCH /api/external-drivers/{id} ───────────────

@router.patch("/{driver_id}", response_model=dict)
async def patch_external_driver(
    driver_id: int,
    data: dict,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    """PATCH /api/external-drivers/{id} — partial update."""
    driver = await db.get(ExternalDriver, driver_id)
    if not driver:
        raise HTTPException(404, {"code": "NOT_FOUND", "detail": "Водитель не найден"})
    _check_visibility(driver, current_user)

    for field, value in data.items():
        if field not in _PATCHABLE_FIELDS:
            continue
        setattr(driver, field, _coerce_patch_value(field, value))

    await db.commit()
    await db.refresh(driver)
    return _driver_out(driver)


# ─────────────────────────── DELETE /api/external-drivers/{id} ──────────────

@router.delete("/{driver_id}", response_model=dict)
async def delete_external_driver(
    driver_id: int,
    current_user: User = Depends(require_action("vehicle.delete")),
    db: AsyncSession = Depends(get_db),
):
    """DELETE /api/external-drivers/{id} — hard delete, 409 if used in trips."""
    driver = await db.get(ExternalDriver, driver_id)
    if not driver:
        raise HTTPException(404, {"code": "NOT_FOUND", "detail": "Водитель не найден"})
    _check_visibility(driver, current_user)

    # 409 guard: check if driver is referenced in any trips
    try:
        from app.models.trip import Trip
        trip_ids_rows = (await db.execute(
            select(Trip.id).where(Trip.driver_external_id == driver_id)
        )).scalars().all()
        if trip_ids_rows:
            raise HTTPException(409, {
                "code": "DRIVER_IN_USE",
                "detail": "Водитель используется в путёвках",
                "trip_ids": list(trip_ids_rows),
            })
    except ImportError:
        pass  # Trip model not available yet — skip check

    await db.delete(driver)
    await db.commit()
    return {"ok": True, "id": driver_id}


# ─────────────────────────── GET /api/drivers/available ─────────────────────

@drivers_router.get("/available", response_model=dict)
async def list_available_drivers(
    org_id: Optional[int] = Query(None, description="Filter by org (for external drivers)"),
    q: Optional[str] = Query(None, description="Search by name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/drivers/available — union of:
      - User WHERE can_drive=true (filtered by user visibility)
      - ExternalDriver WHERE org_id=$org_id OR org_id IS NULL (superadmin: all)

    Response: {items: [{kind, id, full_name, license_categories, license_expires_at}]}
    """
    # 1. Internal users with can_drive=true
    internal_q = select(User).where(User.can_drive.is_(True))
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        internal_q = internal_q.where(User.org_id.in_(org_ids))
    if q:
        internal_q = internal_q.where(User.full_name.ilike(f"%{q}%"))
    internal_users = (await db.execute(internal_q)).scalars().all()

    # 2. External drivers
    external_q = select(ExternalDriver)
    if org_id is not None:
        external_q = external_q.where(
            or_(ExternalDriver.org_id == org_id, ExternalDriver.org_id.is_(None))
        )
    elif org_ids is not None:
        # Non-superadmin: show drivers from user's orgs + unassigned
        external_q = external_q.where(
            or_(ExternalDriver.org_id.in_(org_ids), ExternalDriver.org_id.is_(None))
        )
    if q:
        external_q = external_q.where(ExternalDriver.full_name.ilike(f"%{q}%"))
    external_drivers = (await db.execute(external_q)).scalars().all()

    items = [
        {
            "kind": "user",
            "id": u.id,
            "full_name": u.full_name,
            "license_categories": u.license_categories,
            "license_series": u.license_series,
            "license_number": u.license_number,
            "license_expires_at": u.license_expires_at.isoformat() if u.license_expires_at else None,
        }
        for u in internal_users
    ] + [
        {
            "kind": "external",
            "id": d.id,
            "full_name": d.full_name,
            "license_categories": d.license_categories,
            "license_series": d.license_series,
            "license_number": d.license_number,
            "license_expires_at": d.license_expires_at.isoformat() if d.license_expires_at else None,
        }
        for d in external_drivers
    ]

    return {"items": items}


# ─────────────────────────── Internal helpers ────────────────────────────────

def _driver_out(d: ExternalDriver) -> dict:
    """Serialize ExternalDriver to dict for API response."""
    return {
        "id": d.id,
        "full_name": d.full_name,
        "phone": d.phone,
        "license_series": d.license_series,
        "license_number": d.license_number,
        "license_categories": d.license_categories,
        "license_issued_at": d.license_issued_at.isoformat() if d.license_issued_at else None,
        "license_expires_at": d.license_expires_at.isoformat() if d.license_expires_at else None,
        "medical_cert_expires_at": d.medical_cert_expires_at.isoformat() if d.medical_cert_expires_at else None,
        "org_id": d.org_id,
        "notes": d.notes,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "created_by_id": d.created_by_id,
    }


def _check_visibility(driver: ExternalDriver, user: User) -> None:
    """Raise 403 if user cannot see this driver."""
    if user.role in ("superadmin", "account_owner"):
        return
    org_ids = get_org_filter(user)
    if org_ids is None:
        return
    if driver.org_id is not None and driver.org_id not in org_ids:
        raise HTTPException(403, {"code": "FORBIDDEN", "detail": "Нет доступа к этому водителю"})
