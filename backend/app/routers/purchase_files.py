import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_file import PurchaseFile
from app.schemas.schemas import PurchaseFileOut
from app.auth.jwt import get_current_user
from typing import List, Optional

router = APIRouter(prefix="/api/purchases", tags=["purchase-files"])

UPLOAD_DIR = "/app/uploads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/jpg",
    "image/png",
}

# Scan — only images and PDF; editable — only Office formats
FORMAT_RULES = {
    "scan": {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    },
    "editable": {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
}

FILE_TYPES = {
    "kp":           "КП",
    "service_note": "Служебная записка",
    "protocol":     "Протокол закупки",
    "invoice":      "Счёт",
    "order":        "Приказ",
    "upd":          "УПД",
    "contract":     "Договор",
    "act":          "Акт",
    "other":        "Прочее",
}

DOC_FORMATS = {"scan", "editable"}


def _file_out(pf: PurchaseFile) -> PurchaseFileOut:
    uploaded_by_name = None
    if pf.uploaded_by:
        uploaded_by_name = pf.uploaded_by.full_name or pf.uploaded_by.username
    return PurchaseFileOut(
        id=pf.id,
        purchase_id=pf.purchase_id,
        filename=pf.filename,
        mime_type=pf.mime_type,
        size=pf.size,
        file_type=pf.file_type or "other",
        doc_format=pf.doc_format or "scan",
        created_at=pf.created_at,
        uploaded_by_id=pf.uploaded_by_id,
        uploaded_by_name=uploaded_by_name,
    )


@router.post("/{pid}/files", response_model=PurchaseFileOut)
async def upload_file(
    pid: int,
    file: UploadFile = File(...),
    file_type: Optional[str] = Form(default="other"),
    doc_format: Optional[str] = Form(default="scan"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Закупка не найдена")

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Недопустимый тип файла: {file.content_type}")

    if file_type not in FILE_TYPES:
        file_type = "other"
    if doc_format not in DOC_FORMATS:
        doc_format = "scan"

    # Validate format rules
    allowed_for_format = FORMAT_RULES.get(doc_format)
    if allowed_for_format and file.content_type not in allowed_for_format:
        if doc_format == "scan":
            raise HTTPException(400, "Скан-копии: допускаются только JPEG, PNG, PDF. Редактируемые файлы (Word, Excel) нельзя загружать как скан.")
        else:
            raise HTTPException(400, "Редактируемые документы: допускаются только Word и Excel. JPEG и PDF нельзя загружать как редактируемый файл.")

    dest_dir = os.path.join(UPLOAD_DIR, str(pid))
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, file.filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = os.path.getsize(dest_path)

    # Check file size after saving
    if size > MAX_FILE_SIZE:
        os.remove(dest_path)
        raise HTTPException(400, f"Файл превышает максимальный размер 50 МБ (загружено {size // (1024*1024)} МБ)")

    pf = PurchaseFile(
        purchase_id=pid,
        filename=file.filename,
        original_name=file.filename,
        filepath=dest_path,
        mime_type=file.content_type,
        size=size,
        file_type=file_type,
        doc_format=doc_format,
        uploaded_by_id=current_user.id,
    )
    db.add(pf)
    await db.commit()
    await db.refresh(pf)
    # Reload with relationship
    result2 = await db.execute(
        select(PurchaseFile).where(PurchaseFile.id == pf.id)
    )
    pf = result2.scalar_one()
    return _file_out(pf)


@router.patch("/{pid}/files/{fid}", response_model=PurchaseFileOut)
async def update_file_meta(
    pid: int,
    fid: int,
    file_type: Optional[str] = Form(default=None),
    doc_format: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(PurchaseFile).where(PurchaseFile.id == fid, PurchaseFile.purchase_id == pid)
    )
    pf = result.scalar_one_or_none()
    if not pf:
        raise HTTPException(404, "Файл не найден")
    if file_type is not None:
        if file_type not in FILE_TYPES:
            raise HTTPException(400, f"Неизвестный тип: {file_type}")
        pf.file_type = file_type
    if doc_format is not None:
        if doc_format not in DOC_FORMATS:
            raise HTTPException(400, f"Неизвестный формат: {doc_format}")
        pf.doc_format = doc_format
    await db.commit()
    await db.refresh(pf)
    return _file_out(pf)


@router.get("/{pid}/files", response_model=List[PurchaseFileOut])
async def list_files(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(PurchaseFile).where(PurchaseFile.purchase_id == pid))
    return [_file_out(f) for f in result.scalars().all()]


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
    return FileResponse(pf.filepath, filename=pf.filename,
                        media_type=pf.mime_type or "application/octet-stream")


@router.get("/{pid}/files/{fid}/view")
async def view_file(
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
    return FileResponse(pf.filepath, media_type=pf.mime_type or "application/octet-stream",
                        headers={"Content-Disposition": f"inline; filename=\"{pf.filename}\""})


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
