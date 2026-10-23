"""purchase_list_visibility.py — единый фильтр видимости/scope/org для
Purchase-запросов (ПРАВИЛО №6).

Вынесено из app/routers/purchases.py::list_purchases (перф-задача 21.10.2026,
«значок потолка — отдельной лёгкой ручкой»): GET /api/purchases/ceiling-badges
обязан видеть РОВНО ТЕ ЖЕ закупки, что и реестр (GET /api/purchases/), одной
формулой — а не второй копией той же логики (видел бы закупку, которую
реестр скрывает, или наоборот). Обе ручки строят select(Purchase)... и зовут
apply_purchase_visibility(q, ...) ПЕРЕД остальными, контентными фильтрами
(contract_id/status/search и т.д. — те не входят сюда, это не вопрос
видимости, а вопрос содержимого выдачи).

Что входит (дословно перенесённая логика list_purchases):
  1. org_filter (get_org_filter) + explicit org_id, либо двухуровневая
     видимость по scope ('purchases'/'advance_reports'/'service_notes',
     get_visible_subsidy_ids) — ВЗАИМОИСКЛЮЧАЮЩИЕ ветки, как было;
  2. build_visibility_clause (иерархия/участие, Phase 28) + safety-net для
     org-lead'ов (закупки с assigned_user_id IS NULL);
  3. Purchase.status != 'split' — родительские записи разделённых закупок
     скрыты всегда (решение 21.09);
  4. exclude_hidden_payroll_purchases — право «Видеть ФОТ» (21.10.2026).

Что НЕ входит (контентные фильтры, не видимость): status='wishes' скрытие по
умолчанию для scope=purchases — это специфика РЕЕСТРА (OrdersView), значкам
потолка это решение не нужно (им важны только статусы из PRE_CONTRACT_STATUSES,
которые 'wishes' включают намеренно — см. purchase_ceiling_block.py).
"""
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_org_filter, ADMIN_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User

_SCOPED_TABS = {"purchases", "advance_reports", "service_notes"}


async def apply_purchase_visibility(
    q, current_user: User, db: AsyncSession, *, scope: str | None = None, org_id: int | None = None,
):
    """Применяет к select(Purchase)... фильтр видимости/scope/org — единый для
    list_purchases и ceiling-badges. Возвращает изменённый q (или [] -сигнал
    невозможен — вызывающий сам решает, что делать при org_id вне доступа,
    см. list_purchases)."""
    org_ids = get_org_filter(current_user)
    from app.models.user_subsidy_access import UserSubsidyAccess
    from sqlalchemy import select as _select
    granted_ids = set((await db.execute(
        _select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == current_user.id)
    )).scalars().all())
    needs_subsidy_join = org_ids is not None or org_id is not None
    if scope is not None and scope in _SCOPED_TABS and org_id is None:
        vis = await get_visible_subsidy_ids(current_user, db, scope)
        if vis is not None:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            q = q.where(Subsidy.id.in_(vis))
    else:
        if needs_subsidy_join:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            if org_id is not None:
                if org_ids is not None and org_id not in org_ids:
                    return None
                q = q.where(Subsidy.org_id == org_id)
            elif org_ids is not None:
                q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))
    clause = await build_visibility_clause(current_user, db, 'purchase')
    if clause is not None:
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (
            current_user.role in ADMIN_ROLES
            or (vuids is not None and len(vuids) > 1)
        )
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        q = q.where(clause)
    q = q.where(Purchase.status != "split")
    from app.services.payroll_visibility import exclude_hidden_payroll_purchases as _exclude_hidden_payroll_purchases
    q = await _exclude_hidden_payroll_purchases(q, current_user, db)
    return q
