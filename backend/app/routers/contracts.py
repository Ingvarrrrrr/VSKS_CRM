from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.contract import Contract
from app.models.contract_subsidy import ContractSubsidy
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.schemas.schemas import ContractCreate, ContractOut, ContractSubsidyOut
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.models.subsidy import Subsidy
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
from datetime import date as date_type

try:
    from openpyxl import load_workbook as _load_workbook
except ImportError:
    _load_workbook = None

try:
    import pdfplumber as _pdfplumber
except ImportError:
    _pdfplumber = None

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

@router.get("/", response_model=List[ContractOut])
async def list_contracts(
    subsidy_id: Optional[int] = Query(None),
    contract_type: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contractor_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*ALL_ROLES)),
):
    q = select(Contract).options(
        selectinload(Contract.contractor),
        selectinload(Contract.subsidy),
        selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy),
    ).order_by(Contract.id.desc())
    if subsidy_id is not None:
        q = q.where(Contract.subsidy_id == subsidy_id)
    if contract_type is not None:
        q = q.where(Contract.contract_type == contract_type)
    if purchase_method is not None:
        q = q.where(Contract.purchase_method == purchase_method)
    if status is not None:
        q = q.where(Contract.status == status)
    if contractor_id is not None:
        q = q.where(Contract.contractor_id == contractor_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Contract.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q)
    contracts = result.scalars().all()
    out = []
    for c in contracts:
        # SUM(contract_price) — total ordered
        ordered_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.contract_price), 0))
            .where(Purchase.contract_id == c.id)
        )
        total_ordered = ordered_result.scalar() or Decimal("0")
        # SUM(delivery_payment_amount) — total delivered
        delivered_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
            .where(Purchase.contract_id == c.id)
        )
        total_delivered = delivered_result.scalar() or Decimal("0")
        # SUM(payment_amount) — total paid (only for paid-status purchases)
        paid_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.payment_amount), 0))
            .where(Purchase.contract_id == c.id, Purchase.status == "paid")
        )
        total_paid = paid_result.scalar() or Decimal("0")

        max_amt = c.max_amount or Decimal("0")
        d = ContractOut.model_validate(c)
        d.total_ordered = total_ordered
        d.total_delivered = total_delivered
        d.total_paid = total_paid
        d.total_payment = total_delivered  # legacy compat
        d.remaining_ordered = max_amt - total_ordered                  # сколько ещё можно заказать
        d.remaining_delivered = total_ordered - total_delivered         # заказано, но не поставлено
        d.remaining_paid = total_delivered - total_paid                 # поставлено, но не оплачено
        d.remaining = d.remaining_ordered  # legacy: now shows ordered remaining
        if c.contractor:
            d.contractor_name = c.contractor.name
            d.contractor_inn = c.contractor.inn
        if c.subsidy:
            d.subsidy_name = c.subsidy.name
        d.extra_subsidies = [
            ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
            for es in (c.extra_subsidies or [])
        ]
        out.append(d)
    return out

@router.post("/", response_model=ContractOut)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    # Duplicate check: same number + contractor + subsidy (org) + date
    if data.contractor_id and data.number:
        dup_q = select(Contract).where(
            Contract.number == data.number,
            Contract.contractor_id == data.contractor_id,
        )
        # Same org (subsidy) — different orgs can have same contract number
        if data.subsidy_id:
            dup_q = dup_q.where(Contract.subsidy_id == data.subsidy_id)
        if data.date:
            dup_q = dup_q.where(Contract.date == data.date)
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            raise HTTPException(
                409,
                f"Договор с таким номером, контрагентом и датой уже существует (ID {dup.id})"
            )
    extra_ids = data.extra_subsidy_ids or []
    dump = data.model_dump(exclude={"extra_subsidy_ids"})
    c = Contract(**dump)
    db.add(c)
    await db.flush()
    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=c.id, subsidy_id=sid))
    await db.commit()
    await db.refresh(c)
    result = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == c.id)
    )
    c = result.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return d

@router.put("/{cid}", response_model=ContractOut)
async def update_contract(cid: int, data: ContractCreate, db: AsyncSession = Depends(get_db), current_user=Depends(require_role(*MANAGER_ROLES))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    old_number = c.number
    # Duplicate check on update (exclude self, same org)
    if data.contractor_id and data.number:
        dup_q = select(Contract).where(
            Contract.number == data.number,
            Contract.contractor_id == data.contractor_id,
            Contract.id != cid,
        )
        if data.subsidy_id:
            dup_q = dup_q.where(Contract.subsidy_id == data.subsidy_id)
        if data.date:
            dup_q = dup_q.where(Contract.date == data.date)
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            raise HTTPException(409, f"Договор с таким номером и контрагентом уже существует (ID {dup.id})")
    extra_ids = data.extra_subsidy_ids or []
    for k, v in data.model_dump(exclude={"extra_subsidy_ids"}).items():
        setattr(c, k, v)
    # Sync changes to linked purchases
    if data.number != old_number or data.date is not None:
        linked = await db.execute(select(Purchase).where(Purchase.contract_id == cid))
        for p in linked.scalars().all():
            if data.number != old_number:
                p.contract_number = data.number
            if data.date is not None:
                p.contract_date = data.date
            if data.contractor_id is not None:
                p.contractor_id = data.contractor_id
    # Replace extra subsidies
    old_extras = await db.execute(select(ContractSubsidy).where(ContractSubsidy.contract_id == cid))
    for es in old_extras.scalars().all():
        await db.delete(es)
    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=cid, subsidy_id=sid))
    await db.commit()
    result2 = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == cid)
    )
    c = result2.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return d

@router.delete("/{cid}")
async def delete_contract(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role(*ADMIN_ROLES))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{cid}/merge/{target_id}")
async def merge_contracts(cid: int, target_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_role(*ADMIN_ROLES))):
    """Merge contract cid INTO target_id: move all purchases, then delete cid."""
    if cid == target_id:
        raise HTTPException(400, "Нельзя объединить договор сам с собой")
    source = (await db.execute(select(Contract).where(Contract.id == cid))).scalar_one_or_none()
    target = (await db.execute(select(Contract).where(Contract.id == target_id))).scalar_one_or_none()
    if not source or not target:
        raise HTTPException(404, "Договор не найден")
    # Move purchases from source to target
    linked = (await db.execute(select(Purchase).where(Purchase.contract_id == cid))).scalars().all()
    for p in linked:
        p.contract_id = target_id
        if target.number:
            p.contract_number = target.number
    await db.delete(source)
    await db.commit()
    return {"ok": True, "moved_purchases": len(linked)}


@router.post("/migrate-from-purchases")
async def migrate_contracts_from_purchases(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("superadmin", "account_owner", "admin")),
):
    """Create Contract records from purchases.contract_number strings (skip existing)."""
    # Get all purchases with a contract_number set but no contract_id
    q = select(Purchase).where(
        Purchase.contract_number.isnot(None),
        Purchase.contract_number != "",
    )
    result = await db.execute(q)
    purchases = result.scalars().all()

    # Existing contract numbers
    existing_result = await db.execute(select(Contract.number))
    existing_numbers = {row[0] for row in existing_result.all() if row[0]}

    created = 0
    skipped = 0
    # Map: contract_number -> new Contract (for purchases to link to)
    new_contracts: dict[str, Contract] = {}

    for p in purchases:
        num = (p.contract_number or "").strip()
        if not num:
            continue
        if num in existing_numbers or num in new_contracts:
            skipped += 1
            continue
        c = Contract(
            number=num,
            date=p.contract_date if hasattr(p, "contract_date") else None,
            contract_type="single",
            subsidy_id=p.subsidy_id,
            status="active",
        )
        db.add(c)
        new_contracts[num] = c
        created += 1

    if new_contracts:
        await db.flush()
        # Link purchases to their new contracts
        for p in purchases:
            num = (p.contract_number or "").strip()
            if num in new_contracts and p.contract_id is None:
                p.contract_id = new_contracts[num].id

    await db.commit()
    return {"created": created, "skipped": skipped}


# ── OCR helper ─────────────────────────────────────────────────────────────────

def _ocr_pdf_to_rows(content: bytes) -> tuple[list, str | None]:
    """Fallback: convert scanned PDF pages to images, run OCR, parse lines.
    Returns (rows, error_message). error_message is None on success."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."

    try:
        images = convert_from_bytes(content, dpi=300)
    except Exception as e:
        return [], f"Не удалось преобразовать PDF в изображения для OCR: {e}"

    if not images:
        return [], "PDF не содержит страниц для распознавания."

    import re
    all_rows = []
    for img in images:
        try:
            text = pytesseract.image_to_string(img, lang='rus+eng')
        except Exception as e:
            return [], f"Ошибка OCR-распознавания: {e}"
        if not text:
            continue
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Split by tabs or multiple spaces
            cells = re.split(r'\t|  {2,}', line)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)
    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None


# ── File parsing helpers ───────────────────────────────────────────────────────

_CONTRACT_HINTS = (
    'номер', 'дата', 'контрагент', 'поставщик', 'исполнитель',
    'предмет', 'сумма', 'субсидия', 'статус', 'тип', 'метод',
    'начал', 'оконч', 'number', 'date', 'contractor', 'amount',
)


def _detect_contract_hdr(rows):
    best_score, best_idx = 0, 0
    for ri, row in enumerate(rows):
        norm = [str(h).strip().lower() if h is not None else "" for h in row]
        score = sum(1 for h in norm if h and any(x in h for x in _CONTRACT_HINTS))
        if score > best_score:
            best_score = score
            best_idx = ri
    return best_idx


def _parse_contract_file(fname: str, content: bytes):
    """Parse xlsx/xls/docx/pdf and return (all_rows, hdr_idx)."""
    fname = fname.lower()

    if fname.endswith('.xls') and not fname.endswith('.xlsx'):
        try:
            import xlrd
        except ImportError:
            raise HTTPException(500, "xlrd не установлен")
        try:
            wb = xlrd.open_workbook(file_contents=content)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xls: {e}")
        ws = wb.sheet_by_index(0)
        all_rows = [list(ws.row_values(i)) for i in range(ws.nrows)]

    elif fname.endswith('.xlsx'):
        if not _load_workbook:
            raise HTTPException(500, "openpyxl не установлен")
        try:
            wb = _load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xlsx: {e}")
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

    elif fname.endswith(('.docx', '.doc')):
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(500, "python-docx не установлен")
        try:
            doc = Document(BytesIO(content))
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .docx: {e}")
        if not doc.tables:
            raise HTTPException(400, "В документе не найдено таблиц")
        tbl = doc.tables[0]
        all_rows = [[cell.text.strip() for cell in row.cells] for row in tbl.rows]

    elif fname.endswith('.pdf'):
        if not _pdfplumber:
            raise HTTPException(500, "pdfplumber не установлен")
        try:
            with _pdfplumber.open(BytesIO(content)) as pdf:
                all_rows = []
                has_text = False
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for tbl in tables:
                            all_rows.extend([r for r in tbl if r])
                if not all_rows:
                    for page in _pdfplumber.open(BytesIO(content)).pages:
                        text = page.extract_text()
                        if text:
                            has_text = True
                            for line in text.strip().split('\n'):
                                cells = [c.strip() for c in line.split('\t')]
                                if len(cells) < 2:
                                    cells = [c.strip() for c in line.split('  ') if c.strip()]
                                if cells:
                                    all_rows.append(cells)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать PDF-файл: {e}")
        if not all_rows:
            if not has_text:
                # Scanned PDF — try OCR
                all_rows, ocr_error = _ocr_pdf_to_rows(content)
                if not all_rows:
                    detail = ocr_error or "OCR не смог распознать таблицу."
                    raise HTTPException(
                        400,
                        f"Этот PDF — скан (изображение). {detail} "
                        "Попробуйте сохранить данные в Excel (.xlsx) или Word (.docx)."
                    )
            else:
                raise HTTPException(
                    400,
                    "В PDF найден текст, но не удалось распознать таблицу. "
                    "Попробуйте сохранить данные в Excel (.xlsx) и загрузить его."
                )
    else:
        raise HTTPException(400, "Неподдерживаемый формат. Используйте .xlsx, .xls, .docx, .doc или .pdf")

    if not all_rows:
        raise HTTPException(400, "Файл пустой или не содержит данных")

    hdr_idx = _detect_contract_hdr(all_rows)
    return all_rows, hdr_idx


def _parse_date(val) -> Optional[date_type]:
    if not val:
        return None
    if isinstance(val, date_type):
        return val
    s = str(val).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(val) -> Optional[Decimal]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    s = ''.join(c for c in s if c.isdigit() or c == '.')
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


# ── Import endpoints ──────────────────────────────────────────────────────────

@router.post("/import/preview")
async def contracts_import_preview(
    file: UploadFile = File(...),
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """Parse uploaded file and return headers + sample rows for column mapping UI."""
    fname = (file.filename or '').lower()
    content = await file.read()
    all_rows, hdr_idx = _parse_contract_file(fname, content)
    hdr_rows = all_rows[hdr_idx:]
    if not hdr_rows:
        raise HTTPException(400, "Файл пустой")

    headers = [
        str(c).strip() if c else f"Столбец {j + 1}"
        for j, c in enumerate(hdr_rows[0])
    ]
    sample = [
        [str(c).strip() if c is not None else "" for c in row]
        for row in hdr_rows[1:min(6, len(hdr_rows))]
    ]
    return {
        "headers": headers,
        "sample": sample,
        "total_rows": max(len(all_rows) - hdr_idx - 1, 0),
        "header_row_offset": hdr_idx,
    }


@router.post("/import/mapped")
async def contracts_import_mapped(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*MANAGER_ROLES)),
    col_number: Optional[int] = Query(None),
    col_date: Optional[int] = Query(None),
    col_contractor: Optional[int] = Query(None),
    col_subject: Optional[int] = Query(None),
    col_max_amount: Optional[int] = Query(None),
    col_start_date: Optional[int] = Query(None),
    col_end_date: Optional[int] = Query(None),
    col_contract_type: Optional[int] = Query(None),
    col_purchase_method: Optional[int] = Query(None),
    col_item_type: Optional[int] = Query(None),
    col_status: Optional[int] = Query(None),
    col_notes: Optional[int] = Query(None),
    header_row_offset: int = Query(0),
    subsidy_id: Optional[int] = Query(None),
):
    """Import contracts using user-specified column mapping."""
    if col_number is None:
        raise HTTPException(400, "Не указан столбец «Номер договора»")

    fname = (file.filename or '').lower()
    content = await file.read()
    all_rows, _ = _parse_contract_file(fname, content)
    data_rows = all_rows[header_row_offset + 1:]

    col_map = {
        'number': col_number, 'date': col_date, 'contractor': col_contractor,
        'subject': col_subject, 'max_amount': col_max_amount,
        'start_date': col_start_date, 'end_date': col_end_date,
        'contract_type': col_contract_type, 'purchase_method': col_purchase_method,
        'item_type': col_item_type, 'status': col_status, 'notes': col_notes,
    }

    def _get(row, field):
        idx = col_map.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None

    # Pre-load contractors for matching by name/INN
    ctr_result = await db.execute(select(Contractor))
    all_contractors = ctr_result.scalars().all()
    ctr_by_name = {c.name.strip().lower(): c.id for c in all_contractors if c.name}
    ctr_by_inn = {c.inn.strip(): c.id for c in all_contractors if c.inn}

    created, skipped, errors = 0, 0, []
    for ri, row in enumerate(data_rows, start=1):
        num = _get(row, 'number')
        if not num:
            continue

        # Check duplicate by number
        dup = (await db.execute(
            select(Contract.id).where(Contract.number == num).limit(1)
        )).scalar_one_or_none()
        if dup:
            skipped += 1
            continue

        # Resolve contractor
        contractor_id = None
        ctr_val = _get(row, 'contractor')
        if ctr_val:
            ctr_lower = ctr_val.lower().strip()
            contractor_id = ctr_by_name.get(ctr_lower)
            if not contractor_id:
                contractor_id = ctr_by_inn.get(ctr_val.strip())

        # Resolve contract_type
        ct_raw = (_get(row, 'contract_type') or '').lower()
        if any(x in ct_raw for x in ('рамоч', 'накопит', 'framework')):
            contract_type = 'framework_cumulative'
        elif any(x in ct_raw for x in ('разов', 'единич', 'single')):
            contract_type = 'single'
        else:
            contract_type = 'single'

        c = Contract(
            number=num,
            date=_parse_date(_get(row, 'date')),
            contract_type=contract_type,
            contractor_id=contractor_id,
            subsidy_id=subsidy_id,
            subject=_get(row, 'subject'),
            max_amount=_parse_amount(_get(row, 'max_amount')),
            start_date=_parse_date(_get(row, 'start_date')),
            end_date=_parse_date(_get(row, 'end_date')),
            purchase_method=_get(row, 'purchase_method'),
            item_type=_get(row, 'item_type'),
            status=_get(row, 'status') or 'active',
            notes=_get(row, 'notes'),
        )
        db.add(c)
        created += 1

    if created:
        await db.commit()

    return {"created": created, "skipped": skipped, "errors": errors}


# ── Non-router helper ──────────────────────────────────────────────────────────

async def ensure_contract_linked(p: Purchase, db: AsyncSession) -> None:
    """Find-or-create a Contract for this purchase and link it via purchase.contract_id.

    Uniqueness key: contract_number + contractor_id + contractor INN + contract_date.
    If any of the last 3 are absent they are simply omitted from the lookup
    (making the match less strict when data is incomplete).
    """
    num = (p.contract_number or "").strip()
    if not num:
        return

    # Already linked — sync any changed fields (date, contractor) to contract record
    if p.contract_id:
        existing = await db.get(Contract, p.contract_id)
        if existing and existing.number == num:
            if p.contract_date and existing.date != p.contract_date:
                existing.date = p.contract_date
            if p.contractor_id and existing.contractor_id != p.contractor_id:
                existing.contractor_id = p.contractor_id
            return

    # Resolve contractor INN if we have a contractor_id
    inn: Optional[str] = None
    if p.contractor_id:
        inn_row = await db.execute(
            select(Contractor.inn).where(Contractor.id == p.contractor_id)
        )
        inn = inn_row.scalar_one_or_none()

    # Build lookup query with all 4 uniqueness parameters
    q = (
        select(Contract)
        .outerjoin(Contractor, Contract.contractor_id == Contractor.id)
        .where(Contract.number == num)
    )
    if p.contractor_id:
        q = q.where(Contract.contractor_id == p.contractor_id)
    if p.contract_date:
        q = q.where(Contract.date == p.contract_date)
    if inn:
        q = q.where(Contractor.inn == inn)

    contract = (await db.execute(q)).scalar_one_or_none()

    if not contract:
        contract = Contract(
            number=num,
            date=p.contract_date,
            contract_type=p.purchase_contract_type or "single",
            contractor_id=p.contractor_id,
            subsidy_id=p.subsidy_id,
            status="active",
        )
        db.add(contract)
        await db.flush()

    p.contract_id = contract.id
