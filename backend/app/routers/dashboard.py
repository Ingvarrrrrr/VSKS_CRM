from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
# Правило №6: та же формула фолбэка, что subsidies.py list/detail/create/approve/update —
# единственная реализация в app.services.subsidy_budget. Не используется НИЖЕ (перенесена
# в dashboard_charts.py вместе с /charts) — импорт-реэкспорт оставлен намеренно: тест
# test_subsidy_budget_single_source.py::test_dashboard_and_subsidies_share_one_formula_instance
# читает dashboard_module.effective_subsidy_budget, subsidy_finance.py — dashboard.obligation_date.
from app.services.subsidy_budget import effective_subsidy_budget
from app.config import settings
# ПРАВИЛО №6 (2026-09-05): единый расчёт «суммы закупки» по стадии — заменяет
# точечные COALESCE(contract_price, planned_total_price) / COALESCE(payment_
# amount, contract_price, planned_total_price), разбросанные по этому контуру
# (они не совпадали ни друг с другом по деталям, ни с purchase_amounts()).
from app.services.purchase_amounts import purchase_amounts


def _effective_float(p: Purchase) -> float:
    """Обёртка над purchase_amounts(p).effective для мест этого файла, где
    сумма закупки читается в Python-цикле по ORM-объектам (без Σ по позициям —
    те же ограничения, что и у effective_amount_expr(), но полная цепочка
    фолбэков по сырым колонкам, включая payment_amount_declared и т.д.).
    None -> 0.0 (эти места и раньше трактовали "нечего посчитать" как 0)."""
    eff = purchase_amounts(p).effective
    return float(eff) if eff is not None else 0.0

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _expected_payment_date(p: Purchase):
    """Когда ожидается фактическая выплата."""
    if p.status == 'paid' and p.payment_doc_date:
        return p.payment_doc_date.date() if hasattr(p.payment_doc_date, 'date') else p.payment_doc_date
    # для остальных — service_end_date > execution_term > service_deadline_date > contract_date
    for fld in ('service_end_date', 'execution_term', 'service_deadline_date', 'contract_date'):
        v = getattr(p, fld, None)
        if v:
            return v if isinstance(v, date) else v.date()
    return None


def obligation_date(p: Purchase) -> Optional[date]:
    """Дата возникновения обязательства — НЕ использует contract_date как fallback.

    Приоритет:
    1. is_prepayment + prepayment_date → дата предоплаты
    2. service_deadline_date → срок до даты (mode='deadline')
    3. service_end_date → конец периода оказания услуг
    4. execution_term → срок исполнения
    5. None — «без срока» (попадает в no_deadline bucket)
    """
    if getattr(p, 'is_prepayment', False) and getattr(p, 'prepayment_date', None):
        v = p.prepayment_date
        return v if isinstance(v, date) else v.date()
    for fld in ('service_deadline_date', 'service_end_date', 'execution_term'):
        v = getattr(p, fld, None)
        if v:
            return v if isinstance(v, date) else v.date()
    return None


_UNSET = object()


def _apply_subsidy_org_filter(query, user: User, org_ids=_UNSET, subsidy_ids=_UNSET):
    """Filter subsidies by org_ids — или напрямую по subsidy_ids (приоритет).

    subsidy_ids передаётся для scope=dashboard (двухуровневая видимость по вкладке
    «Дашборд»): None → не фильтровать (SaaS), set → Subsidy.id.in_(set).
    Иначе org_ids (или get_org_filter при _UNSET). Caller различает None и [].
    """
    if subsidy_ids is not _UNSET:
        if subsidy_ids is not None:
            query = query.where(Subsidy.id.in_(subsidy_ids))
        return query
    if org_ids is _UNSET:
        org_ids = get_org_filter(user)
    if org_ids is not None:
        query = query.where(Subsidy.org_id.in_(org_ids))
    return query


def _apply_purchase_org_filter(query, user: User, org_ids=_UNSET, subsidy_ids=_UNSET):
    """Filter purchases via subsidy.org_id — или напрямую по subsidy_ids (приоритет).

    subsidy_ids для scope=dashboard: None → не фильтровать, set →
    Purchase.subsidy_id.in_(set). Иначе org_ids (или get_org_filter при _UNSET).
    """
    if subsidy_ids is not _UNSET:
        if subsidy_ids is not None:
            query = query.where(Purchase.subsidy_id.in_(subsidy_ids))
        return query
    if org_ids is _UNSET:
        org_ids = get_org_filter(user)
    if org_ids is not None:
        query = query.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    return query


@router.get("/")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None),
):
    org_ids = get_org_filter(current_user)
    # scope=dashboard → двухуровневая видимость субсидий по вкладке «Дашборд»
    # (пер-субсидийная галочка перебивает орг-дефолт). Гейтим данные по subsidy_id.
    dash_sids = _UNSET
    if scope == "dashboard":
        dash_sids = await get_visible_subsidy_ids(current_user, db, "dashboard")

    # Get categories filtered by org / dashboard-subsidies
    cat_q = select(FeoCategory).order_by(FeoCategory.level, FeoCategory.id)
    if dash_sids is not _UNSET:
        if dash_sids is not None:
            cat_q = cat_q.where(FeoCategory.subsidy_id.in_(dash_sids))
    elif org_ids is not None:
        cat_q = cat_q.where(FeoCategory.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    cat_result = await db.execute(cat_q)
    cats = cat_result.scalars().all()

    # Get aggregated purchase data per feo_category_id
    agg_q = select(
        Purchase.feo_category_id,
        func.coalesce(func.sum(Purchase.planned_total_price), 0).label("planned"),
        func.coalesce(func.sum(
            case((Purchase.confirmed == True, Purchase.final_total_amount), else_=0)
        ), 0).label("confirmed"),
        func.coalesce(func.sum(Purchase.delivery_payment_amount), 0).label("payment"),
    ).group_by(Purchase.feo_category_id)
    if dash_sids is not _UNSET:
        agg_q = _apply_purchase_org_filter(agg_q, current_user, subsidy_ids=dash_sids)
    else:
        agg_q = _apply_purchase_org_filter(agg_q, current_user, org_ids)
    agg = await db.execute(agg_q)

    agg_map = {}
    for row in agg:
        agg_map[row.feo_category_id] = {
            "total_planned": float(row.planned),
            "total_confirmed": float(row.confirmed),
            "total_payment": float(row.payment),
        }

    # Build tree
    by_id = {}
    for c in cats:
        by_id[c.id] = {
            "id": c.id, "name": c.name, "level": c.level, "code": c.code,
            "subsidy_id": c.subsidy_id,
            "total_planned": 0, "total_confirmed": 0, "total_payment": 0,
            "children": []
        }
        if c.id in agg_map:
            by_id[c.id].update(agg_map[c.id])

    roots = []
    for c in cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)

    # Roll up totals
    def rollup(node):
        for child in node["children"]:
            rollup(child)
            node["total_planned"] += child["total_planned"]
            node["total_confirmed"] += child["total_confirmed"]
            node["total_payment"] += child["total_payment"]
    for r in roots:
        rollup(r)

    # Global totals (filtered by org)
    total_obl_q = select(func.coalesce(func.sum(Purchase.final_total_amount), 0)).where(Purchase.confirmed == True)
    total_obl_q = _apply_purchase_org_filter(total_obl_q, current_user, org_ids, subsidy_ids=dash_sids)
    total_obligations = float((await db.execute(total_obl_q)).scalar() or 0)

    total_pay_q = select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
    total_pay_q = _apply_purchase_org_filter(total_pay_q, current_user, org_ids, subsidy_ids=dash_sids)
    total_payments = float((await db.execute(total_pay_q)).scalar() or 0)

    return {
        "subsidy_limit": settings.SUBSIDY_LIMIT,
        "total_obligations": total_obligations,
        "total_payments": total_payments,
        "remaining": settings.SUBSIDY_LIMIT - total_obligations,
        "categories": roots
    }
