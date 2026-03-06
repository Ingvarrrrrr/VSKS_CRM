import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_file import PurchaseFile
from app.schemas.schemas import PurchaseFileOut
from app.auth.jwt import get_current_user, require_role
from typing import List

router = APIRouter(prefix="/api/purchases", tags=["purchase-files"])

UPLOAD_DIR = "/app/uploads"
ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
}


@router.post("/{pid}/files", response_model=PurchaseFileOut)
async def upload_file(
    pid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Закупка не найдена")

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Недопустимый тип файла: {file.content_type}")

    dest_dir = os.path.join(UPLOAD_DIR, str(pid))
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, file.filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = os.path.getsize(dest_path)
    pf = PurchaseFile(
        purchase_id=pid,
        filename=file.filename,
        filepath=dest_path,
        mime_type=file.content_type,
        size=size,
    )
    db.add(pf)
    await db.commit()
    await db.refresh(pf)
    return PurchaseFileOut(
        id=pf.id,
        purchase_id=pf.purchase_id,
        filename=pf.filename,
        mime_type=pf.mime_type,
        size=pf.size,
        created_at=str(pf.created_at) if pf.created_at else None,
    )


@router.get("/{pid}/files", response_model=List[PurchaseFileOut])
async def list_files(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(PurchaseFile).where(PurchaseFile.purchase_id == pid))
    files = result.scalars().all()
    return [
        PurchaseFileOut(
            id=f.id,
            purchase_id=f.purchase_id,
            filename=f.filename,
            mime_type=f.mime_type,
            size=f.size,
            created_at=str(f.created_at) if f.created_at else None,
        )
        for f in files
    ]


@router.get("/{pid}/files/{fid}/download")
async def download_file(
    pid: int,
    fid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(PurchaseFile).where(PurchaseFile.id == fid, PurchaseFile.purchase_id == pid)
    )
    pf = result.scalar_one_or_none()
    if not pf:
        raise HTTPException(404, "Файл не найден")
    if not os.path.exists(pf.filepath):
        raise HTTPException(404, "Файл не найден на диске")
    return FileResponse(
        pf.filepath,
        filename=pf.filename,
        media_type=pf.mime_type or "application/octet-stream",
    )


@router.delete("/{pid}/files/{fid}")
async def delete_file(
    pid: int,
    fid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(PurchaseFile).where(PurchaseFile.id == fid, PurchaseFile.purchase_id == pid)
    )
    pf = result.scalar_one_or_none()
    if not pf:
        raise HTTPException(404, "Файл не найден")
    if os.path.exists(pf.filepath):
        os.remove(pf.filepath)
    await db.delete(pf)
    await db.commit()
    return {"ok": True}
