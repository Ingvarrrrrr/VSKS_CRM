import difflib
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import select, func, delete, or_
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
from app.schemas.schemas import PurchaseCreate, PurchaseOut, PurchaseOutFull, PurchaseItemOut, PurchaseFileOut, SubsidyAllocationOut
from app.models.subsidy_allocation import PurchaseSubsidyAllocation
from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids
from app.auth.permissions import require_tab, require_action
from app.models.user import User
from app.models.user_org_access import UserOrgAccess
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.product_matcher import find_matching_product
from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, date
from app.models.user_hierarchy import UserHierarchy
router = APIRouter(prefix="/api/purchases", tags=["purchases"])


async def _sync_purchase_from_contract(p: Purchase, db: AsyncSession):
    """Когда установлен contract_id — копируем number/date/contract_type/contractor_id из contracts в purchases.

    Поля в purchases являются денормализованным снапшотом (для list-view без JOIN),
    но при наличии FK должны строго следовать связанному контракту.

    Phase 26-lll: contractor_id ОБЯЗАТЕЛЬНО синхронизируется — иначе в реестре
    закупок колонка «Контрагент» пустая (—), хотя в договоре контрагент есть.
    """
    if not p.contract_id:
        return
    c = await db.get(Contract, p.contract_id)
    if not c:
        return
    if c.number:
        p.contract_number = c.number.strip()
    if c.date:
        p.contract_date = c.date
    if c.contract_type:
        p.purchase_contract_type = c.contract_type
    if c.contractor_id and not p.contractor_id:
        # Не перетираем уже установленного контрагента (multi-contractor сценарии),
        # только заполняем NULL.
        p.contractor_id = c.contractor_id


async def _has_purchase_write_access(user: User, db: AsyncSession) -> bool:
    """True for any authenticated user.

    Дизайн: доступ к конкретной закупке гейтится через org_filter +
    _get_visible_user_ids в list_purchases. GET /{pid} вообще без auth — кто
    смог прочесть, тот может и сохранить (autosave PATCH). Бизнес-проверки
    (статус-переходы, согласование) — отдельные эндпоинты с require_action.

    Раньше эта функция гейтила MANAGER_ROLES + user_org_access — но у юзеров
    созданных давно (до Phase 17.1) могло не быть ни role, ни UOA-row,
    ни org_id (data-issue), что приводило к 403 при autosave формы закупки.
    """
    return user is not None


async def _auto_match_feo_item(
    item_name: str,
    purchase_subsidy_id: Optional[int],
    purchase_feo_category_id: Optional[int],
    db: AsyncSession,
) -> Optional[tuple]:
    """
    Find best matching FeoPlannedItem for item_name.
    Returns (feo_planned_item_id, matched_name, confidence) or None.
    Threshold: 0.6.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC

    if not item_name:
        return None

    if purchase_feo_category_id:
        q = select(_FPI).where(
            _FPI.feo_category_id == purchase_feo_category_id,
            _FPI.is_active == True,
        )
    elif purchase_subsidy_id:
        q = (
            select(_FPI)
            .join(_FC, _FPI.feo_category_id == _FC.id)
            .where(_FC.subsidy_id == purchase_subsidy_id, _FPI.is_active == True)
        )
    else:
        return None

    candidates = (await db.execute(q)).scalars().all()
    if not candidates:
        return None

    name_lower = item_name.lower().strip()
    best_score = 0.0
    best_item = None
    for cand in candidates:
        score = difflib.SequenceMatcher(
            None, name_lower, cand.name.lower().strip()
        ).ratio()
        if score > best_score:
            best_score = score
            best_item = cand

    if best_score >= 0.6 and best_item is not None:
        return (best_item.id, best_item.name, round(best_score, 2))
    return None


async def _create_plan_graph_version(
    subsidy_id: int,
    db: AsyncSession,
    user,
    note: Optional[str] = None,
    effective_date: Optional[date] = None,
) -> None:
    """
    Build a snapshot of all active FeoPlannedItems for the subsidy with residuals
    and save as a new PlanGraphVersion row. Increments version_number.
    schema_version=2: includes recursive FeoCategory tree with budget.
    Caller must commit after this call.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    # Fetch all active FEO items for this subsidy
    items_q = (
        select(_FPI, _FC.id.label("cat_id"))
        .join(_FC, _FPI.feo_category_id == _FC.id)
        .where(_FC.subsidy_id == subsidy_id, _FPI.is_active == True)
        .order_by(_FPI.id)
    )
    rows = (await db.execute(items_q)).all()

    if not rows:
        return  # nothing to version

    item_ids = [r[0].id for r in rows]

    # Aggregate used amounts
    used_q = (
        select(
            PurchaseItem.feo_planned_item_id,
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
        )
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .group_by(PurchaseItem.feo_planned_item_id)
    )
    used_map: dict[int, float] = {
        r.feo_planned_item_id: float(r.used)
        for r in (await db.execute(used_q)).all()
    }

    # Collect linked purchase ids
    links_q = (
        select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
    )
    links_map: dict[int, list] = {}
    for lr in (await db.execute(links_q)).all():
        links_map.setdefault(lr.feo_planned_item_id, [])
        if lr.purchase_id not in links_map[lr.feo_planned_item_id]:
            links_map[lr.feo_planned_item_id].append(lr.purchase_id)

    snapshot_items = []
    total_planned = 0.0
    total_used = 0.0
    for r in rows:
        item = r[0]
        planned = float(item.amount or 0)
        used = used_map.get(item.id, 0.0)
        total_planned += planned
        total_used += used
        snapshot_items.append({
            "feo_item_id": item.id,
            "name": item.name,
            "category_id": item.feo_category_id,
            "planned_amount": planned,
            "used_amount": used,
            "residual": planned - used,
            "linked_purchase_ids": links_map.get(item.id, []),
        })

    # Build FeoCategory tree for schema_version=2
    cats_q = select(_FC).where(_FC.subsidy_id == subsidy_id).order_by(_FC.id)
    all_cats = (await db.execute(cats_q)).scalars().all()

    # FCAT-B3: aggregate used_amount via PurchaseItem.feo_category_id for leaf nodes
    all_cat_ids = [c.id for c in all_cats]
    cat_used_q = (
        select(
            PurchaseItem.feo_category_id,
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
        )
        .where(PurchaseItem.feo_category_id.in_(all_cat_ids))
        .group_by(PurchaseItem.feo_category_id)
    )
    cat_used_map: dict[int, float] = {
        r.feo_category_id: float(r.used)
        for r in (await db.execute(cat_used_q)).all()
    }

    def _build_tree(cats, parent_id=None):
        nodes = []
        for c in cats:
            if c.parent_id == parent_id:
                nodes.append({
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "used_amount": cat_used_map.get(c.id, 0.0),  # FCAT-B3: агрегат через feo_category_id
                    "children": _build_tree(cats, parent_id=c.id),
                })
        return nodes

    feo_tree = _build_tree(all_cats)

    snapshot = {
        "schema_version": 2,
        "subsidy_id": subsidy_id,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "total_planned": total_planned,
        "total_used": total_used,
        "items": snapshot_items,  # backward-compat
        "tree": feo_tree,
    }

    # Get next version_number
    max_ver_q = select(
        func.coalesce(func.max(_PGV.version_number), 0)
    ).where(_PGV.subsidy_id == subsidy_id)
    next_ver = int((await db.execute(max_ver_q)).scalar() or 0) + 1

    pgv = _PGV(
        subsidy_id=subsidy_id,
        version_number=next_ver,
        created_by_id=getattr(user, "id", None),
        created_by_name=getattr(user, "full_name", None) or getattr(user, "username", None),
        snapshot=snapshot,
        note=note,
        effective_date=effective_date,
    )
    db.add(pgv)


# Status workflow
STATUS_ORDER = ["wishes", "plan_schedule", "confirmed", "work_in_progress", "contracted", "ordered", "delivered", "paid"]
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform")


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
        country_origin=item.country_origin,
        # Phase 26-V/W/BB: contractor + match + receipt linkage — критично для UI
        contractor_id=item.contractor_id,
        contractor_inn=item.contractor_inn,
        contractor_name=item.contractor_name,
        match_confirmed=item.match_confirmed if item.match_confirmed is not None else True,
        receipt_id=getattr(item, 'receipt_id', None),
        vat_rate=getattr(item, 'vat_rate', None),
        product_name=product_name,
        product_photo_url=product_photo_url,
        product_description=product_description,
        product_description_44fz=product_description_44fz,
    )


def _purchase_to_full(p: Purchase, contractors: dict, subsidies: dict, allocations: list | None = None, contractor_inns: dict | None = None, receipt_map: dict | None = None, ru_map: dict | None = None) -> PurchaseOutFull:
    data = {c.name: getattr(p, c.name) for c in Purchase.__table__.columns}
    items = [_item_to_out(i) for i in (p.items or [])]
    files = [
        PurchaseFileOut(
            id=f.id,
            purchase_id=f.purchase_id,
            filename=f.filename,
            mime_type=f.mime_type,
            size=f.size,
            file_type=f.file_type,
            doc_format=f.doc_format,
            is_active=f.is_active if f.is_active is not None else True,
            content_hash=f.content_hash,
            uploaded_by_id=f.uploaded_by_id,
            created_at=str(f.created_at) if f.created_at else None,
        )
        for f in (p.files or [])
    ]
    alloc_out = None
    if allocations is not None:
        alloc_out = [
            SubsidyAllocationOut(
                id=a.id,
                subsidy_id=a.subsidy_id,
                subsidy_name=a.subsidy.name if a.subsidy else subsidies.get(a.subsidy_id),
                amount=a.amount,
            )
            for a in allocations
        ]
    # Multi-contractor label for advance reports
    multi_contractor_label: str | None = None
    if p.purchase_method == 'advance' and p.items:
        unique_names = {item.contractor_name for item in p.items if item.contractor_name}
        if len(unique_names) > 1:
            multi_contractor_label = "Множественный контрагент"
        elif len(unique_names) == 1:
            multi_contractor_label = next(iter(unique_names))

    return PurchaseOutFull(
        **data,
        items=items,
        files=files,
        contractor_name=contractors.get(p.contractor_id),
        contractor_inn=(contractor_inns or {}).get(p.contractor_id),
        feo_category_name=p.feo_category.name if p.feo_category else None,
        subsidy_name=subsidies.get(p.subsidy_id),
        event_name=p.event.name if p.event else None,
        subsidy_allocations=alloc_out,
        last_receipt_date=(receipt_map or {}).get(p.id),
        reimbursement_user_name=(ru_map or {}).get(p.reimbursement_user_id),
        multi_contractor_label=multi_contractor_label,
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
    org_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    purchase_basis: Optional[str] = Query(None),
    framework_seq: Optional[int] = Query(None),
    vehicle_id: Optional[int] = Query(None),
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
        selectinload(Purchase.event),
    )
    org_ids = get_org_filter(current_user)
    needs_subsidy_join = org_ids is not None or org_id is not None
    if needs_subsidy_join:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
        if org_id is not None:
            # Explicit org filter takes precedence; still validate user has access to this org
            if org_ids is not None and org_id not in org_ids:
                return []
            q = q.where(Subsidy.org_id == org_id)
        elif org_ids is not None:
            q = q.where(Subsidy.org_id.in_(org_ids))
    # Phase 28: unified visibility helper.
    # — build_visibility_clause возвращает None для SaaS-ролей (фильтр не нужен),
    #   иначе or_() с правилами 1-5 (иерархия + участие).
    clause = await build_visibility_clause(current_user, db, 'purchase')
    if clause is not None:
        # Safety-net: для org-lead'ов всё ещё пропускаем закупки с
        # assigned_user_id IS NULL — на проде осталась 1 legacy-закупка
        # (id 779 без subsidy_id), будет удалена после ручного triage.
        # Org-lead = admin/account_owner ИЛИ есть head/managed dept/org/UOA.
        # Используем visible_user_ids: если size > 1 → user управляет ≥1 чел.
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (
            current_user.role in ADMIN_ROLES
            or (vuids is not None and len(vuids) > 1)
        )
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        q = q.where(clause)
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        q = q.where(Purchase.feo_category_id == feo_category_id)
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    if purchase_method:
        q = q.where(Purchase.purchase_method == purchase_method)
    if purchase_basis:
        q = q.where(Purchase.purchase_basis == purchase_basis)
    if framework_seq is not None:
        q = q.where(Purchase.framework_seq == framework_seq)
    if vehicle_id is not None:
        q = q.where(Purchase.vehicle_id == vehicle_id)
    # Hide purchases that were split into children unless explicitly requested
    if status != "split":
        q = q.where(Purchase.status != "split")
    if search:
        like = f"%{search}%"
        from sqlalchemy import cast, String as SAString
        search_filters = [
            Purchase.item_name.ilike(like),
            Purchase.subject.ilike(like),
            Purchase.registry_number.ilike(like),
            Purchase.contract_number.ilike(like),
            Purchase.order_number.ilike(like),
        ]
        # Search by purchase_number if numeric
        if search.strip().isdigit():
            search_filters.append(Purchase.purchase_number == int(search.strip()))
        q = q.where(or_(*search_filters))
    q = q.order_by(Purchase.id.desc())
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors_list = contractors_r.scalars().all()
    contractors = {c.id: c.name for c in contractors_list}
    contractor_inns = {c.id: c.inn for c in contractors_list}
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}

    # Batch-fetch reimbursement user names
    ru_ids = [p.reimbursement_user_id for p in purchases if p.reimbursement_user_id]
    ru_map: dict = {}
    if ru_ids:
        res = await db.execute(select(User.id, User.full_name).where(User.id.in_(ru_ids)))
        ru_map = {uid: name for uid, name in res.all()}

    # Batch-fetch last receipt date for advance purchases
    from app.models.purchase_receipt import PurchaseReceipt
    adv_ids = [p.id for p in purchases if p.purchase_method == 'advance']
    receipt_map: dict = {}
    if adv_ids:
        res = await db.execute(
            select(PurchaseReceipt.purchase_id, func.max(PurchaseReceipt.receipt_datetime))
            .where(PurchaseReceipt.purchase_id.in_(adv_ids))
            .group_by(PurchaseReceipt.purchase_id)
        )
        receipt_map = {pid: dt for pid, dt in res.all()}

    # phase26-m: batch-load framework_contract_total (max_amount or SUM(contract_price))
    framework_contract_ids = {
        p.contract_id for p in purchases
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount')
    }
    display_total_by_contract: dict = {}
    if framework_contract_ids:
        contracts_r = await db.execute(
            select(Contract.id, Contract.max_amount).where(Contract.id.in_(framework_contract_ids))
        )
        contracts_by_id = {row[0]: row[1] for row in contracts_r.all()}
        for cid in framework_contract_ids:
            max_amount = contracts_by_id.get(cid)
            if max_amount is not None:
                display_total_by_contract[cid] = max_amount
            else:
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(func.coalesce(
                        Purchase.contract_price,
                        Purchase.planned_total_price,
                        Purchase.total_nmck,
                        Decimal("0"),
                    )), Decimal("0"))).where(Purchase.contract_id == cid)
                )
                display_total_by_contract[cid] = sum_r.scalar() or Decimal("0")

    result_rows = []
    for p in purchases:
        out = _purchase_to_full(p, contractors, subsidies, contractor_inns=contractor_inns, receipt_map=receipt_map, ru_map=ru_map)
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
            out.framework_contract_total = display_total_by_contract.get(p.contract_id)
        result_rows.append(out)
    return result_rows


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
    users_result = await db.execute(select(User))  # superadmin-bypass-ok: internal enrichment map by ID, not a user-list endpoint
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
            selectinload(Purchase.event),
            selectinload(Purchase.reimbursement_user),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")

    # Phase 26-Z-bootstrap: для advance закупок — silent idempotent recompute если
    # есть чеки и items с NULL contractor_id ИЛИ receipts без записи в acceptance_docs.
    if p.purchase_method == 'advance':
        try:
            from sqlalchemy import select as _sel
            from app.models.purchase_receipt import PurchaseReceipt as _PR
            from app.models.purchase_item import PurchaseItem as _PI
            receipts_count = (await db.execute(
                _sel(func.count(_PR.id)).where(_PR.purchase_id == pid)
            )).scalar() or 0
            if receipts_count > 0:
                null_items_count = (await db.execute(
                    _sel(func.count(_PI.id)).where(
                        _PI.purchase_id == pid,
                        _PI.contractor_id.is_(None),
                    )
                )).scalar() or 0
                current_docs = p.acceptance_docs or []
                receipt_ids_in_docs = {d.get("receipt_id") for d in current_docs if isinstance(d, dict) and d.get("receipt_id")}
                receipt_ids_actual = set((await db.execute(
                    _sel(_PR.id).where(_PR.purchase_id == pid)
                )).scalars().all())
                # Mismatch detection: позиция привязана к чеку, но контрагент не из этого чека
                mismatch_count = 0
                linked_items_q = await db.execute(
                    _sel(_PI).where(
                        _PI.purchase_id == pid,
                        _PI.receipt_id.is_not(None),
                    )
                )
                for _it in linked_items_q.scalars().all():
                    _r = await db.get(_PR, _it.receipt_id)
                    if not _r or not _r.seller_inn:
                        continue
                    if _it.contractor_inn != _r.seller_inn:
                        mismatch_count += 1
                        break  # достаточно одного для триггера
                # Phase 26-DD: receipts с raw_json items, но 0 PurchaseItem с этими receipt_id
                from app.routers.purchase_receipts import _extract_items as _ext_items
                orphan_receipts = 0
                if receipt_ids_actual:
                    for _rid in receipt_ids_actual:
                        _r = await db.get(_PR, _rid)
                        if not _r:
                            continue
                        _has_items = (await db.execute(
                            _sel(func.count(_PI.id)).where(_PI.receipt_id == _rid)
                        )).scalar() or 0
                        if _has_items == 0:
                            _raw_items = _ext_items(_r.raw_json or {})
                            if _raw_items:
                                orphan_receipts += 1
                                break
                need_recompute = bool(null_items_count) or bool(receipt_ids_actual - receipt_ids_in_docs) or bool(mismatch_count) or bool(orphan_receipts)
                if need_recompute:
                    from app.routers.purchase_receipts import _recompute_from_receipts_core
                    await _recompute_from_receipts_core(pid, db)
                    # Re-fetch p после recompute с теми же relationships
                    result = await db.execute(
                        select(Purchase)
                        .options(
                            selectinload(Purchase.contractor),
                            selectinload(Purchase.feo_category),
                            selectinload(Purchase.items).selectinload(PurchaseItem.product),
                            selectinload(Purchase.files),
                            selectinload(Purchase.event),
                            selectinload(Purchase.reimbursement_user),
                        )
                        .where(Purchase.id == pid)
                    )
                    p = result.scalar_one()
        except Exception as _re:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"auto-recompute on GET /purchases/{pid} skipped: {_re}")

    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    alloc_r = await db.execute(
        select(PurchaseSubsidyAllocation)
        .options(selectinload(PurchaseSubsidyAllocation.subsidy))
        .where(PurchaseSubsidyAllocation.purchase_id == pid)
    )
    allocations = alloc_r.scalars().all()
    single_ru_map: dict = {}
    if p.reimbursement_user_id and p.reimbursement_user:
        single_ru_map = {p.reimbursement_user_id: p.reimbursement_user.full_name}
    out = _purchase_to_full(p, contractors, subsidies, allocations=allocations, ru_map=single_ru_map)
    # phase26-m: populate framework_contract_total for single purchase view
    if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
        c = await db.get(Contract, p.contract_id)
        if c:
            if c.max_amount is not None:
                out.framework_contract_total = c.max_amount
            else:
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(func.coalesce(
                        Purchase.contract_price,
                        Purchase.planned_total_price,
                        Purchase.total_nmck,
                        Decimal("0"),
                    )), Decimal("0"))).where(Purchase.contract_id == p.contract_id)
                )
                out.framework_contract_total = sum_r.scalar() or Decimal("0")
    return out


@router.post("/", response_model=PurchaseOut)
async def create_purchase(
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    # Compute total_nmck from items
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override and data.purchase_basis != 'service_note':
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, None, db)

    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    dump = data.model_dump(exclude={"items", "subsidy_allocations"})
    dump["total_nmck"] = total_nmck
    # Phase 28 B4: validate provided assigned_user_id
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    # Auto-assign current user as owner when frontend did not specify one.
    # Без этого закупка с assigned_user_id=NULL становится невидимой для рядового
    # автора (list_purchases фильтрует по visible_user_ids; NULL IN (...) = false).
    if not dump.get("assigned_user_id"):
        dump["assigned_user_id"] = current_user.id
    p = Purchase(**dump)
    db.add(p)
    await db.flush()  # get p.id before commit

    year = date.today().year
    if not p.registry_number:
        p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
    # removed in phase26-j-1: only set when single contract без FK на existing contracts row
    # auto-generate мусорит номером вида "2026/42" для рамочных закупок с реальным contract_id.
    if not p.contract_number and not p.contract_id:
        p.contract_number = f"{year}/{p.id}"

    # phase26-j-1: sync number/date/type из связанного контракта, если contract_id задан
    await _sync_purchase_from_contract(p, db)

    await _assign_framework_seq(p, db)

    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=p.id, **d)
        db.add(item)

    # Save subsidy allocations
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=p.id,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # Contract price: авто-пересчёт из items для ВСЕХ типов закупок (phase26-l-1).
    # Рамочный (framework_cumulative / framework_with_amount) тоже должен суммироваться в total_ordered контракта.
    _items_sum_create = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck
    if _items_sum_create:
        p.contract_price = _items_sum_create

    # Budget history write hook — record initial planned_total_price
    if p.subsidy_id and p.planned_total_price:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=p.subsidy_id,
            purchase_id=p.id,
            entity_type="purchase",
            old_value=None,
            new_value=float(p.planned_total_price),
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    await db.commit()
    await db.refresh(p)
    return p


@router.put("/{pid}")
async def update_purchase(
    pid: int,
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    old_planned_total_price = p.planned_total_price  # capture BEFORE setattr loop
    # Employees/managers can save any purchase they have access to (org-level access checked at list level)
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    items_sum = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    # Phase 28 B4: validate assigned_user_id on PUT
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    elif data.assigned_user_id == 0:
        raise HTTPException(422, "Укажите ответственного исполнителя")

    # Opportunistic backfill: legacy purchases с assigned_user_id=NULL
    # становятся видимыми создателю через первое же сохранение.
    if p.assigned_user_id is None and not getattr(data, "assigned_user_id", None):
        p.assigned_user_id = current_user.id

    # Auto-assign purchase_number if missing
    if not p.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        p.purchase_number = max_result.scalar() + 1

    # НМЦК logic: frozen after "contracted" status
    CONTRACTED_STATUSES = ("contracted", "ordered", "delivered", "paid")
    is_contracted = p.status in CONTRACTED_STATUSES

    if is_contracted:
        # НМЦК зафиксирована — НЕ пересчитываем, берём из БД
        # Обновляем только цену договора из текущих цен позиций
        pass
    else:
        # До стадии "Договор" — НМЦК = сумма позиций
        p.total_nmck = items_sum
        p.planned_total_price = items_sum or p.planned_total_price

    if not admin_override and data.purchase_basis != 'service_note':
        budget_amount = p.total_nmck if is_contracted else items_sum
        # 12-02: per-item FEO budget check
        _feo_check_items = [
            {"feo_planned_item_id": i.feo_planned_item_id, "amount": i.total_price}
            for i in items_data
            if i.feo_planned_item_id and i.total_price
        ]
        await _check_budget(
            data.subsidy_id,
            budget_amount or data.planned_total_price,
            pid,
            db,
            feo_items=_feo_check_items,
            is_admin=current_user.role in ADMIN_ROLES,
        )

    # If contract_id or type changed, reset seq so it gets re-assigned
    old_contract_id = p.contract_id
    old_type = p.purchase_contract_type
    payload_dict = data.model_dump(exclude={"items", "subsidy_allocations"}, exclude_unset=True)
    # Phase 27.1.4: race-defence — если payload приходит с contractor_id=None,
    # а в БД он был установлен И contract_id не меняется → игнорируем stale null.
    # Это защищает от race в editFrameworkSeq: форма шлёт PUT до завершения async fetch контрагента.
    if (
        'contractor_id' in payload_dict
        and payload_dict['contractor_id'] is None
        and p.contractor_id is not None
        and payload_dict.get('contract_id', p.contract_id) == p.contract_id
    ):
        payload_dict.pop('contractor_id')

    for k, v in payload_dict.items():
        # Don't overwrite frozen total_nmck
        if is_contracted and k in ("total_nmck", "planned_total_price"):
            continue
        setattr(p, k, v)
    # JSONB columns need explicit dirty-flag so SQLAlchemy detects mutations
    if "acceptance_docs" in data.model_fields_set:
        flag_modified(p, "acceptance_docs")

    # Contract price: авто-пересчёт из items для ВСЕХ типов закупок (phase26-l-1).
    # Рамочный (framework_cumulative / framework_with_amount) тоже должен суммироваться в total_ordered контракта.
    if items_sum:
        p.contract_price = items_sum
    if (p.contract_id != old_contract_id or p.purchase_contract_type != old_type) and data.framework_seq is None:
        p.framework_seq = None  # force re-assignment below
    # phase26-j-1 (fix: hotfix после регрессии): sync только при ИЗМЕНЕНИИ contract_id,
    # иначе ручные правки contract_number перетираются на каждом save (Vue v-model шлёт contract_id всегда).
    if p.contract_id and p.contract_id != old_contract_id:
        await _sync_purchase_from_contract(p, db)
    await _assign_framework_seq(p, db, exclude_id=pid)

    # Replace items (auto-link to catalog via fuzzy match if product_id missing)
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=pid, **d)
        db.add(item)

    # Phase 26-Z: при PUT — проставить contractor_id во все позиции без контрагента,
    # если на уровне закупки contractor_id установлен. Идемпотентно.
    if p.contractor_id:
        await db.flush()  # flush чтобы только что созданные items видны в SELECT
        _ctr_put = await db.get(Contractor, p.contractor_id)
        if _ctr_put:
            _null_items_put = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == pid, PurchaseItem.contractor_id.is_(None))
            )).scalars().all()
            for _it in _null_items_put:
                _it.contractor_id = _ctr_put.id
                _it.contractor_inn = _ctr_put.inn
                _it.contractor_name = _ctr_put.name

    # 12-02: Auto-match FEO items for purchase items without feo_planned_item_id
    suggested_feo_matches = []
    await db.flush()  # ensure new items are visible
    _flushed_items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
    )).scalars().all()
    for idx, pi in enumerate(_flushed_items):
        if pi.feo_planned_item_id is not None:
            continue  # already linked
        match = await _auto_match_feo_item(
            pi.item_name,
            p.subsidy_id,
            p.feo_category_id,
            db,
        )
        if match:
            suggested_feo_matches.append({
                "item_index": idx,
                "purchase_item_id": pi.id,
                "item_name": pi.item_name,
                "suggested_item_id": match[0],
                "suggested_name": match[1],
                "confidence": match[2],
            })

    # Replace subsidy allocations
    await db.execute(delete(PurchaseSubsidyAllocation).where(PurchaseSubsidyAllocation.purchase_id == pid))
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=pid,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # Auto-create/link contract record when contract_number is set
    await ensure_contract_linked(p, db)

    # Budget history write hook
    if p.subsidy_id:
        _old = float(old_planned_total_price or 0)
        _new = float(p.planned_total_price or 0)
        if _old != _new:
            from app.models.budget_history import BudgetHistory as _BH
            db.add(_BH(
                subsidy_id=p.subsidy_id,
                purchase_id=p.id,
                entity_type="purchase",
                old_value=_old,
                new_value=_new,
                changed_by_id=current_user.id,
                changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                reason=None,
            ))

    # 12-03: Auto-create plan-graph version if any items are FEO-linked
    if p.subsidy_id and any(i.feo_planned_item_id for i in items_data if i.feo_planned_item_id):
        await _create_plan_graph_version(
            subsidy_id=p.subsidy_id,
            db=db,
            user=current_user,
            note=f"Авто-версия при сохранении закупки #{p.purchase_number or p.id}",
        )

    await db.commit()
    await db.refresh(p)
    # 12-02: Return suggestions if any
    if suggested_feo_matches:
        from app.schemas.schemas import PurchaseOut as _POut
        base = _POut.model_validate(p).model_dump()
        base["suggested_feo_matches"] = suggested_feo_matches
        return base
    return p


# Phase 27.1 D-07: helper — авто-пересчёт purchase.contract_price = SUM(contract_items.total)
async def _recalc_contract_price_from_contract_items(purchase_id: int, db: AsyncSession) -> None:
    """Phase 27.1 D-07: авто-пересчёт purchase.contract_price = SUM(contract_items.total).

    Применимо: разовая (purchase_contract_type='single' или NULL), авансовая
    (purchase_method='advance'), дочерняя рамочного (parent_purchase_id IS NOT NULL).
    НЕ применимо для рамочного головного (framework_cumulative/framework_limited
    AND parent_purchase_id IS NULL) — manual entry сохраняется.
    """
    from app.models.contract_item import ContractItem
    p = await db.get(Purchase, purchase_id)
    if not p:
        return
    is_framework_head = (
        p.purchase_contract_type in ('framework_cumulative', 'framework_limited')
        and p.parent_purchase_id is None
    )
    if is_framework_head:
        return
    result = await db.execute(
        select(func.sum(ContractItem.total)).where(ContractItem.purchase_id == purchase_id)
    )
    ci_sum = result.scalar() or Decimal('0')
    if ci_sum > 0:
        p.contract_price = ci_sum
        await db.commit()


# Phase 26: автосохранение полей карточки закупки.
# Принимает произвольный частичный JSON; обновляет только переданные поля.
# Не пересчитывает items/НМЦК/contract_price (этим занимается PUT при явном Save).
PATCHABLE_FIELDS = {
    "subject", "description", "contractor_id", "feo_category_id",
    "purchase_method", "purchase_contract_type",
    "contract_number", "contract_date", "contract_price", "contract_end_date",
    "nmck", "planned_total_price",
    "delivery_date", "delivery_location", "delivery_address",
    "submission_deadline", "service_term_mode", "service_start_date",
    "service_end_date", "service_term_days", "service_term_type",
    "service_deadline_date", "third_party_involved",
    "vat_applicable", "vat_rate", "vat_exemption_article",
    "acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number",
    "acceptance_doc_amount",
    # Phase 24 D-08: JSONB-массив закрывающих документов (АКТ/УПД/СЧФ/ТТН/...)
    "acceptance_docs",
    "payment_doc_number", "payment_doc_date",
    "payment_amount", "country_origin", "purchase_basis",
    "responsible_person_id", "initiator_id", "subject_kind", "execution_term",
    "event_id", "delivery_location_kind", "region",
    # Phase 24: stages + financial plan
    "is_likely_needed", "is_prepayment", "prepayment_date", "stage_label",
    # Авансовый отчёт: кому возмещать
    "reimbursement_user_id",
    # Phase 28 B4: ответственный исполнитель
    "assigned_user_id",
    # Phase 26-K: доп. соглашение и дата заказа
    "agreement_number", "agreement_date", "order_date",
    # Phase 28: форма договора (выбор шаблона при генерации)
    "contract_form",
    # Phase 28: contract-specific поля (условия конкретного договора)
    'acceptance_term_days', 'penalty_rate', 'contractor_ogrnip_date',
    'repair_request_number',
    'commission_member_1_name', 'commission_member_2_name', 'commission_member_3_name',
    'advance_amount',
    # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
    'warranty_period_days', 'is_retroactive',
    # Phase 29: связь закупки с ТС
    'vehicle_id',
    # SN-UX: адресат служебной записки
    'service_note_to_user_id',
}


# Имена полей с типом DATE/DATETIME — для коэрсии строк в date-объекты в PATCH.
# Фронт шлёт ISO-строки ('2026-05-08'), asyncpg ожидает date()/datetime().
# Полный список из backend/app/models/purchase.py — все Column(Date)/Column(DateTime).
_DATE_FIELDS = {
    "contract_date", "execution_term", "execution_term_changed",
    "delivery_date", "acceptance_doc_date", "payment_doc_date",
    "contract_end_date", "service_start_date", "service_end_date",
    "procurement_planned_date", "service_deadline_date", "prepayment_date",
    # Phase 26-K
    "agreement_date", "order_date",
    # Phase 28
    "contractor_ogrnip_date",
}
_DATETIME_FIELDS = {"submission_deadline", "service_note_at"}


def _coerce_patch_value(field: str, value):
    """Конвертирует ISO-строку в date/datetime для DATE-полей; пустые строки → None."""
    if value == "":
        return None
    if value is None:
        return None
    if field in _DATE_FIELDS and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    if field in _DATETIME_FIELDS and isinstance(value, str):
        try:
            # Поддержка и 'YYYY-MM-DD', и 'YYYY-MM-DDTHH:MM[:SS]'
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return date.fromisoformat(value[:10])
            except Exception:
                return None
    return value


@router.patch("/{pid}")
async def patch_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Not found")
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")

    # Phase 28 B4: нельзя снять ответственного через PATCH
    if "assigned_user_id" in (body or {}):
        val = body["assigned_user_id"]
        if val is None or val == 0:
            raise HTTPException(422, "Нельзя снять ответственного исполнителя")
        target = await db.get(User, val)
        if target is None:
            raise HTTPException(422, f"Пользователь {val} не найден")

    # Opportunistic backfill: первый PATCH (autosave) от user'а закрепляет
    # за ним legacy-закупку без assigned_user_id — иначе после save она опять
    # пропадёт из его OrdersView.
    if p.assigned_user_id is None and "assigned_user_id" not in (body or {}):
        p.assigned_user_id = current_user.id

    # phase26-j-1 (fix): запоминаем contract_id ДО setattr, чтобы sync вызвался
    # только при реальном изменении FK, а не на каждый autosave с тем же contract_id.
    old_contract_id_patch = p.contract_id

    changed: list[str] = []
    for k, v in (body or {}).items():
        if k not in PATCHABLE_FIELDS:
            continue
        if not hasattr(p, k):
            continue
        v = _coerce_patch_value(k, v)
        if getattr(p, k) != v:
            setattr(p, k, v)
            changed.append(k)
            # JSONB колонки: SQLAlchemy не детектирует мутации без flag_modified
            if k == "acceptance_docs":
                flag_modified(p, "acceptance_docs")
    # phase26-j-1 (fix): sync только при ИЗМЕНЕНИИ contract_id, иначе ручные правки
    # contract_number перетираются на каждом autosave (Phase 26 patches шлют contract_id вместе с другими полями).
    if p.contract_id and p.contract_id != old_contract_id_patch:
        await _sync_purchase_from_contract(p, db)
        for f in ("contract_number", "contract_date", "purchase_contract_type"):
            if f not in changed:
                changed.append(f)
    # Phase 26-Z: при установке contractor_id на закупке — проставить во все
    # позиции без указанного контрагента (наследование одним подрядчиком).
    if p.contractor_id and "contractor_id" in changed:
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.contractor import Contractor as _Ctr
        c_row = await db.get(_Ctr, p.contractor_id)
        if c_row:
            upd_q = await db.execute(
                select(_PI).where(_PI.purchase_id == p.id, _PI.contractor_id.is_(None))
            )
            for it in upd_q.scalars().all():
                it.contractor_id = c_row.id
                it.contractor_inn = c_row.inn
                it.contractor_name = c_row.name
    if changed:
        await db.commit()
        await db.refresh(p)
    return {"id": p.id, "changed": changed}


class _SetProductBody(BaseModel):
    product_id: Optional[int] = None  # None — снять привязку


@router.post("/{pid}/items/{item_id}/set-product")
async def set_item_product(
    pid: int,
    item_id: int,
    body: _SetProductBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """27.4-14: точечная запись PurchaseItem.product_id без full PUT.
    Вызывается фронтом сразу после «Добавить в каталог» / выбора товара,
    чтобы привязка пережила F5 без необходимости нажимать общий «Сохранить»."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    if body.product_id is not None:
        prod = await db.get(Product, body.product_id)
        if not prod:
            raise HTTPException(404, "Товар каталога не найден")
        it.product_id = body.product_id
        it.match_confirmed = True
    else:
        it.product_id = None
    await db.commit()
    return {"ok": True, "item_id": item_id, "product_id": it.product_id}


@router.delete("/bulk")
async def bulk_delete_purchases(
    ids: List[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('purchases')),
):
    deleted, failed = [], []
    for pid in ids:
        try:
            result = await db.execute(select(Purchase).where(Purchase.id == pid))
            p = result.scalar_one_or_none()
            if not p:
                failed.append({"id": pid, "reason": "Не найдено"})
                continue
            await db.delete(p)
            await db.flush()
            deleted.append(pid)
        except Exception as e:
            await db.rollback()
            failed.append({"id": pid, "reason": str(e)[:200]})
    if deleted:
        await db.commit()
    return {"deleted": deleted, "failed": failed}


@router.delete("/{pid}")
async def delete_purchase(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    # 27.4-09: авансовый owner может удалить свой отчёт; остальным нужен tab 'purchases'
    from app.auth.permissions import can_manage_purchase
    if not await can_manage_purchase(current_user, p, db):
        raise HTTPException(403, "Нет прав на удаление этой закупки")
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
        .options(selectinload(Purchase.items), selectinload(Purchase.contractor))
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


@router.get("/{pid}/tasks")
async def list_purchase_tasks(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tasks linked to a purchase."""
    from app.models.task import Task
    from app.routers.task_visibility import _enrich_tasks
    from app.schemas.schemas import TaskOut
    result = await db.execute(
        select(Task).where(Task.purchase_id == pid).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    return await _enrich_tasks(list(tasks), db, current_user_id=current_user.id)


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


# ── Purchase members (discussion participants) ───────────────────────────────

def _member_dict(m):
    return {
        "id": m.id,
        "purchase_id": m.purchase_id,
        "user_id": m.user_id,
        "role": m.role,
        "added_by_id": m.added_by_id,
        "username": m.user.username if m.user else "",
        "full_name": m.user.full_name if m.user else None,
        "added_by_name": (m.added_by.full_name or m.added_by.username) if m.added_by else None,
        "consent_pending": bool(getattr(m, "consent_pending", False)),
    }


@router.get("/{pid}/members")
async def list_purchase_members(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember
    result = await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )
    return [_member_dict(m) for m in result.scalars().all()]


@router.post("/{pid}/members")
async def add_purchase_member(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember, PurchaseEvent
    user_id = int(body.get("user_id", 0))
    role = body.get("role", "viewer")

    existing = await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == user_id,
        )
    )
    m = existing.scalar_one_or_none()
    is_new = m is None
    if m:
        m.role = role
    else:
        m = PurchaseMember(
            purchase_id=pid, user_id=user_id, role=role,
            added_by_id=current_user.id, consent_pending=(user_id != current_user.id),
        )
        db.add(m)
    await db.flush()

    u = await db.get(User, user_id)
    ev = PurchaseEvent(
        purchase_id=pid,
        user_id=current_user.id,
        event_type="member_added",
        data={"username": (u.full_name or u.username) if u else str(user_id)},
    )
    db.add(ev)
    await db.commit()
    await db.refresh(m)

    # Notify added user
    if u and u.id != current_user.id and is_new:
        try:
            purchase = await db.get(Purchase, pid)
            if purchase:
                if m.consent_pending:
                    from app.notifications import notify_purchase_consent_required
                    await notify_purchase_consent_required(
                        purchase, u, current_user.full_name or current_user.username
                    )
                else:
                    from app.notifications import notify_purchase_member_added
                    await notify_purchase_member_added(
                        purchase, u, current_user.full_name or current_user.username
                    )
        except Exception as e:
            logger.warning("Member add notify failed: %s", e)

    return _member_dict(m)


@router.delete("/{pid}/members/{user_id}")
async def remove_purchase_member(
    pid: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember, PurchaseEvent
    result = await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == user_id,
        )
    )
    m = result.scalar_one_or_none()
    if m:
        u = await db.get(User, user_id)
        ev = PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="member_removed",
            data={"username": (u.full_name or u.username) if u else str(user_id)},
        )
        db.add(ev)
        await db.delete(m)
        await db.commit()
    return {"ok": True}


# ── Purchase comments (chat) ────────────────────────────────────────────────

@router.get("/{pid}/comments")
async def list_purchase_comments(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    result = await db.execute(
        select(PurchaseComment)
        .where(PurchaseComment.purchase_id == pid)
        .order_by(PurchaseComment.created_at.asc())
    )
    return result.scalars().all()


@router.post("/{pid}/comments")
async def add_purchase_comment(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    import re as _re

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Комментарий не может быть пустым")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    comment = PurchaseComment(
        purchase_id=pid,
        user_id=current_user.id,
        user_name=current_user.full_name or current_user.username,
        text=text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Notify @mentioned users via Telegram
    try:
        from app.notifications import notify_user, _esc, _purchase_url
        mentions = _re.findall(r'@(\S+)', text)
        if mentions:
            all_users = (await db.execute(select(User))).scalars().all()  # superadmin-bypass-ok: @mention lookup for notifications
            clean_text = _re.sub(r'@[A-Za-zА-Яа-яёЁ\s]{2,40}', '', text).strip()
            clean_text = _re.sub(r'\s{2,}', ' ', clean_text) or text
            preview = _esc(clean_text[:150])
            subject = _esc(p.subject or f"Закупка №{p.purchase_number}")
            sender = _esc(current_user.full_name or current_user.username)
            msg = (
                f"💬 <b>Вас упомянули в закупке</b>\n\n"
                f"📌 <b>{subject}</b>\n"
                f"👤 <i>{sender}</i>:\n"
                f"{preview}"
            )
            for u in all_users:
                for m in mentions:
                    if (u.username and m.lower() == u.username.lower()) or \
                       (u.full_name and m.lower() in u.full_name.lower()):
                        if u.id != current_user.id:
                            await notify_user(u, msg,
                                               button_url=_purchase_url(p.id),
                                               button_label="Открыть закупку")
                            break
    except Exception:
        pass

    return comment


@router.delete("/{pid}/comments/{comment_id}")
async def delete_purchase_comment(
    pid: int, comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    c = await db.get(PurchaseComment, comment_id)
    if not c or c.purchase_id != pid:
        raise HTTPException(404, "Комментарий не найден")
    if c.user_id != current_user.id and current_user.role not in ("superadmin", "org_admin", "admin"):
        raise HTTPException(403, "Нельзя удалить чужой комментарий")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{pid}/broadcast")
async def broadcast_from_purchase(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Broadcast from purchase context."""
    from app.models.organization import Organization
    from app.models.department import Department, DepartmentMember
    from app.models.purchase_comment import PurchaseComment
    from app.notifications import notify_user, _esc, _purchase_url

    BROADCAST_ROLES = ("superadmin", "org_admin", "admin", "manager")
    if current_user.role not in BROADCAST_ROLES:
        raise HTTPException(403, "Рассылка доступна только администраторам и менеджерам")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Текст сообщения обязателен")

    scope = body.get("scope", "")
    scope_id = body.get("scope_id")

    q = select(User).where(User.id != current_user.id)  # superadmin-bypass-ok: broadcast notifications, not a user-list endpoint returned to client
    if scope == "department" and scope_id:
        member_uids = select(DepartmentMember.user_id).where(DepartmentMember.department_id == int(scope_id))
        q = q.where(User.id.in_(member_uids))
    elif scope == "organization" and scope_id:
        q = q.where(User.org_id == int(scope_id))
    elif scope == "all":
        org_ids = get_org_filter(current_user)
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
    else:
        raise HTTPException(422, "Укажите scope")

    users = (await db.execute(q)).scalars().all()

    sender_name = current_user.full_name or current_user.username
    subject = _esc(p.subject or f"Закупка №{p.purchase_number}")
    msg = (
        f"📢 <b>Рассылка</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 <i>{_esc(sender_name)}</i>:\n"
        f"{_esc(text)}"
    )

    sent = 0
    for u in users:
        if getattr(u, "telegram_id", None) or getattr(u, "max_chat_id", None):
            await notify_user(u, msg, button_url=_purchase_url(p.id), button_label="Открыть закупку")
            sent += 1

    # Save as comment
    scope_label = {"department": "отделу", "organization": "организации", "all": "всем"}.get(scope, scope)
    db.add(PurchaseComment(
        purchase_id=pid, user_id=current_user.id, user_name=sender_name,
        text=f"[Рассылка {scope_label}] {text}",
    ))
    await db.commit()

    return {"ok": True, "sent": sent, "total_users": len(users)}


@router.post("/{pid}/split")
async def split_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разбить закупку на N дочерних по группам позиций.

    Body: {"groups": [{"column_key": "str", "item_ids": [int, ...]}, ...]}
    - N <= 1 → 400.
    - До status in (contracted, delivered, paid) — разрешено всем, кто имеет доступ.
    - В этих статусах — только ADMIN_ROLES.
    - Наследует subsidy_id, feo_category_id, assigned_user_id, service_note_*, members.
    - Копирует PurchaseItem по item_ids в соответствующие дочерние.
    - Исходная помечается status='split'.
    """
    from app.models.purchase_event import PurchaseMember

    # Load purchase with items
    res = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id == pid)
    )
    purchase = res.scalar_one_or_none()
    if purchase is None:
        raise HTTPException(404, "Закупка не найдена")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        subsidy_res = await db.execute(select(Subsidy).where(Subsidy.id == purchase.subsidy_id))
        subsidy = subsidy_res.scalar_one_or_none()
        if subsidy and subsidy.org_id not in org_ids:
            raise HTTPException(403, "Нет доступа к закупке")

    LOCKED_STATUSES = {"contracted", "delivered", "paid"}
    if purchase.status in LOCKED_STATUSES and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Перераспределять закупку в статусе 'Договор' и далее могут только администраторы")
    if purchase.status == "split":
        raise HTTPException(400, "Закупка уже разбита")

    groups = body.get("groups") or []
    groups = [g for g in groups if g.get("item_ids")]
    if len(groups) < 2:
        raise HTTPException(400, "Разбиение требует минимум 2 непустые группы")

    # Validate all item_ids belong to this purchase and are unique + complete
    own_item_ids = {it.id for it in purchase.items}
    all_supplied_ids: list[int] = []
    for g in groups:
        for iid in g["item_ids"]:
            if iid not in own_item_ids:
                raise HTTPException(400, f"Позиция {iid} не принадлежит закупке {pid}")
            all_supplied_ids.append(iid)
    if len(all_supplied_ids) != len(set(all_supplied_ids)):
        raise HTTPException(400, "Одна позиция указана в нескольких группах")
    if set(all_supplied_ids) != own_item_ids:
        raise HTTPException(400, "Не все позиции распределены по группам")

    # Load members of source
    mem_res = await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )
    source_members = mem_res.scalars().all()

    items_by_id = {it.id: it for it in purchase.items}
    created_ids: list[int] = []

    try:
        for g in groups:
            column_key = (g.get("column_key") or "").strip() or "__uncategorized__"
            display_key = "Не определено" if column_key == "__uncategorized__" else column_key
            group_items = [items_by_id[iid] for iid in g["item_ids"]]
            total = sum(float(it.total_price or 0) for it in group_items)

            base_subject = (purchase.subject or purchase.item_name or "").strip()
            new_subject = f"{base_subject} — {display_key}".strip(" —") if base_subject else display_key

            new_p = Purchase(
                subsidy_id=purchase.subsidy_id,
                feo_category_id=purchase.feo_category_id,
                item_name=purchase.item_name or f"Закупка #{purchase.id}",
                subject=new_subject,
                planned_total_price=total,
                total_nmck=total,
                nmck=total,
                status="wishes" if purchase.status == "wishes" else "planned",
                assigned_user_id=purchase.assigned_user_id,
                service_note_text=purchase.service_note_text,
                service_note_by=purchase.service_note_by,
                parent_purchase_id=purchase.id,
            )
            db.add(new_p)
            await db.flush()
            created_ids.append(new_p.id)

            # Copy items into new purchase
            for src_it in group_items:
                db.add(PurchaseItem(
                    purchase_id=new_p.id,
                    product_id=src_it.product_id,
                    item_name=src_it.item_name,
                    item_type=src_it.item_type,
                    quantity=src_it.quantity,
                    unit=src_it.unit,
                    unit_price=src_it.unit_price,
                    total_price=src_it.total_price,
                    country_origin=src_it.country_origin,
                    feo_planned_item_id=src_it.feo_planned_item_id,
                ))
            # Copy members
            for m in source_members:
                db.add(PurchaseMember(
                    purchase_id=new_p.id,
                    user_id=m.user_id,
                    role=m.role,
                    added_by_id=current_user.id,
                    consent_pending=False,
                ))
            await db.flush()

        # Delete original items (explicit — keeps source row stable with status='split')
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
        purchase.status = "split"
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка разбиения закупки: {e}")

    return {"source_purchase_id": pid, "purchase_ids": created_ids, "count": len(created_ids)}


@router.post("/sync-from-contracts")
async def sync_all_purchases_from_contracts(
    only_mismatched: bool = Query(True, description="Только закупки где denorm-поля расходятся с contract"),
    current_user=Depends(require_action('purchases.edit')),
    db: AsyncSession = Depends(get_db),
):
    """Phase 26-lll: глобальный backfill денормализованных полей purchases из contracts.

    Для каждой purchase с contract_id IS NOT NULL прогоняет
    _sync_purchase_from_contract — выравнивает contract_number / contract_date /
    purchase_contract_type / contractor_id с реальным contracts.*.

    Чинит исторические рассинхронизации до Phase 26-j-1 (sync на save) и до
    Phase 26-k-2 (UPDATE 2 row backfill — недостаточно). Также покрывает баг
    «Контрагент пустой в реестре закупок» — раньше sync не копировал
    contractor_id из contract.
    """
    q = await db.execute(
        select(Purchase).where(Purchase.contract_id.is_not(None))
    )
    purchases_list = q.scalars().all()
    stats = {"total": len(purchases_list), "updated": 0, "skipped_no_contract": 0, "details": []}
    for p in purchases_list:
        before = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        await _sync_purchase_from_contract(p, db)
        after = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        if before != after:
            stats["updated"] += 1
            if len(stats["details"]) < 50:  # cap response size
                stats["details"].append({
                    "purchase_id": p.id,
                    "registry_number": p.registry_number,
                    "contract_id": p.contract_id,
                    "before": {"number": before[0], "date": str(before[1]) if before[1] else None,
                               "type": before[2], "contractor_id": before[3]},
                    "after": {"number": after[0], "date": str(after[1]) if after[1] else None,
                              "type": after[2], "contractor_id": after[3]},
                })
    await db.commit()
    return stats
