import os
import shutil
import hashlib
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select, func
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
        content_hash=pf.content_hash,
        is_active=pf.is_active if pf.is_active is not None else True,
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

    # Read file into memory for hashing and size check
    contents = await file.read()
    size = len(contents)

    if size > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл превышает максимальный размер 50 МБ (загружено {size // (1024*1024)} МБ)")

    # Content-based deduplication
    content_hash = hashlib.sha256(contents).hexdigest()

    # Check if this exact file already exists in THIS purchase
    same_purchase_dup = await db.execute(
        select(PurchaseFile).where(
            PurchaseFile.purchase_id == pid,
            PurchaseFile.content_hash == content_hash,
        ).limit(1)
    )
    if same_purchase_dup.scalar_one_or_none():
        raise HTTPException(409, "Этот файл уже загружен в данную закупку (идентичное содержимое)")

    # Check if file with same hash exists anywhere (for disk dedup)
    dup_result = await db.execute(
        select(PurchaseFile).where(PurchaseFile.content_hash == content_hash).limit(1)
    )
    dup = dup_result.scalar_one_or_none()

    if dup and dup.filepath and os.path.exists(dup.filepath):
        # Reuse existing file on disk
        dest_path = dup.filepath
    else:
        # Write new file to disk
        dest_dir = os.path.join(UPLOAD_DIR, str(pid))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file.filename)
        with open(dest_path, "wb") as f:
            f.write(contents)

    # Deactivate other files of same type in this purchase
    await db.execute(
        PurchaseFile.__table__.update()
        .where(
            PurchaseFile.purchase_id == pid,
            PurchaseFile.file_type == file_type,
            PurchaseFile.is_active == True,
        )
        .values(is_active=False)
    )

    pf = PurchaseFile(
        purchase_id=pid,
        filename=file.filename,
        original_name=file.filename,
        filepath=dest_path,
        mime_type=file.content_type,
        size=size,
        file_type=file_type,
        doc_format=doc_format,
        content_hash=content_hash,
        is_active=True,
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
    is_active: Optional[str] = Form(default=None),
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
    if is_active is not None:
        pf.is_active = is_active.lower() in ('true', '1', 'yes')
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


async def _try_regen_receipt_png(db, pid: int, fid: int, pf) -> bool:
    """Phase 27.1.11: regenerate PNG receipt file from raw_json if file is missing on disk.
    Returns True if file was successfully regenerated. Idempotent."""
    try:
        from app.routers.purchase_receipts import _render_receipt_png
        from app.models.purchase_receipt import PurchaseReceipt as _PR
        from app.models.purchase import Purchase as _P
        from sqlalchemy import select as _s
        p_row = (await db.execute(_s(_P).where(_P.id == pid))).scalar_one_or_none()
        if p_row and p_row.acceptance_docs:
            for ad in p_row.acceptance_docs:
                if ad.get("file_id") == fid and ad.get("receipt_id"):
                    rcpt = await db.get(_PR, ad["receipt_id"])
                    if rcpt:
                        png_bytes = _render_receipt_png(rcpt)
                        os.makedirs(os.path.dirname(pf.filepath), exist_ok=True)
                        with open(pf.filepath, 'wb') as _f:
                            _f.write(png_bytes)
                        return True
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(f"regen receipt PNG failed pid={pid} fid={fid}: {_e}")
    return False


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
        # Phase 27.1.11: fallback — regenerate PNG from receipt raw_json if missing
        if pf.file_type == 'acceptance_doc' and pf.mime_type == 'image/png':
            await _try_regen_receipt_png(db, pid, fid, pf)
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
        # Phase 27.1.11: fallback — regenerate PNG from receipt raw_json if missing
        if pf.file_type == 'acceptance_doc' and pf.mime_type == 'image/png':
            await _try_regen_receipt_png(db, pid, fid, pf)
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
    # Only delete file from disk if no other records reference it
    ref_count = (await db.execute(
        select(func.count(PurchaseFile.id)).where(
            PurchaseFile.filepath == pf.filepath, PurchaseFile.id != pf.id
        )
    )).scalar()
    await db.delete(pf)
    await db.commit()
    if ref_count == 0 and os.path.exists(pf.filepath):
        os.remove(pf.filepath)
    return {"ok": True}
