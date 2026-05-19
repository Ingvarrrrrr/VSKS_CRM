"""
Vehicle attachments router — Plan 29-05, Phase 29 «Автотранспорт».

Endpoints: POST upload, GET list, GET /{id}/download, GET /{id}, PATCH /{id}, DELETE /{id}
Pattern from purchase_files.py — bytea storage + SHA-256 dedup.

Decisions covered: D-07, D-11.
"""
import hashlib
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.vehicle_attachment import VehicleAttachment
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab, require_action

router = APIRouter(prefix="/api/vehicle-attachments", tags=["vehicle-attachments"])

MAX_SIZE = 25 * 1024 * 1024  # 25 MB

ALLOWED_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

VEHICLE_KIND_VALUES = {
    "sts", "pts", "osago", "kasko", "dk", "permit_to", "photo", "other"
}

POLICY_KINDS = {"osago", "kasko", "dk"}

# ── Output schema ──────────────────────────────────────────────────────────────

class VehicleAttachmentOut(BaseModel):
    id: int
    vehicle_id: int
    kind: str
    name: str
    mime: Optional[str]
    size: Optional[int]
    sha256: Optional[str]
    uploaded_at: datetime.datetime
    uploaded_by_id: Optional[int]
    policy_number: Optional[str]
    issued_at: Optional[datetime.date]
    expires_at: Optional[datetime.date]

    class Config:
        from_attributes = True


def _att_out(att: VehicleAttachment) -> VehicleAttachmentOut:
    return VehicleAttachmentOut(
        id=att.id,
        vehicle_id=att.vehicle_id,
        kind=att.kind,
        name=att.name,
        mime=att.mime,
        size=att.size,
        sha256=att.sha256,
        uploaded_at=att.uploaded_at,
        uploaded_by_id=att.uploaded_by_id,
        policy_number=att.policy_number,
        issued_at=att.issued_at,
        expires_at=att.expires_at,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_vehicle(vehicle_id: int, db: AsyncSession, user) -> Vehicle:
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "ТС не найдено"})
    _check_visibility(vehicle, user)
    return vehicle


def _check_visibility(vehicle: Vehicle, user) -> None:
    if user.role == "superadmin":
        return
    user_org = user.org_id
    if vehicle.owner_org_id != user_org and vehicle.assigned_org_id != user_org:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Нет доступа к этому ТС"})


def _coerce_date(value: Optional[str]) -> Optional[datetime.date]:
    """Parse ISO date string (YYYY-MM-DD) to date, return None if blank."""
    if not value or not value.strip():
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_DATE", "message": f"Неверный формат даты: {value!r} (ожидается YYYY-MM-DD)"},
        )


# ── POST /upload ───────────────────────────────────────────────────────────────

@router.post("/upload", response_model=VehicleAttachmentOut)
async def upload_attachment(
    vehicle_id: int = Form(...),
    kind: str = Form(default="other"),
    name: Optional[str] = Form(default=None),
    policy_number: Optional[str] = Form(default=None),
    issued_at: Optional[str] = Form(default=None),
    expires_at: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    # kind validation
    if kind not in VEHICLE_KIND_VALUES:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_KIND", "message": f"Неверный kind: {kind!r}. Допустимые: {sorted(VEHICLE_KIND_VALUES)}"},
        )

    # Visibility
    vehicle = await _get_vehicle(vehicle_id, db, current_user)

    # MIME check
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_MIME", "message": f"Недопустимый тип файла: {mime}"},
        )

    # Read bytes
    file_bytes = await file.read()
    size = len(file_bytes)
    if size > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": f"Файл превышает 25 МБ (загружено {size // (1024 * 1024)} МБ)"},
        )

    # SHA-256 dedup
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    dup_result = await db.execute(
        select(VehicleAttachment).where(
            VehicleAttachment.vehicle_id == vehicle_id,
            VehicleAttachment.sha256 == sha256,
        ).limit(1)
    )
    dup = dup_result.scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_ATTACHMENT", "message": "Файл уже загружен", "id": dup.id},
        )

    # Coerce dates
    issued_at_date = _coerce_date(issued_at)
    expires_at_date = _coerce_date(expires_at)

    # policy_* only meaningful for osago/kasko/dk — accept but don't block
    attachment_name = name or file.filename or "file"

    att = VehicleAttachment(
        vehicle_id=vehicle_id,
        kind=kind,
        name=attachment_name,
        file_data=file_bytes,
        mime=mime,
        size=size,
        sha256=sha256,
        uploaded_by_id=current_user.id,
        policy_number=policy_number if kind in POLICY_KINDS else None,
        issued_at=issued_at_date if kind in POLICY_KINDS else None,
        expires_at=expires_at_date if kind in POLICY_KINDS else None,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return _att_out(att)


# ── GET list ───────────────────────────────────────────────────────────────────

@router.get("", response_model=List[VehicleAttachmentOut])
async def list_attachments(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    await _get_vehicle(vehicle_id, db, current_user)
    result = await db.execute(
        select(VehicleAttachment)
        .where(VehicleAttachment.vehicle_id == vehicle_id)
        .order_by(VehicleAttachment.kind.asc(), VehicleAttachment.uploaded_at.desc())
    )
    return [_att_out(a) for a in result.scalars().all()]


# ── GET metadata ───────────────────────────────────────────────────────────────

@router.get("/{att_id}", response_model=VehicleAttachmentOut)
async def get_attachment(
    att_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    result = await db.execute(select(VehicleAttachment).where(VehicleAttachment.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Вложение не найдено"})
    vehicle = await db.get(Vehicle, att.vehicle_id)
    _check_visibility(vehicle, current_user)
    return _att_out(att)


# ── GET download ───────────────────────────────────────────────────────────────

@router.get("/{att_id}/download")
async def download_attachment(
    att_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("vehicles")),
):
    result = await db.execute(select(VehicleAttachment).where(VehicleAttachment.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Вложение не найдено"})
    vehicle = await db.get(Vehicle, att.vehicle_id)
    _check_visibility(vehicle, current_user)

    async def _streamer():
        yield att.file_data

    safe_name = att.name.replace('"', '_')
    return StreamingResponse(
        _streamer(),
        media_type=att.mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ── PATCH metadata ─────────────────────────────────────────────────────────────

@router.patch("/{att_id}", response_model=VehicleAttachmentOut)
async def patch_attachment(
    att_id: int,
    name: Optional[str] = Form(default=None),
    kind: Optional[str] = Form(default=None),
    policy_number: Optional[str] = Form(default=None),
    issued_at: Optional[str] = Form(default=None),
    expires_at: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    result = await db.execute(select(VehicleAttachment).where(VehicleAttachment.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Вложение не найдено"})
    vehicle = await db.get(Vehicle, att.vehicle_id)
    _check_visibility(vehicle, current_user)

    if name is not None:
        att.name = name
    if kind is not None:
        if kind not in VEHICLE_KIND_VALUES:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_KIND", "message": f"Неверный kind: {kind!r}"},
            )
        att.kind = kind
    if policy_number is not None:
        att.policy_number = policy_number
    if issued_at is not None:
        att.issued_at = _coerce_date(issued_at)
    if expires_at is not None:
        att.expires_at = _coerce_date(expires_at)

    await db.commit()
    await db.refresh(att)
    return _att_out(att)


# ── DELETE ─────────────────────────────────────────────────────────────────────

@router.delete("/{att_id}")
async def delete_attachment(
    att_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("vehicle.edit")),
):
    result = await db.execute(select(VehicleAttachment).where(VehicleAttachment.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Вложение не найдено"})
    vehicle = await db.get(Vehicle, att.vehicle_id)
    _check_visibility(vehicle, current_user)

    await db.delete(att)
    await db.commit()
    return {"ok": True}
