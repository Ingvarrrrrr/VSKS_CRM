from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
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
from app.schemas.wishes import WishCreate, WishUpdate, WishOut, WishReject, WishConvert

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


def _enrich(w: Wish) -> WishOut:
    """Convert Wish ORM object to WishOut, filling computed name fields."""
    d = WishOut.model_validate(w)
    if w.creator:
        d.creator_name = w.creator.full_name or w.creator.username
    if w.approver:
        d.approver_name = w.approver.full_name or w.approver.username
    return d


async def _load_wish(wish_id: int, db: AsyncSession) -> Wish:
    """Load wish with creator and approver relationships."""
    result = await db.execute(
        select(Wish)
        .options(selectinload(Wish.creator), selectinload(Wish.approver))
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
    q = select(Wish).options(selectinload(Wish.creator), selectinload(Wish.approver))
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
        description=body.description,
        quantity=body.quantity,
        unit=body.unit,
        estimated_price=body.estimated_price,
        justification=body.justification,
        status="draft",
        created_by=current_user.id,
    )
    db.add(wish)
    await db.commit()
    await db.refresh(wish)
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
    if wish.status != "draft":
        raise HTTPException(status_code=400, detail="Можно редактировать только черновик")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(wish, field, value)

    await db.commit()
    await db.refresh(wish)
    wish = await _load_wish(wish_id, db)
    return _enrich(wish)


@router.post("/{wish_id}/submit", response_model=WishOut)
async def submit_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft wish for approval (creator only, draft -> submitted)."""
    wish = await _load_wish(wish_id, db)

    if wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Только автор может подать заявку")
    if wish.status != "draft":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'draft'")

    wish.status = "submitted"
    await db.commit()
    await db.refresh(wish)
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
