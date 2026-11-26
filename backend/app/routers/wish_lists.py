from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids, get_visible_user_ids, build_visibility_clause
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_member import WishMember
from app.schemas.wishes import WishOut
from app.services.wish_tabs import wish_tab_statuses
from app.routers import wishes as wishes_core
from app.services.wish_filters import apply_wish_filters

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


async def _build_wishes_query(
    q,
    current_user: User,
    db: AsyncSession,
    *,
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    creator_ids: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    assigned_to_ids: Optional[str] = None,
    subsidy_id: Optional[int] = None,
    subsidy_ids: Optional[str] = None,
    org_id: Optional[int] = None,
    org_ids: Optional[str] = None,
    account_org_id: Optional[int] = None,
    account_org_ids: Optional[str] = None,
    wish_types: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
):
    """Общая видимость + доп. фильтры для GET /wishes/ и GET /wishes/counts."""
    org_ids_filter = get_org_filter(current_user)
    vis = await get_visible_subsidy_ids(current_user, db, "wishes")
    if vis is not None:
        null_branch = (
            and_(Wish.subsidy_id.is_(None), Wish.org_id.in_(org_ids_filter))
            if org_ids_filter is not None
            else Wish.subsidy_id.is_(None)
        )
        q = q.where(or_(Wish.subsidy_id.in_(vis), null_branch))
    elif org_ids_filter is not None:
        q = q.where(Wish.org_id.in_(org_ids_filter))

    member_res = await db.execute(
        select(WishMember.wish_id).where(WishMember.user_id == current_user.id)
    )
    member_wish_ids = {r[0] for r in member_res.all()}

    if assigned_to_me:
        from app.models.wish_approval import WishApproval
        appr_res = await db.execute(
            select(WishApproval.wish_id).where(WishApproval.user_id == current_user.id)
        )
        appr_wish_ids = {r[0] for r in appr_res.all()}
        if appr_wish_ids:
            q = q.where(or_(Wish.assigned_to == current_user.id, Wish.id.in_(appr_wish_ids)))
        else:
            q = q.where(Wish.assigned_to == current_user.id)
    elif mine_only or current_user.role == 'employee':
        base_cond = Wish.created_by == current_user.id
        if member_wish_ids:
            q = q.where(or_(base_cond, Wish.id.in_(member_wish_ids)))
        else:
            q = q.where(base_cond)
    elif subordinates_only:
        visible_uids = await get_visible_user_ids(current_user, db)
        if visible_uids is not None:
            sub_ids = set(visible_uids) | {current_user.id}
            q = q.where(Wish.created_by.in_(sub_ids))
    else:
        clause = await build_visibility_clause(current_user, db, 'wish')
        if clause is not None:
            if member_wish_ids:
                q = q.where(or_(clause, Wish.id.in_(member_wish_ids)))
            else:
                q = q.where(clause)

    # Применяем фильтры через единый хелпер (Правило №6)
    q = await apply_wish_filters(
        q, db,
        creator_id=creator_id, creator_ids=creator_ids,
        assigned_to_id=assigned_to_id, assigned_to_ids=assigned_to_ids,
        subsidy_id=subsidy_id, subsidy_ids=subsidy_ids,
        org_id=org_id, org_ids=org_ids,
        account_org_id=account_org_id, account_org_ids=account_org_ids,
        wish_types=wish_types,
    )

    if created_from is not None:
        q = q.where(func.date(Wish.created_at) >= created_from)
    if created_to is not None:
        q = q.where(func.date(Wish.created_at) <= created_to)
    if deadline_from is not None:
        q = q.where(Wish.desired_date >= deadline_from)
    if deadline_to is not None:
        q = q.where(Wish.desired_date <= deadline_to)

    return q


@router.get("/counts")
async def wish_tab_counts(
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    creator_ids: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    assigned_to_ids: Optional[str] = None,
    subsidy_id: Optional[int] = None,
    subsidy_ids: Optional[str] = None,
    org_id: Optional[int] = None,
    org_ids: Optional[str] = None,
    account_org_id: Optional[int] = None,
    account_org_ids: Optional[str] = None,
    wish_types: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Счётчики вкладок заявок с учётом фильтров."""
    q = await _build_wishes_query(
        select(Wish.status, func.count(Wish.id)),
        current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, creator_ids=creator_ids,
        assigned_to_id=assigned_to_id, assigned_to_ids=assigned_to_ids,
        subsidy_id=subsidy_id, subsidy_ids=subsidy_ids,
        org_id=org_id, org_ids=org_ids,
        account_org_id=account_org_id, account_org_ids=account_org_ids,
        wish_types=wish_types,
        created_from=created_from, created_to=created_to,
        deadline_from=deadline_from, deadline_to=deadline_to,
    )
    q = q.group_by(Wish.status)
    result = await db.execute(q)
    exact_counts: dict[str, int] = {row_status: cnt for row_status, cnt in result.all()}
    return {
        tab: sum(exact_counts.get(s, 0) for s in statuses)
        for tab, statuses in WISH_TAB_STATUS_SETS.items()
    }


@router.get("/standalone-advances")
async def list_standalone_advances_endpoint(
    subsidy_id: Optional[int] = None,
    subsidy_ids: Optional[str] = None,
    org_id: Optional[int] = None,
    org_ids: Optional[str] = None,
    account_org_id: Optional[int] = None,
    account_org_ids: Optional[str] = None,
    creator_id: Optional[int] = None,
    creator_ids: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    assigned_to_ids: Optional[str] = None,
    mine_only: bool = False,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Авансовые отчёты (Purchase.purchase_method='advance') БЕЗ заявки-компаньона."""
    from app.services.standalone_advances import list_standalone_advances
    # Передаем списковые параметры в list_standalone_advances если потребуется, 
    # либо используем одиночные (или расширим список параметров).
    rows = await list_standalone_advances(
        db, current_user,
        subsidy_id=subsidy_id, org_id=org_id, account_org_id=account_org_id,
        creator_id=creator_id, assigned_to_id=assigned_to_id,
        mine_only=mine_only, search=search,
    )
    return [
        {
            "id": r.id,
            "purchase_id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "is_advance": True,
            "registry_number": r.registry_number,
            "subsidy_id": r.subsidy_id,
            "subsidy_name": r.subsidy_name,
            "org_id": r.org_id,
            "reimbursement_user_id": r.reimbursement_user_id,
            "reimbursement_user_name": r.reimbursement_user_name,
            "assigned_user_id": r.assigned_user_id,
            "assigned_user_name": r.assigned_user_name,
            "status": r.status,
            "amount": r.amount,
        }
        for r in rows
    ]


@router.get("/", response_model=list[WishOut])
async def list_wishes(
    status: Optional[str] = None,
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    creator_ids: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    assigned_to_ids: Optional[str] = None,
    subsidy_id: Optional[int] = None,
    subsidy_ids: Optional[str] = None,
    org_id: Optional[int] = None,
    org_ids: Optional[str] = None,
    account_org_id: Optional[int] = None,
    account_org_ids: Optional[str] = None,
    wish_types: Optional[str] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = Query(None, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List wishes with unified visibility."""
    q = select(Wish).options(
        selectinload(Wish.creator),
        selectinload(Wish.approver),
        selectinload(Wish.assignee),
        selectinload(Wish.subsidy),
        selectinload(Wish.event),
        selectinload(Wish.executor),
        selectinload(Wish.items).selectinload(WishItem.planned_item),
        selectinload(Wish.stopped_by_user),
        selectinload(Wish.contractor),
        selectinload(Wish.rejected_by_user),
        selectinload(Wish.tz_waived_by_user),
    )
    q = await _build_wishes_query(
        q, current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, creator_ids=creator_ids,
        assigned_to_id=assigned_to_id, assigned_to_ids=assigned_to_ids,
        subsidy_id=subsidy_id, subsidy_ids=subsidy_ids,
        org_id=org_id, org_ids=org_ids,
        account_org_id=account_org_id, account_org_ids=account_org_ids,
        wish_types=wish_types,
        created_from=created_from, created_to=created_to,
        deadline_from=deadline_from, deadline_to=deadline_to,
    )

    if status and status != 'all':
        q = q.where(Wish.status.in_(wish_tab_statuses(status)))
    elif status == 'all':
        pass
    else:
        q = q.where(Wish.status != 'converted')
    q = q.order_by(Wish.created_at.desc()).offset(skip)
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    wishes = result.scalars().all()

    wish_ids = [w.id for w in wishes]
    unseen_map: dict[int, list[str]] = {}
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        unseen_map = await _get_unseen_map(db, 'wish', wish_ids, current_user.id)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen wish map failed: %s", _exc)

    members_map: dict[int, list[str]] = {}
    approvers_map: dict[int, list[str]] = {}
    purchases_map: dict[int, list[int]] = {}
    if wish_ids:
        mres = await db.execute(
            select(WishMember.wish_id, User.full_name, User.username)
            .join(User, User.id == WishMember.user_id)
            .where(WishMember.wish_id.in_(wish_ids))
        )
        for m_wid, m_fn, m_un in mres.all():
            members_map.setdefault(m_wid, []).append(m_fn or m_un)

        from app.models.wish_approval import WishApproval
        ares = await db.execute(
            select(WishApproval.wish_id, User.full_name, User.username)
            .join(User, User.id == WishApproval.user_id)
            .where(WishApproval.wish_id.in_(wish_ids))
            .order_by(WishApproval.wish_id, WishApproval.order_num)
        )
        for a_wid, a_fn, a_un in ares.all():
            approvers_map.setdefault(a_wid, []).append(a_fn or a_un)

        pres = await db.execute(
            select(Purchase.wish_id, Purchase.id)
            .where(Purchase.wish_id.in_(wish_ids))
            .order_by(Purchase.id)
        )
        for p_wid, p_id in pres.all():
            purchases_map.setdefault(p_wid, []).append(p_id)

    purchase_summaries_map = await wishes_core._wish_purchase_summaries_map(wish_ids, db)

    items_total_map: dict[int, Decimal] = {}
    items_count_map: dict[int, int] = {}
    if wish_ids:
        itres = await db.execute(
            select(
                WishItem.wish_id,
                func.coalesce(func.sum(WishItem.total_price), 0),
                func.count(WishItem.id),
            )
            .where(WishItem.wish_id.in_(wish_ids))
            .group_by(WishItem.wish_id)
        )
        for wid, total, cnt in itres.all():
            items_total_map[wid] = total
            items_count_map[wid] = cnt

    out_list = []
    for w in wishes:
        enriched = wishes_core._enrich(w)
        enriched.member_names = members_map.get(w.id, [])
        enriched.approver_names = approvers_map.get(w.id, [])
        enriched.purchase_ids = purchases_map.get(w.id, [])
        enriched.purchases = purchase_summaries_map.get(w.id, [])
        enriched.items_total = items_total_map.get(w.id, Decimal("0"))
        enriched.items_count = items_count_map.get(w.id, 0)
        _unseen = unseen_map.get(w.id, [])
        enriched.unseen_fields = _unseen
        enriched.unseen_changes_count = len(_unseen)
        out_list.append(enriched)
    return out_list
