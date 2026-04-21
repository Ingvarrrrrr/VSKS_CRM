from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.auth.jwt import (
    get_current_user, get_org_filter, require_role,
    ALL_ROLES, MANAGER_ROLES, ADMIN_ROLES,
)
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.wishes import WishCreate, WishUpdate, WishOut, WishReject, WishConvert, WishItemPatch
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_event import PurchaseMember
from app.routers.purchase_members import _create_assignment_chat_room
from app.models.chat_message import ChatMessage

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


def _enrich(w: Wish) -> WishOut:
    """Convert Wish ORM object to WishOut, filling computed name fields."""
    d = WishOut.model_validate(w)
    if w.creator:
        d.creator_name = w.creator.full_name or w.creator.username
    if w.approver:
        d.approver_name = w.approver.full_name or w.approver.username
    if w.subsidy:
        d.subsidy_name = w.subsidy.name
    if w.assignee:
        d.assignee_name = w.assignee.full_name or w.assignee.username
    return d


async def _load_wish(wish_id: int, db: AsyncSession) -> Wish:
    """Load wish with all relationships."""
    result = await db.execute(
        select(Wish)
        .options(
            selectinload(Wish.creator),
            selectinload(Wish.approver),
            selectinload(Wish.assignee),
            selectinload(Wish.subsidy),
            selectinload(Wish.items),
        )
        .where(Wish.id == wish_id)
    )
    wish = result.scalar_one_or_none()
    if wish is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return wish


@router.get("/", response_model=list[WishOut])
async def list_wishes(
    status: Optional[str] = None,
    mine_only: bool = False,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List wishes. Employee sees only own; manager/admin sees all in org."""
    org_ids = get_org_filter(current_user)
    q = select(Wish).options(
        selectinload(Wish.creator),
        selectinload(Wish.approver),
        selectinload(Wish.assignee),
        selectinload(Wish.subsidy),
        selectinload(Wish.items),
    )
    if org_ids is not None:
        q = q.where(Wish.org_id.in_(org_ids))
    # Employee: always own only
    if current_user.role == 'employee' or mine_only:
        q = q.where(Wish.created_by == current_user.id)
    if status:
        q = q.where(Wish.status == status)
    q = q.order_by(Wish.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    wishes = result.scalars().all()
    return [_enrich(w) for w in wishes]


@router.post("/", response_model=WishOut, status_code=201)
async def create_wish(
    body: WishCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new wish (all roles)."""
    org_ids = get_org_filter(current_user)
    org_id = org_ids[0] if org_ids else current_user.org_id

    wish = Wish(
        org_id=org_id,
        title=body.title,
        category=body.category,
        description=body.description,
        quantity=body.quantity,
        unit=body.unit,
        estimated_price=body.estimated_price,
        link=body.link,
        priority=body.priority,
        desired_date=body.desired_date,
        justification=body.justification,
        subsidy_id=body.subsidy_id,
        feo_category_id=body.feo_category_id,
        assigned_to=body.assigned_to,
        status="draft",
        created_by=current_user.id,
    )
    db.add(wish)
    await db.flush()

    if body.items:
        for item_data in body.items:
            wi = WishItem(
                wish_id=wish.id,
                item_name=item_data.get('item_name', ''),
                item_type=item_data.get('item_type', 'товар'),
                quantity=item_data.get('quantity', 1),
                unit=item_data.get('unit', 'шт'),
                unit_price=item_data.get('unit_price', 0),
                total_price=item_data.get('total_price', 0),
                country_origin=item_data.get('country_origin', 'Россия'),
            )
            db.add(wi)
        await db.flush()

    await db.commit()
    wish = await _load_wish(wish.id, db)
    return _enrich(wish)


@router.put("/{wish_id}", response_model=WishOut)
async def update_wish(
    wish_id: int,
    body: WishUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a draft wish (creator only)."""
    wish = await _load_wish(wish_id, db)

    if wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if wish.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Можно редактировать только черновик или отклонённую заявку")

    update_data = body.model_dump(exclude_none=True, exclude={'items'})
    for field, value in update_data.items():
        setattr(wish, field, value)

    if body.items is not None:
        await db.execute(delete(WishItem).where(WishItem.wish_id == wish.id))
        for item_data in body.items:
            wi = WishItem(
                wish_id=wish.id,
                item_name=item_data.get('item_name', ''),
                item_type=item_data.get('item_type', 'товар'),
                quantity=item_data.get('quantity', 1),
                unit=item_data.get('unit', 'шт'),
                unit_price=item_data.get('unit_price', 0),
                total_price=item_data.get('total_price', 0),
                country_origin=item_data.get('country_origin', 'Россия'),
            )
            db.add(wi)
        await db.flush()

    await db.commit()
    wish = await _load_wish(wish_id, db)
    return _enrich(wish)


@router.post("/{wish_id}/submit", response_model=WishOut)
async def submit_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft wish for approval (creator only, draft/rejected -> submitted)."""
    wish = await _load_wish(wish_id, db)

    if wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Только автор может подать заявку")
    if wish.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'draft' или 'rejected'")

    wish.status = "submitted"
    await db.flush()

    # Notify approver
    if wish.assigned_to and wish.assigned_to != current_user.id:
        org_id = getattr(current_user, 'org_id', None) or wish.org_id
        room_id = await _create_assignment_chat_room(
            db, current_user.id, wish.assigned_to,
            org_id,
            f"Заявка №{wish.id}: {wish.title or 'без названия'}",
        )
        db.add(ChatMessage(
            room_id=room_id,
            sender_id=current_user.id,
            content=f"📋 Заявка отправлена на согласование: {wish.title or '(без названия)'}",
        ))
        await db.flush()

    await db.commit()
    wish = await _load_wish(wish_id, db)
    return _enrich(wish)


@router.post("/{wish_id}/approve", response_model=WishOut)
async def approve_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    """Approve a submitted wish (manager+ roles, submitted -> approved)."""
    wish = await _load_wish(wish_id, db)

    if wish.status != "submitted":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'submitted'")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    wish.status = "approved"
    wish.approved_by = current_user.id
    await db.commit()
    await db.refresh(wish)
    wish = await _load_wish(wish_id, db)
    return _enrich(wish)


@router.post("/{wish_id}/reject", response_model=WishOut)
async def reject_wish(
    wish_id: int,
    body: WishReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    """Reject a submitted wish with reason (manager+ roles, submitted -> rejected)."""
    wish = await _load_wish(wish_id, db)

    if wish.status != "submitted":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'submitted'")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    wish.status = "rejected"
    wish.rejection_reason = body.rejection_reason
    await db.commit()
    await db.refresh(wish)
    wish = await _load_wish(wish_id, db)
    return _enrich(wish)


@router.post("/{wish_id}/convert")
async def convert_wish(
    wish_id: int,
    body: WishConvert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Convert an approved wish to a purchase (org_admin+, approved -> converted)."""
    from app.models.purchase import Purchase

    wish = await _load_wish(wish_id, db)

    if wish.status != "approved":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'approved'")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    # Create Purchase inline (D-23)
    p = Purchase(
        subsidy_id=body.subsidy_id,  # nullable OK — can be assigned later
        item_name=wish.title,
        subject=wish.title,
        planned_quantity=body.approved_quantity or wish.quantity,
        planned_total_price=body.approved_price or wish.estimated_price,
        status="wishes",  # default purchase status for wish-origin purchases
        service_note_text=wish.justification,
        service_note_by=wish.created_by,
    )
    db.add(p)
    await db.flush()  # get p.id before writing back to wish

    wish.purchase_id = p.id
    wish.status = "converted"
    wish.approved_by = current_user.id
    await db.commit()

    return {"wish_id": wish.id, "purchase_id": p.id, "status": "converted"}


@router.delete("/{wish_id}", status_code=204)
async def delete_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a draft wish (creator only)."""
    wish = await _load_wish(wish_id, db)

    if wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Только автор может удалить заявку")
    if wish.status != "draft":
        raise HTTPException(status_code=400, detail="Можно удалить только черновик")

    await db.delete(wish)
    await db.commit()


@router.patch("/{wish_id}/items/{item_id}")
async def patch_wish_item(
    wish_id: int,
    item_id: int,
    body: WishItemPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """D-04: Drag-drop target update. Scoped to wish — cannot move items between wishes.

    Returns 409 if wish is approved (read-only).
    Returns 404 if item does not belong to wish_id.
    """
    wish = await _load_wish(wish_id, db)
    if wish.status not in ("draft", "submitted"):
        raise HTTPException(status_code=409, detail="Заявка уже одобрена — редактирование запрещено")
    # Find item BELONGING TO THIS WISH
    item = next((i for i in wish.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена в данной заявке")
    # body.target_column_key may be None (clear) or a non-empty string (override)
    item.target_column_key = body.target_column_key
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "target_column_key": item.target_column_key}


@router.post("/{wish_id}/approve-distribution")
async def approve_distribution(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """D-05/D-06: Atomic all-or-nothing approve. Creates N purchases (status='wishes'),
    one per distinct resolved column key group, copies wish items to purchase_items,
    creates assignment chat rooms, then marks wish.status='approved'.

    Rolls back entirely on any failure — zero purchases persist if any step fails.
    Returns 400 if wish is already approved.
    """
    from sqlalchemy.orm import selectinload as sil

    wish = await _load_wish(wish_id, db)
    if wish.status == "approved":
        raise HTTPException(status_code=400, detail="Заявка уже одобрена")
    if wish.status not in ("draft", "submitted"):
        raise HTTPException(status_code=400, detail=f"Нельзя одобрить заявку в статусе {wish.status}")
    if not wish.items:
        raise HTTPException(status_code=400, detail="Заявка пустая — нечего одобрять")

    # Preload wish items with products for category resolution
    res = await db.execute(
        select(WishItem)
        .options(sil(WishItem.product))
        .where(WishItem.wish_id == wish_id)
    )
    items_full = res.scalars().all()

    def _resolve_key(it: WishItem) -> str:
        """target_column_key → product.category → '__uncategorized__'"""
        if it.target_column_key:
            return it.target_column_key
        if it.product_id and it.product and it.product.category:
            return it.product.category
        return "__uncategorized__"

    groups: dict[str, list] = {}
    for it in items_full:
        groups.setdefault(_resolve_key(it), []).append(it)

    if not groups:
        raise HTTPException(status_code=400, detail="Нет позиций для распределения")

    created_purchase_ids: list[int] = []
    try:
        for column_key, items_in_col in groups.items():
            total_nmck = sum(float(i.total_price or 0) for i in items_in_col)
            display_key = "Не определено" if column_key == "__uncategorized__" else column_key
            p = Purchase(
                subsidy_id=wish.subsidy_id,
                feo_category_id=wish.feo_category_id,
                item_name=(wish.title or "").strip() or f"Заявка #{wish.id}",
                subject=f"{(wish.title or '').strip() or f'Заявка #{wish.id}'} — {display_key}",
                planned_total_price=total_nmck,
                total_nmck=total_nmck,
                nmck=total_nmck,
                status="wishes",
                assigned_user_id=wish.assigned_to,
                service_note_text=wish.justification,
                service_note_by=wish.created_by,
            )
            db.add(p)
            await db.flush()  # get p.id
            created_purchase_ids.append(p.id)

            for wi in items_in_col:
                pi = PurchaseItem(
                    purchase_id=p.id,
                    product_id=wi.product_id,
                    item_name=wi.item_name,
                    item_type=wi.item_type,
                    quantity=wi.quantity,
                    unit=wi.unit,
                    unit_price=wi.unit_price,
                    total_price=wi.total_price,
                    country_origin=wi.country_origin,
                )
                db.add(pi)
            await db.flush()

            # Add wish author as purchase member (viewer role) so they can see the purchase
            if wish.created_by and wish.created_by != current_user.id:
                db.add(PurchaseMember(
                    purchase_id=p.id,
                    user_id=wish.created_by,
                    role="viewer",
                    added_by_id=current_user.id,
                    consent_pending=False,
                ))
            # Also add assigned_to as member if different from author and current_user
            if wish.assigned_to and wish.assigned_to not in (wish.created_by, current_user.id):
                db.add(PurchaseMember(
                    purchase_id=p.id,
                    user_id=wish.assigned_to,
                    role="viewer",
                    added_by_id=current_user.id,
                    consent_pending=False,
                ))
            await db.flush()

            # Create chat room per purchase if there is an assignee different from current user
            if wish.assigned_to and wish.assigned_to != current_user.id:
                org_id = getattr(current_user, 'org_id', None) or wish.org_id
                await _create_assignment_chat_room(
                    db, current_user.id, wish.assigned_to,
                    org_id,
                    f"Закупка: {p.subject}",
                )

        wish.status = "approved"
        wish.approved_by = current_user.id
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании закупок — откат: {e}")

    return {
        "wish_id": wish.id,
        "purchase_ids": created_purchase_ids,
        "count": len(created_purchase_ids),
        "status": "approved",
    }
