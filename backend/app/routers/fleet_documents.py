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
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    q = select(FleetDocument)
    if vehicle_id:
        q = q.where(FleetDocument.vehicle_id == vehicle_id)
    if type:
        q = q.where(FleetDocument.type == type)
    if expires_before:
        q = q.where(FleetDocument.expires_at <= expires_before)
    docs = (await db.execute(q)).scalars().all()

    # post-filter by status
    if status:
        docs = [d for d in docs if _compute_status(d) == status]

    return [FleetDocumentOut.model_validate(d) for d in docs]


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
