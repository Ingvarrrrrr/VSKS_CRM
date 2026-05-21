"""
Incidents CRUD router — Phase 30-PR1.

Endpoints:
  POST   /api/incidents/              — создать
  GET    /api/incidents/              — список (vehicle_id, driver_id фильтры)
  GET    /api/incidents/{id}          — карточка
  PATCH  /api/incidents/{id}          — обновить
  PATCH  /api/incidents/{id}/resolve  — выставить resolved_at=NOW()
  DELETE /api/incidents/{id}          — удалить
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab, require_action
from app.models.incident import Incident
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentPatch, IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("/", response_model=List[IncidentOut])
async def list_incidents(
    vehicle_id: Optional[int] = Query(None),
    driver_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    q = select(Incident).order_by(Incident.created_at.desc())
    if vehicle_id:
        q = q.where(Incident.vehicle_id == vehicle_id)
    if driver_id:
        q = q.where(Incident.driver_user_id == driver_id)
    incidents = (await db.execute(q)).scalars().all()
    return [IncidentOut.model_validate(i) for i in incidents]


@router.post("/", response_model=IncidentOut, status_code=201)
async def create_incident(
    body: IncidentCreate,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    incident = Incident(**body.model_dump())
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return IncidentOut.model_validate(incident)


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Инцидент не найден")
    return IncidentOut.model_validate(inc)


@router.patch("/{incident_id}", response_model=IncidentOut)
async def patch_incident(
    incident_id: int,
    body: IncidentPatch,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Инцидент не найден")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(inc, field, value)
    await db.commit()
    await db.refresh(inc)
    return IncidentOut.model_validate(inc)


@router.patch("/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(
    incident_id: int,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Инцидент не найден")
    inc.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(inc)
    return IncidentOut.model_validate(inc)


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: int,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Инцидент не найден")
    await db.delete(inc)
    await db.commit()
