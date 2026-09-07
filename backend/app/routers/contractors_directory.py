"""Справочные GET-эндпоинты каталога контрагентов: категории, статистика, дубли по ИНН.

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/contractors. ВАЖНО: все три пути здесь — ровно один сегмент
(/product-categories, /with-stats, /duplicates-by-inn), поэтому ОБЯЗАНЫ
регистрироваться в app/routes.py ДО contractors.router — иначе Starlette
матчит их на литерал маршрута GET /{cid} раньше, чем на эти, и FastAPI
падает 422 при попытке привести "product-categories" и т.п. к int.

find_duplicate_contractor_groups в app/services/contractor_dedup.py решает
похожую, но НЕ ту же задачу (группировка по TRIM(inn) для offline-скрипта
слияния дублей, без деталей контрагентов для UI) — сознательно не сливаем,
у list_duplicates_by_inn ниже свой формат ответа для фронта.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, distinct, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contractor import Contractor
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.schemas.schemas import ContractorOut
from app.models.user import User

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


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
    search: str = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: str = Query(None),
):
    """Contractors with product categories, server-side pagination + search."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product

    q = select(Contractor).order_by(Contractor.name)
    # Контрагенты — общий справочник юрлиц (см. фикс в list_contractors:1071).
    # Org-фильтр снят: ContractorsView и autocomplete показывают всех.
    if search:
        term = f"%{search}%"
        q = q.where(or_(Contractor.name.ilike(term), Contractor.inn.ilike(term)))
    if category:
        # Filter by manual_product_categories JSONB contains, or "Все"
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast, literal
        q = q.where(or_(
            Contractor.manual_product_categories.op('?')(category),
            Contractor.manual_product_categories.op('?')('Все'),
        ))

    # Total count for pagination
    from sqlalchemy import func as safunc
    count_q = select(safunc.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    contractors = (await db.execute(q.offset(offset).limit(limit))).scalars().all()
    c_ids = [c.id for c in contractors]

    # Product categories per contractor (only for current page)
    prod_cat_map = {}
    if c_ids:
        prod_stmt = (
            select(
                Purchase.contractor_id,
                func.array_agg(distinct(Product.category)).label("product_categories"),
            )
            .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
            .join(Product, Product.id == PurchaseItem.product_id)
            .where(Purchase.contractor_id.in_(c_ids))
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
        if "Все" in manual:
            c_dict["product_categories"] = ["Все"]
        else:
            merged = list(dict.fromkeys(manual + auto))
            c_dict["product_categories"] = merged
        result.append(c_dict)
    return {"items": result, "total": total}


@router.get("/duplicates-by-inn")
async def list_duplicates_by_inn(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('contractors')),
):
    """
    Группирует контрагентов с непустым ИНН, возвращает только группы где count>1.
    Сортировка: max count first, потом по ИНН.
    """
    groups_rows = (await db.execute(
        select(Contractor.inn, func.count(Contractor.id).label('cnt'))
        .where(Contractor.inn.isnot(None))
        .where(func.trim(Contractor.inn) != '')
        .group_by(Contractor.inn)
        .having(func.count(Contractor.id) > 1)
        .order_by(func.count(Contractor.id).desc(), Contractor.inn)
    )).all()

    if not groups_rows:
        return {"groups": [], "total_groups": 0, "total_extra": 0}

    inns = [r[0] for r in groups_rows]
    details = (await db.execute(
        select(Contractor).where(Contractor.inn.in_(inns)).order_by(Contractor.inn, Contractor.id)
    )).scalars().all()

    by_inn: dict = {}
    for c in details:
        by_inn.setdefault(c.inn, []).append({
            "id": c.id,
            "name": c.name or "",
            "full_name": c.full_name or "",
            "kpp": c.kpp or "",
            "address": c.address or "",
            "ogrn": c.ogrn or "",
            "org_type": c.org_type or "",
        })

    out = []
    total_extra = 0
    for inn, cnt in groups_rows:
        contractors = by_inn.get(inn, [])
        out.append({"inn": inn, "count": cnt, "contractors": contractors})
        total_extra += cnt - 1

    return {"groups": out, "total_groups": len(out), "total_extra": total_extra}
