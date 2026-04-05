from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, ALL_ROLES, MANAGER_ROLES, ADMIN_ROLES
from app.models.user import User
from app.models.wish import Wish
from app.schemas.wishes import WishCreate, WishUpdate, WishOut, WishReject, WishConvert

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


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
    q = select(Wish)
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
    # Enrich with creator/approver names
    out = []
    for w in wishes:
        d = WishOut.model_validate(w)
        if w.creator:
            d.creator_name = w.creator.full_name or w.creator.username
        if w.approver:
            d.approver_name = w.approver.full_name or w.approver.username
        out.append(d)
    return out
