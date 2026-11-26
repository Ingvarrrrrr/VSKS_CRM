from typing import Optional
from sqlalchemy import or_, select
from app.models.wish import Wish
from app.models.organization import Organization


def _parse_id_list(val: Optional[str]) -> Optional[list[int]]:
    """Парсит строку со списком ID через запятую или одиночный/список."""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        res = []
        for x in val:
            if x is not None:
                try:
                    res.append(int(x))
                except (ValueError, TypeError):
                    pass
        return res if res else None
    
    # Строка или число
    s = str(val).strip()
    if not s:
        return None
    
    parts = s.split(",")
    res = []
    for p in parts:
        p = p.strip()
        if p:
            try:
                res.append(int(p))
            except (ValueError, TypeError):
                pass
    return res if res else None


async def apply_wish_filters(
    q,
    db,
    *,
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
):
    """Применяет фильтры по ID (с поддержкой списков через запятую и обратной
    совместимостью со старыми одиночными параметрами) и по типу заявки (wish_types).
    """
    # 1. creator_ids / creator_id
    c_ids = _parse_id_list(creator_ids)
    if c_ids is None and creator_id is not None:
        c_ids = [int(creator_id)]
    if c_ids is not None:
        q = q.where(Wish.created_by.in_(c_ids))

    # 2. assigned_to_ids / assigned_to_id
    a_ids = _parse_id_list(assigned_to_ids)
    if a_ids is None and assigned_to_id is not None:
        a_ids = [int(assigned_to_id)]
    if a_ids is not None:
        q = q.where(Wish.assigned_to.in_(a_ids))

    # 3. subsidy_ids / subsidy_id
    s_ids = _parse_id_list(subsidy_ids)
    if s_ids is None and subsidy_id is not None:
        s_ids = [int(subsidy_id)]
    if s_ids is not None:
        q = q.where(Wish.subsidy_id.in_(s_ids))

    # 4. org_ids / org_id
    o_ids = _parse_id_list(org_ids)
    if o_ids is None and org_id is not None:
        o_ids = [int(org_id)]
    if o_ids is not None:
        q = q.where(Wish.org_id.in_(o_ids))

    # 5. account_org_ids / account_org_id
    acc_ids = _parse_id_list(account_org_ids)
    if acc_ids is None and account_org_id is not None:
        acc_ids = [int(account_org_id)]
    if acc_ids is not None:
        acc_orgs_subq = select(Organization.id).where(or_(
            Organization.id.in_(acc_ids),
            Organization.root_org_id.in_(acc_ids),
            Organization.parent_org_id.in_(acc_ids),
        ))
        q = q.where(Wish.org_id.in_(acc_orgs_subq))

    # 6. wish_types ('advance_report', 'regular')
    if wish_types:
        wt_list = [w.strip() for w in str(wish_types).split(",") if w.strip()]
        has_advance = 'advance_report' in wt_list
        has_regular = 'regular' in wt_list
        
        if has_advance and not has_regular:
            q = q.where(Wish.source == 'advance_report')
        elif has_regular and not has_advance:
            q = q.where(or_(Wish.source.is_(None), Wish.source != 'advance_report'))

    return q
