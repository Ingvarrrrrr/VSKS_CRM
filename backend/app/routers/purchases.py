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
from app.models.feo_category import FeoCategory
from app.schemas.schemas import PurchaseCreate, PurchaseOut, PurchaseOutFull, PurchaseItemOut, PurchaseFileOut
from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.models.user import User
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
STATUS_ORDER = ["wishes", "plan_schedule", "confirmed", "work_in_progress", "contracted", "delivered", "paid"]
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform")

# ---------------------------------------------------------------------------
# Excel export: column registry
# ---------------------------------------------------------------------------

ALL_EXPORT_COLUMNS = {
    "purchase_number":        {"label": "№ п/п",                 "group": "Идентификация"},
    "order_number":           {"label": "Номер заявки",          "group": "Идентификация"},
    "registry_number":        {"label": "Реестровый №",          "group": "Идентификация"},
    "status":                 {"label": "Статус",                "group": "Идентификация"},
    "subsidy":                {"label": "Субсидия",              "group": "Идентификация"},
    "feo_category":           {"label": "Категория ФЭО",         "group": "Идентификация"},
    "item_name":              {"label": "Наименование",          "group": "Позиция"},
    "item_type":              {"label": "Тип",                   "group": "Позиция"},
    "unit":                   {"label": "Ед. изм",               "group": "Позиция"},
    "quantity":               {"label": "Кол-во",                "group": "Позиция"},
    "subject":                {"label": "Предмет закупки",       "group": "Позиция"},
    "country_origin":         {"label": "Страна происхождения",  "group": "Позиция"},
    "planned_unit_price":     {"label": "Плановая цена за ед.",  "group": "Цены"},
    "planned_total_price":    {"label": "Плановая сумма",        "group": "Цены"},
    "nmck":                   {"label": "НМЦК",                  "group": "Цены"},
    "contract_price":         {"label": "Цена договора",         "group": "Цены"},
    "economy":                {"label": "Экономия",              "group": "Цены"},
    "price_increase":         {"label": "Удорожание",            "group": "Цены"},
    "purchase_method":        {"label": "Способ закупки",        "group": "Закупка"},
    "purchase_basis":         {"label": "Основание",             "group": "Закупка"},
    "purchase_contract_type": {"label": "Тип договора",          "group": "Закупка"},
    "framework_seq":          {"label": "№ в рамочном",          "group": "Закупка"},
    "contract_number":        {"label": "№ договора",            "group": "Договор"},
    "contract_date":          {"label": "Дата договора",         "group": "Договор"},
    "execution_term":         {"label": "Срок исполнения",       "group": "Договор"},
    "execution_term_changed": {"label": "Срок (изменён)",        "group": "Договор"},
    "delivery_date":          {"label": "Дата доставки",         "group": "Договор"},
    "contractor":             {"label": "Контрагент",            "group": "Контрагент"},
    "responsible_person":     {"label": "Ответственное лицо",    "group": "Контрагент"},
    "acceptance_doc_name":    {"label": "Акт: наименование",     "group": "Исполнение"},
    "acceptance_doc_number":  {"label": "Акт: №",               "group": "Исполнение"},
    "acceptance_doc_date":    {"label": "Акт: дата",             "group": "Исполнение"},
    "acceptance_doc_amount":  {"label": "Акт: сумма",            "group": "Исполнение"},
    "payment_doc_number":     {"label": "ПП: №",                 "group": "Оплата"},
    "payment_doc_date":       {"label": "ПП: дата",              "group": "Оплата"},
    "payment_amount":         {"label": "ПП: сумма",             "group": "Оплата"},
    "payment_federal":        {"label": "В т.ч. фед. бюджет",   "group": "Оплата"},
    "delivery_payment_amount":{"label": "Оплата с доставкой",    "group": "Оплата"},
    "vat_applicable":         {"label": "НДС применяется",       "group": "НДС"},
    "vat_rate":               {"label": "Ставка НДС",            "group": "НДС"},
    "vat_exemption_article":  {"label": "Статья НК РФ",          "group": "НДС"},
}

DEFAULT_EXPORT_COLUMNS = [
    "purchase_number", "registry_number", "item_name", "item_type", "unit", "quantity",
    "nmck", "contract_price", "economy", "purchase_method",
    "contract_number", "contract_date", "contractor",
    "execution_term", "country_origin",
    "acceptance_doc_name", "acceptance_doc_number", "acceptance_doc_date", "acceptance_doc_amount",
    "payment_doc_number", "payment_doc_date", "payment_amount", "payment_federal",
    "status",
]

_PURCHASE_METHOD_LABELS = {
    "single": "Единственный исполнитель",
    "competitive": "Конкурсная процедура",
    "quote_request": "Запрос котировок",
}
_PURCHASE_BASIS_LABELS = {
    "plan_schedule": "план-график",
    "service_note": "служебная записка",
}
_CONTRACT_TYPE_LABELS = {
    "single": "Разовая поставка",
    "framework_cumulative": "Рамочный (нарастающий итог)",
    "framework_with_amount": "Рамочный (с указанием суммы)",
}
_STATUS_LABELS = {
    "wishes": "Желания сотрудников",
    "plan_schedule": "План-график",
    "confirmed": "Подтверждено руководством",
    "work_in_progress": "Ведётся работа",
    "contracted": "Заключён договор",
    "delivered": "Поставлено",
    "paid": "Оплачено",
}
_SUBSTATUS_LABELS = {
    "tz_forming": "Формируется ТЗ",
    "kp_collecting": "Идёт сбор КП",
    "on_platform": "Выставлено на площадку",
}


def _get_cell_value(key: str, p: Purchase, ctx: dict):
    if key == "purchase_number":         return p.purchase_number or ""
    if key == "order_number":            return p.order_number or ""
    if key == "registry_number":         return p.registry_number or ""
    if key == "status":                  return _STATUS_LABELS.get(p.status, p.status or "")
    if key == "subsidy":                 return ctx["subsidies"].get(p.subsidy_id, "")
    if key == "feo_category":            return ctx["feo_categories"].get(p.feo_category_id, "")
    if key == "item_name":               return p.item_name or ""
    if key == "item_type":               return p.item_type or ""
    if key == "unit":                    return p.unit or ""
    if key == "quantity":                return float(p.planned_quantity) if p.planned_quantity else ""
    if key == "subject":                 return p.subject or ""
    if key == "country_origin":          return p.country_origin or ""
    if key == "planned_unit_price":      return float(p.planned_unit_price) if p.planned_unit_price else ""
    if key == "planned_total_price":     return float(p.planned_total_price) if p.planned_total_price else ""
    if key == "nmck":                    return float(p.nmck or p.planned_total_price or 0) or ""
    if key == "contract_price":          return float(p.contract_price) if p.contract_price else ""
    if key == "economy":                 return float(p.economy) if p.economy else ""
    if key == "price_increase":          return float(p.price_increase) if p.price_increase else ""
    if key == "purchase_method":         return _PURCHASE_METHOD_LABELS.get(p.purchase_method, p.purchase_method or "")
    if key == "purchase_basis":          return _PURCHASE_BASIS_LABELS.get(p.purchase_basis, p.purchase_basis or "")
    if key == "purchase_contract_type":  return _CONTRACT_TYPE_LABELS.get(p.purchase_contract_type, p.purchase_contract_type or "")
    if key == "framework_seq":           return p.framework_seq if p.framework_seq is not None else ""
    if key == "contract_number":         return p.contract_number or ""
    if key == "contract_date":           return str(p.contract_date) if p.contract_date else ""
    if key == "execution_term":          return str(p.execution_term) if p.execution_term else ""
    if key == "execution_term_changed":  return str(p.execution_term_changed) if p.execution_term_changed else ""
    if key == "delivery_date":           return str(p.delivery_date) if p.delivery_date else ""
    if key == "contractor":              return ctx["contractors"].get(p.contractor_id, "")
    if key == "responsible_person":      return p.responsible_person or ""
    if key == "acceptance_doc_name":     return p.acceptance_doc_name or ""
    if key == "acceptance_doc_number":   return p.acceptance_doc_number or ""
    if key == "acceptance_doc_date":     return str(p.acceptance_doc_date) if p.acceptance_doc_date else ""
    if key == "acceptance_doc_amount":   return float(p.acceptance_doc_amount) if p.acceptance_doc_amount else ""
    if key == "payment_doc_number":      return p.payment_doc_number or ""
    if key == "payment_doc_date":        return str(p.payment_doc_date) if p.payment_doc_date else ""
    if key == "payment_amount":          return float(p.payment_amount) if p.payment_amount else ""
    if key == "payment_federal":         return float(p.payment_federal) if p.payment_federal else ""
    if key == "delivery_payment_amount": return float(p.delivery_payment_amount) if p.delivery_payment_amount else ""
    if key == "vat_applicable":          return "Да" if p.vat_applicable else ""
    if key == "vat_rate":                return p.vat_rate if p.vat_rate is not None else ""
    if key == "vat_exemption_article":   return p.vat_exemption_article or ""
    return ""


FRAMEWORK_TYPES = {"framework_cumulative", "framework_with_amount"}


async def _assign_framework_seq(p: Purchase, db: AsyncSession, exclude_id: Optional[int] = None) -> None:
    """Auto-assign framework_seq if purchase belongs to a framework contract and seq is not set."""
    if p.purchase_contract_type not in FRAMEWORK_TYPES or not p.contract_id:
        return
    if p.framework_seq is not None:
        return  # already set (manual override)
    q = select(func.coalesce(func.max(Purchase.framework_seq), 0)).where(
        Purchase.contract_id == p.contract_id
    )
    if exclude_id:
        q = q.where(Purchase.id != exclude_id)
    result = await db.execute(q)
    p.framework_seq = (result.scalar() or 0) + 1


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
    product_description_44fz = None
    if item.product:
        product_name = item.product.name
        product_photo_url = item.product.photo_url
        product_description = item.product.description
        product_description_44fz = item.product.description_44fz
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
        product_description_44fz=product_description_44fz,
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
        event_name=p.event.name if p.event else None,
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
    search: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
        selectinload(Purchase.items).selectinload(PurchaseItem.product),
        selectinload(Purchase.files),
    )
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        q = q.where(Purchase.feo_category_id == feo_category_id)
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    if search:
        like = f"%{search}%"
        q = q.where(
            Purchase.item_name.ilike(like) |
            Purchase.subject.ilike(like) |
            Purchase.registry_number.ilike(like) |
            Purchase.contract_number.ilike(like)
        )
    q = q.order_by(Purchase.id.desc())
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}

    return [_purchase_to_full(p, contractors, subsidies) for p in purchases]


@router.get("/my-tasks")
async def my_tasks(
    include_archive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kanban: purchases assigned to current user."""
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
    ).where(Purchase.assigned_user_id == current_user.id)
    if not include_archive:
        q = q.where(Purchase.status != "paid")
    q = q.order_by(Purchase.execution_term.asc().nulls_last(), Purchase.id.desc())
    result = await db.execute(q)
    purchases = result.scalars().all()
    return [
        {
            "id": p.id, "subject": p.subject or p.item_name or "",
            "status": p.status, "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "execution_term": str(p.execution_term) if p.execution_term else None,
            "delivery_date": str(p.delivery_date) if p.delivery_date else None,
            "planned_total_price": float(p.planned_total_price or 0),
            "contract_price": float(p.contract_price or 0),
            "contractor_name": p.contractor.name if p.contractor else None,
            "feo_category_name": p.feo_category.name if p.feo_category else None,
            "task_comment": p.task_comment,
            "subsidy_id": p.subsidy_id,
        }
        for p in purchases
    ]


@router.get("/kanban-all")
async def kanban_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kanban: all purchases grouped by assigned user (for managers/admins)."""
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
    ).where(Purchase.assigned_user_id.isnot(None))
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    q = q.order_by(Purchase.assigned_user_id, Purchase.execution_term.asc().nulls_last())
    result = await db.execute(q)
    purchases = result.scalars().all()

    # Group by user
    users_result = await db.execute(select(User))
    users_map = {u.id: u.full_name or u.username for u in users_result.scalars().all()}

    grouped = {}
    for p in purchases:
        uid = p.assigned_user_id
        if uid not in grouped:
            grouped[uid] = {"user_id": uid, "user_name": users_map.get(uid, f"User #{uid}"), "tasks": []}
        grouped[uid]["tasks"].append({
            "id": p.id, "subject": p.subject or p.item_name or "",
            "status": p.status, "purchase_number": p.purchase_number,
            "execution_term": str(p.execution_term) if p.execution_term else None,
            "contractor_name": p.contractor.name if p.contractor else None,
            "planned_total_price": float(p.planned_total_price or 0),
            "task_comment": p.task_comment,
        })
    return list(grouped.values())


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
    current_user=Depends(require_role(*MANAGER_ROLES))
):
    if admin_override and current_user.role not in ADMIN_ROLES:
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

    await _assign_framework_seq(p, db)

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
    current_user=Depends(require_role(*MANAGER_ROLES))
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override:
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, pid, db)

    # If contract_id or type changed, reset seq so it gets re-assigned
    old_contract_id = p.contract_id
    old_type = p.purchase_contract_type
    for k, v in data.model_dump(exclude={"items"}, exclude_unset=True).items():
        setattr(p, k, v)
    p.total_nmck = total_nmck
    if (p.contract_id != old_contract_id or p.purchase_contract_type != old_type) and data.framework_seq is None:
        p.framework_seq = None  # force re-assignment below
    await _assign_framework_seq(p, db, exclude_id=pid)

    # Replace items
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        item = PurchaseItem(purchase_id=pid, **item_d.model_dump())
        db.add(item)

    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/{pid}")
async def delete_purchase(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role(*ADMIN_ROLES))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.get("/by-contract/{contract_id}", response_model=List[PurchaseOutFull])
async def purchases_by_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Все закупки в рамках одного договора, отсортированные по framework_seq."""
    result = await db.execute(
        select(Purchase)
        .where(Purchase.contract_id == contract_id)
        .order_by(
            Purchase.framework_seq.asc().nulls_last(),
            Purchase.id.asc()
        )
    )
    purchases = result.scalars().all()
    out = []
    for p in purchases:
        d = PurchaseOutFull.model_validate(p)
        if p.contractor:
            d.contractor_name = p.contractor.name
        out.append(d)
    return out


@router.post("/{pid}/transition", response_model=PurchaseOutFull)
async def transition_status(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Forward-only status transition.
    wishes → plan_schedule → confirmed → work_in_progress → contracted → delivered → paid
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

    # Role check: only manager+ can transition
    if current_user.role not in MANAGER_ROLES:
        raise HTTPException(403, "Недостаточно прав для смены статуса")

    # Direction check: forward-only for non-admin
    if target_idx <= current_idx:
        if current_user.role not in ADMIN_ROLES:
            raise HTTPException(422, "Откат статуса разрешён только администратору")

    # Approval guard: block contracted transition if approval is pending/rejected
    if target_status == "contracted" and p.approval_status and p.approval_status not in ("approved",):
        raise HTTPException(
            422,
            f"Закупка должна быть согласована перед заключением договора. "
            f"Текущий статус согласования: {p.approval_status}"
        )

    # Catalog guard: all items must be linked to product catalog (except advance reports)
    if target_status == "confirmed" and getattr(p, 'purchase_method', None) != "advance":
        unmatched = [i for i in (p.items or []) if not i.product_id]
        if unmatched:
            names = ", ".join(i.item_name for i in unmatched[:3])
            suffix = "..." if len(unmatched) > 3 else ""
            raise HTTPException(
                422,
                f"Не все позиции привязаны к каталогу ({len(unmatched)} шт: {names}{suffix}). "
                f"Привяжите позиции к каталогу продуктов или используйте авансовый отчёт."
            )

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

    old_status = p.status
    p.status = target_status

    # При переходе в contracted — обновить цены в каталоге товаров
    if target_status == "contracted" and p.items:
        sub = await db.get(Subsidy, p.subsidy_id) if p.subsidy_id else None
        contract_org_id = sub.org_id if sub else None
        for item in p.items:
            if not item.product_id:
                continue
            product = await db.get(Product, item.product_id)
            if not product:
                continue
            item_price = item.unit_price
            product.contract_price = item_price
            product.price = item_price
            product.contract_number = p.contract_number
            product.contract_date = p.contract_date
            product.contract_org_id = contract_org_id

    await db.commit()
    await db.refresh(p)

    # Auto-log status change event
    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=getattr(current_user, "id", None),
            event_type="status_changed",
            data={"from": old_status, "to": target_status},
        ))
        await db.commit()
    except Exception:
        pass

    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.patch("/{pid}/assign")
async def assign_purchase(
    pid: int,
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign a purchase to a user (or unassign if user_id is None)."""
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if user_id is not None:
        user_check = await db.execute(select(User).where(User.id == user_id))
        if not user_check.scalar_one_or_none():
            raise HTTPException(404, "Пользователь не найден")
    p.assigned_user_id = user_id
    await db.commit()
    return {"ok": True, "assigned_user_id": user_id}


@router.patch("/{pid}/kanban-status")
async def kanban_status_change(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Quick status change from kanban board (same rules as transition)."""
    if target_status not in STATUS_ORDER:
        raise HTTPException(422, f"Недопустимый статус: {target_status}")
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # Only assigned user, managers or admins can change status
    is_assigned = p.assigned_user_id == current_user.id
    is_admin_or_manager = current_user.role in MANAGER_ROLES
    if not is_assigned and not is_admin_or_manager:
        raise HTTPException(403, "Недостаточно прав")

    old_status = p.status
    p.status = target_status
    await db.commit()

    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="status_changed",
            data={"from": old_status, "to": target_status, "via": "kanban"},
        ))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "status": target_status}


@router.patch("/{pid}/substatus")
async def update_substatus(
    pid: int,
    substatus: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set substatus for work_in_progress purchases."""
    if substatus and substatus not in VALID_SUBSTATUSES:
        raise HTTPException(422, f"Недопустимый подстатус: {substatus}. Допустимые: {', '.join(VALID_SUBSTATUSES)}")
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    is_assigned = p.assigned_user_id == current_user.id
    is_admin_or_manager = current_user.role in MANAGER_ROLES
    if not is_assigned and not is_admin_or_manager:
        raise HTTPException(403, "Недостаточно прав")

    # Auto-set status to work_in_progress if setting a substatus
    if substatus and p.status != "work_in_progress":
        p.status = "work_in_progress"
    p.substatus = substatus
    await db.commit()

    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="substatus_changed",
            data={"substatus": substatus},
        ))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "substatus": substatus, "status": p.status}


@router.patch("/{pid}/comment")
async def update_task_comment(
    pid: int,
    comment: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update task comment for kanban card."""
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    p.task_comment = comment
    await db.commit()
    return {"ok": True}


@router.get("/users-list")
async def users_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users available for assignment."""
    q = select(User.id, User.full_name, User.username, User.role)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q.order_by(User.full_name))
    return [
        {"id": r.id, "name": r.full_name or r.username, "role": r.role}
        for r in result
    ]


@router.get("/export/columns")
async def get_export_columns(_=Depends(get_current_user)):
    """Return available export column definitions."""
    return [
        {"key": k, "label": v["label"], "group": v["group"]}
        for k, v in ALL_EXPORT_COLUMNS.items()
    ]


@router.get("/export/excel")
async def export_purchases_to_excel(
    subsidy_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    columns: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    col_keys = (
        [k.strip() for k in columns.split(",") if k.strip() in ALL_EXPORT_COLUMNS]
        if columns else DEFAULT_EXPORT_COLUMNS
    )
    if not col_keys:
        col_keys = DEFAULT_EXPORT_COLUMNS

    q = select(Purchase).order_by(Purchase.id.desc())
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    purchases = (await db.execute(q)).scalars().all()

    contractors = {c.id: c.name for c in (await db.execute(select(Contractor))).scalars().all()}
    subsidies_map = {s.id: s.name for s in (await db.execute(select(Subsidy))).scalars().all()}
    feo_map = {f.id: f.name for f in (await db.execute(select(FeoCategory))).scalars().all()}
    ctx = {"contractors": contractors, "subsidies": subsidies_map, "feo_categories": feo_map}

    wb = Workbook()
    ws = wb.active
    ws.title = "Закупки"

    col_headers = [ALL_EXPORT_COLUMNS[k]["label"] for k in col_keys]
    ws.append(col_headers)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    empty_counts = {k: 0 for k in col_keys}
    for p in purchases:
        row = []
        for k in col_keys:
            val = _get_cell_value(k, p, ctx)
            row.append(val)
            if val == "" or val is None:
                empty_counts[k] += 1
        ws.append(row)

    for i, key in enumerate(col_keys, 1):
        col_letter = ws.cell(1, i).column_letter
        ws.column_dimensions[col_letter].width = max(len(col_headers[i - 1]) + 2, 12)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"purchases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    missing = []
    if len(purchases) >= 5:
        for k in col_keys:
            if empty_counts[k] / len(purchases) > 0.8:
                missing.append(ALL_EXPORT_COLUMNS[k]["label"])

    resp_headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Access-Control-Expose-Headers": "X-Missing-Columns",
    }
    if missing:
        resp_headers["X-Missing-Columns"] = ",".join(missing[:5])

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=resp_headers,
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
        "wishes": "wishes", "желания": "wishes", "planned": "wishes", "планируется": "wishes", "план": "wishes",
        "plan_schedule": "plan_schedule", "план-график": "plan_schedule",
        "confirmed": "confirmed", "подтверждено": "confirmed",
        "work_in_progress": "work_in_progress", "в работе": "work_in_progress", "in_progress": "work_in_progress",
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
        if v is None:
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
            status_raw = (cell(row, "status") or "wishes").lower().strip()
            status = STATUS_MAP.get(status_raw, "wishes")

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


# ---------------------------------------------------------------------------
# Purchase items import from Excel
# ---------------------------------------------------------------------------

@router.get("/items/import/template")
async def items_import_template(_=Depends(require_role(*MANAGER_ROLES))):
    """Download xlsx template for bulk purchase items import."""
    if not Workbook:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "Позиции"

    headers = ["Наименование", "Тип (товар/услуга/работа)", "Количество", "Ед. изм.", "Цена за единицу"]
    required = {"Наименование"}

    header_fill = PatternFill("solid", fgColor="1E40AF")
    req_fill = PatternFill("solid", fgColor="1D4ED8")
    header_font = Font(bold=True, color="FFFFFF")

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = req_fill if h in required else header_fill
        cell.alignment = Alignment(horizontal="center")

    example = ["Ноутбук Lenovo ThinkPad", "товар", "5", "шт", "85000"]
    for ci, val in enumerate(example, 1):
        ws.cell(row=2, column=ci, value=val)

    col_widths = [45, 25, 15, 15, 20]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=items_template.xlsx"},
    )


@router.post("/{pid}/items/import")
async def import_items_excel(
    pid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    """Bulk import items into a purchase from Excel."""
    if not (file.filename or '').lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx / .xls")
    if not load_workbook:
        raise HTTPException(500, "openpyxl не установлен")

    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    content = await file.read()
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    ws = wb.active
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise HTTPException(400, "Файл пустой")

    def _norm(v) -> str:
        return str(v).strip().lower() if v else ''

    # Fuzzy column mapping
    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        h_str = _norm(h)
        if any(x in h_str for x in ('наименован', 'назван', 'name', 'товар', 'предмет')):
            col.setdefault('item_name', i)
        elif any(x in h_str for x in ('тип', 'type', 'вид')):
            col.setdefault('item_type', i)
        elif any(x in h_str for x in ('кол', 'количеств', 'qty', 'quantity')):
            col.setdefault('quantity', i)
        elif any(x in h_str for x in ('ед.', 'единиц', 'unit', 'изм')):
            col.setdefault('unit', i)
        elif any(x in h_str for x in ('цена', 'price', 'стоимость', 'за единиц')):
            col.setdefault('unit_price', i)

    if 'item_name' not in col:
        raise HTTPException(400, "Не найдена колонка с наименованием.")

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
        return s

    def _to_dec(v):
        if v is None:
            return None
        try:
            return Decimal(str(v).replace(',', '.').replace(' ', ''))
        except Exception:
            return None

    # Load products for auto-matching by name
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    prod_result = await db.execute(prod_q)
    products = prod_result.scalars().all()
    # Build name lookup (lowercase → product)
    product_by_name: dict[str, Product] = {}
    for p in products:
        if p.name:
            product_by_name[p.name.lower().strip()] = p

    TYPE_MAP = {
        'товар': 'товар', 'товары': 'товар', 'product': 'товар', 'goods': 'товар',
        'услуга': 'услуга', 'услуги': 'услуга', 'service': 'услуга',
        'работа': 'работа', 'работы': 'работа', 'work': 'работа',
    }

    added = 0
    matched_catalog = 0
    unmatched = 0
    errors_list = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        item_name = _cell(row, 'item_name')
        if not item_name:
            continue

        item_type_raw = (_cell(row, 'item_type') or 'товар').lower().strip()
        item_type = TYPE_MAP.get(item_type_raw, 'товар')
        quantity = _to_dec(_cell(row, 'quantity')) or Decimal('1')
        unit = _cell(row, 'unit') or 'шт'
        unit_price = _to_dec(_cell(row, 'unit_price'))
        total_price = (quantity * unit_price) if unit_price else None

        # Auto-match product
        product_id = None
        matched_product = product_by_name.get(item_name.lower().strip())
        if matched_product:
            product_id = matched_product.id
            matched_catalog += 1
            if not unit_price and matched_product.price:
                unit_price = matched_product.price
                total_price = quantity * unit_price
        else:
            unmatched += 1

        item = PurchaseItem(
            purchase_id=pid,
            product_id=product_id,
            item_name=item_name,
            item_type=item_type,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total_price=total_price,
        )
        db.add(item)
        added += 1

    await db.commit()
    return {"added": added, "matched_catalog": matched_catalog, "unmatched": unmatched, "errors": errors_list}
