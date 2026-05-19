"""
Vehicle repairs router — Plan 29-06, Phase 29 «Имущество → Автотранспорт».

Decisions covered: D-12, D-18.

D-12: status ENUM planned/in_progress/done/cancelled.
D-18: nullable purchase_id FK для двусторонней ссылки Purchase ↔ VehicleRepair.

Visibility: через parent Vehicle (owner_org_id / assigned_org_id ∈ user org_ids).
Write actions: require_action('vehicle.repair.write').
Delete action:  require_action('vehicle.delete').

NOTE: Роутер не регистрируется здесь в __init__.py — отдельным коммитом после Wave 1.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.vehicle_repair import VehicleRepair
from app.models.repair_attachment import RepairAttachment  # noqa: F401 — loaded via selectin
from app.models.purchase import Purchase
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab, require_action
from app.schemas.vehicle import RepairCreate, RepairOut

router = APIRouter(prefix="/api/vehicle-repairs", tags=["vehicles"])

# ─────────────────────── PATCH coerce helper ───────────────────────

_REPAIR_DATE_FIELDS = {"date"}
_REPAIR_DATETIME_FIELDS: set[str] = set()

_REPAIR_PATCHABLE = {
    "date", "description", "cost_amount", "performed_by_name",
    "mileage_at_repair", "status", "purchase_id",
}

VALID_STATUSES = {"planned", "in_progress", "done", "cancelled"}


def _coerce_patch_value(field: str, value):
    """Конвертирует ISO-строку в date для DATE-полей; пустые строки → None."""
    if value == "" or value is None:
        return None
    if field in _REPAIR_DATE_FIELDS and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    if field in _REPAIR_DATETIME_FIELDS and isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return date.fromisoformat(value[:10])
            except Exception:
                return None
    return value


# ─────────────────────── Visibility helpers ───────────────────────

def _get_user_org_ids(user) -> Optional[List[int]]:
    """Вернуть список org_id активного юзера или None для SaaS-ролей."""
    return get_org_filter(user)


def _check_vehicle_visibility(vehicle: Vehicle, user) -> None:
    """403 если юзер не видит данный Vehicle (по org).

    SaaS-роли (superadmin / account_owner с org_ids=None) — bypass.
    Visibility: пересечение {owner_org_id, assigned_org_id} ∩ user.org_ids.
    """
    if user.role in ("superadmin", "account_owner"):
        return
    org_ids = _get_user_org_ids(user)
    if org_ids is None:
        return  # SaaS без выбранной org — bypass
    vehicle_orgs = {vehicle.owner_org_id}
    if vehicle.assigned_org_id:
        vehicle_orgs.add(vehicle.assigned_org_id)
    if not vehicle_orgs.intersection(org_ids):
        raise HTTPException(status_code=403, detail="Нет доступа к этому ТС")


async def _load_repair_with_vehicle(repair_id: int, db: AsyncSession) -> VehicleRepair:
    """Загрузить ремонт вместе с parent vehicle (joined) и attachments (selectin).

    Поднимает 404 если не найден.
    """
    result = await db.execute(
        select(VehicleRepair)
        .options(
            selectinload(VehicleRepair.vehicle),
            selectinload(VehicleRepair.attachments),
        )
        .where(VehicleRepair.id == repair_id)
    )
    repair = result.scalar_one_or_none()
    if repair is None:
        raise HTTPException(status_code=404, detail="Ремонт не найден")
    return repair


# ─────────────────────── Endpoints ───────────────────────

@router.get("", response_model=List[RepairOut])
async def list_repairs(
    vehicle_id: int,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    """GET /api/vehicle-repairs?vehicle_id={id}[&status=&date_from=&date_to=]

    Visibility: проверяем доступ к parent Vehicle.
    """
    # Проверяем vehicle существует + visibility
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="ТС не найдено")
    _check_vehicle_visibility(vehicle, current_user)

    q = (
        select(VehicleRepair)
        .options(selectinload(VehicleRepair.attachments))
        .where(VehicleRepair.vehicle_id == vehicle_id)
    )
    if status:
        q = q.where(VehicleRepair.status == status)
    if date_from:
        q = q.where(VehicleRepair.date >= date_from)
    if date_to:
        q = q.where(VehicleRepair.date <= date_to)
    q = q.order_by(VehicleRepair.date.desc())

    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/{repair_id}", response_model=RepairOut)
async def get_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    """GET /api/vehicle-repairs/{repair_id}"""
    repair = await _load_repair_with_vehicle(repair_id, db)
    _check_vehicle_visibility(repair.vehicle, current_user)
    return repair


@router.post("", response_model=RepairOut, status_code=201)
async def create_repair(
    body: RepairCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.repair.write")),
):
    """POST /api/vehicle-repairs — создать запись ремонта."""
    # Visibility на parent Vehicle
    vehicle = await db.get(Vehicle, body.vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="ТС не найдено")
    _check_vehicle_visibility(vehicle, current_user)

    # Валидация статуса
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_STATUS", "message": f"Допустимые статусы: {sorted(VALID_STATUSES)}"},
        )

    # D-18: если purchase_id передан — проверяем существование
    if body.purchase_id is not None:
        purchase = await db.get(Purchase, body.purchase_id)
        if purchase is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_PURCHASE_ID", "message": f"Закупка {body.purchase_id} не найдена"},
            )

    repair = VehicleRepair(
        vehicle_id=body.vehicle_id,
        date=body.date,
        description=body.description,
        cost_amount=body.cost_amount,
        performed_by_name=body.performed_by_name,
        mileage_at_repair=body.mileage_at_repair,
        status=body.status,
        purchase_id=body.purchase_id,
        created_by_id=current_user.id,
    )
    db.add(repair)
    await db.flush()

    # Reload with attachments (пустой список)
    repair = await _load_repair_with_vehicle(repair.id, db)
    await db.commit()
    return repair


@router.put("/{repair_id}", response_model=RepairOut)
async def update_repair(
    repair_id: int,
    body: RepairCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.repair.write")),
):
    """PUT /api/vehicle-repairs/{repair_id} — full update."""
    repair = await _load_repair_with_vehicle(repair_id, db)
    _check_vehicle_visibility(repair.vehicle, current_user)

    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_STATUS", "message": f"Допустимые статусы: {sorted(VALID_STATUSES)}"},
        )

    if body.purchase_id is not None:
        purchase = await db.get(Purchase, body.purchase_id)
        if purchase is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_PURCHASE_ID", "message": f"Закупка {body.purchase_id} не найдена"},
            )

    repair.date = body.date
    repair.description = body.description
    repair.cost_amount = body.cost_amount
    repair.performed_by_name = body.performed_by_name
    repair.mileage_at_repair = body.mileage_at_repair
    repair.status = body.status
    repair.purchase_id = body.purchase_id

    await db.commit()
    await db.refresh(repair)
    return repair


@router.patch("/{repair_id}", response_model=RepairOut)
async def patch_repair(
    repair_id: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.repair.write")),
):
    """PATCH /api/vehicle-repairs/{repair_id} — partial update."""
    repair = await _load_repair_with_vehicle(repair_id, db)
    _check_vehicle_visibility(repair.vehicle, current_user)

    for k, v in (body or {}).items():
        if k not in _REPAIR_PATCHABLE:
            continue
        if not hasattr(repair, k):
            continue
        v = _coerce_patch_value(k, v)

        # Валидируем статус при изменении
        if k == "status" and v not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_STATUS", "message": f"Допустимые статусы: {sorted(VALID_STATUSES)}"},
            )

        # D-18: при изменении purchase_id — проверить существование
        if k == "purchase_id" and v is not None:
            purchase = await db.get(Purchase, v)
            if purchase is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_PURCHASE_ID", "message": f"Закупка {v} не найдена"},
                )

        setattr(repair, k, v)

    await db.commit()
    await db.refresh(repair)
    return repair


@router.delete("/{repair_id}", status_code=204)
async def delete_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.delete")),
):
    """DELETE /api/vehicle-repairs/{repair_id}

    CASCADE удаляет repair_attachments через FK ON DELETE CASCADE.
    """
    repair = await _load_repair_with_vehicle(repair_id, db)
    _check_vehicle_visibility(repair.vehicle, current_user)

    await db.delete(repair)
    await db.commit()
    return None


# ─────────────────────── Cross-link helper ───────────────────────

@router.get("/by-purchase/{purchase_id}/repair-link")
async def get_repair_link_for_purchase(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    """GET /api/vehicle-repairs/by-purchase/{purchase_id}/repair-link

    D-18 helper: возвращает {repair_id, vehicle_id} первого VehicleRepair
    связанного с данной закупкой, или null если нет.
    Используется на фронте для cross-link Purchase ↔ Repair.
    """
    result = await db.execute(
        select(VehicleRepair.id, VehicleRepair.vehicle_id)
        .where(VehicleRepair.purchase_id == purchase_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        return {"repair_id": None, "vehicle_id": None}
    return {"repair_id": row[0], "vehicle_id": row[1]}
