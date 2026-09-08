"""GET /api/dashboard/financial-plan(/details) — сосед dashboard.py
(Правило №5, резка 1641→core, 2026-09-08).

Помесячная/поквартальная разбивка ожидаемых выплат (plan/committed/overdue/
no_deadline/feo_plan) и drill-down список закупок за период+категорию.
Экспорт в xlsx для этих же данных — в dashboard_financial_plan_export.py.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.routers.dashboard import (
    _UNSET, _apply_purchase_org_filter, _effective_float, _expected_payment_date, obligation_date,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/financial-plan")
async def get_financial_plan(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None),
):
    """Возвращает помесячную и поквартальную разбивку ожидаемых выплат.

    Структура ответа:
    - plan / committed — текущий план/обязательства по obligation_date
    - overdue[M] — накопленный долг: закупка с obligation_date < M и не полностью оплачена
      добавляется в каждый месяц от (obligation_month+1) до текущего включительно
    - no_deadline — закупки без obligation_date (не оплачены)
    """
    org_ids = get_org_filter(current_user)
    dash_sids = _UNSET
    if scope in ("dashboard", "plan"):
        dash_sids = await get_visible_subsidy_ids(current_user, db, scope)
    q = select(Purchase)
    q = _apply_purchase_org_filter(q, current_user, org_ids, subsidy_ids=dash_sids)
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    rows = (await db.execute(q)).scalars().all()

    PLAN_STATUSES = {'planned', 'wishes', 'plan_schedule'}
    COMMITTED_STATUSES = {'contracted', 'ordered', 'delivered', 'work_in_progress'}
    # paid — учитывается через _expected_payment_date, в overdue не попадает

    today = date.today()
    current_ym = f"{today.year}-{today.month:02d}"

    # buckets
    by_month_plan: dict = {}        # ym -> {amount, count}
    by_month_committed: dict = {}   # ym -> {amount, count}
    by_month_overdue: dict = {}     # ym -> {accumulated, items_count}
    no_deadline_amount = 0.0
    no_deadline_count = 0

    by_quarter_plan: dict = {}
    by_quarter_committed: dict = {}
    by_quarter_overdue: dict = {}

    def _add_bucket(bkt: dict, key: str, amount: float, count: int = 1):
        if key not in bkt:
            bkt[key] = {"amount": 0.0, "count": 0}
        bkt[key]["amount"] += amount
        bkt[key]["count"] += count

    def _add_overdue(bkt: dict, key: str, amount: float):
        if key not in bkt:
            bkt[key] = {"accumulated": 0.0, "items_count": 0}
        bkt[key]["accumulated"] += amount
        bkt[key]["items_count"] += 1

    for p in rows:
        amount = _effective_float(p)
        if amount == 0:
            continue

        paid_amount = float(p.delivery_payment_amount or 0)
        is_fully_paid = paid_amount >= amount

        obl = obligation_date(p)

        # paid закупки — используем _expected_payment_date (по payment_doc_date)
        if p.status == 'paid':
            d = _expected_payment_date(p)
            if d:
                ym = f"{d.year}-{d.month:02d}"
                yq = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
                _add_bucket(by_month_committed, ym, amount)
                _add_bucket(by_quarter_committed, yq, amount)
            continue

        # no_deadline bucket
        if obl is None:
            no_deadline_amount += amount
            no_deadline_count += 1
            continue

        obl_ym = f"{obl.year}-{obl.month:02d}"
        obl_yq = f"{obl.year}-Q{(obl.month - 1) // 3 + 1}"

        # overdue: obligation_date < first_day_of_current_month and not fully paid
        # Distribute to every month from obl_month+1 up to current month
        if not is_fully_paid:
            # compute first day of month after obligation month
            if obl.month == 12:
                next_year, next_month = obl.year + 1, 1
            else:
                next_year, next_month = obl.year, obl.month + 1
            overdue_start = date(next_year, next_month, 1)
            first_day_current = date(today.year, today.month, 1)

            if overdue_start <= first_day_current:
                # Distribute the remaining amount to each month from overdue_start to today (inclusive)
                remaining = amount - paid_amount
                cur = overdue_start
                while cur <= first_day_current:
                    m_ym = f"{cur.year}-{cur.month:02d}"
                    m_yq = f"{cur.year}-Q{(cur.month - 1) // 3 + 1}"
                    _add_overdue(by_month_overdue, m_ym, remaining)
                    _add_overdue(by_quarter_overdue, m_yq, remaining)
                    # advance month
                    if cur.month == 12:
                        cur = date(cur.year + 1, 1, 1)
                    else:
                        cur = date(cur.year, cur.month + 1, 1)
                # Also add to plan/committed for original period
                if p.status in PLAN_STATUSES:
                    _add_bucket(by_month_plan, obl_ym, amount)
                    _add_bucket(by_quarter_plan, obl_yq, amount)
                elif p.status in COMMITTED_STATUSES:
                    _add_bucket(by_month_committed, obl_ym, amount)
                    _add_bucket(by_quarter_committed, obl_yq, amount)
                continue

        # Future or not-overdue — add to plan/committed normally
        if p.status in PLAN_STATUSES:
            _add_bucket(by_month_plan, obl_ym, amount)
            _add_bucket(by_quarter_plan, obl_yq, amount)
        elif p.status in COMMITTED_STATUSES:
            _add_bucket(by_month_committed, obl_ym, amount)
            _add_bucket(by_quarter_committed, obl_yq, amount)

    def _fmt_plan(d: dict):
        return [{"period": k, "amount": v["amount"], "count": v["count"]} for k, v in sorted(d.items())]

    def _fmt_overdue(d: dict):
        return [{"period": k, "accumulated": v["accumulated"], "items_count": v["items_count"]}
                for k, v in sorted(d.items())]

    # --- feo_plan: real ФЭО cash-flow from FeoPlannedItem schedule ---
    from app.services.plan_cashflow import cashflow_for_subsidies

    # Determine subsidy id set for feo_plan aggregation
    if subsidy_id:
        feo_sids = [subsidy_id]
    elif dash_sids is not _UNSET:
        # dash_sids is either None (superadmin — no restriction) or a list
        if dash_sids is None:
            # superadmin: all subsidies, filtered by org if applicable
            _sid_q = select(Subsidy.id)
            if org_ids is not None:
                _sid_q = _sid_q.where(Subsidy.org_id.in_(org_ids))
            feo_sids = [r[0] for r in (await db.execute(_sid_q)).all()]
        else:
            feo_sids = list(dash_sids)
    else:
        # scope not in dashboard/plan — fall back to org filter
        _sid_q = select(Subsidy.id)
        if org_ids is not None:
            _sid_q = _sid_q.where(Subsidy.org_id.in_(org_ids))
        feo_sids = [r[0] for r in (await db.execute(_sid_q)).all()]

    by_month_feo: dict[str, float] = {}
    by_quarter_feo: dict[str, float] = {}
    if feo_sids:
        cf = await cashflow_for_subsidies(db, feo_sids)
        for sub_data in cf.values():
            for (y, m), amt in sub_data.items():
                mk = f"{y}-{m:02d}"
                qk = f"{y}-Q{(m - 1) // 3 + 1}"
                by_month_feo[mk] = by_month_feo.get(mk, 0.0) + float(amt)
                by_quarter_feo[qk] = by_quarter_feo.get(qk, 0.0) + float(amt)

    def _fmt_feo(d: dict):
        return [{"period": k, "amount": v} for k, v in sorted(d.items())]

    return {
        "by_month": {
            "plan":        _fmt_plan(by_month_plan),
            "committed":   _fmt_plan(by_month_committed),
            "overdue":     _fmt_overdue(by_month_overdue),
            "no_deadline": {"amount": no_deadline_amount, "items_count": no_deadline_count},
            "feo_plan":    _fmt_feo(by_month_feo),
        },
        "by_quarter": {
            "plan":        _fmt_plan(by_quarter_plan),
            "committed":   _fmt_plan(by_quarter_committed),
            "overdue":     _fmt_overdue(by_quarter_overdue),
            "no_deadline": {"amount": no_deadline_amount, "items_count": no_deadline_count},
            "feo_plan":    _fmt_feo(by_quarter_feo),
        },
    }


@router.get("/financial-plan/details")
async def get_financial_plan_details(
    period: Optional[str] = Query(None, description="'YYYY-MM' для месяца или 'YYYY-Qn' для квартала. Не требуется для category=no_deadline"),
    category: str = Query(..., regex="^(plan|committed|overdue|no_deadline)$"),
    granularity: str = Query("month", regex="^(month|quarter)$"),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None),
):
    """Список закупок попавших в указанный период+категорию.

    category:
    - plan / committed — плановые/принятые обязательства по obligation_date
    - overdue — просроченные (obligation_date в прошлом, не полностью оплачены)
    - no_deadline — без срока исполнения (obligation_date is None)
    """
    PLAN_STATUSES = {"planned", "wishes", "plan_schedule"}
    COMMITTED_STATUSES = {"contracted", "ordered", "delivered", "paid", "work_in_progress"}

    today = date.today()
    org_ids = get_org_filter(current_user)
    dash_sids = _UNSET
    if scope in ("dashboard", "plan"):
        dash_sids = await get_visible_subsidy_ids(current_user, db, scope)

    # period обязателен для всех категорий кроме no_deadline
    if category != "no_deadline" and not period:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="period обязателен для category != 'no_deadline'")

    if category == "no_deadline":
        # Загружаем все не-paid закупки без obligation_date
        q = select(Purchase).where(Purchase.status != "paid")
        if subsidy_id:
            q = q.where(Purchase.subsidy_id == subsidy_id)
        q = _apply_purchase_org_filter(q, current_user, org_ids, subsidy_ids=dash_sids)
        q = q.options(selectinload(Purchase.contractor))
        rows = (await db.execute(q)).scalars().all()

        result = []
        for p in rows:
            obl = obligation_date(p)
            if obl is not None:
                continue
            amount = _effective_float(p)
            if amount == 0:
                continue
            paid_amount = float(p.delivery_payment_amount or 0)
            result.append({
                "id": p.id,
                "purchase_number": p.purchase_number,
                "subject": p.subject or "",
                "contractor_name": (p.contractor.name if p.contractor else None) or "—",
                "amount": amount,
                "status": p.status,
                "expected_date": None,
                "contract_number": p.contract_number,
                "obligation_date": None,
                "is_likely_needed": p.is_likely_needed if hasattr(p, 'is_likely_needed') else True,
                "is_prepayment": p.is_prepayment if hasattr(p, 'is_prepayment') else False,
                "is_overdue": False,
                "missing_deadline": True,
                "paid_amount": paid_amount,
                "remaining": max(amount - paid_amount, 0),
                "stage_label": p.stage_label if hasattr(p, 'stage_label') else None,
            })
        result.sort(key=lambda r: (-r["amount"],))
        return {"period": period, "category": category, "granularity": granularity, "items": result}

    elif category == "overdue":
        # Закупки у которых obligation_date < first_day_of_period и не полностью оплачены
        q = select(Purchase).where(Purchase.status != "paid")
        if subsidy_id:
            q = q.where(Purchase.subsidy_id == subsidy_id)
        q = _apply_purchase_org_filter(q, current_user, org_ids, subsidy_ids=dash_sids)
        q = q.options(selectinload(Purchase.contractor))
        rows = (await db.execute(q)).scalars().all()

        # Parse period to get first day of period
        if granularity == "month":
            year, month = int(period[:4]), int(period[5:7])
            first_day_of_period = date(year, month, 1)
        else:
            year = int(period[:4])
            q_num = int(period[-1])
            first_month = (q_num - 1) * 3 + 1
            first_day_of_period = date(year, first_month, 1)

        result = []
        for p in rows:
            obl = obligation_date(p)
            if obl is None:
                continue
            amount = _effective_float(p)
            if amount == 0:
                continue
            paid_amount = float(p.delivery_payment_amount or 0)
            is_fully_paid = paid_amount >= amount
            if is_fully_paid:
                continue
            # obligation must be before first_day_of_period
            if obl >= first_day_of_period:
                continue
            # check that period <= current (overdue only goes up to today)
            if first_day_of_period > date(today.year, today.month, 1):
                continue
            remaining = max(amount - paid_amount, 0)
            result.append({
                "id": p.id,
                "purchase_number": p.purchase_number,
                "subject": p.subject or "",
                "contractor_name": (p.contractor.name if p.contractor else None) or "—",
                "amount": amount,
                "status": p.status,
                "expected_date": obl.isoformat(),
                "contract_number": p.contract_number,
                "obligation_date": obl.isoformat(),
                "is_likely_needed": p.is_likely_needed if hasattr(p, 'is_likely_needed') else True,
                "is_prepayment": p.is_prepayment if hasattr(p, 'is_prepayment') else False,
                "is_overdue": True,
                "missing_deadline": False,
                "paid_amount": paid_amount,
                "remaining": remaining,
                "stage_label": p.stage_label if hasattr(p, 'stage_label') else None,
            })
        result.sort(key=lambda r: (r["obligation_date"], -r["amount"]))
        return {"period": period, "category": category, "granularity": granularity, "items": result}

    else:
        # plan / committed — используем obligation_date
        target_statuses = PLAN_STATUSES if category == "plan" else COMMITTED_STATUSES

        q = select(Purchase).where(Purchase.status.in_(target_statuses))
        if subsidy_id:
            q = q.where(Purchase.subsidy_id == subsidy_id)
        q = _apply_purchase_org_filter(q, current_user, org_ids, subsidy_ids=dash_sids)
        q = q.options(selectinload(Purchase.contractor))
        rows = (await db.execute(q)).scalars().all()

        result = []
        for p in rows:
            if p.status == 'paid':
                d = _expected_payment_date(p)
            else:
                d = obligation_date(p)
            if not d:
                continue
            if granularity == "month":
                row_period = f"{d.year}-{d.month:02d}"
            else:
                row_period = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            if row_period != period:
                continue

            amount = _effective_float(p)
            if amount == 0:
                continue
            paid_amount = float(p.delivery_payment_amount or 0)
            obl = obligation_date(p)
            is_overdue_flag = (obl is not None and obl < today and paid_amount < amount)

            result.append({
                "id": p.id,
                "purchase_number": p.purchase_number,
                "subject": p.subject or "",
                "contractor_name": (p.contractor.name if p.contractor else None) or "—",
                "amount": amount,
                "status": p.status,
                "expected_date": d.isoformat(),
                "contract_number": p.contract_number,
                "obligation_date": obl.isoformat() if obl else None,
                "is_likely_needed": p.is_likely_needed if hasattr(p, 'is_likely_needed') else True,
                "is_prepayment": p.is_prepayment if hasattr(p, 'is_prepayment') else False,
                "is_overdue": is_overdue_flag,
                "missing_deadline": obl is None,
                "paid_amount": paid_amount,
                "remaining": max(amount - paid_amount, 0),
                "stage_label": p.stage_label if hasattr(p, 'stage_label') else None,
            })

        result.sort(key=lambda r: (r["expected_date"], -r["amount"]))
        return {"period": period, "category": category, "granularity": granularity, "items": result}
