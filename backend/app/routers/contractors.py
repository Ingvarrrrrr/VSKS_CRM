from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.contractor import Contractor
from app.schemas.schemas import ContractorCreate, ContractorOut
from app.auth.jwt import require_role, get_current_user, get_org_filter, get_single_org_id, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.models.user import User
from typing import List, Optional
from io import BytesIO

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    import pdfplumber as _pdfplumber
except ImportError:
    _pdfplumber = None

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


# ---------------------------------------------------------------------------
# Shared file parsing helpers
# ---------------------------------------------------------------------------

_CONTRACTOR_HINTS = (
    'назван', 'наимен', 'инн', 'inn', 'кпп', 'огрн', 'адрес',
    'email', 'телефон', 'банк', 'бик', 'контакт', 'подписант',
)


def _detect_hdr(rows):
    """Return index of the row most likely to be a header row."""
    best_score, best_idx = 0, 0
    for ri, row in enumerate(rows):
        norm = [str(h).strip().lower() if h is not None else "" for h in row]
        score = sum(1 for h in norm if h and any(x in h for x in _CONTRACTOR_HINTS))
        if score > best_score:
            best_score = score
            best_idx = ri
    return best_idx


def _parse_file_to_rows(fname: str, content: bytes):
    """Parse xlsx/xls/docx/doc/pdf and return (all_rows, hdr_idx)."""
    fname = fname.lower()

    if fname.endswith('.xls') and not fname.endswith('.xlsx'):
        try:
            import xlrd as _xlrd_mod
        except ImportError:
            raise HTTPException(500, "xlrd не установлен")
        try:
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xls файл: {e}")
        ws_xls = wb_xls.sheet_by_index(0)
        all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]

    elif fname.endswith('.xlsx'):
        if not load_workbook:
            raise HTTPException(500, "openpyxl не установлен")
        try:
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xlsx файл: {e}")
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
            raise HTTPException(400, f"Не удалось прочитать .docx файл: {e}")
        if not doc.tables:
            raise HTTPException(400, "В документе .docx не найдено таблиц")
        tbl = doc.tables[0]
        all_rows = [[cell.text.strip() for cell in row.cells] for row in tbl.rows]

    elif fname.endswith('.pdf'):
        if not _pdfplumber:
            raise HTTPException(500, "pdfplumber не установлен")
        try:
            with _pdfplumber.open(BytesIO(content)) as pdf:
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for tbl in tables:
                            all_rows.extend([r for r in tbl if r])
                # Fallback: if no tables found, try extracting text lines
                if not all_rows:
                    for page in _pdfplumber.open(BytesIO(content)).pages:
                        text = page.extract_text()
                        if text:
                            for line in text.strip().split('\n'):
                                cells = [c.strip() for c in line.split('\t')]
                                if len(cells) < 2:
                                    cells = [c.strip() for c in line.split('  ') if c.strip()]
                                if cells:
                                    all_rows.append(cells)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .pdf файл: {e}")
        if not all_rows:
            raise HTTPException(400, "В PDF не найдено таблиц. Попробуйте Excel формат.")

    else:
        raise HTTPException(400, "Неподдерживаемый формат файла. Используйте .xlsx, .xls, .docx, .doc или .pdf")

    if not all_rows:
        raise HTTPException(400, "Файл пустой или не содержит данных")

    hdr_idx = _detect_hdr(all_rows)
    return all_rows, hdr_idx


@router.get("/product-categories")
async def list_all_product_categories(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """All unique product categories from products + manual contractor categories."""
    from app.models.product import Product
    # From products table
    prod_res = await db.execute(
        select(distinct(Product.category))
        .where(Product.category.isnot(None), Product.category != '')
    )
    cats = {r[0] for r in prod_res}
    # From manual contractor categories
    ctr_res = await db.execute(
        select(Contractor.manual_product_categories)
        .where(Contractor.manual_product_categories.isnot(None))
    )
    for row in ctr_res:
        for c in (row[0] or []):
            if c and c != 'Все':
                cats.add(c)
    return sorted(cats)


@router.get("/with-stats")
async def list_contractors_with_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contractors with product categories derived from purchase_items → products."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product

    q = select(Contractor).order_by(Contractor.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Contractor.org_id.in_(org_ids))
    contractors = (await db.execute(q)).scalars().all()

    # Product categories per contractor: purchase → purchase_items → product.category
    prod_stmt = (
        select(
            Purchase.contractor_id,
            func.array_agg(distinct(Product.category)).label("product_categories"),
        )
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .join(Product, Product.id == PurchaseItem.product_id)
        .where(Purchase.contractor_id.isnot(None))
        .where(Product.category.isnot(None))
        .where(Product.category != '')
        .group_by(Purchase.contractor_id)
    )
    prod_rows = (await db.execute(prod_stmt)).all()
    prod_cat_map = {
        row.contractor_id: [x for x in (row.product_categories or []) if x]
        for row in prod_rows
    }

    result = []
    for c in contractors:
        c_dict = ContractorOut.model_validate(c).model_dump()
        manual = c.manual_product_categories or []
        auto = prod_cat_map.get(c.id, [])
        # "Все" = special marker meaning all categories
        if "Все" in manual:
            c_dict["product_categories"] = ["Все"]
        else:
            merged = list(dict.fromkeys(manual + auto))  # deduplicate, keep order
            c_dict["product_categories"] = merged
        result.append(c_dict)
    return result


@router.get("/", response_model=List[ContractorOut])
async def list_contractors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search: str = None,
):
    q = select(Contractor).order_by(Contractor.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Contractor.org_id.in_(org_ids))
    if search:
        q = q.where(Contractor.name.ilike(f"%{search}%") | Contractor.inn.ilike(f"%{search}%"))
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=ContractorOut)
async def create_contractor(
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALL_ROLES)),
):
    d = data.model_dump()
    d['org_id'] = get_single_org_id(current_user) or current_user.org_id
    c = Contractor(**d)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.patch("/{cid}/email", response_model=ContractorOut)
async def patch_contractor_email(
    cid: int,
    email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ALL_ROLES)),
):
    c = (await db.execute(select(Contractor).where(Contractor.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    c.email = email
    await db.commit()
    await db.refresh(c)
    return c


@router.put("/{cid}", response_model=ContractorOut)
async def update_contractor(
    cid: int,
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ALL_ROLES))
):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/bulk")
async def bulk_delete_contractors(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES))
):
    from app.models.purchase import Purchase
    ids = payload.get("ids", [])
    if not ids:
        return {"deleted": 0, "skipped_linked": 0, "skipped_not_found": 0}

    # IDs referenced in purchases — cannot delete
    linked_result = await db.execute(
        select(Purchase.contractor_id).where(Purchase.contractor_id.in_(ids)).distinct()
    )
    linked_ids = {r[0] for r in linked_result}

    safe_ids = [i for i in ids if i not in linked_ids]

    result = await db.execute(select(Contractor).where(Contractor.id.in_(safe_ids)))
    contractors_found = result.scalars().all()
    for c in contractors_found:
        await db.delete(c)
    await db.commit()

    return {
        "deleted": len(contractors_found),
        "skipped_linked": len(linked_ids),
        "skipped_not_found": len(safe_ids) - len(contractors_found),
    }


@router.delete("/{cid}")
async def delete_contractor(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES))
):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.get("/import/template")
async def contractors_import_template(_=Depends(require_role(*MANAGER_ROLES))):
    """Download xlsx template for bulk contractor import."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "Контрагенты"

    headers = [
        "Наименование", "ИНН", "КПП", "ОГРН",
        "Адрес местонахождения", "Почтовый адрес",
        "Подписант", "Основание",
        "Контактное лицо", "Телефон", "Email",
        "Расчётный счёт", "Банк", "БИК", "Корр. счёт",
        "Банковские реквизиты",
    ]
    required = {"Наименование", "ИНН"}

    header_fill = PatternFill("solid", fgColor="1E40AF")
    req_fill    = PatternFill("solid", fgColor="1D4ED8")
    header_font = Font(bold=True, color="FFFFFF")

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = req_fill if h in required else header_fill
        cell.alignment = Alignment(horizontal="center")

    # Example row
    example = [
        "ООО Пример", "1234567890", "123456789", "1234567890123",
        "г. Москва, ул. Примерная, д. 1", "г. Москва, ул. Почтовая, д. 2",
        "Иванов Иван Иванович, Генеральный директор", "Устава",
        "Петров Пётр Петрович", "+7 (999) 000-00-00", "example@mail.ru",
        "40702810000000000000", "ПАО Сбербанк", "044525225", "30101810400000000225",
        "",
    ]
    for ci, val in enumerate(example, 1):
        ws.cell(row=2, column=ci, value=val)

    col_widths = [35, 14, 12, 16, 40, 40, 45, 20, 30, 20, 25, 24, 30, 12, 24, 35]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contractors_template.xlsx"},
    )


@router.post("/import/excel")
async def import_contractors_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ALL_ROLES))
):
    """Bulk import contractors from Excel. First row must be headers."""
    if not (file.filename or '').lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx / .xls")

    if not load_workbook:
        raise HTTPException(500, "openpyxl не установлен")

    content = await file.read()
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    ws = wb.active

    # Detect header row
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise HTTPException(400, "Файл пустой")

    def _norm(v) -> str:
        return str(v).strip().lower() if v else ''

    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        h_str = _norm(h)
        if any(x in h_str for x in ('назван', 'наимен', 'name', 'органи')):
            col.setdefault('name', i)
        elif any(x in h_str for x in ('инн', 'inn', 'идентиф')):
            col.setdefault('inn', i)
        elif any(x in h_str for x in ('кпп', 'kpp')):
            col.setdefault('kpp', i)
        elif any(x in h_str for x in ('огрн', 'ogrn')):
            col.setdefault('ogrn', i)
        elif any(x in h_str for x in ('почтов', 'postal')):
            col.setdefault('postal_address', i)
        elif any(x in h_str for x in ('адрес', 'address')):
            col.setdefault('address', i)
        elif any(x in h_str for x in ('основан', 'basis', 'устав', 'действует')):
            col.setdefault('signatory_basis', i)
        elif any(x in h_str for x in ('подписант', 'signatory', 'директор', 'руководит')):
            col.setdefault('signatory', i)
        elif any(x in h_str for x in ('контакт', 'contact', 'лицо')):
            col.setdefault('contact_person', i)
        elif any(x in h_str for x in ('телефон', 'phone', 'тел.')):
            col.setdefault('phone', i)
        elif 'email' in h_str or 'e-mail' in h_str or 'mail' in h_str:
            col.setdefault('email', i)
        elif any(x in h_str for x in ('расч', 'р/с', 'р/с', 'settlement')):
            col.setdefault('settlement_account', i)
        elif any(x in h_str for x in ('корр', 'к/с', 'correspondent')):
            col.setdefault('correspondent_account', i)
        elif any(x in h_str for x in ('бик', 'bik')):
            col.setdefault('bik', i)
        elif any(x in h_str for x in ('банк', 'bank')):
            col.setdefault('bank_name', i)
        elif any(x in h_str for x in ('реквизит',)):
            col.setdefault('bank_details', i)

    if 'name' not in col:
        raise HTTPException(
            400,
            "Не найдена колонка с наименованием. "
            "Убедитесь что первая строка — заголовки с колонкой «Наименование» или «name»."
        )

    _limits = {
        'inn': 12, 'kpp': 9, 'ogrn': 20, 'bik': 20,
        'settlement_account': 100, 'correspondent_account': 100,
        'phone': 50, 'email': 255, 'contact_person': 255,
        'signatory': 255, 'signatory_basis': 500, 'bank_name': 500,
    }

    def _cell(row, field):
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null', '-', '—'):
            return None
        limit = _limits.get(field)
        return s[:limit] if limit else s

    created = 0
    skipped = 0
    errors_list = []

    # Collect existing INNs for dedup
    inn_result = await db.execute(select(Contractor.inn).where(Contractor.inn.isnot(None)))
    existing_inns = {r[0] for r in inn_result}

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        name = _cell(row, 'name')
        if not name:
            skipped += 1
            continue

        inn = _cell(row, 'inn')
        if inn and inn in existing_inns:
            skipped += 1
            continue

        c = Contractor(
            name=name,
            inn=inn,
            kpp=_cell(row, 'kpp'),
            ogrn=_cell(row, 'ogrn'),
            address=_cell(row, 'address'),
            postal_address=_cell(row, 'postal_address'),
            signatory=_cell(row, 'signatory'),
            signatory_basis=_cell(row, 'signatory_basis'),
            contact_person=_cell(row, 'contact_person'),
            phone=_cell(row, 'phone'),
            email=_cell(row, 'email'),
            settlement_account=_cell(row, 'settlement_account'),
            bank_name=_cell(row, 'bank_name'),
            bik=_cell(row, 'bik'),
            correspondent_account=_cell(row, 'correspondent_account'),
            bank_details=_cell(row, 'bank_details'),
        )
        db.add(c)
        if inn:
            existing_inns.add(inn)
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# New multi-format import endpoints
# ---------------------------------------------------------------------------

@router.post("/import/preview")
async def contractors_import_preview(
    file: UploadFile = File(...),
    _=Depends(require_role(*ALL_ROLES)),
):
    """Parse uploaded file and return headers + sample rows for column mapping UI."""
    fname = (file.filename or '').lower()
    content = await file.read()

    try:
        all_rows, hdr_idx = _parse_file_to_rows(fname, content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    hdr_rows = all_rows[hdr_idx:]
    if not hdr_rows:
        raise HTTPException(400, "Файл пустой или не содержит данных после заголовка")

    headers = [
        str(c).strip() if c else f"Столбец {j + 1}"
        for j, c in enumerate(hdr_rows[0])
    ]
    sample = [
        [str(c).strip() if c is not None else "" for c in row]
        for row in hdr_rows[1:min(4, len(hdr_rows))]
    ]
    total_rows = len(all_rows) - hdr_idx - 1

    return {
        "headers": headers,
        "sample": sample,
        "total_rows": max(total_rows, 0),
        "header_row_offset": hdr_idx,
    }


@router.post("/import/mapped")
async def contractors_import_mapped(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ALL_ROLES)),
    col_name: Optional[int] = Query(None),
    col_inn: Optional[int] = Query(None),
    col_kpp: Optional[int] = Query(None),
    col_ogrn: Optional[int] = Query(None),
    col_address: Optional[int] = Query(None),
    col_postal_address: Optional[int] = Query(None),
    col_signatory: Optional[int] = Query(None),
    col_signatory_basis: Optional[int] = Query(None),
    col_contact_person: Optional[int] = Query(None),
    col_phone: Optional[int] = Query(None),
    col_email: Optional[int] = Query(None),
    col_settlement_account: Optional[int] = Query(None),
    col_bank_name: Optional[int] = Query(None),
    col_bik: Optional[int] = Query(None),
    col_correspondent_account: Optional[int] = Query(None),
    col_bank_details: Optional[int] = Query(None),
    header_row_offset: int = Query(0),
):
    """Import contractors using user-specified column mapping."""
    if col_name is None:
        raise HTTPException(400, "Не указан столбец «Наименование»")

    fname = (file.filename or '').lower()
    content = await file.read()

    try:
        all_rows, _ = _parse_file_to_rows(fname, content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    # Skip header row
    skip = header_row_offset + 1
    data_rows = all_rows[skip:]

    _limits = {
        'inn': 12, 'kpp': 9, 'ogrn': 20, 'bik': 20,
        'settlement_account': 100, 'correspondent_account': 100,
        'phone': 50, 'email': 255, 'contact_person': 255,
        'signatory': 255, 'signatory_basis': 500, 'bank_name': 500,
    }

    col_map = {
        'name': col_name,
        'inn': col_inn,
        'kpp': col_kpp,
        'ogrn': col_ogrn,
        'address': col_address,
        'postal_address': col_postal_address,
        'signatory': col_signatory,
        'signatory_basis': col_signatory_basis,
        'contact_person': col_contact_person,
        'phone': col_phone,
        'email': col_email,
        'settlement_account': col_settlement_account,
        'bank_name': col_bank_name,
        'bik': col_bik,
        'correspondent_account': col_correspondent_account,
        'bank_details': col_bank_details,
    }

    def _get(row, field):
        idx = col_map.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null', '-', '—'):
            return None
        limit = _limits.get(field)
        return s[:limit] if limit else s

    # Collect existing INNs for dedup
    inn_result = await db.execute(select(Contractor.inn).where(Contractor.inn.isnot(None)))
    existing_inns = {r[0] for r in inn_result}

    created = 0
    skipped = 0
    errors_list = []

    for row in data_rows:
        try:
            name = _get(row, 'name')
            if not name:
                skipped += 1
                continue

            inn = _get(row, 'inn')
            if inn and inn in existing_inns:
                skipped += 1
                continue

            c = Contractor(
                name=name,
                inn=inn,
                kpp=_get(row, 'kpp'),
                ogrn=_get(row, 'ogrn'),
                address=_get(row, 'address'),
                postal_address=_get(row, 'postal_address'),
                signatory=_get(row, 'signatory'),
                signatory_basis=_get(row, 'signatory_basis'),
                contact_person=_get(row, 'contact_person'),
                phone=_get(row, 'phone'),
                email=_get(row, 'email'),
                settlement_account=_get(row, 'settlement_account'),
                bank_name=_get(row, 'bank_name'),
                bik=_get(row, 'bik'),
                correspondent_account=_get(row, 'correspondent_account'),
                bank_details=_get(row, 'bank_details'),
            )
            db.add(c)
            if inn:
                existing_inns.add(inn)
            created += 1
        except Exception as e:
            errors_list.append(str(e))

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors_list}
