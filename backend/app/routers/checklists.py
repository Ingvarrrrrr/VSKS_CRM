"""
Checklists CRUD router — Phase 30-PR1.

Endpoints:
  GET    /api/checklists/     — список (vehicle_id, type фильтры)
  POST   /api/checklists/     — создать с items
  GET    /api/checklists/{id} — карточка
  PATCH  /api/checklists/{id} — обновить
  DELETE /api/checklists/{id} — удалить
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab, require_action
from app.models.checklist import Checklist, ChecklistItem
from app.models.user import User
from app.schemas.checklist import (
    ChecklistCreate,
    ChecklistPatch,
    ChecklistOut,
)

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


@router.get("/", response_model=List[ChecklistOut])
async def list_checklists(
    vehicle_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    q = select(Checklist)
    if vehicle_id:
        q = q.where(Checklist.vehicle_id == vehicle_id)
    if type:
        q = q.where(Checklist.type == type)
    q = q.order_by(Checklist.created_at.desc())
    checklists = (await db.execute(q)).scalars().all()
    return [ChecklistOut.model_validate(c) for c in checklists]


@router.post("/", response_model=ChecklistOut, status_code=201)
async def create_checklist(
    body: ChecklistCreate,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    checklist = Checklist(
        vehicle_id=body.vehicle_id,
        driver_user_id=body.driver_user_id,
        waybill_id=body.waybill_id,
        type=body.type,
        overall_state=body.overall_state,
        fuel_level=body.fuel_level,
        paint_condition=body.paint_condition,
        notes=body.notes,
    )
    db.add(checklist)
    await db.flush()  # get checklist.id

    for item_data in body.items:
        item = ChecklistItem(
            checklist_id=checklist.id,
            key=item_data.key,
            status=item_data.status,
            photo_url=item_data.photo_url,
            note=item_data.note,
        )
        db.add(item)

    await db.commit()
    await db.refresh(checklist)
    return ChecklistOut.model_validate(checklist)


@router.get("/{checklist_id}", response_model=ChecklistOut)
async def get_checklist(
    checklist_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    c = await db.get(Checklist, checklist_id)
    if not c:
        raise HTTPException(404, "Чеклист не найден")
    return ChecklistOut.model_validate(c)


@router.patch("/{checklist_id}", response_model=ChecklistOut)
async def patch_checklist(
    checklist_id: int,
    body: ChecklistPatch,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    c = await db.get(Checklist, checklist_id)
    if not c:
        raise HTTPException(404, "Чеклист не найден")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    await db.commit()
    await db.refresh(c)
    return ChecklistOut.model_validate(c)


@router.delete("/{checklist_id}", status_code=204)
async def delete_checklist(
    checklist_id: int,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    c = await db.get(Checklist, checklist_id)
    if not c:
        raise HTTPException(404, "Чеклист не найден")
    await db.delete(c)
    await db.commit()
