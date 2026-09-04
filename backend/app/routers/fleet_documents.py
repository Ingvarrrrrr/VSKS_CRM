"""
FleetDocuments CRUD router — Phase 30-PR1.

Endpoints:
  GET    /api/fleet-documents/summary     — сводка статусов (ПЕРЕД catch-all)
  GET    /api/fleet-documents/            — список с фильтрами
  POST   /api/fleet-documents/            — создать
  GET    /api/fleet-documents/{id}        — карточка
  PATCH  /api/fleet-documents/{id}        — обновить
  DELETE /api/fleet-documents/{id}        — удалить
  GET    /api/fleet-documents/{id}/file   — скачать bytea
"""
from __future__ import annotations

from typing import List, Optional
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab, require_action
from app.models.fleet_document import FleetDocument
from app.models.user import User
from app.schemas.fleet_document import (
    FleetDocumentCreate,
    FleetDocumentPatch,
    FleetDocumentOut,
    FleetDocumentSummary,
)

router = APIRouter(prefix="/api/fleet-documents", tags=["fleet-documents"])

VALID_TYPES = {"osago", "sts", "pts", "to", "tachograph", "fpg", "purchase_contract"}


def _compute_status(doc: FleetDocument) -> str:
    if doc.expires_at is None:
        return "no_expiry"
    today = date.today()
    if doc.expires_at < today:
        return "expired"
    if doc.expires_at <= today + timedelta(days=30):
        return "expiring_soon"
    return "valid"


@router.get("/summary", response_model=FleetDocumentSummary)
async def get_fleet_documents_summary(
    vehicle_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Сводка по документам: количество по статусам и типам."""
    q = select(FleetDocument)
    if vehicle_id:
        q = q.where(FleetDocument.vehicle_id == vehicle_id)
    docs = (await db.execute(q)).scalars().all()

    total = len(docs)
    valid = 0
    expiring_soon = 0
    expired = 0
    no_expiry = 0
    by_type: dict = {}

    for doc in docs:
        st = _compute_status(doc)
        if st == "valid":
            valid += 1
        elif st == "expiring_soon":
            expiring_soon += 1
        elif st == "expired":
            expired += 1
        else:
            no_expiry += 1
        by_type[doc.type] = by_type.get(doc.type, 0) + 1

    return FleetDocumentSummary(
        total=total,
        valid=valid,
        expiring_soon=expiring_soon,
        expired=expired,
        no_expiry=no_expiry,
        by_type=by_type,
    )


@router.get("/", response_model=List[FleetDocumentOut])
async def list_fleet_documents(
    vehicle_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="valid/expiring_soon/expired/no_expiry"),
    expires_before: Optional[date] = Query(None),
    search: Optional[str] = Query(None, alias="q", description="Phase 29.3-R3 (Д-4): поиск по brand/model/plate/vin (тот же паттерн что в /api/vehicles)"),
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    # Phase 29.3-R3 (Д-2): JOIN с Vehicle + assigned_org для plate/model/type/operator
    from app.models.vehicle import Vehicle
    from app.models.organization import Organization
    from sqlalchemy.orm import aliased

    AssignedOrg = aliased(Organization)
    q = (
        select(
            FleetDocument, Vehicle.plate, Vehicle.brand, Vehicle.model, Vehicle.type,
            AssignedOrg.name.label("op_name"), Vehicle.body_type,
        )
        .outerjoin(Vehicle, Vehicle.id == FleetDocument.vehicle_id)
        .outerjoin(AssignedOrg, AssignedOrg.id == Vehicle.assigned_org_id)
    )
    if vehicle_id:
        q = q.where(FleetDocument.vehicle_id == vehicle_id)
    if type:
        q = q.where(FleetDocument.type == type)
    if expires_before:
        q = q.where(FleetDocument.expires_at <= expires_before)
    # Phase 29.3-R3 (Д-4): поиск по brand/model/plate/vin — паттерн из /api/vehicles (строки 266-275)
    if search and search.strip():
        from sqlalchemy import or_
        pattern = f"%{search.strip()}%"
        q = q.where(or_(
            Vehicle.brand.ilike(pattern),
            Vehicle.model.ilike(pattern),
            Vehicle.plate.ilike(pattern),
            Vehicle.vin.ilike(pattern),
        ))
    rows = (await db.execute(q)).all()

    # Build response with denormalized vehicle info
    result = []
    for row in rows:
        doc = row[0]
        if status:
            if _compute_status(doc) != status:
                continue
        out = FleetDocumentOut.model_validate(doc)
        out.vehicle_plate = row[1]
        out.vehicle_model = f"{row[2] or ''} {row[3] or ''}".strip() or None
        out.vehicle_type = row[4]
        out.operator_org_name = row[5]
        out.vehicle_body_type = row[6]
        out.has_file = bool(doc.file_url or doc.file_name)
        result.append(out)
    return result


@router.post("/", response_model=FleetDocumentOut, status_code=201)
async def create_fleet_document(
    body: FleetDocumentCreate,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    doc = FleetDocument(
        **body.model_dump(exclude_none=True),
        created_by_user_id=current_user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return FleetDocumentOut.model_validate(doc)


@router.get("/{doc_id}", response_model=FleetDocumentOut)
async def get_fleet_document(
    doc_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(FleetDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    return FleetDocumentOut.model_validate(doc)


@router.patch("/{doc_id}", response_model=FleetDocumentOut)
async def patch_fleet_document(
    doc_id: int,
    body: FleetDocumentPatch,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(FleetDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(doc, field, value)
    await db.commit()
    await db.refresh(doc)
    return FleetDocumentOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_fleet_document(
    doc_id: int,
    current_user: User = Depends(require_action("vehicle.edit")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(FleetDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    await db.delete(doc)
    await db.commit()


@router.get("/{doc_id}/file")
async def download_fleet_document_file(
    doc_id: int,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Скачать файл документа (bytea)."""
    doc = await db.get(FleetDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    if not doc.file_data:
        raise HTTPException(404, "Файл не прикреплён к документу")
    filename = doc.file_name or f"document_{doc_id}.bin"
    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
