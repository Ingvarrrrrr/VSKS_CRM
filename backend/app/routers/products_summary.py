"""Сводная по продукции — вынесено из products.py (Правило №5, сессия 2026-09-08).

GET /api/products/summary — статический литеральный путь на префиксе
/api/products, ОДИН сегмент ("summary"). products.router несёт
GET /{product_id} БЕЗ явного int-конвертера в строке пути (совпадает по форме
с любым односегментным литералом), поэтому этот роутер обязан
регистрироваться в routes.py ДО products.router — иначе Starlette матчит
"/summary" на catch-all первым и FastAPI падает 422 при попытке привести
"summary" к int.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.schemas import ProductSummaryGroup, ProductSummaryItem
from decimal import Decimal

router = APIRouter(prefix="/api/products", tags=["products"])

# Сводная строит ОДНУ группу на КАЖДЫЙ отдельный товар, вложенные "items" —
# по одной строке на закупку этого товара (не ограничены лимитом, т.к. число
# закупок одного товара в разумных пределах; лимит — на число РАЗНЫХ товаров
# в ответе, владелец, 2026-10-26, рост каталога к 250+ тыс.).
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@router.get("/summary", response_model=dict)
async def product_summary(
    subsidy_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None),
    region: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _perm: User = Depends(require_tab('products.summary')),
):
    """Сводная по продукции — агрегация закупок по продуктам через все субсидии.

    КОНТРАКТ ИЗМЕНЁН (владелец, 2026-10-26, рост каталога к 250+ тыс.
    товаров): раньше отдавался ПЛОСКИЙ список ProductSummaryGroup без лимита
    (одна группа на каждый товар, встретившийся хоть раз в закупках, —
    без явного product_id/search это могло быть «весь каталог, у которого
    есть покупки»). Теперь — {"items": [...], "total": N} с пагинацией
    (limit/offset, default 100, max 500) ПО ЧИСЛУ ТОВАРОВ (групп), не строк
    внутри группы. Список товаров, у которых есть закупки, отбирается ОДНИМ
    легковесным SELECT DISTINCT (без JOIN на PurchaseItem/Purchase целиком),
    затем для НИХ ЖЕ строится полная агрегация — вместо того, чтобы грузить
    все строки фактов закупок по ВСЕМ подходящим товарам сразу."""
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase
    from app.models.subsidy import Subsidy
    from app.models.organization import Organization
    from sqlalchemy.orm import joinedload
    from sqlalchemy import extract, func
    from datetime import date as _date

    def _apply_common_filters(stmt):
        if subsidy_id is not None:
            stmt = stmt.where(Purchase.subsidy_id == subsidy_id)
        if category is not None:
            stmt = stmt.where(Product.category == category)
        if product_id is not None:
            stmt = stmt.where(Product.id == product_id)
        if search:
            stmt = stmt.where(Product.name.ilike(f"%{search}%"))
        if org_id is not None:
            stmt = stmt.where(Subsidy.org_id == org_id)
        if region is not None:
            stmt = stmt.where(Purchase.region == region)
        if date_from is not None:
            try:
                df = _date.fromisoformat(date_from)
                stmt = stmt.where(Purchase.delivery_date >= df)
            except ValueError:
                pass
        if date_to is not None:
            try:
                dt = _date.fromisoformat(date_to)
                stmt = stmt.where(Purchase.delivery_date <= dt)
            except ValueError:
                pass
        if quarter is not None:
            stmt = stmt.where(extract("quarter", Purchase.delivery_date) == quarter)
        return stmt

    # Двухуровневая видимость по вкладке «Сводная по продукции».
    vis = await get_visible_subsidy_ids(current_user, db, "products.summary")
    if vis is not None and not vis:
        return {"items": [], "total": 0}

    # Шаг 1: ЛЁГКИЙ запрос — только id товаров, у которых есть подходящая
    # закупка, под теми же фильтрами (без джойна на Organization/без
    # вытягивания строк PurchaseItem). Пагинация (limit/offset) — ПО ЭТОМУ
    # списку, не по количеству строк факта закупок.
    id_q = (
        select(Product.id)
        .join(PurchaseItem, PurchaseItem.product_id == Product.id)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(Subsidy, Purchase.subsidy_id == Subsidy.id)
        .where(PurchaseItem.product_id.isnot(None))
        .distinct()
    )
    id_q = _apply_common_filters(id_q)
    if vis is not None:
        id_q = id_q.where(Purchase.subsidy_id.in_(vis))

    total = (await db.execute(
        select(func.count()).select_from(id_q.subquery())
    )).scalar_one()

    page_ids = (await db.execute(
        id_q.order_by(Product.name).offset(offset).limit(limit)
    )).scalars().all()
    if not page_ids:
        return {"items": [], "total": total}

    # Шаг 2: полная агрегация (как и раньше), но ТОЛЬКО для товаров этой
    # страницы — не для всего отфильтрованного множества сразу.
    q = (
        select(PurchaseItem)
        .join(Product, PurchaseItem.product_id == Product.id)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(Subsidy, Purchase.subsidy_id == Subsidy.id)
        .outerjoin(Organization, Subsidy.org_id == Organization.id)
        .where(Product.id.in_(page_ids))
        .options(
            joinedload(PurchaseItem.product),
            joinedload(PurchaseItem.purchase).joinedload(Purchase.feo_category),
        )
    )
    q = _apply_common_filters(q)
    if vis is not None:
        q = q.where(Purchase.subsidy_id.in_(vis))

    # Also need subsidy name, org name, org_id — use add_columns
    q = q.add_columns(
        Subsidy.name.label("subsidy_name"),
        Organization.name.label("org_name"),
        Subsidy.org_id.label("s_org_id"),
    )
    q = q.order_by(Product.name, Subsidy.name)

    result = await db.execute(q)
    rows = result.unique().all()

    # Group by product
    groups: dict[int, dict] = {}
    for row in rows:
        pi = row[0]       # PurchaseItem
        s_name = row[1]   # subsidy_name
        o_name = row[2]   # org_name
        s_org_id = row[3] # subsidy.org_id
        product = pi.product
        purchase = pi.purchase

        pid = product.id
        if pid not in groups:
            groups[pid] = {
                "product_id": pid,
                "product_name": product.name,
                "category": product.category,
                "product_type": product.product_type,
                "total_quantity": Decimal(0),
                "total_amount": Decimal(0),
                "purchase_count": 0,
                "items": [],
            }

        qty = pi.quantity or Decimal(0)
        amt = pi.total_price or pi.final_total or Decimal(0)
        groups[pid]["total_quantity"] += qty
        groups[pid]["total_amount"] += amt
        groups[pid]["purchase_count"] += 1
        groups[pid]["items"].append(ProductSummaryItem(
            purchase_id=purchase.id,
            subsidy_name=s_name or "",
            org_name=o_name,
            org_id=s_org_id,
            region=purchase.region,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total_price=pi.total_price or pi.final_total,
            status=purchase.status,
            delivery_date=purchase.delivery_date,
            delivery_address=purchase.delivery_address,
            procurement_planned_date=purchase.procurement_planned_date,
            purchase_method=purchase.purchase_method,
        ))

    return {
        "items": [ProductSummaryGroup(**g) for g in groups.values()],
        "total": total,
    }
