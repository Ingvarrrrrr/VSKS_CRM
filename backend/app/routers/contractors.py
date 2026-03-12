from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.contractor import Contractor
from app.schemas.schemas import ContractorCreate, ContractorOut
from app.auth.jwt import require_role
from typing import List
from io import BytesIO

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


@router.get("/with-stats")
async def list_contractors_with_stats(db: AsyncSession = Depends(get_db)):
    """Contractors with product categories derived from purchase_items → products."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product

    contractors = (await db.execute(select(Contractor).order_by(Contractor.name))).scalars().all()

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
        c_dict["product_categories"] = prod_cat_map.get(c.id, [])
        result.append(c_dict)
    return result


@router.get("/", response_model=List[ContractorOut])
async def list_contractors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contractor).order_by(Contractor.name))
    return result.scalars().all()


@router.post("/", response_model=ContractorOut)
async def create_contractor(
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager"))
):
    c = Contractor(**data.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.put("/{cid}", response_model=ContractorOut)
async def update_contractor(
    cid: int,
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager"))
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
    _=Depends(require_role("admin"))
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
    _=Depends(require_role("admin"))
):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.get("/import/template")
async def contractors_import_template(_=Depends(require_role("admin", "manager"))):
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
    _=Depends(require_role("admin", "manager"))
):
    """Bulk import contractors from Excel. First row must be headers."""
    if not (file.filename or '').lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx / .xls")

    try:
        from openpyxl import load_workbook
    except ImportError:
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
        elif any(x in h_str for x in ('фИо', 'ф и о', 'фио', 'fio')):
            col.setdefault('signatory_fio', i)
        elif any(x in h_str for x in ('должност', 'position', 'должн')):
            col.setdefault('signatory_position', i)
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
        'signatory': 255, 'signatory_fio': 255, 'signatory_position': 255, 'signatory_basis': 500, 'bank_name': 500,
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
            signatory_fio=_cell(row, 'signatory_fio'),
            signatory_position=_cell(row, 'signatory_position'),
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
