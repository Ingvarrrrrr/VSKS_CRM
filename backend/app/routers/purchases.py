from fastapi import APIRouter, Depends, HTTPException, Query
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
    from openpyxl import Workbook
except ImportError:
    Workbook = None

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
            raise HTTPException(
                422,
                f"Для перехода в статус «{target_status}» заполните: {', '.join(missing_labels)}"
            )

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
