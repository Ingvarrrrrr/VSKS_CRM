"""Список заявок, счётчики вкладок и общая видимость/фильтры (Wish).

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-08,
вторая резка wishes.py по образцу первой — commit 89187a0 — и users.py →
commit ca7b02c) БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

GET "/" и GET "/counts" — статические пути без сегментов сверх префикса,
структурно не пересекаются с catch-all "/{wish_id}" из wishes.router (ноль
сегментов против одного обязательного) — но регистрируется этот роутер ВСЁ
РАВНО до wishes.router в app/routes.py, тем же защитным принципом, что и
wish_documents/wish_members/wish_approvals там же (см. комментарии рядом).

Хелперы ядра (_enrich/_wish_purchase_summaries_map) вызываются через
`wishes_core.<имя>`, не `from app.routers.wishes import <имя>` — чтобы
monkeypatch на ядре видел переопределение и здесь тоже (см. докстринг
wish_transitions.py про этот приём).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_member import WishMember
from app.models.purchase import Purchase
from app.schemas.wishes import WishOut
from app.services.wish_tabs import WISH_TAB_STATUS_SETS, wish_tab_statuses
from app.routers import wishes as wishes_core

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
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
):
    """Общая видимость + доп. фильтры для GET /wishes/ и GET /wishes/counts.

    Вынесено из list_wishes (сессия 2026-09-01, жалоба владельца на счётчики
    вкладок), чтобы список и счётчики видели РОВНО одни и те же заявки — иначе
    числа разъедутся между вкладкой и бейджем. НЕ накладывает статус-фильтр,
    order_by, offset/limit — это решает вызывающий (у /counts своя логика
    группировки, у списка — своя пагинация).
    """
    org_ids = get_org_filter(current_user)
    vis = await get_visible_subsidy_ids(current_user, db, "wishes")
    if vis is not None:
        # Two-level gate: rows WITH subsidy → gate by vis; rows WITHOUT subsidy → org gate
        null_branch = (
            and_(Wish.subsidy_id.is_(None), Wish.org_id.in_(org_ids))
            if org_ids is not None
            else Wish.subsidy_id.is_(None)
        )
        q = q.where(or_(Wish.subsidy_id.in_(vis), null_branch))
    elif org_ids is not None:
        # SaaS role but org restriction still applies (e.g. account_owner with org_id set)
        q = q.where(Wish.org_id.in_(org_ids))

    # Preload wish_ids where current user is a participant (for visibility extension)
    member_res = await db.execute(
        select(WishMember.wish_id).where(WishMember.user_id == current_user.id)
    )
    member_wish_ids = {r[0] for r in member_res.all()}

    if assigned_to_me:
        # Explicit shortcut: wishes where I am the designated approver
        # или я — согласующий из цепочки (WishApproval)
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
        # Employee always sees only own + wishes they are a participant in
        base_cond = Wish.created_by == current_user.id
        if member_wish_ids:
            q = q.where(or_(base_cond, Wish.id.in_(member_wish_ids)))
        else:
            q = q.where(base_cond)
    elif subordinates_only:
        # Phase 28: use unified visibility helper (covers SaaS bypass + hierarchy +
        # dept heads + managed orgs + UOA org_admin/manager)
        visible_uids = await get_visible_user_ids(current_user, db)
        if visible_uids is None:
            # SaaS role (superadmin/account_owner) → видят всё
            # (org filter уже применён выше). Дополнительных фильтров не нужно.
            pass
        else:
            # «Заявки сотрудников» = видимые подчинённые + сам пользователь
            # (руководитель — тоже сотрудник, свои заявки видит здесь же)
            sub_ids = set(visible_uids) | {current_user.id}
            q = q.where(Wish.created_by.in_(sub_ids))
    else:
        # Phase 28: unified visibility helper + member visibility
        clause = await build_visibility_clause(current_user, db, 'wish')
        if clause is not None:
            if member_wish_ids:
                q = q.where(or_(clause, Wish.id.in_(member_wish_ids)))
            else:
                q = q.where(clause)

    # Дополнительные фильтры (применяются после visibility — только сужают)
    if creator_id is not None:
        q = q.where(Wish.created_by == creator_id)
    if assigned_to_id is not None:
        q = q.where(Wish.assigned_to == assigned_to_id)
    if subsidy_id is not None:
        q = q.where(Wish.subsidy_id == subsidy_id)
    if org_id is not None:
        q = q.where(Wish.org_id == org_id)
    if account_org_id is not None:
        # Аккаунт = корневая орг + все её дочерние (root_org_id/parent_org_id)
        from app.models.organization import Organization
        acc_orgs = select(Organization.id).where(or_(
            Organization.id == account_org_id,
            Organization.root_org_id == account_org_id,
            Organization.parent_org_id == account_org_id,
        ))
        q = q.where(Wish.org_id.in_(acc_orgs))
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
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Счётчики по вкладкам «Заявки на закупку» — с теми же параметрами
    видимости, что и GET /wishes/, но COUNT()-ом, а не выборкой записей.

    Жалоба владельца (сессия 2026-09-01): список обрезан limit=50, поэтому
    сравнивать «сколько заявок» по длине ответа списка нельзя в принципе —
    нужен отдельный точный счётчик. Вкладки накопительные (см.
    app/services/wish_tabs.py): «Отправленные» включает approved/rejected/
    converted, «Одобренные» включает converted и т.д. — один GROUP BY по
    точному статусу, накопление сумм в Python (без 6 отдельных COUNT-запросов).
    """
    q = await _build_wishes_query(
        select(Wish.status, func.count(Wish.id)),
        current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, assigned_to_id=assigned_to_id, subsidy_id=subsidy_id,
        org_id=org_id, account_org_id=account_org_id,
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


@router.get("/", response_model=list[WishOut])
async def list_wishes(
    status: Optional[str] = None,
    mine_only: bool = False,
    assigned_to_me: bool = False,
    subordinates_only: bool = False,
    creator_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List wishes with unified visibility (Phase 28 Bundle 2B).
    assigned_to_me=true: wishes where current user is the assignee.
    subordinates_only=true: wishes created by direct subordinates (not current user).
    mine_only=true / role==employee: show only own wishes (shortcut filters).

    status: имя вкладки ('draft'/'submitted'/'approved'/'rejected'/'converted'/'all')
    фильтрует НАКОПИТЕЛЬНО через wish_tab_statuses (сессия 2026-09-01, жалоба
    владельца) — 'submitted' включает approved/rejected/converted и т.д.
    Отсутствие параметра сохраняет ПРЕЖНЕЕ поведение (список без converted) —
    на него рассчитывают другие потребители эндпоинта (см. wish_tab_statuses
    докстринг и вызовы GET /wishes/ без status в useRiskScores.ts и
    WishesView.vue::loadWishes/loadIncoming).
    """
    q = select(Wish).options(
        selectinload(Wish.creator),
        selectinload(Wish.approver),
        selectinload(Wish.assignee),
        selectinload(Wish.subsidy),
        selectinload(Wish.event),
        selectinload(Wish.executor),
        selectinload(Wish.items),
        selectinload(Wish.stopped_by_user),
        selectinload(Wish.contractor),
        selectinload(Wish.rejected_by_user),
    )
    q = await _build_wishes_query(
        q, current_user, db,
        mine_only=mine_only, assigned_to_me=assigned_to_me, subordinates_only=subordinates_only,
        creator_id=creator_id, assigned_to_id=assigned_to_id, subsidy_id=subsidy_id,
        org_id=org_id, account_org_id=account_org_id,
        created_from=created_from, created_to=created_to,
        deadline_from=deadline_from, deadline_to=deadline_to,
    )

    if status and status != 'all':
        # Накопительная цепочка (владелец, 2026-09-01): именованная вкладка
        # включает всё, что когда-либо прошло через это состояние.
        q = q.where(Wish.status.in_(wish_tab_statuses(status)))
    elif status == 'all':
        # Явное «Все» — действительно всё, включая draft и converted.
        pass
    else:
        # status отсутствует вовсе: ПРЕЖНЕЕ поведение не меняем — по умолчанию
        # «Заявки» = в работе; распределённые (converted) живут в «Закупках».
        # Другие экраны (useRiskScores.ts, WishesView.vue myWishes/incoming)
        # зовут без status и рассчитывают именно на это.
        q = q.where(Wish.status != 'converted')
    q = q.order_by(Wish.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    wishes = result.scalars().all()

    # Phase 31: batch unseen_fields/unseen_changes_count (2 queries, no N+1) (D-05..D-09)
    wish_ids = [w.id for w in wishes]
    unseen_map: dict[int, list[str]] = {}
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        unseen_map = await _get_unseen_map(db, 'wish', wish_ids, current_user.id)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen wish map failed: %s", _exc)

    # «От кого»: имена участников (WishMember) батчем, без N+1
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

        # «Кому»: цепочка согласующих по order_num (батчем, без N+1)
        from app.models.wish_approval import WishApproval
        ares = await db.execute(
            select(WishApproval.wish_id, User.full_name, User.username)
            .join(User, User.id == WishApproval.user_id)
            .where(WishApproval.wish_id.in_(wish_ids))
            .order_by(WishApproval.wish_id, WishApproval.order_num)
        )
        for a_wid, a_fn, a_un in ares.all():
            approvers_map.setdefault(a_wid, []).append(a_fn or a_un)

        # Конвертация разбивает заявку на несколько закупок — отдаём все id
        pres = await db.execute(
            select(Purchase.wish_id, Purchase.id)
            .where(Purchase.wish_id.in_(wish_ids))
            .order_by(Purchase.id)
        )
        for p_wid, p_id in pres.all():
            purchases_map.setdefault(p_wid, []).append(p_id)

    # Пункт 4 (владелец, 2026-08-13): сводка закупок (номер/статус/сумма) для меню
    # «Перейти в закупку» — батчем, тем же приёмом, что purchases_map выше.
    purchase_summaries_map = await wishes_core._wish_purchase_summaries_map(wish_ids, db)

    # Владелец: столбец «сумма заявки» на листе /wishes — Σ total_price позиций
    # (WishItem), ОДНИМ агрегирующим запросом на всю страницу (без N+1 и без
    # загрузки всех позиций построчно).
    items_total_map: dict[int, Decimal] = {}
    if wish_ids:
        itres = await db.execute(
            select(WishItem.wish_id, func.coalesce(func.sum(WishItem.total_price), 0))
            .where(WishItem.wish_id.in_(wish_ids))
            .group_by(WishItem.wish_id)
        )
        items_total_map = {wid: total for wid, total in itres.all()}

    out_list = []
    for w in wishes:
        enriched = wishes_core._enrich(w)
        enriched.member_names = members_map.get(w.id, [])
        enriched.approver_names = approvers_map.get(w.id, [])
        enriched.purchase_ids = purchases_map.get(w.id, [])
        enriched.purchases = purchase_summaries_map.get(w.id, [])
        enriched.items_total = items_total_map.get(w.id, Decimal("0"))
        _unseen = unseen_map.get(w.id, [])
        enriched.unseen_fields = _unseen
        enriched.unseen_changes_count = len(_unseen)
        out_list.append(enriched)
    return out_list
