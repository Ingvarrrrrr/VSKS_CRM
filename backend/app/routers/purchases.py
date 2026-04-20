from fastapi import APIRouter, Depends, HTTPException, Query, Body
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
from app.models.user import User
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date
from app.models.user_hierarchy import UserHierarchy
router = APIRouter(prefix="/api/purchases", tags=["purchases"])


# Status workflow
STATUS_ORDER = ["wishes", "plan_schedule", "confirmed", "work_in_progress", "contracted", "ordered", "delivered", "paid"]
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform")


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
        country_origin=item.country_origin,
        product_name=product_name,
        product_photo_url=product_photo_url,
        product_description=product_description,
        product_description_44fz=product_description_44fz,
    )


def _purchase_to_full(p: Purchase, contractors: dict, subsidies: dict, allocations: list | None = None) -> PurchaseOutFull:
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
    return PurchaseOutFull(
        **data,
        items=items,
        files=files,
        contractor_name=contractors.get(p.contractor_id),
        feo_category_name=p.feo_category.name if p.feo_category else None,
        subsidy_name=subsidies.get(p.subsidy_id),
        event_name=p.event.name if p.event else None,
        subsidy_allocations=alloc_out,
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
    limit: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    from app.models.purchase_event import PurchaseMember
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
    # Visibility by hierarchy position (business rule, not title):
    # - superadmin / account_owner: SaaS-level, see everything in tenant (already
    #   scoped by get_org_filter above; no extra user-level filter).
    # - employee: sees ONLY purchases where they are the executor OR a participant
    #   (PurchaseMember); no one else's rows, even if they share an org.
    # - everyone else (manager, admin, org_admin): sees own + recursive subordinates
    #   + managed-department members + managed-organization members (by hierarchy).
    #   Being 'admin' is a system-privilege role (delete/export/settings), not a
    #   visibility role — an admin without subordinates sees only their own stuff.
    # Chat participation (purchase-linked rooms) — a user can join a purchase
    # discussion via @mention / consent, and that also means "I participate".
    from app.models.chat_room import ChatRoom, ChatParticipant
    chat_pids_me = (
        select(ChatRoom.entity_id)
        .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
        .where(
            ChatParticipant.user_id == current_user.id,
            ChatRoom.entity_type == 'purchase',
            ChatRoom.entity_id.isnot(None),
        )
    )

    if current_user.role == 'employee':
        member_pids = select(PurchaseMember.purchase_id).where(PurchaseMember.user_id == current_user.id)
        q = q.where(
            (Purchase.assigned_user_id == current_user.id) |
            (Purchase.id.in_(member_pids)) |
            (Purchase.id.in_(chat_pids_me))
        )
    elif current_user.role not in ('superadmin', 'account_owner'):
        # manager / admin / org_admin — all follow the same hierarchy rule.
        from app.models.user_hierarchy import UserHierarchy
        from app.models.manager_organization import ManagerOrganization
        from app.models.manager_department import ManagerDepartment
        from app.models.department import DepartmentMember

        visible_user_ids = {current_user.id}

        # Direct subordinates
        sub_res = await db.execute(
            select(UserHierarchy.subordinate_id).where(UserHierarchy.manager_id == current_user.id)
        )
        visible_user_ids.update(r[0] for r in sub_res.all())

        # Members of managed depts
        md_res = await db.execute(
            select(ManagerDepartment.dept_id).where(ManagerDepartment.manager_user_id == current_user.id)
        )
        managed_dept_ids = [r[0] for r in md_res.all()]
        if managed_dept_ids:
            dm_res = await db.execute(
                select(DepartmentMember.user_id).where(DepartmentMember.department_id.in_(managed_dept_ids))
            )
            visible_user_ids.update(r[0] for r in dm_res.all())

        # Members of managed orgs
        mo_res = await db.execute(
            select(ManagerOrganization.org_id).where(ManagerOrganization.manager_user_id == current_user.id)
        )
        managed_org_ids = [r[0] for r in mo_res.all()]
        if managed_org_ids:
            org_users = await db.execute(select(User.id).where(User.org_id.in_(managed_org_ids)))
            visible_user_ids.update(r[0] for r in org_users.all())

        # Filter: assigned to visible user OR purchase member OR chat-room participant.
        # NOTE: intentionally dropped the "assigned_user_id IS NULL" OR-branch — previously
        # every unassigned purchase leaked to every non-superadmin role, defeating the
        # hierarchy rule. Unassigned purchases are now visible only via participation.
        member_pids = select(PurchaseMember.purchase_id).where(PurchaseMember.user_id.in_(visible_user_ids))
        q = q.where(
            (Purchase.assigned_user_id.in_(visible_user_ids)) |
            (Purchase.id.in_(member_pids)) |
            (Purchase.id.in_(chat_pids_me))
        )
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
            selectinload(Purchase.event),
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
    alloc_r = await db.execute(
        select(PurchaseSubsidyAllocation)
        .options(selectinload(PurchaseSubsidyAllocation.subsidy))
        .where(PurchaseSubsidyAllocation.purchase_id == pid)
    )
    allocations = alloc_r.scalars().all()
    return _purchase_to_full(p, contractors, subsidies, allocations=allocations)


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
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            from app.models.product import Product as _Prod
            existing = (await db.execute(
                select(_Prod).where(_Prod.name == d["item_name"].strip()).limit(1)
            )).scalar_one_or_none()
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = _Prod(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=get_single_org_id(current_user) or current_user.org_id,
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


@router.put("/{pid}", response_model=PurchaseOut)
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
    # Employees can save any purchase they have access to (org-level access checked at list level)
    if current_user.role not in MANAGER_ROLES and current_user.role not in ("employee",):
        raise HTTPException(403, "Insufficient permissions")
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    items_sum = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

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
        await _check_budget(data.subsidy_id, budget_amount or data.planned_total_price, pid, db)

    # If contract_id or type changed, reset seq so it gets re-assigned
    old_contract_id = p.contract_id
    old_type = p.purchase_contract_type
    for k, v in data.model_dump(exclude={"items", "subsidy_allocations"}, exclude_unset=True).items():
        # Don't overwrite frozen total_nmck
        if is_contracted and k in ("total_nmck", "planned_total_price"):
            continue
        setattr(p, k, v)

    # Contract price: for single purchases = sum of current item prices
    is_single = not p.purchase_contract_type or p.purchase_contract_type == "single"
    if is_single and items_sum:
        p.contract_price = items_sum
    if (p.contract_id != old_contract_id or p.purchase_contract_type != old_type) and data.framework_seq is None:
        p.framework_seq = None  # force re-assignment below
    await _assign_framework_seq(p, db, exclude_id=pid)

    # Replace items (auto-link to catalog if product_id is missing)
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            # Try to find existing product by exact name
            from app.models.product import Product as _Prod
            existing = (await db.execute(
                select(_Prod).where(_Prod.name == d["item_name"].strip()).limit(1)
            )).scalar_one_or_none()
            if existing:
                d["product_id"] = existing.id
            else:
                # Auto-create product in catalog
                new_prod = _Prod(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=get_single_org_id(current_user) or current_user.org_id,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=pid, **d)
        db.add(item)

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

    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/bulk")
async def bulk_delete_purchases(
    ids: List[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
            selectinload(Purchase.event),
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

    # Catalog guard: warn but don't block (except advance reports)
    # Previously blocked status transition — now just logs a warning
    if target_status == "confirmed" and getattr(p, 'purchase_method', None) != "advance":
        unmatched = [i for i in (p.items or []) if not i.product_id]
        if unmatched:
            import logging
            logging.getLogger(__name__).warning(
                "Purchase %s has %d items not linked to catalog", pid, len(unmatched)
            )

    # Field guards for specific target statuses
    if target_status in TRANSITION_REQUIRED:
        # acceptance_docs JSONB overrides legacy single fields
        has_acceptance_docs = bool(p.acceptance_docs and len(p.acceptance_docs) > 0 and any(d.get("name") for d in p.acceptance_docs))
        required_fields = TRANSITION_REQUIRED[target_status]
        if has_acceptance_docs and target_status == "delivered":
            required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        missing = [
            f for f in required_fields
            if not getattr(p, f, None)
        ]
        if missing:
            labels = {
                "contract_number": "Номер договора",
                "contract_date": "Дата договора",
                "acceptance_doc_name": "Наименование закрывающего документа",
                "acceptance_doc_date": "Дата закрывающего документа",
                "acceptance_doc_number": "Номер закрывающего документа",
                "acceptance_doc_amount": "Сумма закрывающего документа",
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

    # Auto-create/link contract record when moving to contracted status
    if target_status == "contracted":
        await ensure_contract_linked(p, db)

    await db.commit()

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

    # Notify purchase members + linked task assignees about status change
    try:
        from app.notifications import notify_purchase_status_changed
        from app.models.purchase_event import PurchaseMember
        from app.models.task import Task, TaskAssignee

        notify_user_ids: set[int] = set()
        notify_users = []

        # 1. Purchase members
        members_r = await db.execute(
            select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
        )
        for m in members_r.scalars().all():
            if m.user_id != current_user.id:
                notify_user_ids.add(m.user_id)

        # 2. Assigned user of purchase
        if p.assigned_user_id and p.assigned_user_id != current_user.id:
            notify_user_ids.add(p.assigned_user_id)

        # 3. All assignees of tasks linked to this purchase
        linked_tasks_r = await db.execute(
            select(Task.id).where(Task.purchase_id == pid)
        )
        linked_task_ids = [r[0] for r in linked_tasks_r.all()]
        if linked_task_ids:
            ta_r = await db.execute(
                select(TaskAssignee.user_id).where(
                    TaskAssignee.task_id.in_(linked_task_ids)
                )
            )
            for r in ta_r.all():
                if r[0] != current_user.id:
                    notify_user_ids.add(r[0])

        # Load user objects
        for uid in notify_user_ids:
            u = await db.get(User, uid)
            if u:
                notify_users.append(u)

        if notify_users:
            await notify_purchase_status_changed(
                p, current_user.full_name or current_user.username,
                target_status, notify_users
            )
    except Exception:
        pass

    # Re-fetch with eager loads after commit
    result2 = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result2.scalar_one()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.post("/{pid}/convert-to-order", response_model=PurchaseOutFull)
async def convert_service_note_to_order(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """Конвертировать служебную записку на выдачу в закупку (меняет purchase_basis на plan_schedule)."""
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if p.purchase_basis != 'service_note':
        raise HTTPException(422, "Конвертация доступна только для служебных записок")
    p.purchase_basis = 'plan_schedule'
    await db.commit()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.get("/{pid}/tasks")
async def list_purchase_tasks(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tasks linked to a purchase."""
    from app.models.task import Task
    from app.routers.tasks import _enrich_tasks
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
            all_users = (await db.execute(select(User))).scalars().all()
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

    q = select(User).where(User.id != current_user.id)
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
