"""
Vehicle passes router — произвольный набор пропусков ТС (владелец, 2026-09).

Заменяет 10 фиксированных колонок vehicles.pass_* (см. AUTOBLOCK_FIELDS_SPEC.md
§1 / app/models/vehicle_pass.py) — у каждой машины может быть свой набор
пропусков с произвольным названием (не enum), потому что разные организации
заводят разные зоны/пропуска.

Endpoints:
  GET    /api/vehicle-passes?vehicle_id={id}     — список пропусков машины
  POST   /api/vehicle-passes                      — добавить пропуск
  PATCH  /api/vehicle-passes/{pass_id}            — изменить пропуск
  DELETE /api/vehicle-passes/{pass_id}            — удалить пропуск
  POST   /api/vehicle-passes/copy                 — скопировать набор с другой машины

Права — везде require_action('vehicle.edit') (то же право, что на редактирование
карточки ТС) — задание владельца прямо это указывает для ВСЕХ операций с
пропусками, включая удаление (не 'vehicle.delete', которое в этом проекте
зарезервировано за удалением самой карточки ТС).

Copy (POST /copy): по умолчанию (replace=False) — MERGE: пропуска источника
накладываются на пропуска цели по имени (совпадающее имя — значения источника
перезаписывают цель; пропуска цели, которых нет у источника, НЕ удаляются).
replace=True — поведение «заменить»: сначала все пропуска цели удаляются,
затем копируется полный набор источника. Merge выбран поведением по умолчанию,
чтобы случайный вызов копирования не стёр то, что уже было заведено вручную на
целевой машине.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_org_filter
from app.auth.permissions import require_action, require_tab
from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.vehicle_pass import VehiclePass
from app.schemas.vehicle import (
    VehiclePassCopyRequest,
    VehiclePassCreate,
    VehiclePassOut,
    VehiclePassPatch,
)

router = APIRouter(prefix="/api/vehicle-passes", tags=["vehicles"])

_PASS_PATCHABLE = {"name", "status", "expires_at", "note"}


def _check_vehicle_visibility(vehicle: Vehicle, user) -> None:
    """403, если пользователь не видит данный Vehicle (та же логика, что и в
    других sub-resource роутерах ТС — app/routers/vehicle_repairs.py)."""
    if user.role in ("superadmin", "account_owner"):
        return
    org_ids = get_org_filter(user)
    if org_ids is None:
        return
    vehicle_orgs = {vehicle.owner_org_id}
    if vehicle.assigned_org_id:
        vehicle_orgs.add(vehicle.assigned_org_id)
    if not vehicle_orgs.intersection(org_ids):
        raise HTTPException(status_code=403, detail="Нет доступа к этому ТС")


async def _get_vehicle_or_404(db: AsyncSession, vehicle_id: int) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="ТС не найдено")
    return vehicle


@router.get("", response_model=List[VehiclePassOut])
async def list_vehicle_passes(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    """GET /api/vehicle-passes?vehicle_id={id} — список пропусков машины."""
    vehicle = await _get_vehicle_or_404(db, vehicle_id)
    _check_vehicle_visibility(vehicle, current_user)
    rows = (await db.execute(
        select(VehiclePass).where(VehiclePass.vehicle_id == vehicle_id).order_by(VehiclePass.name)
    )).scalars().all()
    return rows


@router.post("", response_model=VehiclePassOut, status_code=201)
async def create_vehicle_pass(
    body: VehiclePassCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    """POST /api/vehicle-passes — добавить пропуск машине."""
    vehicle = await _get_vehicle_or_404(db, body.vehicle_id)
    _check_vehicle_visibility(vehicle, current_user)

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название пропуска не может быть пустым")

    existing = (await db.execute(
        select(VehiclePass).where(VehiclePass.vehicle_id == body.vehicle_id, VehiclePass.name == name)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"У этой машины уже есть пропуск «{name}» — измените существующий вместо создания нового.",
        )

    vp = VehiclePass(
        vehicle_id=body.vehicle_id,
        name=name,
        status=body.status,
        expires_at=body.expires_at,
        note=body.note,
    )
    db.add(vp)
    await db.commit()
    await db.refresh(vp)
    return vp


@router.patch("/{pass_id}", response_model=VehiclePassOut)
async def patch_vehicle_pass(
    pass_id: int,
    body: VehiclePassPatch,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    """PATCH /api/vehicle-passes/{pass_id} — изменить пропуск (частично)."""
    vp = await db.get(VehiclePass, pass_id)
    if vp is None:
        raise HTTPException(status_code=404, detail="Пропуск не найден")
    vehicle = await _get_vehicle_or_404(db, vp.vehicle_id)
    _check_vehicle_visibility(vehicle, current_user)

    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        new_name = (data["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="Название пропуска не может быть пустым")
        if new_name != vp.name:
            dup = (await db.execute(
                select(VehiclePass).where(
                    VehiclePass.vehicle_id == vp.vehicle_id, VehiclePass.name == new_name
                )
            )).scalar_one_or_none()
            if dup is not None:
                raise HTTPException(
                    status_code=409, detail=f"У этой машины уже есть пропуск «{new_name}»."
                )
        data["name"] = new_name

    for k, v in data.items():
        if k in _PASS_PATCHABLE:
            setattr(vp, k, v)

    await db.commit()
    await db.refresh(vp)
    return vp


@router.delete("/{pass_id}", status_code=204)
async def delete_vehicle_pass(
    pass_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    """DELETE /api/vehicle-passes/{pass_id} — удалить пропуск."""
    vp = await db.get(VehiclePass, pass_id)
    if vp is None:
        raise HTTPException(status_code=404, detail="Пропуск не найден")
    vehicle = await _get_vehicle_or_404(db, vp.vehicle_id)
    _check_vehicle_visibility(vehicle, current_user)

    await db.delete(vp)
    await db.commit()
    return None


@router.post("/copy", response_model=List[VehiclePassOut])
async def copy_vehicle_passes(
    body: VehiclePassCopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    """POST /api/vehicle-passes/copy — скопировать набор пропусков между машинами.

    См. поведение merge/replace в docstring модуля.
    """
    if body.source_vehicle_id == body.target_vehicle_id:
        raise HTTPException(status_code=422, detail="Источник и цель копирования пропусков совпадают")

    source = await _get_vehicle_or_404(db, body.source_vehicle_id)
    target = await _get_vehicle_or_404(db, body.target_vehicle_id)
    _check_vehicle_visibility(source, current_user)
    _check_vehicle_visibility(target, current_user)

    source_passes = (await db.execute(
        select(VehiclePass).where(VehiclePass.vehicle_id == source.id)
    )).scalars().all()

    if body.replace:
        target_passes = (await db.execute(
            select(VehiclePass).where(VehiclePass.vehicle_id == target.id)
        )).scalars().all()
        for tp in target_passes:
            await db.delete(tp)
        await db.flush()
        for sp in source_passes:
            db.add(VehiclePass(
                vehicle_id=target.id, name=sp.name, status=sp.status,
                expires_at=sp.expires_at, note=sp.note,
            ))
    else:
        existing_by_name = {
            p.name: p
            for p in (await db.execute(
                select(VehiclePass).where(VehiclePass.vehicle_id == target.id)
            )).scalars().all()
        }
        for sp in source_passes:
            tp = existing_by_name.get(sp.name)
            if tp is None:
                db.add(VehiclePass(
                    vehicle_id=target.id, name=sp.name, status=sp.status,
                    expires_at=sp.expires_at, note=sp.note,
                ))
            else:
                tp.status = sp.status
                tp.expires_at = sp.expires_at
                tp.note = sp.note

    await db.commit()

    rows = (await db.execute(
        select(VehiclePass).where(VehiclePass.vehicle_id == target.id).order_by(VehiclePass.name)
    )).scalars().all()
    return rows
