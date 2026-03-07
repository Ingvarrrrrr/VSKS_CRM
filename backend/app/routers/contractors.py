from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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
    """Contractors with purchase counts, subsidy_ids, feo_category_ids."""
    from app.models.purchase import Purchase

    contractors = (await db.execute(select(Contractor).order_by(Contractor.name))).scalars().all()

    stats_stmt = (
        select(
            Purchase.contractor_id,
            func.count(Purchase.id).label("purchase_count"),
            func.array_agg(distinct(Purchase.subsidy_id)).label("subsidy_ids"),
            func.array_agg(distinct(Purchase.feo_category_id)).label("feo_category_ids"),
        )
        .where(Purchase.contractor_id.isnot(None))
        .group_by(Purchase.contractor_id)
    )
    stats_rows = (await db.execute(stats_stmt)).all()
    stats_map = {row.contractor_id: row for row in stats_rows}

    result = []
    for c in contractors:
        s = stats_map.get(c.id)
        c_dict = ContractorOut.model_validate(c).model_dump()
        c_dict["purchase_count"] = s.purchase_count if s else 0
        c_dict["subsidy_ids"] = [x for x in (s.subsidy_ids or []) if x is not None] if s else []
        c_dict["feo_category_ids"] = [x for x in (s.feo_category_ids or []) if x is not None] if s else []
        result.append(c_dict)
    return result


@router.get("/{cid}/purchases")
async def get_contractor_purchases(cid: int, db: AsyncSession = Depends(get_db)):
    """List purchases for a specific contractor."""
    from app.models.purchase import Purchase
    from app.models.feo_category import FeoCategory
    from app.models.subsidy import Subsidy

    stmt = (
        select(
            Purchase.id,
            Purchase.subject,
            Purchase.item_name,
            Purchase.status,
            Purchase.planned_total_price,
            Purchase.subsidy_id,
            FeoCategory.name.label("feo_category_name"),
            Subsidy.name.label("subsidy_name"),
        )
        .outerjoin(FeoCategory, Purchase.feo_category_id == FeoCategory.id)
        .outerjoin(Subsidy, Purchase.subsidy_id == Subsidy.id)
        .where(Purchase.contractor_id == cid)
        .order_by(Purchase.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "subject": r.subject or r.item_name or "—",
            "status": r.status,
            "planned_total_price": float(r.planned_total_price) if r.planned_total_price else None,
            "subsidy_name": r.subsidy_name or "—",
            "feo_category_name": r.feo_category_name or "—",
        }
        for r in rows
    ]


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


@router.post("/import/excel")
async def import_contractors_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager"))
):
    """
    Bulk import contractors from Excel (.xlsx).
    First row must be headers. Recognized column names (Russian or English):
    Наименование/name, ИНН/inn, КПП/kpp, Адрес/address,
    Контакт/contact_person, Телефон/phone, Email/email, Банк/bank_details
    Rows with duplicate INN are skipped.
    """
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
        elif any(x in h_str for x in ('адрес', 'address')):
            col.setdefault('address', i)
        elif any(x in h_str for x in ('контакт', 'contact', 'лицо')):
            col.setdefault('contact_person', i)
        elif any(x in h_str for x in ('телефон', 'phone', 'тел.')):
            col.setdefault('phone', i)
        elif 'email' in h_str or 'почт' in h_str or 'mail' in h_str:
            col.setdefault('email', i)
        elif any(x in h_str for x in ('банк', 'bank', 'расч', 'реквизит')):
            col.setdefault('bank_details', i)

    if 'name' not in col:
        raise HTTPException(
            400,
            "Не найдена колонка с наименованием. "
            "Убедитесь что первая строка — заголовки с колонкой «Наименование» или «name»."
        )

    def _cell(row, field):
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ('none', 'null', '-', '—') else None

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
            address=_cell(row, 'address'),
            contact_person=_cell(row, 'contact_person'),
            phone=_cell(row, 'phone'),
            email=_cell(row, 'email'),
            bank_details=_cell(row, 'bank_details'),
        )
        db.add(c)
        if inn:
            existing_inns.add(inn)
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped}
