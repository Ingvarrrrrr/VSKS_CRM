from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.schemas.schemas import PurchaseCreate, PurchaseOut, PurchaseOutFull, PurchaseItemOut, PurchaseFileOut
from app.auth.jwt import get_current_user, require_role
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
from datetime import datetime, date
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

# Status workflow
STATUS_ORDER = ["planned", "confirmed", "in_progress", "contracted", "delivered", "paid"]


async def _check_budget(
    subsidy_id: Optional[int],
    amount: Optional[Decimal],
    exclude_pid: Optional[int],
    db: AsyncSession
):
    """Raises 422 if adding `amount` to subsidy total would exceed its budget."""
    if not subsidy_id or not amount:
        return
    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()
    if not subsidy:
        return
    q = select(func.coalesce(func.sum(Purchase.planned_total_price), 0)).where(
        Purchase.subsidy_id == subsidy_id
    )
    if exclude_pid:
        q = q.where(Purchase.id != exclude_pid)
    total_r = await db.execute(q)
    total = Decimal(str(total_r.scalar() or 0))
    amt = Decimal(str(amount))
    budget = Decimal(str(subsidy.budget))
    if total + amt > budget:
        remaining = budget - total
        raise HTTPException(
            422,
            f"Превышение бюджета субсидии «{subsidy.name}». "
            f"Доступно: {remaining:,.2f} ₽, запрашивается: {amt:,.2f} ₽"
        )

# Fields required for each transition target
TRANSITION_REQUIRED: dict[str, list[str]] = {
    "contracted": ["contract_number", "contract_date"],
    "delivered": ["acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number", "acceptance_doc_amount"],
    "paid": ["payment_doc_number", "payment_doc_date", "payment_amount"],
}

STATUS_LABELS = {
    "planned": "Планируется",
    "confirmed": "Подтверждено",
    "in_progress": "Ведётся работа",
    "contracted": "Договор",
    "delivered": "Поставлено",
    "paid": "Оплачено",
}


def _item_to_out(item: PurchaseItem) -> PurchaseItemOut:
    product_name = None
    product_photo_url = None
    product_description = None
    if item.product:
        product_name = item.product.name
        product_photo_url = item.product.photo_url
        product_description = item.product.description
    return PurchaseItemOut(
        id=item.id,
        product_id=item.product_id,
        item_name=item.item_name,
        item_type=item.item_type,
        quantity=item.quantity,
        unit=item.unit,
        unit_price=item.unit_price,
        total_price=item.total_price,
        final_unit_price=item.final_unit_price,
        final_total=item.final_total,
        product_name=product_name,
        product_photo_url=product_photo_url,
        product_description=product_description,
    )


def _purchase_to_full(p: Purchase, contractors: dict, subsidies: dict) -> PurchaseOutFull:
    data = {c.name: getattr(p, c.name) for c in Purchase.__table__.columns}
    items = [_item_to_out(i) for i in (p.items or [])]
    files = [
        PurchaseFileOut(
            id=f.id,
            purchase_id=f.purchase_id,
            filename=f.filename,
            mime_type=f.mime_type,
            size=f.size,
            created_at=str(f.created_at) if f.created_at else None,
        )
        for f in (p.files or [])
    ]
    return PurchaseOutFull(
        **data,
        items=items,
        files=files,
        contractor_name=contractors.get(p.contractor_id),
        feo_category_name=p.feo_category.name if p.feo_category else None,
        subsidy_name=subsidies.get(p.subsidy_id),
    )


@router.get("/responsible-persons")
async def list_responsible_persons(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Уникальные ответственные исполнители из закупок (для выпадающего списка)."""
    q = select(Purchase.responsible_person).where(Purchase.responsible_person.isnot(None))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    q = q.distinct().order_by(Purchase.responsible_person)
    result = await db.execute(q)
    return [row[0] for row in result.fetchall()]


@router.get("/", response_model=List[PurchaseOutFull])
async def list_purchases(
    contract_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
        selectinload(Purchase.items).selectinload(PurchaseItem.product),
        selectinload(Purchase.files),
    )
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        q = q.where(Purchase.feo_category_id == feo_category_id)
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    result = await db.execute(q.order_by(Purchase.id.desc()))
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}

    return [_purchase_to_full(p, contractors, subsidies) for p in purchases]


@router.get("/{pid}/kp-items")
async def get_purchase_kp_items(pid: int, db: AsyncSession = Depends(get_db)):
    """Items in a purchase with product category info for КП smart sending."""
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product

    stmt = (
        select(
            PurchaseItem.id,
            PurchaseItem.item_name,
            PurchaseItem.quantity,
            PurchaseItem.unit,
            PurchaseItem.unit_price,
            Product.name.label("product_name"),
            Product.category.label("product_category"),
        )
        .outerjoin(Product, Product.id == PurchaseItem.product_id)
        .where(PurchaseItem.purchase_id == pid)
        .order_by(PurchaseItem.id)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "item_name": r.product_name or r.item_name,
            "quantity": float(r.quantity or 0),
            "unit": r.unit or "шт.",
            "unit_price": float(r.unit_price or 0),
            "category": r.product_category or None,
        }
        for r in rows
    ]


@router.get("/{pid}", response_model=PurchaseOutFull)
async def get_purchase(pid: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.post("/", response_model=PurchaseOut)
async def create_purchase(
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("admin", "manager"))
):
    if admin_override and current_user.role != "admin":
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    # Compute total_nmck from items
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override:
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, None, db)

    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    dump = data.model_dump(exclude={"items"})
    dump["total_nmck"] = total_nmck
    p = Purchase(**dump)
    db.add(p)
    await db.flush()  # get p.id before commit

    year = date.today().year
    if not p.registry_number:
        p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
    if not p.contract_number:
        p.contract_number = f"{year}/{p.id}"

    for item_d in items_data:
        item = PurchaseItem(
            purchase_id=p.id,
            **item_d.model_dump(),
        )
        db.add(item)

    await db.commit()
    await db.refresh(p)
    return p


@router.put("/{pid}", response_model=PurchaseOut)
async def update_purchase(
    pid: int,
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("admin", "manager"))
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    if admin_override and current_user.role != "admin":
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override:
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, pid, db)

    for k, v in data.model_dump(exclude={"items"}, exclude_unset=True).items():
        setattr(p, k, v)
    p.total_nmck = total_nmck

    # Replace items
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        item = PurchaseItem(purchase_id=pid, **item_d.model_dump())
        db.add(item)

    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/{pid}")
async def delete_purchase(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.post("/{pid}/transition", response_model=PurchaseOutFull)
async def transition_status(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Forward-only status transition.
    planned → confirmed → in_progress → contracted → delivered → paid
    """
    if target_status not in STATUS_ORDER:
        raise HTTPException(422, f"Недопустимый статус: {target_status}")

    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    current_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
    target_idx = STATUS_ORDER.index(target_status)

    # Role check: only manager/admin can transition
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(403, "Недостаточно прав для смены статуса")

    # Direction check: forward-only for non-admin
    if target_idx <= current_idx:
        if current_user.role != "admin":
            raise HTTPException(422, "Откат статуса разрешён только администратору")

    # Field guards for specific target statuses
    if target_status in TRANSITION_REQUIRED:
        missing = [
            f for f in TRANSITION_REQUIRED[target_status]
            if not getattr(p, f, None)
        ]
        if missing:
            labels = {
                "contract_number": "Номер договора",
                "contract_date": "Дата договора",
                "acceptance_doc_name": "Наименование акта приёмки",
                "acceptance_doc_date": "Дата акта",
                "acceptance_doc_number": "Номер акта",
                "acceptance_doc_amount": "Сумма акта",
                "payment_doc_number": "Номер платёжного поручения",
                "payment_doc_date": "Дата платёжного поручения",
                "payment_amount": "Сумма платежа",
            }
            missing_labels = [labels.get(f, f) for f in missing]
            status_label = STATUS_LABELS.get(target_status, target_status)
            raise HTTPException(
                422,
                f"Для перехода в статус «{status_label}» заполните: {', '.join(missing_labels)}"
            )

    # Auto-calculate contract_price from items when transitioning to "contracted"
    if target_status == "contracted":
        total = sum((item.total_price or 0) for item in p.items)
        if total > 0 and (not p.contract_price or p.contract_price == 0):
            p.contract_price = total
        
        # Save last price to each product
        for item in p.items:
            if item.product_id and item.total_price:
                prod_r = await db.execute(select(Product).where(Product.id == item.product_id))
                product = prod_r.scalar_one_or_none()
                if product:
                    product.price = item.total_price
                    product.last_contract_number = p.contract_number
                    product.last_contract_date = p.contract_date
                    product.last_contractor = p.contractor.name if p.contractor else None

    p.status = target_status
    await db.commit()
    await db.refresh(p)

    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.get("/export/excel")
async def export_purchases_to_excel(
    subsidy_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    q = select(Purchase).order_by(Purchase.id.desc())
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    result = await db.execute(q)
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    contracts_r = await db.execute(select(Contract))
    contracts = {c.id: c.number for c in contracts_r.scalars().all()}

    wb = Workbook()
    ws = wb.active
    ws.title = "GoodsService"

    headers = [
        "№ п/п", "Реестровый №", "Наименование", "Тип", "Ед. изм", "Кол-во",
        "НМЦК", "Цена договора", "Экономия", "Способ закупки",
        "№ договора", "Дата договора", "Контрагент",
        "Срок исполнения", "Страна происхождения",
        "Акт: наименование", "Акт: №", "Акт: дата", "Акт: сумма",
        "ПП: №", "ПП: дата", "ПП: сумма", "в т.ч. фед. бюджет",
        "Статус"
    ]
    ws.append(headers)

    for p in purchases:
        ws.append([
            p.purchase_number or "",
            p.registry_number or "",
            p.item_name or "",
            p.item_type or "",
            p.unit or "",
            float(p.planned_quantity) if p.planned_quantity else 0,
            float(p.nmck or p.planned_total_price or 0),
            float(p.contract_price or 0),
            float(p.economy or 0),
            "Единственный исполнитель" if p.purchase_method == "single" else ("Конкурсная процедура" if p.purchase_method == "competitive" else ""),
            p.contract_number or "",
            str(p.contract_date) if p.contract_date else "",
            contractors.get(p.contractor_id, ""),
            str(p.execution_term) if p.execution_term else "",
            p.country_origin or "",
            p.acceptance_doc_name or "",
            p.acceptance_doc_number or "",
            str(p.acceptance_doc_date) if p.acceptance_doc_date else "",
            float(p.acceptance_doc_amount or 0),
            p.payment_doc_number or "",
            str(p.payment_doc_date) if p.payment_doc_date else "",
            float(p.payment_amount or 0),
            float(p.payment_federal or 0),
            p.status or "",
        ])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"purchases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/import/template")
async def download_import_template():
    """Скачать шаблон Excel для импорта закупок."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Закупки"

    headers = [
        "Наименование", "Субсидия", "Категория ФЭО", "Контрагент", "ИНН контрагента",
        "НМЦК", "Способ закупки", "Реестровый №", "№ договора", "Дата договора",
        "Цена договора", "Срок исполнения", "ПП №", "ПП дата", "Оплачено",
        "Статус", "Год",
    ]
    ws.append(headers)

    # Style header row
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Sample row
    ws.append([
        "Закупка компьютеров", "ФАДМ_2026", "Техническое оснащение", "ООО Поставщик", "1234567890",
        "500000", "ЕИ", "2026/001", "Д-001", "15.03.2026",
        "490000", "30.06.2026", "", "", "",
        "confirmed", "2026",
    ])

    # Column widths
    col_widths = [35, 20, 30, 25, 15, 12, 15, 14, 14, 14, 14, 14, 12, 12, 12, 14, 6]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w

    ws.freeze_panes = "A2"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=import_template.xlsx"}
    )


@router.post("/import")
async def import_purchases_from_excel(
    file: UploadFile = File(...),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Импорт закупок из Excel. Возвращает {created, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой или содержит только заголовки")

    # Parse headers (case-insensitive)
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    COLUMN_MAP = {
        "наименование": "item_name", "предмет закупки": "item_name",
        "субсидия": "subsidy_name",
        "категория фэо": "feo_category_name",
        "контрагент": "contractor_name",
        "инн контрагента": "contractor_inn", "инн": "contractor_inn",
        "нмцк": "nmck", "сумма": "nmck", "цена": "nmck",
        "способ закупки": "purchase_method", "способ": "purchase_method",
        "реестровый №": "registry_number", "реестровый номер": "registry_number", "реестр. №": "registry_number",
        "№ договора": "contract_number", "номер договора": "contract_number",
        "дата договора": "contract_date",
        "цена договора": "contract_price",
        "срок исполнения": "execution_term",
        "пп №": "payment_doc_number", "пп номер": "payment_doc_number",
        "пп дата": "payment_doc_date",
        "оплачено": "payment_amount",
        "статус": "status",
        "год": "year",
        "№ п/п": "purchase_number",
    }
    col_idx: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i

    # Load lookup tables
    from app.models.feo_category import FeoCategory
    subs_rows = (await db.execute(select(Subsidy))).scalars().all()
    subs_by_name = {s.name.lower().strip(): s.id for s in subs_rows}

    contractors_rows = (await db.execute(select(Contractor))).scalars().all()
    cont_by_name = {c.name.lower().strip(): c.id for c in contractors_rows}
    cont_by_inn  = {c.inn.strip(): c.id for c in contractors_rows if c.inn}

    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name = {f.name.lower().strip(): f.id for f in feo_rows}

    STATUS_MAP = {
        "planned": "planned", "планируется": "planned", "план": "planned",
        "confirmed": "confirmed", "подтверждено": "confirmed",
        "contracted": "contracted", "законтрактовано": "contracted",
        "delivered": "delivered", "исполнено": "delivered",
        "paid": "paid", "оплачено": "paid",
    }
    METHOD_MAP = {
        "еи": "single", "единственный исполнитель": "single", "single": "single",
        "кп": "competitive", "конкурсная процедура": "competitive", "competitive": "competitive",
    }

    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None

    def to_dec(v):
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return None
        try:
            return Decimal(str(v).replace(" ", "").replace(",", "."))
        except Exception:
            return None

    def to_date_val(v):
        if v is None:
            return None
        if hasattr(v, "date"):
            return v.date()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(str(v).strip(), fmt).date()
            except Exception:
                pass
        return None

    created = 0
    skipped = 0
    errors: list[dict] = []

    for row_num, row in enumerate(rows[1:], start=2):
        try:
            item_name = cell(row, "item_name")
            if not item_name:
                skipped += 1
                continue

            # Resolve subsidy
            sid = subsidy_id
            if not sid:
                sub_name = cell(row, "subsidy_name")
                if sub_name:
                    sid = subs_by_name.get(sub_name.lower().strip())
            if not sid:
                errors.append({"row": row_num, "name": item_name, "message": "Субсидия не найдена"})
                continue

            # Resolve contractor
            cid = None
            c_name = cell(row, "contractor_name")
            c_inn  = cell(row, "contractor_inn")
            if c_inn:
                cid = cont_by_inn.get(c_inn.strip())
            if not cid and c_name:
                cid = cont_by_name.get(c_name.lower().strip())

            # Resolve FEO
            feo_id = None
            feo_name = cell(row, "feo_category_name")
            if feo_name:
                feo_id = feo_by_name.get(feo_name.lower().strip())

            # Status
            status_raw = (cell(row, "status") or "planned").lower().strip()
            status = STATUS_MAP.get(status_raw, "planned")

            # Method
            method_raw = (cell(row, "purchase_method") or "").lower().strip()
            method = METHOD_MAP.get(method_raw)

            nmck = to_dec(cell(row, "nmck"))
            p = Purchase(
                subsidy_id=sid,
                feo_category_id=feo_id,
                contractor_id=cid,
                item_name=item_name,
                status=status,
                nmck=nmck,
                total_nmck=nmck,
                planned_total_price=nmck,
                contract_price=to_dec(cell(row, "contract_price")),
                payment_amount=to_dec(cell(row, "payment_amount")),
                purchase_method=method,
                registry_number=cell(row, "registry_number"),
                contract_number=cell(row, "contract_number"),
                contract_date=to_date_val(cell(row, "contract_date")),
                execution_term=to_date_val(cell(row, "execution_term")),
                payment_doc_number=cell(row, "payment_doc_number"),
                payment_doc_date=to_date_val(cell(row, "payment_doc_date")),
            )
            db.add(p)
            created += 1
        except Exception as e:
            errors.append({"row": row_num, "name": cell(row, "item_name") or "?", "message": str(e)})

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
