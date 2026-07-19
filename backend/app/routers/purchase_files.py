import os
import shutil
import hashlib
import zipfile
import re
import mimetypes
from decimal import Decimal, InvalidOperation
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_file import PurchaseFile
from app.models.contractor import Contractor
from app.schemas.schemas import PurchaseFileOut
from app.auth.jwt import get_current_user
from typing import List, Optional, Dict, Any

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


# ---------------------------------------------------------------------------
# Internal helper: store one file for bulk-upload (reuses same disk/db logic)
# ---------------------------------------------------------------------------

async def _store_purchase_file(
    db: AsyncSession,
    purchase_id: int,
    filename: str,
    data: bytes,
    file_type: str,
    doc_format: str,
    uploaded_by_id: Optional[int] = None,
) -> PurchaseFile:
    """Write bytes to disk and create a PurchaseFile record.

    Mirrors the dedup + path logic of the single-file upload endpoint.
    Does NOT commit — caller is responsible for commit.
    """
    size = len(data)
    content_hash = hashlib.sha256(data).hexdigest()

    # Disk deduplication: reuse existing file path if hash already on disk
    dup_result = await db.execute(
        select(PurchaseFile).where(PurchaseFile.content_hash == content_hash).limit(1)
    )
    dup = dup_result.scalar_one_or_none()

    if dup and dup.filepath and os.path.exists(dup.filepath):
        dest_path = dup.filepath
    else:
        dest_dir = os.path.join(UPLOAD_DIR, str(purchase_id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        with open(dest_path, "wb") as fh:
            fh.write(data)

    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"

    pf = PurchaseFile(
        purchase_id=purchase_id,
        filename=filename,
        original_name=filename,
        filepath=dest_path,
        mime_type=mime_type,
        size=size,
        file_type=file_type,
        doc_format=doc_format,
        content_hash=content_hash,
        is_active=True,
        uploaded_by_id=uploaded_by_id,
    )
    db.add(pf)
    return pf


# ---------------------------------------------------------------------------
# Helpers for bulk-upload matching
# ---------------------------------------------------------------------------

def _infer_file_type(name: str) -> str:
    """Map filename (lowercased) to one of the 9 canonical file_type keys."""
    n = name.lower()
    if "договор" in n:
        return "contract"
    if "акт" in n:
        return "act"
    if "счет" in n or "счёт" in n:
        return "invoice"
    if "упд" in n:
        return "upd"
    if "служебн" in n or " сз" in n or n.startswith("сз") or "_сз" in n:
        return "service_note"
    if "кп" in n:
        return "kp"
    if "приказ" in n:
        return "order"
    if "протокол" in n:
        return "protocol"
    return "other"


def _infer_doc_format(name: str) -> str:
    """Determine doc_format from file extension."""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    if ext in {"pdf", "jpg", "jpeg", "png", "tif", "tiff", "heic"}:
        return "scan"
    if ext in {"docx", "xlsx", "doc", "xls"}:
        return "editable"
    return "scan"


def _parse_folder_inn(folder_name: str) -> Optional[str]:
    """Extract ИНН (10 or 12 digits) from folder name. Prefer 12 digits."""
    tokens = re.findall(r"\d{10,12}", folder_name)
    twelves = [t for t in tokens if len(t) == 12]
    tens = [t for t in tokens if len(t) == 10]
    if twelves:
        return twelves[0]
    if tens:
        return tens[0]
    return None


def _parse_folder_sum(folder_name: str) -> Optional[Decimal]:
    """Extract contract sum from folder name, if present."""
    # Match numbers like 1 234 567,89 or 1234567.89 or 1 234 567
    pattern = r"(\d[\d\u00a0 ]*(?:[.,]\d+)?)"
    candidates = re.findall(pattern, folder_name)
    for raw in reversed(candidates):  # prefer rightmost / largest
        normalized = re.sub(r"[\u00a0 ]", "", raw).replace(",", ".")
        try:
            val = Decimal(normalized)
            if val > 0:
                return val
        except InvalidOperation:
            pass
    return None


def _is_hidden(path_part: str) -> bool:
    return path_part.startswith(".") or path_part == "__MACOSX"


# ---------------------------------------------------------------------------
# Bulk-upload endpoint
# ---------------------------------------------------------------------------

@router.post("/files/bulk-upload")
async def bulk_upload_scan_archive(
    subsidy_id: int = Query(..., description="ID субсидии"),
    dry_run: bool = Query(False, description="Только маппинг, без записи"),
    archive: Optional[UploadFile] = File(None, description=".zip архив"),
    files: Optional[List[UploadFile]] = File(None, description="Файлы из webkitdirectory"),
    paths: Optional[List[str]] = Form(None, description="Relative paths aligned to files"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Bulk-attach scanned documents to purchases in a subsidy.

    Two input modes:
    - Single .zip file (archive param) — unzipped in memory.
    - Multiple files + paths (files/paths params) — webkitdirectory upload.

    Folders are matched to purchases by ИНН + contract_price within the subsidy.
    Returns a mapping report. With dry_run=True nothing is written.
    """
    # ------------------------------------------------------------------
    # 1. Collect (folder_key → list[(filename, bytes)]) mapping
    # ------------------------------------------------------------------
    folder_files: Dict[str, List[tuple]] = {}  # folder_name → [(filename, data)]

    if archive is not None:
        # Mode A: zip archive
        zip_bytes = await archive.read()
        try:
            zf = zipfile.ZipFile(BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise HTTPException(400, "Файл не является корректным ZIP-архивом")

        for member in zf.infolist():
            if member.is_dir():
                continue
            parts = member.filename.replace("\\", "/").split("/")
            # Skip macOS artifacts and hidden entries
            if any(_is_hidden(p) for p in parts):
                continue
            if len(parts) < 2:
                # File at zip root — skip (no folder grouping)
                continue
            top_folder = parts[0]
            basename = parts[-1]
            if _is_hidden(basename):
                continue
            data = zf.read(member.filename)
            folder_files.setdefault(top_folder, []).append((basename, data))

    elif files:
        # Mode B: webkitdirectory — parallel lists files + paths
        if paths and len(paths) != len(files):
            raise HTTPException(400, "Количество paths не совпадает с количеством files")

        for idx, uf in enumerate(files):
            rel_path = (paths[idx] if paths else uf.filename) or uf.filename or ""
            parts = rel_path.replace("\\", "/").split("/")
            if any(_is_hidden(p) for p in parts):
                continue
            top_folder = parts[0] if len(parts) > 1 else "__root__"
            basename = parts[-1]
            data = await uf.read()
            folder_files.setdefault(top_folder, []).append((basename, data))

    else:
        raise HTTPException(400, "Необходимо передать archive (.zip) или files (webkitdirectory)")

    # ------------------------------------------------------------------
    # 2. Load all purchases for this subsidy (joined to contractor for ИНН)
    # ------------------------------------------------------------------
    stmt = (
        select(Purchase, Contractor)
        .outerjoin(Contractor, Purchase.contractor_id == Contractor.id)
        .where(Purchase.subsidy_id == subsidy_id)
    )
    rows = (await db.execute(stmt)).all()
    # Build indexed structures
    purchases_by_inn: Dict[str, List[tuple]] = {}  # inn → [(purchase, contractor)]
    for purchase, contractor in rows:
        inn = contractor.inn if contractor else None
        if inn:
            purchases_by_inn.setdefault(inn, []).append((purchase, contractor))

    # ------------------------------------------------------------------
    # 3. Match folders → purchases, collect report
    # ------------------------------------------------------------------
    attached_count = 0
    skipped_count = 0
    folder_reports = []

    for folder_name, file_list in folder_files.items():
        inn = _parse_folder_inn(folder_name)
        _sum_source = folder_name.replace(inn, " ", 1) if inn else folder_name
        folder_sum = _parse_folder_sum(_sum_source)

        entry: Dict[str, Any] = {
            "folder": folder_name,
            "inn": inn,
            "sum": str(folder_sum) if folder_sum is not None else None,
            "purchase_id": None,
            "contract_number": None,
            "files": [
                {
                    "name": fname,
                    "file_type": _infer_file_type(fname),
                    "doc_format": _infer_doc_format(fname),
                }
                for fname, _ in file_list
            ],
            "status": "skipped",
        }

        if inn is None:
            entry["reason"] = "ИНН не распознан в имени папки"
            skipped_count += 1
            folder_reports.append(entry)
            continue

        candidates = purchases_by_inn.get(inn, [])

        if not candidates:
            entry["reason"] = f"нет закупки с ИНН {inn}"
            skipped_count += 1
            folder_reports.append(entry)
            continue

        # Try to narrow by contract_price if sum was found
        matched = candidates
        if folder_sum is not None:
            price_matches = [
                (p, c) for p, c in candidates
                if p.contract_price is not None
                and abs(Decimal(str(p.contract_price)) - folder_sum) < Decimal("1")
            ]
            if price_matches:
                matched = price_matches
            # else fall back to ИНН-only match (matched stays as candidates)

        if len(matched) > 1:
            entry["reason"] = f"неоднозначно: {len(matched)} закупок"
            skipped_count += 1
            folder_reports.append(entry)
            continue

        # Exactly 1 match
        purchase, contractor = matched[0]
        entry["purchase_id"] = purchase.id
        entry["contract_number"] = getattr(purchase, "contract_number", None)
        entry["status"] = "attached"

        if not dry_run:
            for fname, fdata in file_list:
                ft = _infer_file_type(fname)
                df = _infer_doc_format(fname)
                await _store_purchase_file(
                    db=db,
                    purchase_id=purchase.id,
                    filename=fname,
                    data=fdata,
                    file_type=ft,
                    doc_format=df,
                    uploaded_by_id=current_user.id,
                )
            await db.commit()

        attached_count += 1
        folder_reports.append(entry)

    return {
        "dry_run": dry_run,
        "attached": attached_count,
        "skipped": skipped_count,
        "folders": folder_reports,
    }


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
