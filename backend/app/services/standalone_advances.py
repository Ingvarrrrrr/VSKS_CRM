"""standalone_advances.py — авансовые отчёты (Purchase.purchase_method='advance')
БЕЗ заявки-компаньона (wish_id IS NULL), для показа во вкладке «Заявки».

Контекст (задача владельца, 16.10.2026): «авансовый — частный случай заявки…
реестр авансовых — чтобы сотрудник смотрел свои авансовые, а не лез в
заявки». Обычный путь создания авансового отчёта ставит ему заявку-компаньон
автоматически (см. app/routers/purchases.py, create_purchase: «Авансовый без
wish_id → авто-заявка на возмещение»), и такой отчёт уже виден в «Заявках»
через Purchase.wish_id. Но загрузчик (backend/scripts/load_prod_subsidy_copy_dnr.py
и т.п.) создаёт Purchase напрямую, минуя этот путь, — у таких записей
wish_id остаётся NULL, и в «Заявках» их не было видно вовсе (жалоба: 28
авансовых субсидии «ФАДМ 2026_3» не находились поиском по номеру РЕЕ).

ПРАВИЛО №6 (не вторая видимость) — видимость этого списка СОБРАНА из тех же
кирпичей, что list_purchases в app/routers/purchases.py: get_org_filter +
UserSubsidyAccess (грант) + get_visible_subsidy_ids(scope='advance_reports')
для субсидийного join'а + build_visibility_clause(current_user, db, 'purchase')
для пользовательской видимости (иерархия/участие). Никакой новой формулы
видимости здесь не вводится.

Сумма строки — Purchase.purchase_amounts.load_purchase_amounts(...).effective
(тот же единый расчёт «суммы закупки», что и в реестре закупок/авансовых —
Правило №6, не считаем Σ item.total_price заново).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_org_filter
from app.auth.visibility import build_visibility_clause, get_visible_subsidy_ids
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.models.user_subsidy_access import UserSubsidyAccess


@dataclass
class StandaloneAdvanceRow:
    id: int
    registry_number: Optional[str]
    subsidy_id: Optional[int]
    subsidy_name: Optional[str]
    org_id: Optional[int]
    reimbursement_user_id: Optional[int]
    reimbursement_user_name: Optional[str]
    assigned_user_id: Optional[int]
    assigned_user_name: Optional[str]
    status: Optional[str]
    amount: Optional[Decimal]


async def list_standalone_advances(
    db: AsyncSession,
    current_user: User,
    *,
    subsidy_id: Optional[int] = None,
    org_id: Optional[int] = None,
    account_org_id: Optional[int] = None,
    creator_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    mine_only: bool = False,
    search: Optional[str] = None,
) -> list[StandaloneAdvanceRow]:
    """Авансовые Purchase без заявки-компаньона, в скоупе видимости закупок
    этого пользователя. created_from/created_to не фильтруют — у Purchase нет
    колонки created_at (см. docstring _registry_number_for в app/models/purchase.py),
    «даты» из задачи владельца здесь неприменимы.
    """
    q = select(Purchase).where(
        Purchase.purchase_method == "advance",
        Purchase.wish_id.is_(None),
        Purchase.stopped_at.is_(None),
    )

    # ПРАВИЛО №6 — тот же приём видимости, что list_purchases (routers/purchases.py).
    org_ids = get_org_filter(current_user)
    granted_ids = set(
        (
            await db.execute(
                select(UserSubsidyAccess.subsidy_id).where(
                    UserSubsidyAccess.user_id == current_user.id
                )
            )
        )
        .scalars()
        .all()
    )
    needs_subsidy_join = org_ids is not None or org_id is not None or account_org_id is not None
    subsidy_joined = False
    vis = await get_visible_subsidy_ids(current_user, db, "advance_reports")
    if vis is not None:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
        subsidy_joined = True
        q = q.where(Subsidy.id.in_(vis))
    elif needs_subsidy_join:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
        subsidy_joined = True
        if org_id is not None:
            if org_ids is not None and org_id not in org_ids:
                return []
            q = q.where(Subsidy.org_id == org_id)
        elif org_ids is not None:
            q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))

    clause = await build_visibility_clause(current_user, db, "purchase")
    if clause is not None:
        q = q.where(clause)

    if account_org_id is not None:
        from app.models.organization import Organization

        acc_orgs = select(Organization.id).where(
            or_(
                Organization.id == account_org_id,
                Organization.root_org_id == account_org_id,
                Organization.parent_org_id == account_org_id,
            )
        )
        if not subsidy_joined:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            subsidy_joined = True
        q = q.where(Subsidy.org_id.in_(acc_orgs))

    if subsidy_id is not None:
        q = q.where(Purchase.subsidy_id == subsidy_id)

    # Автор/получатель возмещения (задача владельца: «автор → reimbursement_user_id/
    # assigned_user_id») — для «Мои» и для фильтра «Автор».
    if mine_only:
        q = q.where(
            or_(
                Purchase.reimbursement_user_id == current_user.id,
                Purchase.assigned_user_id == current_user.id,
            )
        )
    if creator_id is not None:
        q = q.where(
            or_(
                Purchase.reimbursement_user_id == creator_id,
                Purchase.assigned_user_id == creator_id,
            )
        )
    if assigned_to_id is not None:
        q = q.where(Purchase.assigned_user_id == assigned_to_id)
    if search:
        q = q.where(Purchase.registry_number.ilike(f"%{search}%"))

    q = q.order_by(Purchase.id.desc())
    result = await db.execute(q)
    purchases = result.scalars().all()
    if not purchases:
        return []

    subsidy_ids = {p.subsidy_id for p in purchases if p.subsidy_id}
    subsidy_names: dict[int, str] = {}
    subsidy_orgs: dict[int, int] = {}
    if subsidy_ids:
        rows = (
            await db.execute(
                select(Subsidy.id, Subsidy.name, Subsidy.org_id).where(Subsidy.id.in_(subsidy_ids))
            )
        ).all()
        for sid, sname, s_org_id in rows:
            subsidy_names[sid] = sname
            subsidy_orgs[sid] = s_org_id

    user_ids: set[int] = set()
    for p in purchases:
        if p.reimbursement_user_id:
            user_ids.add(p.reimbursement_user_id)
        if p.assigned_user_id:
            user_ids.add(p.assigned_user_id)
    user_names: dict[int, str] = {}
    if user_ids:
        rows = (
            await db.execute(
                select(User.id, User.full_name, User.username).where(User.id.in_(user_ids))
            )
        ).all()
        for uid, fn, un in rows:
            user_names[uid] = fn or un

    from app.services.purchase_amounts import load_purchase_amounts

    amounts_map = await load_purchase_amounts(db, [p.id for p in purchases])

    out: list[StandaloneAdvanceRow] = []
    for p in purchases:
        amounts = amounts_map.get(p.id)
        out.append(
            StandaloneAdvanceRow(
                id=p.id,
                registry_number=p.registry_number,
                subsidy_id=p.subsidy_id,
                subsidy_name=subsidy_names.get(p.subsidy_id) if p.subsidy_id else None,
                org_id=subsidy_orgs.get(p.subsidy_id) if p.subsidy_id else None,
                reimbursement_user_id=p.reimbursement_user_id,
                reimbursement_user_name=user_names.get(p.reimbursement_user_id) if p.reimbursement_user_id else None,
                assigned_user_id=p.assigned_user_id,
                assigned_user_name=user_names.get(p.assigned_user_id) if p.assigned_user_id else None,
                status=p.status,
                amount=amounts.effective if amounts else None,
            )
        )
    return out
