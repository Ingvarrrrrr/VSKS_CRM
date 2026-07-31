from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES, ALL_ROLES
from app.auth.permissions import require_tab
from app.auth.visibility import get_visible_subsidy_ids
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


def _content_disposition(filename: str) -> str:
    """RFC 5987 — кириллица в имени файла недопустима в latin-1 заголовке."""
    from urllib.parse import quote
    ascii_fallback = filename.encode('ascii', 'ignore').decode('ascii').strip() or 'export'
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/purchase-totals")
async def get_purchase_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Фактическая сумма per feo_category_id: только поставленное/оплаченное (по актам)."""
    from app.models.purchase import Purchase
    stmt = (
        select(
            Purchase.feo_category_id,
            func.coalesce(
                func.sum(func.coalesce(Purchase.final_total_amount, Purchase.planned_total_price)), 0
            ).label("total_planned"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .where(Purchase.status.in_(["delivered", "paid"]))
        .group_by(Purchase.feo_category_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r.feo_category_id: float(r.total_planned) for r in rows}


@router.get("/planned-purchase-totals")
async def get_planned_purchase_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Плановая сумма и количество из заявок per feo_category_id: позиции закупок в статусах план-графика и дальше."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_budget import PLANNED_STATUSES

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            cat_col.label("cat_id"),
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("total"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(cat_col.isnot(None))
        .group_by(cat_col)
    )
    rows = (await db.execute(stmt)).all()
    return {r.cat_id: {"total": float(r.total), "qty": float(r.qty)} for r in rows}


@router.get("/planned-purchase-items")
async def get_planned_purchase_items(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Позиции закупок «из заявок» per feo_category_id (статусы план-графика и дальше)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.routers.purchase_budget import PLANNED_STATUSES

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            cat_col.label("cat_id"),
            PurchaseItem.id,
            PurchaseItem.item_name,
            PurchaseItem.quantity,
            PurchaseItem.unit,
            PurchaseItem.unit_price,
            PurchaseItem.total_price,
            PurchaseItem.purchase_id,
            PurchaseItem.product_id,
            Purchase.purchase_number,
            Purchase.registry_number,
            Purchase.status.label("purchase_status"),
            Purchase.wish_id,
            Product.category.label("product_category"),
            Product.product_type.label("product_type"),
            Product.photo_data.isnot(None).label("product_has_photo"),
            Product.photo_url,
            Product.photo_link,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(Product, PurchaseItem.product_id == Product.id)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(cat_col.isnot(None))
        .order_by(cat_col, PurchaseItem.item_name)
    )
    rows = (await db.execute(stmt)).all()
    result: dict[int, list] = {}
    for r in rows:
        if r.product_id is not None and r.product_has_photo:
            product_photo = f"/api/products/{r.product_id}/photo"
        elif r.product_id is not None:
            product_photo = r.photo_url or r.photo_link or None
        else:
            product_photo = None
        result.setdefault(r.cat_id, []).append({
            "id": r.id,
            "item_name": r.item_name,
            "quantity": float(r.quantity or 0),
            "unit": r.unit,
            "unit_price": float(r.unit_price or 0),
            "total_price": float(r.total_price or 0),
            "purchase_id": r.purchase_id,
            "purchase_number": r.purchase_number,
            "registry_number": r.registry_number,
            "purchase_status": r.purchase_status,
            "wish_id": r.wish_id,
            "category": r.product_category or "Без категории",
            "product_type": r.product_type or "Без вида",
            "product_photo": product_photo,
        })
    return result


@router.get("/leaves")
async def get_feo_leaves(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Returns leaf FeoCategory nodes (без детей) with aggregated used_amount via feo_category_id.

    Response: [{id, name, parent_id, level, budget, used_amount, residual, path}]
    where path = "Direction › Subcategory › LeafName".
    """
    from sqlalchemy import select, func as sqlfunc, case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES, PLANNED_STATUSES

    # Все FeoCategory для subsidy
    cats_q = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    all_cats = (await db.execute(cats_q)).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1

    # Leaves = категории у которых нет детей в feo_categories
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]
    if not leaves:
        return []

    leaf_ids = [c.id for c in leaves]

    # Aggregate contracted_used and planned_used per feo_category_id via conditional sums
    used_q = (
        select(
            PurchaseItem.feo_category_id,
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(PLANNED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(PurchaseItem.feo_category_id.in_(leaf_ids))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(PurchaseItem.feo_category_id)
    # leaf_used_map: {feo_category_id: (contracted_used, planned_used)}
    leaf_used_map: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        leaf_used_map[r.feo_category_id] = (float(r.contracted_used), float(r.planned_used))

    # Build path "Direction › Subcategory › Leaf"
    def build_path(cat) -> str:
        names = [cat.name]
        cur = cat
        while cur.parent_id is not None and cur.parent_id in cat_by_id:
            cur = cat_by_id[cur.parent_id]
            names.append(cur.name)
        return " \u203a ".join(reversed(names))

    result = []
    for c in leaves:
        budget = float(c.budget or 0)
        contracted_used, planned_used = leaf_used_map.get(c.id, (0.0, 0.0))
        uncontracted_remaining = budget - contracted_used
        spendable_remaining = budget - planned_used
        result.append({
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "level": c.level,
            "budget": budget,
            # New metrics
            "contracted_used": contracted_used,
            "planned_used": planned_used,
            "uncontracted_remaining": uncontracted_remaining,
            "spendable_remaining": spendable_remaining,
            # Legacy fields (kept for backward compat): used_amount = planned_used, residual = spendable_remaining
            "used_amount": planned_used,
            "residual": spendable_remaining,
            "path": build_path(c),
        })

    # Сортировка по path для удобства autocomplete
    result.sort(key=lambda x: x["path"])
    return result


@router.get("/budget-residuals")
async def feo_budget_residuals(
    subsidy_id: int = Query(...),
    category_ids: str = Query("", description="comma-separated leaf FeoCategory ids"),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Остатки бюджета по ФЭО для формы закупки.

    Для пользователей с feo_budget.view_all_levels возвращает направления (ур.1)
    и ancestors предков в каждом листе. Без этого права: directions=[],
    ancestors=[] — только сам листовой остаток.

    budget листа = FeoCategory.budget; used = SUM(PurchaseItem.total_price) по feo_category_id листа.
    Узел выше: budget = собственный .budget если задан, иначе сумма budget детей;
    used = сумма used всех листьев-потомков. residual = budget - used.
    Ответ: {directions:[{id,name,level,path,budget,used,residual}],
            leaves:[{id,name,level,path,budget,used,residual,ancestors:[...]}]}
    (ancestors — сверху вниз: ур.1 первым).
    """
    from app.auth.permissions import _get_effective, _active_org
    effective = await _get_effective(current_user, db, _active_org(current_user))
    can_view_all_levels = (current_user.role == "superadmin") or ("feo_budget.view_all_levels" in effective)
    from sqlalchemy import select as _sel, func as _f, case as _case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES, PLANNED_STATUSES

    ids = [int(x) for x in category_ids.split(",") if x.strip().isdigit()]
    all_cats = (await db.execute(
        _sel(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return {"directions": [], "leaves": []}
    cat_by_id = {c.id: c for c in all_cats}
    children: dict[int, list] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children.setdefault(c.parent_id, []).append(c.id)
    leaf_ids_all = [c.id for c in all_cats if not children.get(c.id)]

    used_q = (
        _sel(
            PurchaseItem.feo_category_id,
            _f.coalesce(
                _f.sum(_case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            _f.coalesce(
                _f.sum(_case((_Purchase.status.in_(list(PLANNED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(PurchaseItem.feo_category_id.in_(leaf_ids_all))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(PurchaseItem.feo_category_id)
    # leaf_used: {feo_category_id: (contracted_used, planned_used)}
    leaf_used: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        leaf_used[r.feo_category_id] = (float(r.contracted_used), float(r.planned_used))

    def descendant_leaves(cid):
        ch = children.get(cid)
        if not ch:
            return [cid]
        out = []
        for x in ch:
            out.extend(descendant_leaves(x))
        return out

    def calc_budget(cid):
        c = cat_by_id[cid]
        ch = children.get(cid)
        if not ch:
            return float(c.budget) if c.budget is not None else 0.0
        if c.budget is not None:
            return float(c.budget)
        return sum(calc_budget(x) for x in ch)

    def contracted_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[0] for l in descendant_leaves(cid))

    def planned_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[1] for l in descendant_leaves(cid))

    def node_info(cid):
        c = cat_by_id[cid]
        b = calc_budget(cid)
        cu = contracted_of(cid)
        pu = planned_of(cid)
        return {
            "id": cid, "name": c.name, "level": c.level,
            "budget": b,
            "contracted_used": cu,
            "planned_used": pu,
            "uncontracted_remaining": b - cu,
            "spendable_remaining": b - pu,
            # Legacy fields (backward compat): used = planned_used, residual = spendable_remaining
            "used": pu,
            "residual": b - pu,
        }

    def path_of(cid):
        names = []
        cur = cat_by_id.get(cid)
        while cur is not None:
            names.append(cur.name)
            cur = cat_by_id.get(cur.parent_id) if cur.parent_id else None
        return " \u203a ".join(reversed(names))

    # Направления (ур.1) субсидии — только для пользователей с view_all_levels.
    directions = []
    if can_view_all_levels:
        # Порядок как во вкладке субсидии: sort_order, затем id (не алфавит)
        roots = [c for c in all_cats if c.level == 1 or c.parent_id is None]
        roots.sort(key=lambda c: (c.sort_order is None, c.sort_order or 0, c.id))
        for c in roots:
            d = node_info(c.id)
            d["path"] = path_of(c.id)
            directions.append(d)

    leaves = []
    for lid in ids:
        if lid not in cat_by_id:
            continue
        leaf = node_info(lid)
        leaf["path"] = path_of(lid)
        # ancestors только для пользователей с view_all_levels
        if can_view_all_levels:
            ancestors = []
            cur = cat_by_id[lid]
            while cur.parent_id and cur.parent_id in cat_by_id:
                cur = cat_by_id[cur.parent_id]
                ancestors.append(node_info(cur.id))
            leaf["ancestors"] = list(reversed(ancestors))
        else:
            leaf["ancestors"] = []
        leaves.append(leaf)
    return {"directions": directions, "leaves": leaves}


@router.get("/", response_model=List[FeoCategoryOut])
async def list_categories(
    parent_id: Optional[int] = Query(None),
    level: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    appendix: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(FeoCategory)
    vis = await get_visible_subsidy_ids(current_user, db, "feo_categories")
    if vis is not None:
        # ФЭО-категории выбираются внутри форм заявки/закупки, поэтому пикер
        # доступен всем, кто видит субсидию по вкладкам wishes или purchases
        # (напр. роль Менеджер без админской вкладки feo_categories видит субсидию
        # только через «Заявки») — иначе список категорий пуст.
        vis = vis | await get_visible_subsidy_ids(current_user, db, "purchases")
        vis = vis | await get_visible_subsidy_ids(current_user, db, "wishes")
        q = q.where(FeoCategory.subsidy_id.in_(vis))
    if parent_id is not None:
        q = q.where(FeoCategory.parent_id == parent_id)
    if level is not None:
        q = q.where(FeoCategory.level == level)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    if appendix is not None:
        q = q.where(FeoCategory.appendix == appendix)
    if is_active is not None:
        q = q.where(FeoCategory.is_active == is_active)
    result = await db.execute(q.order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id))
    return result.scalars().all()


@router.get("/flat")
async def get_feo_flat(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Returns all FeoCategory nodes for a subsidy as a flat list with is_leaf flag.

    Response: [{id, name, parent_id, level, is_leaf, budget}]
    is_leaf = True if the node has no children within the same subsidy.
    budget = собственная (ручная) сумма финансирования узла, без расчёта по детям.
    Sorted by level, then sort_order, then id.
    """
    cats_q = (
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .order_by(FeoCategory.level, FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )
    all_cats = (await db.execute(cats_q)).scalars().all()
    if not all_cats:
        return []

    # Determine which nodes have children
    has_children: set[int] = set()
    for c in all_cats:
        if c.parent_id is not None:
            has_children.add(c.parent_id)

    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "level": c.level,
            "is_leaf": c.id not in has_children,
            "description": c.description,
            "budget": float(c.budget) if c.budget is not None else None,
        }
        for c in all_cats
    ]


@router.get("/tree")
async def category_tree(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(FeoCategory)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, FeoCategory.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q.order_by(FeoCategory.level, FeoCategory.sort_order.nulls_last(), FeoCategory.id))
    all_cats = result.scalars().all()
    by_id = {c.id: {"id": c.id, "parent_id": c.parent_id, "subsidy_id": c.subsidy_id,
                    "level": c.level, "name": c.name, "code": c.code,
                    "appendix": c.appendix, "is_active": c.is_active,
                    "description": c.description,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "feo_quantity": float(c.feo_quantity) if c.feo_quantity is not None else None,
                    "feo_unit": c.feo_unit,
                    "feo_amount": float(c.feo_amount) if c.feo_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "unit": c.unit,
                    "children": []} for c in all_cats}
    roots = []
    for c in all_cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


class _UnallocatedBody(BaseModel):
    subsidy_id: int
    parent_id: Optional[int] = None


@router.post("/unallocated")
async def get_or_create_unallocated(
    body: _UnallocatedBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Найти или создать категорию «Не определена» (или «Нераспределённое») для субсидии.

    Доступна всем авторизованным пользователям с доступом к субсидии
    (wishes / purchases / feo_categories). Не требует require_tab('feo_categories').

    parent_id (опц.) — создать дочернюю «Не определена» под этим родителем.

    Response: {id, name, subsidy_id, parent_id, created: bool}
    """
    from app.models.subsidy import Subsidy

    # Проверить существование субсидии
    sub = (await db.execute(select(Subsidy).where(Subsidy.id == body.subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Субсидия не найдена")

    # Изоляция по организации (аналогично list_categories)
    vis = await get_visible_subsidy_ids(current_user, db, "feo_categories")
    if vis is not None:
        vis = vis | await get_visible_subsidy_ids(current_user, db, "purchases")
        vis = vis | await get_visible_subsidy_ids(current_user, db, "wishes")
        if body.subsidy_id not in vis:
            raise HTTPException(status_code=403, detail="Нет доступа к этой субсидии")

    # Загрузить родителя, если указан
    parent: Optional[FeoCategory] = None
    if body.parent_id is not None:
        parent = (await db.execute(
            select(FeoCategory).where(FeoCategory.id == body.parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != body.subsidy_id:
            raise HTTPException(
                status_code=422,
                detail="Родительская категория относится к другой субсидии",
            )

    # Найти существующую (все варианты имён для обратной совместимости)
    stmt = (
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == body.subsidy_id)
        .where(FeoCategory.is_active.is_(True))
        .where(func.lower(FeoCategory.name).in_([
            "не определена",
            "нераспределённое",
            "нераспределенное",
        ]))
    )
    if body.parent_id is None:
        stmt = stmt.where(FeoCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(FeoCategory.parent_id == body.parent_id)

    existing = (await db.execute(stmt.order_by(FeoCategory.id).limit(1))).scalars().first()
    if existing:
        return {
            "id": existing.id,
            "name": existing.name,
            "subsidy_id": existing.subsidy_id,
            "parent_id": existing.parent_id,
            "created": False,
        }

    # Создать новую
    new_level = (parent.level + 1) if parent is not None else 1
    new_cat = FeoCategory(
        name="Не определена",
        subsidy_id=body.subsidy_id,
        parent_id=body.parent_id,
        level=new_level,
        sort_order=9999,
        is_active=True,
    )
    db.add(new_cat)
    await db.commit()
    await db.refresh(new_cat)
    return {
        "id": new_cat.id,
        "name": new_cat.name,
        "subsidy_id": new_cat.subsidy_id,
        "parent_id": new_cat.parent_id,
        "created": True,
    }


@router.post("/", response_model=FeoCategoryOut)
async def create_category(
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    if category_data.parent_id:
        parent_result = await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена")
        level = parent.level + 1
    else:
        level = 1

    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active,
        description=category_data.description,
        budget=category_data.budget,
        feo_quantity=category_data.feo_quantity,
        feo_unit=category_data.feo_unit,
        feo_amount=category_data.feo_amount,
        planned_quantity=category_data.planned_quantity,
        planned_amount=category_data.planned_amount,
        unit=category_data.unit,
    )
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category


@router.get("/import/template")
async def download_feo_template(
    _=Depends(get_current_user),
):
    """Шаблон Excel для импорта категорий ФЭО (37 колонок).

    Для Ур.2–4: ФЭО-кол-во + ед.изм. + стоимость за ед. + СУММА по строке ФЭО;
                плановое кол-во + ед.изм. + стоимость за ед. + СУММА плана.
    Ур.5: плановый товар/услуга — кол-во, ед.изм., цена за ед., итоговая сумма.
    Атрибуты: Код, Приложение, Финансирование, Активна.
    Если уровень пропущен, содержимое нижнего поднимается на его место.
    Сумма строки приоритетнее кол-во × цена; расхождение = предупреждение.
    """
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Категории ФЭО"
    headers = [
        "Субсидия",                                         # A   1
        "Уровень 2 (Направление расходов по ФЭО)",          # B   2
        "Кол-во по ФЭО (Ур.2)",                             # C   3
        "Ед. изм. по ФЭО (Ур.2)",                           # D   4
        "Стоимость по ФЭО (Ур.2)",                          # E   5
        "Сумма по ФЭО (Ур.2)",                              # F   6  ← НОВАЯ
        "Плановое кол-во (Ур.2)",                           # G   7
        "Ед. изм. плана (Ур.2)",                            # H   8
        "Плановая стоимость за ед. (Ур.2)",                 # I   9
        "Сумма плана (Ур.2)",                               # J  10  ← НОВАЯ
        "Уровень 3 (Тип расходов по ФЭО)",                  # K  11
        "Кол-во по ФЭО (Ур.3)",                             # L  12
        "Ед. изм. по ФЭО (Ур.3)",                           # M  13
        "Стоимость по ФЭО (Ур.3)",                          # N  14
        "Сумма по ФЭО (Ур.3)",                              # O  15  ← НОВАЯ
        "Плановое кол-во (Ур.3)",                           # P  16
        "Ед. изм. плана (Ур.3)",                            # Q  17
        "Плановая стоимость за ед. (Ур.3)",                 # R  18
        "Сумма плана (Ур.3)",                               # S  19  ← НОВАЯ
        "Уровень 4 (Конкретизированный)",                   # T  20
        "Кол-во по ФЭО (Ур.4)",                             # U  21
        "Ед. изм. по ФЭО (Ур.4)",                           # V  22
        "Стоимость по ФЭО (Ур.4)",                          # W  23
        "Сумма по ФЭО (Ур.4)",                              # X  24  ← НОВАЯ
        "Плановое кол-во (Ур.4)",                           # Y  25
        "Ед. изм. плана (Ур.4)",                            # Z  26
        "Плановая стоимость за ед. (Ур.4)",                 # AA 27
        "Сумма плана (Ур.4)",                               # AB 28  ← НОВАЯ
        "Уровень 5 (Плановый товар/услуга)",                # AC 29
        "Количество (Ур.5)",                                # AD 30
        "Ед. измерения (Ур.5)",                             # AE 31
        "Цена за ед. (Ур.5)",                               # AF 32  ← НОВАЯ
        "Сумма по позиции (Ур.5)",                          # AG 33  ← переименование
        "Код",                                              # AH 34
        "Приложение",                                       # AI 35
        "Финансирование",                                   # AJ 36
        "Активна",                                          # AK 37
    ]
    ws.append(headers)

    # Цветовое кодирование заголовков
    fill_cat  = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")   # синий — категории + ФЭО
    fill_plan = PatternFill(start_color="0891B2", end_color="0891B2", fill_type="solid")   # голубой — плановые
    fill_item = PatternFill(start_color="059669", end_color="059669", fill_type="solid")   # зелёный — ур.5
    fill_attr = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")  # фиолетовый — атрибуты
    font_w = Font(color="FFFFFF", bold=True, size=10)

    # col index (1-based):
    # синий: 1-2 (субсидия+ур2), 3-6 (feo ур2+сумма), 11-15 (ур3+feo), 20-24 (ур4+feo)
    # голубой: 7-10 (plan ур2), 16-19 (plan ур3), 25-28 (plan ур4)
    # зелёный: 29-33 (ур5)
    # фиолетовый: 34-37 (атрибуты)
    _blue_cols  = {1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 20, 21, 22, 23, 24}
    _cyan_cols  = {7, 8, 9, 10, 16, 17, 18, 19, 25, 26, 27, 28}
    _green_cols = {29, 30, 31, 32, 33}

    for i, cell in enumerate(ws[1], start=1):
        if i in _blue_cols:
            cell.fill = fill_cat
        elif i in _cyan_cols:
            cell.fill = fill_plan
        elif i in _green_cols:
            cell.fill = fill_item
        else:
            cell.fill = fill_attr
        cell.font = font_w
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 52

    # Примеры (строки 2–6), 37 элементов каждая:
    # col:  1=Субс 2=Ур2       3=feoQ2  4=feoU2     5=feoA2 6=feoS2   7=pQ2 8=pU2 9=pA2 10=pS2   11=Ур3               12=feoQ3 13=feoU3  14=feoA3 15=feoS3   16=pQ3 17=pU3 18=pA3 19=pS3  20=Ур4                 21=feoQ4 22=feoU4 23=feoA4 24=feoS4   25=pQ4 26=pU4 27=pA4 28=pS4  29=Ур5                        30=qty 31=unit 32=цена  33=сумма   34=Код      35=Прил    36=Финанс  37=Акт
    # Строка 1: у Ур.4 задана только сумма (без кол-во и цены)
    ws.append(["ФАДМ_2026", "Техническое оснащение", "", "", "", "", "", "", "", "", "Оргтехника", "", "", "", "2000000", "", "", "", "", "Закупка компьютеров", "6", "шт", "", "", "", "", "", "", "", "", "", "", "", "01.01.01", "Прил. 1", "2000000", "да"])
    # Строка 2: Ур.5 с ценой и кол-вом, сумма пуста → рассчитывается автоматически
    ws.append(["ФАДМ_2026", "Техническое оснащение", "", "", "", "", "", "", "", "", "Оргтехника", "", "", "", "2000000", "", "", "", "", "Закупка компьютеров", "6", "шт", "", "", "", "", "", "", "Ноутбук HP 15 Intel i5", "3", "шт", "150000", "", "01.01.01", "Прил. 1", "2000000", "да"])
    # Строка 3: Ур.5 с явной суммой — сумма из файла приоритетна над кол-во × цена
    ws.append(["ФАДМ_2026", "Техническое оснащение", "", "", "", "", "", "", "", "", "Оргтехника", "", "", "", "2000000", "", "", "", "", "Закупка компьютеров", "6", "шт", "", "", "", "", "", "", "Монитор Dell 24\"", "3", "шт", "90000", "270000", "01.01.01", "Прил. 1", "", "да"])
    # Строка 4: Ур.3 задан, Ур.4 пуст → атрибуты ложатся на Ур.3; только сумма плана
    ws.append(["ФАДМ_2026", "Организация мероприятий", "", "", "", "", "", "", "", "", "Слёт студентов-спасателей", "102", "чел.", "", "", "", "", "", "3500000", "", "", "", "", "", "", "", "", "", "Услуга проживания участников", "100", "чел.", "", "3000000", "02.01.01", "Прил. 2", "3000000", "да"])
    # Строка 5: Ур.3 задан, Ур.4 пуст; Ур.5 только цена без суммы
    ws.append(["ФАДМ_2026", "Организация мероприятий", "", "", "", "", "", "", "", "", "Слёт студентов-спасателей", "102", "чел.", "", "", "", "", "", "3500000", "", "", "", "", "", "", "", "", "", "Услуга логистики участников", "2", "рейс", "250000", "", "02.01.02", "Прил. 2", "", "да"])

    # Подсказки в строке 7
    hints = [
        "← Точное название как в системе",                                                        # A   1
        "← Направление расходов (создаётся если нет)",                                            # B   2
        "← Кол-во ФЭО Ур.2 (из документа ФЭО)",                                                  # C   3
        "← Ед. изм. ФЭО Ур.2 (шт, компл...)",                                                    # D   4
        "← Стоимость за ед. по ФЭО Ур.2 (руб.)",                                                 # E   5
        "← Сумма по строке ФЭО (руб.); если пусто — кол-во × цена",                              # F   6
        "← Плановое кол-во Ур.2 (CRM-план, необязательно)",                                      # G   7
        "← Ед. изм. плана Ур.2",                                                                  # H   8
        "← Плановая стоимость за ед. Ур.2 (руб.)",                                               # I   9
        "← Сумма плана (руб.); если пусто — кол-во × цена",                                      # J  10
        "← Тип расходов (если пусто — атрибуты к Ур.2); если уровень пропущен, содержимое нижнего поднимается на его место",  # K  11
        "← Кол-во ФЭО Ур.3 (из документа ФЭО)",                                                  # L  12
        "← Ед. изм. ФЭО Ур.3",                                                                   # M  13
        "← Стоимость за ед. по ФЭО Ур.3 (руб.)",                                                 # N  14
        "← Сумма по строке ФЭО (руб.); если пусто — кол-во × цена",                              # O  15
        "← Плановое кол-во Ур.3 (CRM-план)",                                                     # P  16
        "← Ед. изм. плана Ур.3",                                                                  # Q  17
        "← Плановая стоимость за ед. Ур.3 (руб.)",                                               # R  18
        "← Сумма плана (руб.); если пусто — кол-во × цена",                                      # S  19
        "← Конкретизированный (если пусто — к Ур.3); если уровень пропущен, содержимое нижнего поднимается на его место",  # T  20
        "← Кол-во ФЭО Ур.4 (из документа ФЭО)",                                                  # U  21
        "← Ед. изм. ФЭО Ур.4",                                                                   # V  22
        "← Стоимость за ед. по ФЭО Ур.4 (руб.)",                                                 # W  23
        "← Сумма по строке ФЭО (руб.); если пусто — кол-во × цена",                              # X  24
        "← Плановое кол-во Ур.4 (CRM-план)",                                                     # Y  25
        "← Ед. изм. плана Ур.4",                                                                  # Z  26
        "← Плановая стоимость за ед. Ур.4 (руб.)",                                               # AA 27
        "← Сумма плана (руб.); если пусто — кол-во × цена",                                      # AB 28
        "← Плановый товар/услуга (необязательно)",                                                # AC 29
        "← Кол-во Ур.5 (необязательно)",                                                          # AD 30
        "← Ед. изм. (шт, кг, услуга...)",                                                        # AE 31
        "← Цена за ед. позиции (если сумма пуста)",                                               # AF 32
        "← Итог по позиции (руб.)",                                                               # AG 33
        "← Код категории",                                                                        # AH 34
        "← Номер приложения",                                                                     # AI 35
        "← Бюджет категории",                                                                     # AJ 36
        "← да/нет",                                                                               # AK 37
    ]
    for col, hint in enumerate(hints, start=1):
        ws.cell(7, col).value = hint
        ws.cell(7, col).font = Font(italic=True, color="888888", size=8)

    # Ширины колонок (37 штук):
    # A(18) B(42) C(14) D(14) E(16) F(16) G(14) H(14) I(16) J(16)
    # K(42) L(14) M(14) N(16) O(16) P(14) Q(14) R(16) S(16)
    # T(45) U(14) V(14) W(16) X(16) Y(14) Z(14) AA(16) AB(16)
    # AC(45) AD(12) AE(14) AF(16) AG(18) AH(10) AI(12) AJ(18) AK(10)
    col_widths = [18, 42, 14, 14, 16, 16, 14, 14, 16, 16, 42, 14, 14, 16, 16, 14, 14, 16, 16, 45, 14, 14, 16, 16, 14, 14, 16, 16, 45, 12, 14, 16, 18, 10, 12, 18, 10]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition("Шаблон_импорта_направлений_ФЭО.xlsx")})


@router.post("/import-preview")
async def feo_import_preview(
    file: UploadFile = File(...),
    _=Depends(require_tab('feo_categories')),
):
    """Read Excel/DOCX file and return headers + sample rows for column mapping."""
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".docx", ".doc", ".pdf")):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .docx, .pdf")

    content = await file.read()

    _FEO_HINTS = (
        "субсидия", "наименован", "направлен", "расходов", "уровень",
        "код", "финансирован", "количеств", "ед. изм", "ед.изм",
        "активн", "приложен", "бюджет", "плановый", "тип расх",
    )

    def _detect_hdr(rows):
        best_score, best_idx = 0, 0
        for ri, row in enumerate(rows[:20]):
            norm = [str(h).strip().lower() if h is not None else "" for h in row]
            score = sum(1 for h in norm if h and any(x in h for x in _FEO_HINTS))
            if score > best_score:
                best_score = score
                best_idx = ri
        return best_idx

    try:
        # ── PDF ──
        if fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь таблицы из PDF")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "PDF", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── DOCX ──
        if fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
            if not all_rows:
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        all_rows.append([text])
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь данные из документа")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "Document", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── XLS ──
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            sheets = []
            for sheet_name in wb_xls.sheet_names():
                ws_xls = wb_xls.sheet_by_name(sheet_name)
                all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": ws_xls.nrows - hdr_idx - 1, "header_row_offset": hdr_idx})

        # ── XLSX ──
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            sheets = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                all_rows = list(ws.iter_rows(values_only=True))
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": len(all_rows) - hdr_idx - 1, "header_row_offset": hdr_idx})
            wb.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}


async def _do_feo_import(
    rows: list,
    c_subsidy: int | None,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
    c_lvl5: int | None,
    c_qty: int | None,
    c_unit: int | None,
    c_item_amt: int | None,
    c_code: int | None,
    c_appendix: int | None,
    c_budget: int | None,
    c_active: int | None,
    db: AsyncSession,
    c_qty_lvl2: int | None = None,
    c_qty_lvl3: int | None = None,
    c_qty_lvl4: int | None = None,
    c_unit_lvl2: int | None = None,
    c_unit_lvl3: int | None = None,
    c_unit_lvl4: int | None = None,
    c_amt_lvl2: int | None = None,
    c_amt_lvl3: int | None = None,
    c_amt_lvl4: int | None = None,
    c_feo_qty_lvl2: int | None = None,
    c_feo_qty_lvl3: int | None = None,
    c_feo_qty_lvl4: int | None = None,
    c_feo_unit_lvl2: int | None = None,
    c_feo_unit_lvl3: int | None = None,
    c_feo_unit_lvl4: int | None = None,
    c_feo_amt_lvl2: int | None = None,
    c_feo_amt_lvl3: int | None = None,
    c_feo_amt_lvl4: int | None = None,
    c_feo_sum_lvl2: int | None = None,
    c_feo_sum_lvl3: int | None = None,
    c_feo_sum_lvl4: int | None = None,
    c_plan_sum_lvl2: int | None = None,
    c_plan_sum_lvl3: int | None = None,
    c_plan_sum_lvl4: int | None = None,
    c_item_price: int | None = None,
    default_subsidy_id: int | None = None,
    dry_run: bool = False,
    user=None,
    remap: str = "",
    apply_remap: bool = False,
) -> dict:
    """Core import logic shared by /import и /import-mapped endpoints.

    dry_run=True: вся обработка выполняется, но транзакция откатывается.
    Возвращает {created, updated, skipped, errors, warnings, ...}.

    N2б: `remap` — JSON-список {"old_id": int, "new_path": str} для явного
    переезда несопоставленных узлов на новые (переезд + удаление опустевших
    старых узлов выполняются после основного цикла, см. блок ниже unmatched).
    Фаза переезда/удаления выполняется ТОЛЬКО при apply_remap=True — иначе
    (обычная загрузка без мастера сопоставления) выполняется только анализ.
    """
    import re as _re
    import json as _json

    if c_lvl2 is None:
        raise HTTPException(400, "Не найден обязательный столбец: 'Уровень 2 (Направление расходов)'")
    if c_subsidy is None and default_subsidy_id is None:
        raise HTTPException(400, "Укажите столбец 'Субсидия' или выберите субсидию назначения")
    if remap and not apply_remap:
        raise HTTPException(400, "Параметр remap передан без apply_remap=true")

    remap_list: list[dict] = []
    if remap:
        try:
            _raw_remap = _json.loads(remap)
            if not isinstance(_raw_remap, list):
                raise ValueError("ожидался список")
            for _item in _raw_remap:
                if not isinstance(_item, dict) or "old_id" not in _item or "new_path" not in _item:
                    raise ValueError("каждый элемент должен содержать old_id и new_path")
                remap_list.append({
                    "old_id": int(_item["old_id"]),
                    "new_path": str(_item["new_path"]).strip(),
                })
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Неверный формат параметра remap: {e}")

    def get_cell(row, col: int | None) -> str | None:
        if col is None or col < 0: return None
        if col >= len(row): return None
        v = row[col]
        if v is None: return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null'):
            return None
        return s

    def to_bool(v: str | None) -> bool:
        if v is None: return True
        return v.lower() in ("да", "yes", "true", "1", "+")

    def to_dec(v: str | None):
        if not v: return None
        s = str(v).strip()
        if not s or s in ('-', '—', '–', 'None', 'null', 'н/д', 'N/A'):
            return None
        s = s.replace(" ", "").replace("\xa0", "").replace("\u202f", "")
        s = s.replace("₽", "").replace("руб", "").replace("р.", "").replace("р", "")
        s = s.replace(",", ".")
        s = s.rstrip(".")
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            return None

    def _fmt(v) -> str:
        """Число с разделителями разрядов для читаемых предупреждений."""
        try:
            return f"{float(v):,.2f}".replace(",", " ")
        except Exception:
            return str(v)

    def _norm(s: str) -> str:
        """Нормализация имени уровня для сравнения."""
        s2 = _re.sub(r'^\s*\d+([.\)]\d+)*[.\)]?\s*', '', s)
        s2 = s2.lower().strip()
        return _re.sub(r'\s+', ' ', s2)

    ZERO = Decimal("0")
    QUANT = Decimal("0.01")

    from app.models.subsidy import Subsidy
    sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    sub_by_name = {s.name.lower().strip(): s.id for s in sub_rows}

    existing_cats = (await db.execute(select(FeoCategory))).scalars().all()
    cat_cache: dict[tuple, FeoCategory] = {}
    for c in existing_cats:
        cat_cache[(c.subsidy_id, c.parent_id, c.name.lower().strip())] = c

    # --- Снимок дерева ДО импорта (нужен и для отчёта "несопоставленные узлы",
    # и для фазы переезда/удаления N2б). Перенесено сюда с места ниже (после
    # основного цикла) — переезд/удаление должны опираться на состояние дерева
    # ДО того, как основной цикл его изменит.
    existing_by_id: dict[int, FeoCategory] = {c.id: c for c in existing_cats}
    existing_children: dict[int, list[int]] = {}
    for c in existing_cats:
        if c.parent_id is not None:
            existing_children.setdefault(c.parent_id, []).append(c.id)

    def _get_root_id(cat_id: int) -> int:
        cur = existing_by_id.get(cat_id)
        if cur is None:
            return cat_id
        visited: set[int] = set()
        while cur.parent_id is not None and cur.parent_id in existing_by_id:
            if cur.id in visited:
                break
            visited.add(cur.id)
            cur = existing_by_id[cur.parent_id]
        return cur.id

    def _full_path(cat_id: int) -> str:
        chain: list[str] = []
        cur = existing_by_id.get(cat_id)
        visited: set[int] = set()
        while cur is not None and cur.id not in visited:
            chain.append(cur.name)
            visited.add(cur.id)
            if cur.parent_id is None:
                break
            cur = existing_by_id.get(cur.parent_id)
        return " / ".join(reversed(chain))

    def _subtree_ids_local(root_id: int) -> list[int]:
        ids = [root_id]
        stack = [root_id]
        while stack:
            cur_id = stack.pop()
            for ch_id in existing_children.get(cur_id, []):
                ids.append(ch_id)
                stack.append(ch_id)
        return ids

    def _strip_num(s: str) -> str:
        return _re.sub(r'^\s*\d+([.\)]\d+)*[.\)]?\s*', '', s).strip()

    def _canon_path(path: str, *, lower: bool, yo: bool) -> str:
        out = []
        for seg in path.split(" / "):
            s = _strip_num(seg)
            if lower:
                s = _re.sub(r'\s+', ' ', s.lower()).strip()
            if yo:
                s = s.replace('ё', 'е')
            out.append(s)
        return " / ".join(out)

    created = 0; updated = 0; skipped = 0; errors: list[dict] = []
    warnings: list[dict] = []
    created_details: list[dict] = []
    updated_details: list[dict] = []
    skipped_details: list[dict] = []

    # Множество id родительских узлов, затронутых импортом — для parent_sum_mismatch
    touched_parents: set[int] = set()

    # --- Для отчёта "несопоставленные узлы" (только анализ, БЕЗ мутаций) ---
    seen_ids: set[int] = set()      # id всех категорий, вернувшихся из find_or_create
    seen_roots: set[int] = set()    # id корневых (ур.2) узлов, затронутых файлом
    new_paths: list[str] = []       # пути узлов, которые описывает файл ("Ур2 / Ур3 / Ур4")
    _new_paths_seen: set[str] = set()
    new_path_cats: dict[str, FeoCategory] = {}  # путь → объект категории (для резолва remap.new_path)

    async def find_or_create(subsidy_id: int, parent_id, name: str, level: int):
        key = (subsidy_id, parent_id, name.lower().strip())
        if key in cat_cache:
            return cat_cache[key], False
        cat = FeoCategory(
            name=name, subsidy_id=subsidy_id, parent_id=parent_id, level=level,
            is_active=True,
        )
        db.add(cat)
        await db.flush()
        cat_cache[key] = cat
        return cat, True

    # --- N2б: пред-проход ТОЛЬКО ради определения затронутых субсидий (для
    # снимка предыдущей редакции ниже) — лёгкая версия резолва subsidy_id,
    # без накопления ошибок (их соберёт основной цикл).
    touched_subsidies: set[int] = set()
    for _row in rows:
        _lvl2 = get_cell(_row, c_lvl2)
        if not _lvl2 or _lvl2.startswith("←"):
            continue
        _sub_name = get_cell(_row, c_subsidy) if c_subsidy is not None else None
        if _sub_name and not _sub_name.startswith("←"):
            _sid = sub_by_name.get(_sub_name.lower().strip()) or default_subsidy_id
        else:
            _sid = default_subsidy_id
        if _sid:
            touched_subsidies.add(_sid)

    # --- N2б: снимок предыдущей редакции — ВСЕГДА и ДО основного цикла.
    # _create_plan_graph_version заново селектит FeoCategory, поэтому вызывать
    # её нужно именно здесь: после основного цикла дерево уже было бы изменено
    # (создание/обновление/удаление), и снимок перестал бы быть "предыдущей"
    # редакцией. Снимок самодостаточен (дерево пишется в JSON инлайном), так
    # что последующее удаление узлов не портит уже сохранённую версию.
    version_created = False
    if user is not None:
        _remap_note_suffix = ""
        if remap_list:
            _pairs = []
            for _rm in remap_list[:5]:
                _pairs.append(f"«{_full_path(_rm['old_id'])}» → «{_rm['new_path']}»")
            _remap_note_suffix = "; перенос узлов: " + "; ".join(_pairs)
            if len(remap_list) > 5:
                _remap_note_suffix += f" и ещё {len(remap_list) - 5}"
        _note = "Загрузка новой редакции разбивки ФЭО" + _remap_note_suffix
        from app.routers.purchases import _create_plan_graph_version
        for _sid in touched_subsidies:
            _v_created = await _create_plan_graph_version(subsidy_id=_sid, db=db, user=user, note=_note)
            if _v_created:
                version_created = True

    for row_num, row in enumerate(rows, start=2):
        lvl2_name = get_cell(row, c_lvl2)
        if not lvl2_name or lvl2_name.startswith("←"):
            skipped += 1
            skipped_details.append({
                "row": row_num,
                "name": lvl2_name or "(пустая строка)",
                "reason": "служебная строка" if lvl2_name else "нет наименования (уровень 2 пуст)",
            })
            continue

        sub_name = get_cell(row, c_subsidy) if c_subsidy is not None else None
        if sub_name and not sub_name.startswith("←"):
            subsidy_id = sub_by_name.get(sub_name.lower().strip()) or default_subsidy_id
            if not subsidy_id:
                errors.append({"row": row_num, "name": lvl2_name, "message": f"Субсидия не найдена: '{sub_name}'"})
                continue
        else:
            subsidy_id = default_subsidy_id
            if not subsidy_id:
                skipped += 1
                skipped_details.append({"row": row_num, "name": lvl2_name, "reason": "не указана субсидия назначения"})
                continue

        lvl3_name = get_cell(row, c_lvl3)
        lvl4_name = get_cell(row, c_lvl4)
        lvl5_name = get_cell(row, c_lvl5)

        code      = get_cell(row, c_code)
        appendix  = get_cell(row, c_appendix)
        budget    = to_dec(get_cell(row, c_budget))
        is_active = to_bool(get_cell(row, c_active))

        item_qty    = to_dec(get_cell(row, c_qty))
        item_unit   = get_cell(row, c_unit)
        item_amount = to_dec(get_cell(row, c_item_amt))
        item_price  = to_dec(get_cell(row, c_item_price)) if c_item_price is not None else None

        # Считать все данные по уровням (raw, без приоритизации)
        _lv = [
            {
                "level_src": 2,
                "name": lvl2_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl2))  if c_feo_qty_lvl2  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl2) if c_feo_unit_lvl2 is not None else get_cell(row, c_unit_lvl2),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl2))  if c_feo_amt_lvl2  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl2))  if c_feo_sum_lvl2  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl2))      if c_qty_lvl2      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl2)             if c_unit_lvl2     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl2))      if c_amt_lvl2      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl2)) if c_plan_sum_lvl2 is not None else None,
            },
            {
                "level_src": 3,
                "name": lvl3_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl3))  if c_feo_qty_lvl3  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl3) if c_feo_unit_lvl3 is not None else get_cell(row, c_unit_lvl3),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl3))  if c_feo_amt_lvl3  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl3))  if c_feo_sum_lvl3  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl3))      if c_qty_lvl3      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl3)             if c_unit_lvl3     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl3))      if c_amt_lvl3      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl3)) if c_plan_sum_lvl3 is not None else None,
            },
            {
                "level_src": 4,
                "name": lvl4_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl4))  if c_feo_qty_lvl4  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl4) if c_feo_unit_lvl4 is not None else get_cell(row, c_unit_lvl4),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl4))  if c_feo_amt_lvl4  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl4))  if c_feo_sum_lvl4  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl4))      if c_qty_lvl4      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl4)             if c_unit_lvl4     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl4))      if c_amt_lvl4      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl4)) if c_plan_sum_lvl4 is not None else None,
            },
        ]

        # Обратная совместимость: если нет явного c_feo_qty_lvlN — берём plan_qty за feo_qty
        for lv in _lv:
            if lv["level_src"] == 2 and c_feo_qty_lvl2 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]
            elif lv["level_src"] == 3 and c_feo_qty_lvl3 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]
            elif lv["level_src"] == 4 and c_feo_qty_lvl4 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]

        # Оставляем только уровни с непустым именем
        filled = [lv for lv in _lv if lv["name"]]

        # Схлопываем соседние дубли по нормализованному имени
        deduped: list[dict] = []
        for lv in filled:
            if deduped and _norm(deduped[-1]["name"]) == _norm(lv["name"]):
                warnings.append({
                    "kind": "level_duplicate",
                    "row": row_num,
                    "name": lv["name"],
                    "message": f"Ур.{lv['level_src']} и Ур.{deduped[-1]['level_src']} названы одинаково — склеены в один узел",
                })
                # Числа объединяем с приоритетом нижнего непустого
                prev = deduped[-1]
                for k in ("feo_qty", "feo_unit", "feo_amt", "feo_sum", "plan_qty", "plan_unit", "plan_amt", "plan_sum"):
                    if lv[k] is not None:
                        prev[k] = lv[k]
            else:
                # Проверяем пропуск уровня: если предыдущий src=2 а текущий src=4 — Ур.3 был пропущен
                if deduped and lv["level_src"] - deduped[-1]["level_src"] > 1:
                    warnings.append({
                        "kind": "level_gap",
                        "row": row_num,
                        "name": lv["name"],
                        "message": f"Ур.{lv['level_src']} поднят на место Ур.{deduped[-1]['level_src'] + 1} — промежуточный уровень не заполнен",
                    })
                deduped.append(lv)

        # Нет ни одного заполненного уровня — уже пропустили по lvl2_name выше
        try:
            prev_cat = None
            cats_in_row: list[FeoCategory] = []
            leaf_is_new = False  # будет обновлён на последней итерации
            # Базовый level в БД для первого элемента = 1 (совпадает со старым поведением)
            for seq_idx, lv in enumerate(deduped):
                db_level = seq_idx + 1
                parent_id = prev_cat.id if prev_cat else None
                cat, is_new = await find_or_create(subsidy_id, parent_id, lv["name"], db_level)
                leaf_is_new = is_new  # последнее значение = флаг создания листового узла

                if is_new:
                    created += 1
                    label = {1: "направление (ур. 2)", 2: "категория (ур. 3)", 3: "статья (ур. 4)"}.get(db_level, f"уровень {db_level + 1}")
                    created_details.append({"row": row_num, "name": lv["name"], "reason": label})

                # --- ФЭО-поля ---
                feo_qty  = lv["feo_qty"]
                feo_unit = lv["feo_unit"]
                feo_amt  = lv["feo_amt"]
                feo_sum  = lv["feo_sum"]

                # Сумма ФЭО → budget
                if feo_sum is not None:
                    # Проверяем расхождение с кол-во × цена
                    if feo_qty is not None and feo_amt is not None and feo_qty != ZERO:
                        calc = (feo_qty * feo_amt).quantize(QUANT)
                        if abs(calc - feo_sum) > Decimal("0.01"):
                            warnings.append({
                                "kind": "sum_mismatch",
                                "row": row_num,
                                "name": lv["name"],
                                "message": f"Сумма по ФЭО {_fmt(feo_sum)} ≠ кол-во × цена = {_fmt(calc)}; взята сумма из файла",
                            })
                    if cat.budget != feo_sum:
                        cat.budget = feo_sum
                    # Если feo_amt пуст, но есть кол-во — восстановим цену
                    if feo_amt is None and feo_qty is not None and feo_qty != ZERO:
                        feo_amt = (feo_sum / feo_qty).quantize(QUANT)

                if feo_qty is not None and cat.feo_quantity != feo_qty:
                    cat.feo_quantity = feo_qty
                if feo_unit and cat.feo_unit != feo_unit:
                    cat.feo_unit = feo_unit
                if feo_amt is not None and cat.feo_amount != feo_amt:
                    cat.feo_amount = feo_amt

                # --- Плановые поля ---
                plan_qty  = lv["plan_qty"]
                plan_unit = lv["plan_unit"]
                plan_amt  = lv["plan_amt"]
                plan_sum  = lv["plan_sum"]

                if plan_sum is not None:
                    # Проверяем расхождение
                    if plan_qty is not None and plan_amt is not None and plan_qty != ZERO:
                        calc_ps = (plan_qty * plan_amt).quantize(QUANT)
                        if abs(calc_ps - plan_sum) > Decimal("0.01"):
                            warnings.append({
                                "kind": "sum_mismatch",
                                "row": row_num,
                                "name": lv["name"],
                                "message": f"Сумма плана {_fmt(plan_sum)} ≠ кол-во × цена = {_fmt(calc_ps)}; взята сумма из файла",
                            })
                    if plan_qty is None:
                        warnings.append({
                            "kind": "sum_without_qty",
                            "row": row_num,
                            "name": lv["name"],
                            "message": f"Сумма плана {_fmt(plan_sum)} задана без кол-во; установлено кол-во = 1",
                        })
                    # Обратный пересчёт: planned_amount = plan_sum / plan_qty
                    eff_plan_qty = plan_qty if (plan_qty is not None and plan_qty != ZERO) else Decimal("1")
                    if plan_qty is None:
                        if cat.planned_quantity != Decimal("1"):
                            cat.planned_quantity = Decimal("1")
                    else:
                        if cat.planned_quantity != plan_qty:
                            cat.planned_quantity = plan_qty
                    derived_plan_amt = (plan_sum / eff_plan_qty).quantize(QUANT)
                    if cat.planned_amount != derived_plan_amt:
                        cat.planned_amount = derived_plan_amt
                else:
                    # Старое поведение: план кол-во/ед/цена напрямую
                    _pq = plan_qty if plan_qty is not None else feo_qty
                    if _pq is not None and cat.planned_quantity != _pq:
                        cat.planned_quantity = _pq
                    _pa = plan_amt if plan_amt is not None else feo_amt
                    if _pa is not None and cat.planned_amount != _pa:
                        cat.planned_amount = _pa

                _pu = plan_unit if plan_unit is not None else feo_unit
                if _pu and cat.unit != _pu:
                    cat.unit = _pu

                cats_in_row.append(cat)
                if prev_cat is not None and prev_cat.id is not None:
                    touched_parents.add(prev_cat.id)
                prev_cat = cat

            leaf = cats_in_row[-1]

            # --- Учёт для отчёта "несопоставленные узлы" (только анализ) ---
            root_c = cats_in_row[0]
            if root_c.id is not None:
                seen_roots.add(root_c.id)
            _path_parts: list[str] = []
            for _c in cats_in_row:
                if _c.id is not None:
                    seen_ids.add(_c.id)
                _path_parts.append(_c.name)
                _p = " / ".join(_path_parts)
                if _p not in _new_paths_seen:
                    _new_paths_seen.add(_p)
                    new_paths.append(_p)
                new_path_cats[_p] = _c

            changed = False
            if code is not None and leaf.code != code:
                leaf.code = code; changed = True
            if appendix is not None and leaf.appendix != appendix:
                leaf.appendix = appendix; changed = True
            # budget из легаси-колонки «Финансирование» пишем только если per-level сумма не задана
            if budget is not None:
                # per-level feo_sum уже записан выше; не перезаписываем
                if deduped and deduped[-1].get("feo_sum") is None:
                    if leaf.budget != budget:
                        leaf.budget = budget; changed = True
            if leaf.is_active != is_active:
                leaf.is_active = is_active; changed = True
            if changed and not leaf_is_new:
                updated += 1
                updated_details.append({"row": row_num, "name": leaf.name, "reason": "обновлены поля категории"})

            if lvl5_name and lvl5_name not in ("←", ""):
                from app.models.feo_planned_item import FeoPlannedItem

                # Вычислить итоговую сумму позиции: item_amount приоритетнее
                eff_item_amount = item_amount
                if eff_item_amount is None and item_price is not None:
                    eff_item_qty = item_qty if item_qty is not None else Decimal("1")
                    eff_item_amount = (item_price * eff_item_qty).quantize(QUANT)

                existing_item = (await db.execute(
                    select(FeoPlannedItem).where(
                        FeoPlannedItem.feo_category_id == leaf.id,
                        FeoPlannedItem.name == lvl5_name,
                    )
                )).scalar_one_or_none()
                if not existing_item:
                    pi = FeoPlannedItem(
                        feo_category_id=leaf.id,
                        name=lvl5_name,
                        quantity=item_qty,
                        unit=item_unit,
                        amount=eff_item_amount,
                        is_active=is_active,
                    )
                    db.add(pi)
                    await db.flush()
                    created += 1
                    created_details.append({"row": row_num, "name": lvl5_name, "reason": "плановая позиция (ур. 5)"})
                else:
                    ch2 = False
                    if item_qty is not None and existing_item.quantity != item_qty:
                        existing_item.quantity = item_qty; ch2 = True
                    if item_unit is not None and existing_item.unit != item_unit:
                        existing_item.unit = item_unit; ch2 = True
                    if eff_item_amount is not None and existing_item.amount != eff_item_amount:
                        existing_item.amount = eff_item_amount; ch2 = True
                    if ch2:
                        updated += 1
                        updated_details.append({"row": row_num, "name": lvl5_name, "reason": "обновлена позиция"})
                    else:
                        skipped += 1
                        skipped_details.append({"row": row_num, "name": lvl5_name, "reason": "без изменений"})

        except Exception as e:
            errors.append({"row": row_num, "name": lvl2_name, "message": str(e)})

    # Проверка родитель vs сумма ВСЕХ дочерних узлов (до commit)
    # Собираем актуальные объекты по id через cat_cache (все объекты уже в сессии)
    cat_by_db_id: dict[int, FeoCategory] = {c.id: c for c in cat_cache.values() if c.id is not None}
    for parent_id in touched_parents:
        if parent_id not in cat_by_db_id:
            continue
        parent_cat = cat_by_db_id[parent_id]
        parent_budget = parent_cat.budget or ZERO
        if not parent_budget:
            continue
        # Сумма budget всех прямых детей из cat_cache (весь справочник)
        children_sum = sum(
            (c.budget or ZERO)
            for c in cat_cache.values()
            if c.parent_id == parent_id and c.id is not None
        )
        if abs(parent_budget - children_sum) > Decimal("0.01"):
            warnings.append({
                "kind": "parent_sum_mismatch",
                "row": None,
                "name": parent_cat.name,
                "message": (
                    f"Родитель «{parent_cat.name}»: бюджет {_fmt(parent_budget)} ≠ "
                    f"сумма всех дочерних узлов {_fmt(children_sum)}; победит значение родителя"
                ),
            })

    # --- Отчёт "несопоставленные узлы": ТОЛЬКО анализ, без мутаций/перепривязок ---
    # Дерево родитель→дети (existing_by_id/existing_children) и хелперы
    # (_get_root_id/_full_path/_subtree_ids_local/_strip_num/_canon_path)
    # определены выше, сразу после загрузки existing_cats — они нужны и здесь,
    # и в фазе переезда/удаления ниже.
    unmatched: list[dict] = []
    if seen_roots:
        candidates = [
            c for c in existing_cats
            if c.id not in seen_ids and _get_root_id(c.id) in seen_roots
        ]
        # Предрасчёт канонических форм всех new_paths (для подсказок)
        _np_nonum = [(np, _canon_path(np, lower=False, yo=False)) for np in new_paths]
        _np_norm = [(np, _canon_path(np, lower=True, yo=False)) for np in new_paths]
        _np_yo = [(np, _canon_path(np, lower=True, yo=True)) for np in new_paths]

        for cand in candidates:
            cand_path = _full_path(cand.id)
            subtree_ids = _subtree_ids_local(cand.id)
            load = await _feo_category_load(subtree_ids, db)
            has_refs = any(load[k] for k in (
                "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
            ))
            kind = "needs_mapping" if has_refs else "empty"

            suggestion = None
            suggestion_reason = None
            if kind == "needs_mapping":
                cand_nonum = _canon_path(cand_path, lower=False, yo=False)
                for np, np_c in _np_nonum:
                    if np != cand_path and np_c == cand_nonum:
                        suggestion, suggestion_reason = np, "отличается нумерацией"
                        break
                if suggestion is None:
                    cand_norm = _canon_path(cand_path, lower=True, yo=False)
                    for np, np_c in _np_norm:
                        if np != cand_path and np_c == cand_norm:
                            suggestion, suggestion_reason = np, "отличается регистром или пробелами"
                            break
                if suggestion is None:
                    cand_yo = _canon_path(cand_path, lower=True, yo=True)
                    for np, np_c in _np_yo:
                        if np != cand_path and np_c == cand_yo:
                            suggestion, suggestion_reason = np, "отличается ё/е"
                            break

            unmatched.append({
                "id": cand.id,
                "path": cand_path,
                "kind": kind,
                "suggestion": suggestion,
                "suggestion_reason": suggestion_reason,
                "load": {
                    "purchases": load["purchases"],
                    "purchase_items": load["purchase_items"],
                    "wishes": load["wishes"],
                    "wish_items": load["wish_items"],
                    "products": load["products"],
                    "feo_planned_items": load["feo_planned_items"],
                },
                "blocking_purchases": load["blocking_purchases"],
            })

    # --- N2б: переезд (remap) + удаление опустевших старых узлов ---
    # Обязательно ДО dry_run rollback/commit — все строки путей ниже нужно
    # материализовать в обычные str/dict, пока ORM-объекты ещё не просрочены.
    # Выполняется ТОЛЬКО при apply_remap=True (см. docstring) — обычная
    # загрузка (без явного согласия из мастера сопоставления) делает только
    # анализ unmatched/new_paths выше, ничего не переносит и не удаляет.
    relinked_count = 0
    deleted_count = 0
    remap_applied: list[dict] = []
    deleted_details: list[dict] = []
    remap_aborted_reason: str | None = None

    if apply_remap:
        _unmatched_ids = {u["id"] for u in unmatched}

        if errors:
            remap_aborted_reason = "переезд отменён: в файле есть ошибки"
        elif any(sd.get("reason") == "не указана субсидия назначения" for sd in skipped_details):
            remap_aborted_reason = "переезд отменён: часть строк без субсидии назначения"
        elif not seen_ids:
            remap_aborted_reason = "переезд отменён: файл не описал ни одного узла"

        _resolved_remap: list[tuple[int, FeoCategory, str]] = []
        if remap_aborted_reason is None:
            for _rm in remap_list:
                _old_id = _rm["old_id"]
                _new_path = _rm["new_path"]
                if _old_id not in _unmatched_ids:
                    remap_aborted_reason = f"переезд отменён: узел не найден среди несопоставленных (id={_old_id})"
                    break
                _new_cat = new_path_cats.get(_new_path)
                if _new_cat is None or _new_cat.id is None:
                    remap_aborted_reason = f"переезд отменён: цель сопоставления не найдена в новой разбивке: «{_new_path}»"
                    break
                _resolved_remap.append((_old_id, _new_cat, _new_path))

        if remap_aborted_reason is None:
            # Шаг A — применить переезды. Пути берём СЕЙЧАС (пока объекты живы).
            for _old_id, _new_cat, _new_path in _resolved_remap:
                _old_path = _full_path(_old_id)
                _counts = await _relink_feo_category(_old_id, _new_cat.id, db)
                relinked_count += sum(_counts.values())
                remap_applied.append({
                    "old_path": _old_path,
                    "new_path": _new_path,
                    "counts": _counts,
                })

            # Шаг B — удалить опустевшие несопоставленные узлы (кроме тех, кого
            # файл всё-таки назвал где-то в поддереве — их каскадом не трогаем).
            already_deleted: set[int] = set()
            # обходим от корня к листьям (по глубине path), иначе ребёнок удалится раньше родителя и родитель останется пустым висяком
            _unmatched_by_depth = sorted(unmatched, key=lambda _c: _c["path"].count(" / "))
            for _cand in _unmatched_by_depth:
                _cand_id = _cand["id"]
                if _cand_id in already_deleted:
                    continue
                subtree = _subtree_ids_local(_cand_id)
                if any(_sid in already_deleted for _sid in subtree):
                    continue
                if any(_sid in seen_ids for _sid in subtree):
                    continue
                load = await _feo_category_load(subtree, db)
                has_refs = any(load[k] for k in (
                    "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
                ))
                if has_refs:
                    continue
                for _sid in subtree:
                    if _sid == _cand_id:
                        deleted_details.append({"path": _cand["path"], "reason": "нет в новом файле, ссылок нет"})
                    else:
                        deleted_details.append({"path": _full_path(_sid), "reason": f"внутри удаляемого «{_cand['path']}»"})
                await _purge_feo_categories(subtree, db)
                deleted_count += len(subtree)
                already_deleted.update(subtree)

            # Шаг C — вычистить cat_cache от удалённых id, чтобы ниже по коду
            # (если он появится) не переиспользовать протухшие объекты.
            if already_deleted:
                for _k in [k for k, c in cat_cache.items() if c.id in already_deleted]:
                    del cat_cache[_k]

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    # Схлопываем одинаковые предупреждения по ключу (kind, name, message-без-суффикса)
    # Сохраняем номер строки первого вхождения и порядок появления
    _seen: dict[tuple, int] = {}   # ключ → индекс в _dedup_warnings
    _dedup_counts: list[int] = []
    _dedup_warnings: list[dict] = []
    for w in warnings:
        key = (w.get("kind"), w.get("name"), w.get("message"))
        if key in _seen:
            _dedup_counts[_seen[key]] += 1
        else:
            _seen[key] = len(_dedup_warnings)
            _dedup_warnings.append(dict(w))
            _dedup_counts.append(1)
    for i, cnt in enumerate(_dedup_counts):
        if cnt > 1:
            _dedup_warnings[i]["message"] = _dedup_warnings[i]["message"] + f" (строк: {cnt})"
    warnings = _dedup_warnings

    return {
        "created": created, "updated": updated, "skipped": skipped,
        "errors": errors, "warnings": warnings,
        "created_details": created_details,
        "updated_details": updated_details, "skipped_details": skipped_details,
        "dry_run": dry_run,
        "unmatched": unmatched,
        "new_paths": new_paths,
        "deleted_count": deleted_count,
        "relinked_count": relinked_count,
        "deleted_details": deleted_details,
        "remap_applied": remap_applied,
        "remap_aborted_reason": remap_aborted_reason,
        "version_created": version_created,
        "deletes_applied": bool(apply_remap),
    }


@router.post("/import")
async def import_feo_from_excel(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    remap: str = Query(""),
    apply_remap: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Импорт категорий ФЭО из Excel.
    Формат: Субсидия | Уровень 2 | Уровень 3 | Уровень 4 | Код | Приложение | Финансирование | Активна
    Каждая строка задаёт путь в иерархии. Промежуточные узлы создаются автоматически.
    Код/Приложение/Финансирование/Активна применяются к самому глубокому указанному уровню.
    dry_run=true: возвращает {created, updated, skipped, errors, warnings} без записи в БД.
    Переезд (remap) несопоставленных узлов и удаление опустевших старых узлов выполняются
    только при apply_remap=true; иначе выполняется только анализ (unmatched/new_paths).
    Возвращает {created, updated, skipped, errors, warnings}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    # Определяем индексы столбцов по заголовку строки 1
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    # Каждая колонка достаётся ровно одному полю
    _used_cols: set[int] = set()

    def find_col(keywords: list[str]) -> int | None:
        for kw in keywords:
            for i, h in enumerate(raw_headers):
                if i in _used_cols:
                    continue
                if kw in h:
                    _used_cols.add(i)
                    return i
        return None

    c_subsidy  = find_col(["субсидия"])
    c_lvl2     = find_col(["уровень 2", "направление расходов", "level 2"])
    c_lvl3     = find_col(["уровень 3", "тип расходов", "level 3"])
    c_lvl4     = find_col(["уровень 4", "конкретизир", "level 4"])
    c_lvl5     = find_col(["уровень 5", "плановый товар", "level 5"])
    c_qty      = find_col(["количество (ур.5)", "количество ур.5", "кол-во (ур.5)", "кол-во ур.5"])
    # Новый шаблон: «кол-во по фэо» — feo_quantity
    c_feo_qty_lvl2  = find_col(["кол-во по фэо (ур.2)", "кол-во по фэо ур.2"])
    c_feo_qty_lvl3  = find_col(["кол-во по фэо (ур.3)", "кол-во по фэо ур.3"])
    c_feo_qty_lvl4  = find_col(["кол-во по фэо (ур.4)", "кол-во по фэо ур.4"])
    c_feo_unit_lvl2 = find_col(["ед. изм. по фэо (ур.2)", "ед. изм. по фэо ур.2"])
    c_feo_unit_lvl3 = find_col(["ед. изм. по фэо (ур.3)", "ед. изм. по фэо ур.3"])
    c_feo_unit_lvl4 = find_col(["ед. изм. по фэо (ур.4)", "ед. изм. по фэо ур.4"])
    c_feo_amt_lvl2  = find_col(["стоимость по фэо (ур.2)", "стоимость по фэо ур.2"])
    c_feo_amt_lvl3  = find_col(["стоимость по фэо (ур.3)", "стоимость по фэо ур.3"])
    c_feo_amt_lvl4  = find_col(["стоимость по фэо (ур.4)", "стоимость по фэо ур.4"])
    # Сумма по ФЭО (итог строки) — НОВЫЕ колонки; НЕ путать со стоимостью за ед.
    c_feo_sum_lvl2  = find_col(["сумма по фэо (ур.2)", "сумма по фэо ур.2"])
    c_feo_sum_lvl3  = find_col(["сумма по фэо (ур.3)", "сумма по фэо ур.3"])
    c_feo_sum_lvl4  = find_col(["сумма по фэо (ур.4)", "сумма по фэо ур.4"])
    # Плановое кол-во (CRM-план)
    c_qty_lvl2 = find_col(["плановое кол-во (ур.2)", "плановое кол-во ур.2", "кол-во (ур.2)", "кол-во ур.2", "количество (ур.2)"])
    c_qty_lvl3 = find_col(["плановое кол-во (ур.3)", "плановое кол-во ур.3", "кол-во (ур.3)", "кол-во ур.3", "количество (ур.3)"])
    c_qty_lvl4 = find_col(["плановое кол-во (ур.4)", "плановое кол-во ур.4", "кол-во (ур.4)", "кол-во ур.4", "количество (ур.4)"])
    c_unit_lvl2 = find_col(["ед. изм. плана (ур.2)", "ед. изм. плана ур.2", "ед. изм. (ур.2)", "ед.изм. ур.2", "единица ур.2"])
    c_unit_lvl3 = find_col(["ед. изм. плана (ур.3)", "ед. изм. плана ур.3", "ед. изм. (ур.3)", "ед.изм. ур.3", "единица ур.3"])
    c_unit_lvl4 = find_col(["ед. изм. плана (ур.4)", "ед. изм. плана ур.4", "ед. изм. (ур.4)", "ед.изм. ур.4", "единица ур.4"])
    # Плановая стоимость за ед. — НЕ путать с «сумма плана»
    c_amt_lvl2 = find_col(["плановая стоимость за ед. (ур.2)", "плановая стоимость (ур.2)", "стоимость за ед. (ур.2)", "стоимость ур.2"])
    c_amt_lvl3 = find_col(["плановая стоимость за ед. (ур.3)", "плановая стоимость (ур.3)", "стоимость за ед. (ур.3)", "стоимость ур.3"])
    c_amt_lvl4 = find_col(["плановая стоимость за ед. (ур.4)", "плановая стоимость (ур.4)", "стоимость за ед. (ур.4)", "стоимость ур.4"])
    # Сумма плана — отдельные колонки; старые алиасы «плановая сумма / сумма ур.N» сюда, а НЕ в c_amt_lvl*
    c_plan_sum_lvl2 = find_col(["сумма плана (ур.2)", "плановая сумма (ур.2)", "сумма ур.2"])
    c_plan_sum_lvl3 = find_col(["сумма плана (ур.3)", "плановая сумма (ур.3)", "сумма ур.3"])
    c_plan_sum_lvl4 = find_col(["сумма плана (ур.4)", "плановая сумма (ур.4)", "сумма ур.4"])
    # Fallback: generic qty column if no specific level columns present
    if c_qty is None and c_qty_lvl2 is None and c_qty_lvl3 is None and c_qty_lvl4 is None and c_feo_qty_lvl2 is None and c_feo_qty_lvl3 is None and c_feo_qty_lvl4 is None:
        c_qty = find_col(["количество", "кол-во", "qty"])
    c_unit      = find_col(["ед. измерения (ур.5)", "ед. изм. (ур.5)", "единица ур.5", "ед. изм", "единица изм", "ед.изм"])
    c_item_price = find_col(["цена за ед. (ур.5)", "цена за ед. ур.5"])
    c_item_amt  = find_col(["сумма по позиции (ур.5)", "сумма (ур.5)", "сумма ур", "плановая стоимость за ед. (ур.5)", "плановая стоимость (ур.5)", "стоимость за ед. (ур.5)", "стоимость ур.5", "сумма плановая"])
    c_code      = find_col(["код"])
    c_appendix  = find_col(["приложение"])
    c_budget    = find_col(["финансирование", "бюджет", "budget"])
    c_active    = find_col(["активна", "активен", "active"])

    return await _do_feo_import(
        rows=rows[1:],
        c_subsidy=c_subsidy, c_lvl2=c_lvl2, c_lvl3=c_lvl3, c_lvl4=c_lvl4,
        c_lvl5=c_lvl5, c_qty=c_qty, c_unit=c_unit, c_item_amt=c_item_amt,
        c_code=c_code, c_appendix=c_appendix, c_budget=c_budget, c_active=c_active,
        c_qty_lvl2=c_qty_lvl2, c_qty_lvl3=c_qty_lvl3, c_qty_lvl4=c_qty_lvl4,
        c_unit_lvl2=c_unit_lvl2, c_unit_lvl3=c_unit_lvl3, c_unit_lvl4=c_unit_lvl4,
        c_amt_lvl2=c_amt_lvl2, c_amt_lvl3=c_amt_lvl3, c_amt_lvl4=c_amt_lvl4,
        c_feo_qty_lvl2=c_feo_qty_lvl2, c_feo_qty_lvl3=c_feo_qty_lvl3, c_feo_qty_lvl4=c_feo_qty_lvl4,
        c_feo_unit_lvl2=c_feo_unit_lvl2, c_feo_unit_lvl3=c_feo_unit_lvl3, c_feo_unit_lvl4=c_feo_unit_lvl4,
        c_feo_amt_lvl2=c_feo_amt_lvl2, c_feo_amt_lvl3=c_feo_amt_lvl3, c_feo_amt_lvl4=c_feo_amt_lvl4,
        c_feo_sum_lvl2=c_feo_sum_lvl2, c_feo_sum_lvl3=c_feo_sum_lvl3, c_feo_sum_lvl4=c_feo_sum_lvl4,
        c_plan_sum_lvl2=c_plan_sum_lvl2, c_plan_sum_lvl3=c_plan_sum_lvl3, c_plan_sum_lvl4=c_plan_sum_lvl4,
        c_item_price=c_item_price,
        db=db, dry_run=dry_run,
        user=current_user, remap=remap, apply_remap=apply_remap,
    )


@router.post("/import-mapped")
async def import_feo_mapped(
    file: UploadFile = File(...),
    sheet_name: str = Query(""),
    header_row_offset: int = Query(0),
    col_subsidy: int = Query(-1),
    col_lvl2: int = Query(-1),
    col_lvl3: int = Query(-1),
    col_lvl4: int = Query(-1),
    col_lvl5: int = Query(-1),
    col_code: int = Query(-1),
    col_appendix: int = Query(-1),
    col_budget: int = Query(-1),
    col_quantity: int = Query(-1),
    col_unit: int = Query(-1),
    col_item_amt: int = Query(-1),
    col_active: int = Query(-1),
    col_qty_lvl2: int = Query(-1),
    col_qty_lvl3: int = Query(-1),
    col_qty_lvl4: int = Query(-1),
    col_unit_lvl2: int = Query(-1),
    col_unit_lvl3: int = Query(-1),
    col_unit_lvl4: int = Query(-1),
    col_amt_lvl2: int = Query(-1),
    col_amt_lvl3: int = Query(-1),
    col_amt_lvl4: int = Query(-1),
    col_feo_qty_lvl2: int = Query(-1),
    col_feo_qty_lvl3: int = Query(-1),
    col_feo_qty_lvl4: int = Query(-1),
    col_feo_unit_lvl2: int = Query(-1),
    col_feo_unit_lvl3: int = Query(-1),
    col_feo_unit_lvl4: int = Query(-1),
    col_feo_amount_lvl2: int = Query(-1),
    col_feo_amount_lvl3: int = Query(-1),
    col_feo_amount_lvl4: int = Query(-1),
    # Новые параметры — сумма по ФЭО, сумма плана, цена за ед. Ур.5
    col_feo_sum_lvl2: int = Query(-1),
    col_feo_sum_lvl3: int = Query(-1),
    col_feo_sum_lvl4: int = Query(-1),
    col_plan_sum_lvl2: int = Query(-1),
    col_plan_sum_lvl3: int = Query(-1),
    col_plan_sum_lvl4: int = Query(-1),
    col_item_price: int = Query(-1),
    default_subsidy_id: int = Query(-1),
    dry_run: bool = Query(False),
    remap: str = Query(""),
    apply_remap: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Импорт категорий ФЭО с пользовательским маппингом столбцов.
    dry_run=true: вся обработка выполняется, транзакция откатывается; возвращает предупреждения.
    Переезд (remap) несопоставленных узлов и удаление опустевших старых узлов выполняются
    только при apply_remap=true; иначе выполняется только анализ (unmatched/new_paths).
    """
    if col_lvl2 < 0:
        raise HTTPException(400, "Не указан обязательный столбец: Уровень 2")
    if col_subsidy < 0 and default_subsidy_id <= 0:
        raise HTTPException(400, "Укажите столбец Субсидия или выберите субсидию назначения")

    fname = (file.filename or "").lower()
    content = await file.read()

    try:
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            ws_names = wb_xls.sheet_names()
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws_xls = wb_xls.sheet_by_name(target_sheet)
            all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
        elif fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
        elif fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), data_only=True)
            ws_names = wb.sheetnames
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws = wb[target_sheet]
            all_rows = list(ws.iter_rows(values_only=True))
            wb.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    if len(all_rows) <= header_row_offset + 1:
        raise HTTPException(400, "Файл пустой или не содержит данных после строки заголовка")

    data_rows = all_rows[header_row_offset + 1:]

    return await _do_feo_import(
        rows=data_rows,
        c_subsidy=col_subsidy if col_subsidy >= 0 else None,
        c_lvl2=col_lvl2,
        c_lvl3=col_lvl3 if col_lvl3 >= 0 else None,
        c_lvl4=col_lvl4 if col_lvl4 >= 0 else None,
        c_lvl5=col_lvl5 if col_lvl5 >= 0 else None,
        c_qty=col_quantity if col_quantity >= 0 else None,
        c_unit=col_unit if col_unit >= 0 else None,
        c_item_amt=col_item_amt if col_item_amt >= 0 else None,
        c_code=col_code if col_code >= 0 else None,
        c_appendix=col_appendix if col_appendix >= 0 else None,
        c_budget=col_budget if col_budget >= 0 else None,
        c_active=col_active if col_active >= 0 else None,
        c_qty_lvl2=col_qty_lvl2 if col_qty_lvl2 >= 0 else None,
        c_qty_lvl3=col_qty_lvl3 if col_qty_lvl3 >= 0 else None,
        c_qty_lvl4=col_qty_lvl4 if col_qty_lvl4 >= 0 else None,
        c_unit_lvl2=col_unit_lvl2 if col_unit_lvl2 >= 0 else None,
        c_unit_lvl3=col_unit_lvl3 if col_unit_lvl3 >= 0 else None,
        c_unit_lvl4=col_unit_lvl4 if col_unit_lvl4 >= 0 else None,
        c_amt_lvl2=col_amt_lvl2 if col_amt_lvl2 >= 0 else None,
        c_amt_lvl3=col_amt_lvl3 if col_amt_lvl3 >= 0 else None,
        c_amt_lvl4=col_amt_lvl4 if col_amt_lvl4 >= 0 else None,
        c_feo_qty_lvl2=col_feo_qty_lvl2 if col_feo_qty_lvl2 >= 0 else None,
        c_feo_qty_lvl3=col_feo_qty_lvl3 if col_feo_qty_lvl3 >= 0 else None,
        c_feo_qty_lvl4=col_feo_qty_lvl4 if col_feo_qty_lvl4 >= 0 else None,
        c_feo_unit_lvl2=col_feo_unit_lvl2 if col_feo_unit_lvl2 >= 0 else None,
        c_feo_unit_lvl3=col_feo_unit_lvl3 if col_feo_unit_lvl3 >= 0 else None,
        c_feo_unit_lvl4=col_feo_unit_lvl4 if col_feo_unit_lvl4 >= 0 else None,
        c_feo_amt_lvl2=col_feo_amount_lvl2 if col_feo_amount_lvl2 >= 0 else None,
        c_feo_amt_lvl3=col_feo_amount_lvl3 if col_feo_amount_lvl3 >= 0 else None,
        c_feo_amt_lvl4=col_feo_amount_lvl4 if col_feo_amount_lvl4 >= 0 else None,
        c_feo_sum_lvl2=col_feo_sum_lvl2 if col_feo_sum_lvl2 >= 0 else None,
        c_feo_sum_lvl3=col_feo_sum_lvl3 if col_feo_sum_lvl3 >= 0 else None,
        c_feo_sum_lvl4=col_feo_sum_lvl4 if col_feo_sum_lvl4 >= 0 else None,
        c_plan_sum_lvl2=col_plan_sum_lvl2 if col_plan_sum_lvl2 >= 0 else None,
        c_plan_sum_lvl3=col_plan_sum_lvl3 if col_plan_sum_lvl3 >= 0 else None,
        c_plan_sum_lvl4=col_plan_sum_lvl4 if col_plan_sum_lvl4 >= 0 else None,
        c_item_price=col_item_price if col_item_price >= 0 else None,
        default_subsidy_id=default_subsidy_id if default_subsidy_id > 0 else None,
        db=db, dry_run=dry_run,
        user=current_user, remap=remap, apply_remap=apply_remap,
    )


@router.get("/export")
async def export_feo_to_excel(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Экспорт дерева категорий ФЭО в Excel."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()

    # purchase totals
    pt_rows = (await db.execute(
        select(Purchase.feo_category_id, func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .group_by(Purchase.feo_category_id)
    )).all()
    purchase_totals = {r.feo_category_id: float(r.total) for r in pt_rows}

    # Build tree
    by_id = {c.id: {"cat": c, "children": []} for c in cats}
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(by_id[c.id])
        else:
            roots.append(by_id[c.id])

    def calc_budget(node):
        c = node["cat"]
        if not node["children"]:
            return float(c.budget) if c.budget is not None else None
        child_sum = sum(v for ch in node["children"] if (v := calc_budget(ch)) is not None)
        return child_sum if any(calc_budget(ch) is not None for ch in node["children"]) else (float(c.budget) if c.budget is not None else None)

    def calc_purchased(node):
        c = node["cat"]
        if not node["children"]:
            return purchase_totals.get(c.id, 0.0)
        return sum(calc_purchased(ch) for ch in node["children"])

    wb = Workbook()
    ws = wb.active
    ws.title = sub.name[:31]

    header_fill = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    l1_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    l2_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    bold_font = Font(bold=True)
    semi_font = Font(bold=False)

    ws.append(["Наименование", "Код", "Прил.", "Финансирование по ФЭО (₽)", "Фактически запланировано (₽)", "Активна"])
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32

    def write_node(node, depth=0):
        c = node["cat"]
        indent = "  " * depth
        budget = calc_budget(node)
        purchased = calc_purchased(node)
        row = [
            indent + c.name,
            c.code or "",
            c.appendix or "",
            budget if budget is not None else "",
            purchased if purchased > 0 else "",
            "Да" if c.is_active else "Нет",
        ]
        ws.append(row)
        r = ws.max_row
        fill = l1_fill if c.level == 1 else (l2_fill if c.level == 2 else None)
        font = bold_font if c.level == 1 else (semi_font)
        for col in range(1, 7):
            cell = ws.cell(r, col)
            if fill:
                cell.fill = fill
            cell.font = font
            if col in (4, 5) and isinstance(cell.value, float):
                cell.number_format = '#,##0.00'
        for ch in node["children"]:
            write_node(ch, depth + 1)

    for root in roots:
        write_node(root)

    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 22
    ws.column_dimensions["F"].width = 10
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = sub.name.replace(" ", "_").replace("/", "-")[:40]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(f"ФЭО_{safe_name}.xlsx")},
    )


@router.put("/{cat_id}", response_model=FeoCategoryOut)
async def update_category(
    cat_id: int,
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    _old_plan = (cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount)
    cat.name = category_data.name
    cat.code = category_data.code
    cat.appendix = category_data.appendix
    cat.is_active = category_data.is_active
    cat.description = category_data.description
    cat.budget = category_data.budget
    cat.feo_quantity = category_data.feo_quantity
    cat.feo_unit = category_data.feo_unit
    cat.feo_amount = category_data.feo_amount
    cat.planned_quantity = category_data.planned_quantity
    cat.planned_amount = category_data.planned_amount
    cat.unit = category_data.unit
    if (cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount) != _old_plan and cat.subsidy_id:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(subsidy_id=cat.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение плановых показателей ФЭО «{cat.name}»")
    await db.commit()
    await db.refresh(cat)
    return cat


async def _collect_subtree_ids(cat_id: int, db: AsyncSession) -> list[int]:
    """Recursively collect all descendant IDs including the given cat_id."""
    ids = [cat_id]
    children = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for cid in children:
        ids.extend(await _collect_subtree_ids(cid, db))
    return ids


async def _update_subtree_levels(cat_id: int, level_delta: int, db: AsyncSession):
    """Recursively update levels of all children by delta."""
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for child in children:
        child.level = child.level + level_delta
        await _update_subtree_levels(child.id, level_delta, db)


# Удаление блокируют только закупки, по которым работа реально идёт
# (стадия «Ведётся работа» и далее). Желания/план-график/подтверждено —
# работа не начата, категория удаляется, привязка обнуляется (FK SET NULL).
BLOCKING_STATUSES = ("work_in_progress", "contracted", "ordered", "delivered", "paid")


async def _collect_blocking_purchases(ids: list[int], db: AsyncSession) -> list:
    """Закупки в блокирующих статусах, привязанные к переданным категориям
    напрямую (Purchase.feo_category_id) либо через позиции (PurchaseItem.feo_category_id).
    Уникальные по id, поля: id, purchase_number, subject, status."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    direct = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status).where(
            Purchase.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()
    via_items = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()

    seen: dict[int, object] = {}
    for row in direct:
        seen[row.id] = row
    for row in via_items:
        seen.setdefault(row.id, row)
    return list(seen.values())


async def _purge_feo_categories(ids: list[int], db: AsyncSession):
    """Отвязать все ссылки на переданные категории и удалить их. Не коммитит —
    коммитит вызывающий."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem

    # Отвязать закупки ранних стадий и их позиции от удаляемого поддерева
    await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id.in_(ids)).values(feo_category_id=None)
    )
    await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK references in products before deleting
    await db.execute(
        Product.__table__.update().where(Product.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK in purchase_items referencing planned_items of these categories
    planned_item_ids = (await db.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalars().all()
    if planned_item_ids:
        await db.execute(
            PurchaseItem.__table__.update().where(
                PurchaseItem.feo_planned_item_id.in_(planned_item_ids)
            ).values(feo_planned_item_id=None)
        )

    # Delete planned items explicitly (in case DB lacks CASCADE)
    await db.execute(
        FeoPlannedItem.__table__.delete().where(FeoPlannedItem.feo_category_id.in_(ids))
    )

    # Delete categories in one statement — feo_categories.parent_id is
    # ON DELETE CASCADE in the DB, so order doesn't matter. Doing it via
    # a table-level DELETE (instead of ORM db.delete per object) avoids
    # lazy-loading the `children` backref (FeoCategory.parent relationship).
    await db.execute(
        FeoCategory.__table__.delete().where(FeoCategory.id.in_(ids))
    )


async def _relink_feo_category(old_id: int, new_id: int, db: AsyncSession) -> dict:
    """Перевести все ссылки со старой категории на новую. Не коммитит.
    Возвращает счётчик переехавших строк по каждой таблице."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    counts: dict[str, int] = {}

    def _rowcount(result) -> int:
        rc = result.rowcount
        return rc if rc and rc > 0 else 0

    result = await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchases"] = _rowcount(result)

    result = await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchase_items"] = _rowcount(result)

    result = await db.execute(
        Wish.__table__.update().where(Wish.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wishes"] = _rowcount(result)

    result = await db.execute(
        WishItem.__table__.update().where(WishItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wish_items"] = _rowcount(result)

    result = await db.execute(
        Product.__table__.update().where(Product.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["products"] = _rowcount(result)

    # Плановые позиции — с дедупликацией по имени (регистронезависимо, trim)
    old_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == old_id)
    )).scalars().all()
    new_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == new_id)
    )).scalars().all()
    new_by_name = {(i.name or "").strip().lower(): i for i in new_items}

    planned_items_moved = 0
    for item in old_items:
        key = (item.name or "").strip().lower()
        existing = new_by_name.get(key)
        if existing is not None:
            await db.execute(
                PurchaseItem.__table__.update()
                .where(PurchaseItem.feo_planned_item_id == item.id)
                .values(feo_planned_item_id=existing.id)
            )
            await db.execute(
                FeoPlannedItem.__table__.delete().where(FeoPlannedItem.id == item.id)
            )
        else:
            await db.execute(
                FeoPlannedItem.__table__.update()
                .where(FeoPlannedItem.id == item.id)
                .values(feo_category_id=new_id)
            )
            new_by_name[key] = item
        planned_items_moved += 1
    counts["feo_planned_items"] = planned_items_moved

    return counts


async def _feo_category_load(ids: list[int], db: AsyncSession) -> dict:
    """Что висит на переданных категориях: количества по каждой из ссылающихся
    таблиц + список блокирующих закупок с человекочитаемым статусом.
    Позволяет вызывающему решить, пуст ли узел, и показать пользователю причину."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.routers.purchase_transitions import STATUS_LABELS

    purchases_count = (await db.execute(
        select(func.count(Purchase.id)).where(Purchase.feo_category_id.in_(ids))
    )).scalar_one()
    purchase_items_count = (await db.execute(
        select(func.count(PurchaseItem.id)).where(PurchaseItem.feo_category_id.in_(ids))
    )).scalar_one()
    wishes_count = (await db.execute(
        select(func.count(Wish.id)).where(Wish.feo_category_id.in_(ids))
    )).scalar_one()
    wish_items_count = (await db.execute(
        select(func.count(WishItem.id)).where(WishItem.feo_category_id.in_(ids))
    )).scalar_one()
    products_count = (await db.execute(
        select(func.count(Product.id)).where(Product.feo_category_id.in_(ids))
    )).scalar_one()
    planned_items_count = (await db.execute(
        select(func.count(FeoPlannedItem.id)).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalar_one()

    blocking = await _collect_blocking_purchases(ids, db)
    purchases_list = [
        {
            "id": p.id,
            "purchase_number": p.purchase_number,
            "subject": p.subject,
            "status": p.status,
            "status_label": STATUS_LABELS.get(p.status, p.status),
        }
        for p in blocking
    ]

    return {
        "purchases": purchases_count,
        "purchase_items": purchase_items_count,
        "wishes": wishes_count,
        "wish_items": wish_items_count,
        "products": products_count,
        "feo_planned_items": planned_items_count,
        "blocking_purchases": purchases_list,
    }


@router.get("/{cat_id}/subtree")
async def get_category_subtree(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Имя категории + id всего поддерева (для фильтра «закупки этой категории»)."""
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == cat_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    ids = await _collect_subtree_ids(cat_id, db)
    return {"id": cat.id, "name": cat.name, "ids": ids}


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Collect entire subtree
    all_ids = await _collect_subtree_ids(cat_id, db)

    linked_purchases = await _collect_blocking_purchases(all_ids, db)
    if linked_purchases:
        purchase_ids = [p.id for p in linked_purchases]
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Нельзя удалить: {len(linked_purchases)} закупок со стадией "
                    f"«Ведётся работа» и далее привязано к этой категории. "
                    f"Закупки на ранних стадиях (желания, план-график) удалению не мешают."
                ),
                "purchase_ids": purchase_ids,
                "feo_category_ids": all_ids,
            }
        )

    await _purge_feo_categories(all_ids, db)
    await db.commit()
    deleted_count = len(all_ids)
    return {"ok": True, "deleted_count": deleted_count}


@router.patch("/{cat_id}/move")
async def move_category(
    cat_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Move category to a new parent. Set parent_id=null to make root."""
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    new_parent_id = data.get("parent_id")
    warning = None

    # Determine new level
    if new_parent_id:
        parent = (await db.execute(select(FeoCategory).where(FeoCategory.id == new_parent_id))).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != cat.subsidy_id:
            raise HTTPException(status_code=400, detail="Нельзя переместить в другую субсидию")
        new_level = parent.level + 1
    else:
        new_level = 1

    level_delta = new_level - cat.level

    # Check for circular reference
    if new_parent_id:
        subtree_ids = await _collect_subtree_ids(cat_id, db)
        if new_parent_id in subtree_ids:
            raise HTTPException(status_code=400, detail="Нельзя переместить в собственное поддерево")

    # Check if new max depth creates a previously unseen level
    max_child_depth = 0
    all_ids = await _collect_subtree_ids(cat_id, db)
    if len(all_ids) > 1:
        max_existing = (await db.execute(
            select(func.max(FeoCategory.level)).where(FeoCategory.id.in_(all_ids))
        )).scalar() or cat.level
        max_child_depth = max_existing - cat.level
    new_max_level = new_level + max_child_depth
    existing_max = (await db.execute(
        select(func.max(FeoCategory.level)).where(FeoCategory.subsidy_id == cat.subsidy_id)
    )).scalar() or 1
    if new_max_level > existing_max:
        warning = f"Создан новый уровень вложенности: {new_max_level}"

    # Update category
    cat.parent_id = new_parent_id
    cat.level = new_level

    # Recursively update children levels
    if level_delta != 0:
        await _update_subtree_levels(cat_id, level_delta, db)

    await db.commit()
    result = {"ok": True, "new_level": new_level}
    if warning:
        result["warning"] = warning
    return result


@router.patch("/{cat_id}/reorder")
async def reorder_category(
    cat_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Move a category up/down among its siblings (same parent, same subsidy).
    Body: {"direction": "up"|"down"}. Swaps sort_order with the adjacent sibling."""
    direction = (data.get("direction") or "").lower()
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction должен быть 'up' или 'down'")
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    sib_filter = (
        FeoCategory.parent_id.is_(None) if cat.parent_id is None
        else FeoCategory.parent_id == cat.parent_id
    )
    siblings = (await db.execute(
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == cat.subsidy_id, sib_filter)
        .order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()
    # Normalize any NULL sort_order to a stable increasing sequence
    for i, s in enumerate(siblings):
        if s.sort_order is None:
            s.sort_order = (i + 1) * 10
    idx = next((i for i, s in enumerate(siblings) if s.id == cat_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Категория не найдена среди соседей")
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(siblings):
        await db.commit()
        return {"ok": True, "moved": False}
    a, b = siblings[idx], siblings[swap_idx]
    a.sort_order, b.sort_order = b.sort_order, a.sort_order
    await db.commit()
    return {"ok": True, "moved": True}
