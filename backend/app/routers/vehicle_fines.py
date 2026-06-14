"""
VehicleFine CRUD router — Phase 29.3-fines.

Endpoints:
  POST   /api/vehicle-fines/            — создать штраф + авто-матч по trip date
  GET    /api/vehicle-fines/            — список штрафов (vehicle_id обязателен)
  GET    /api/vehicle-fines/{id}        — один штраф
  PATCH  /api/vehicle-fines/{id}        — обновить (status, поля)
  DELETE /api/vehicle-fines/{id}        — удалить
  POST   /api/vehicle-fines/{id}/rematch — пересчитать матч по trip

Permission: require_tab('vehicles') для всех.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.auth.jwt import get_org_filter
from app.models.user import User
from app.models.vehicle_fine import VehicleFine
from app.models.trip import Trip
from app.schemas.vehicle_fine import VehicleFineCreate, VehicleFinePatch, VehicleFineOut

router = APIRouter(prefix="/api/vehicle-fines", tags=["vehicle-fines"])


# ─────────────────────────────── helpers ────────────────────────────────────

def _resolve_driver(fine: VehicleFine) -> tuple[Optional[str], str]:
    """Return (driver_name, driver_kind) from a fine instance."""
    if fine.driver_user_id and fine.driver_user:
        return getattr(fine.driver_user, "full_name", None), "user"
    if fine.driver_external_id and fine.driver_external:
        return getattr(fine.driver_external, "full_name", None), "external"
    return None, "unmatched"


def _fine_to_out(fine: VehicleFine) -> VehicleFineOut:
    driver_name, driver_kind = _resolve_driver(fine)
    veh = getattr(fine, "vehicle", None)
    return VehicleFineOut(
        id=fine.id,
        vehicle_id=fine.vehicle_id,
        issued_at=fine.issued_at,
        amount=fine.amount,
        doc_number=fine.doc_number,
        violation_type=fine.violation_type,
        location=fine.location,
        status=fine.status,
        paid_at=fine.paid_at,
        comment=fine.comment,
        driver_user_id=fine.driver_user_id,
        driver_external_id=fine.driver_external_id,
        matched_trip_id=fine.matched_trip_id,
        created_at=fine.created_at,
        created_by_id=fine.created_by_id,
        driver_name=driver_name,
        driver_kind=driver_kind,
        has_photo=bool(fine.photo_data),
        vehicle_plate=veh.plate if veh else None,
        vehicle_brand_model=(f"{veh.brand or ''} {veh.model or ''}".strip() if veh else None),
    )


async def _match_trip(
    db: AsyncSession,
    vehicle_id: int,
    issued_at: datetime,
) -> Optional[Trip]:
    """Find a Trip for the vehicle on the calendar day of issued_at (UTC date)."""
    day = issued_at.astimezone(timezone.utc).date() if issued_at.tzinfo else issued_at.date()
    result = await db.execute(
        select(Trip)
        .where(Trip.vehicle_id == vehicle_id, Trip.date == day)
        .limit(1)
    )
    return result.scalars().first()


def _apply_match(fine: VehicleFine, trip: Optional[Trip]) -> None:
    """Copy driver snapshot from trip onto fine."""
    if trip:
        fine.matched_trip_id = trip.id
        fine.driver_user_id = trip.driver_user_id
        fine.driver_external_id = trip.driver_external_id
    else:
        fine.matched_trip_id = None
        fine.driver_user_id = None
        fine.driver_external_id = None


# ─────────────────────────────── endpoints ──────────────────────────────────

@router.post("/", response_model=VehicleFineOut, status_code=201)
async def create_fine(
    body: VehicleFineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Создать штраф и выполнить авто-матч по путевому листу на дату штрафа."""
    fine = VehicleFine(
        vehicle_id=body.vehicle_id,
        issued_at=body.issued_at,
        amount=body.amount,
        doc_number=body.doc_number,
        violation_type=body.violation_type,
        location=body.location,
        comment=body.comment,
        status="unpaid",
        created_by_id=current_user.id,
    )
    # Авто-матч по trip
    trip = await _match_trip(db, body.vehicle_id, body.issued_at)
    _apply_match(fine, trip)

    db.add(fine)
    await db.flush()
    await db.refresh(fine)
    await db.commit()
    await db.refresh(fine)
    return _fine_to_out(fine)


@router.get("/", response_model=List[VehicleFineOut])
async def list_fines(
    vehicle_id: Optional[int] = Query(None, description="Фильтр по ТС (опционально)"),
    driver_user_id: Optional[int] = Query(None, description="Фильтр по водителю User.id"),
    driver_external_id: Optional[int] = Query(None, description="Фильтр по внешнему водителю"),
    org_id: Optional[int] = Query(None, description="Фильтр по филиалу (Vehicle.owner_org_id)"),
    status: Optional[str] = Query(None, description="Фильтр по статусу: unpaid/paid/disputed"),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Список штрафов. Без фильтров — все штрафы (для /fleet/fines страницы)."""
    from sqlalchemy.orm import selectinload
    from app.models.vehicle import Vehicle
    q = select(VehicleFine).options(selectinload(VehicleFine.vehicle))
    if vehicle_id is not None:
        q = q.where(VehicleFine.vehicle_id == vehicle_id)
    if driver_user_id is not None:
        q = q.where(VehicleFine.driver_user_id == driver_user_id)
    if driver_external_id is not None:
        q = q.where(VehicleFine.driver_external_id == driver_external_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None or org_id is not None:
        q = q.join(Vehicle, Vehicle.id == VehicleFine.vehicle_id)
        if org_ids is not None:
            q = q.where(Vehicle.owner_org_id.in_(org_ids))
        if org_id is not None:
            q = q.where(Vehicle.owner_org_id == org_id)
    if status:
        q = q.where(VehicleFine.status == status)
    q = q.order_by(VehicleFine.issued_at.desc()).limit(limit)
    result = await db.execute(q)
    fines = result.scalars().all()
    return [_fine_to_out(f) for f in fines]


@router.get("/{fine_id}/photo")
async def get_fine_photo(
    fine_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Phase 29.3-R3 (pt9): отдать фото штрафа (из ГИБДД API импорта)."""
    from fastapi import HTTPException
    from fastapi.responses import Response
    fine = (await db.execute(
        select(VehicleFine).where(VehicleFine.id == fine_id)
    )).scalar_one_or_none()
    if not fine or not fine.photo_data:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    return Response(content=bytes(fine.photo_data), media_type=fine.photo_mime or "image/jpeg")


@router.get("/{fine_id}", response_model=VehicleFineOut)
async def get_fine(
    fine_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    result = await db.execute(select(VehicleFine).where(VehicleFine.id == fine_id))
    fine = result.scalars().first()
    if not fine:
        raise HTTPException(status_code=404, detail="Штраф не найден")
    return _fine_to_out(fine)


@router.patch("/{fine_id}", response_model=VehicleFineOut)
async def patch_fine(
    fine_id: int,
    body: VehicleFinePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    result = await db.execute(select(VehicleFine).where(VehicleFine.id == fine_id))
    fine = result.scalars().first()
    if not fine:
        raise HTTPException(status_code=404, detail="Штраф не найден")

    needs_rematch = False
    data = body.model_dump(exclude_unset=True)

    # Если изменилась дата — нужен re-match
    if "issued_at" in data and data["issued_at"] != fine.issued_at:
        needs_rematch = True

    for field, value in data.items():
        setattr(fine, field, value)

    # Авто-установка paid_at при переводе в статус paid
    if data.get("status") == "paid" and fine.paid_at is None:
        fine.paid_at = datetime.now(timezone.utc)

    if needs_rematch:
        trip = await _match_trip(db, fine.vehicle_id, fine.issued_at)
        _apply_match(fine, trip)

    await db.flush()
    await db.refresh(fine)
    await db.commit()
    await db.refresh(fine)
    return _fine_to_out(fine)


@router.delete("/{fine_id}", status_code=204)
async def delete_fine(
    fine_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    result = await db.execute(select(VehicleFine).where(VehicleFine.id == fine_id))
    fine = result.scalars().first()
    if not fine:
        raise HTTPException(status_code=404, detail="Штраф не найден")
    await db.delete(fine)
    await db.commit()


@router.post("/{fine_id}/rematch", response_model=VehicleFineOut)
async def rematch_fine(
    fine_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Пересчитать матч водителя по путевому листу (если путёвка создана позже штрафа)."""
    result = await db.execute(select(VehicleFine).where(VehicleFine.id == fine_id))
    fine = result.scalars().first()
    if not fine:
        raise HTTPException(status_code=404, detail="Штраф не найден")

    trip = await _match_trip(db, fine.vehicle_id, fine.issued_at)
    _apply_match(fine, trip)

    await db.flush()
    await db.refresh(fine)
    await db.commit()
    await db.refresh(fine)
    return _fine_to_out(fine)
