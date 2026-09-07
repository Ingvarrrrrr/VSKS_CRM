"""Финансовые сводки субсидии: сверка платежей и помесячный cash-flow.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09-07):
GET /{subsidy_id}/payment-summary (закупки vs банковская выписка) и
GET /{subsidy_id}/financial-plan (план/обязательства/оплачено по месяцам).

Собственный APIRouter на префиксе /api/subsidies — регистрируется в
app/routes.py рядом с subsidies.router.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


# ---------------------------------------------------------------------------
# GET /api/subsidies/{subsidy_id}/payment-summary
# Сверка платежей закупок vs банковской выписки по субсидии.
# ---------------------------------------------------------------------------

@router.get("/{subsidy_id}/payment-summary")
async def payment_summary(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сводка платежей субсидии: закупки vs реестр (BankPayment).

    Скоупинг BankPayment к субсидии:
    - Используем BankPayment.matched_subsidy_id == subsidy_id (прямое поле match-состояния).
    - Дополнительно берём BankPayment с payment_number, совпадающим с payment_doc_number
      закупок этой субсидии — на случай, если matched_subsidy_id ещё не проставлен.
    Объединяем оба набора (дедуп по id) для максимального покрытия.
    """
    from decimal import Decimal
    from app.models.bank_statement import BankPayment
    from app.services.payment_reconciliation import build_reconciliation, _normalize_num
    from app.auth.visibility import get_visible_subsidy_ids, build_visibility_clause

    # --- security: visibility check (mirror of budget-check) ---
    visible = await get_visible_subsidy_ids(current_user, db)
    if visible is not None and subsidy_id not in visible:
        clause = await build_visibility_clause(current_user, db, "purchase")
        allowed = clause is None
        if clause is not None:
            cnt = (await db.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.subsidy_id == subsidy_id, clause
                )
            )).scalar() or 0
            allowed = cnt > 0
        if not allowed:
            raise HTTPException(status_code=404, detail="Subsidy not found")

    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # --- 1. Purchase payments for this subsidy ---
    purchase_rows = (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.payment_doc_number.isnot(None),
        )
    )).scalars().all()

    purchases_total = float(sum(
        Decimal(str(p.payment_amount or 0)) for p in purchase_rows
    ))

    # Normalised ПП numbers from purchases (for bank lookup)
    purchase_pp_set: set[str] = set()
    for p in purchase_rows:
        norm = _normalize_num(p.payment_doc_number)
        if norm:
            purchase_pp_set.add(norm)

    # --- 2. Bank payments scoped to this subsidy ---
    # Primary: matched_subsidy_id directly links BankPayment to subsidy
    bp_by_matched_q = select(BankPayment).where(
        BankPayment.matched_subsidy_id == subsidy_id,
        BankPayment.payment_number.isnot(None),
    )
    bp_matched = (await db.execute(bp_by_matched_q)).scalars().all()
    bp_ids_seen: set[int] = {bp.id for bp in bp_matched}

    # Secondary: BankPayment whose payment_number normalises to one of the purchase ПП numbers
    bp_extra: list = []
    if purchase_pp_set:
        bp_all_q = select(BankPayment).where(
            BankPayment.payment_number.isnot(None),
            BankPayment.matched_subsidy_id.is_(None),  # skip already counted
        )
        for bp in (await db.execute(bp_all_q)).scalars().all():
            if _normalize_num(bp.payment_number) in purchase_pp_set and bp.id not in bp_ids_seen:
                bp_extra.append(bp)
                bp_ids_seen.add(bp.id)

    all_bank_payments = list(bp_matched) + bp_extra
    bank_total = float(sum(Decimal(str(bp.amount or 0)) for bp in all_bank_payments))

    difference = round(purchases_total - bank_total, 2)

    # --- 3. Reconciliation via existing service ---
    # build_reconciliation works over ALL bank payments and payments. We call it for
    # the whole dataset and then filter to rows relevant to this subsidy's ПП numbers.
    # The service is NOT subsidy-aware, so we post-filter by normalised ПП set.
    all_recon = await build_reconciliation(db)

    # ПП numbers appearing in this subsidy's purchases (already built above)
    relevant_rows = [
        row for row in all_recon
        if _normalize_num(row.get("payment_number", "")) in purchase_pp_set
    ] if purchase_pp_set else []

    # Split into buckets
    matched_count = sum(1 for r in relevant_rows if r["status"] == "match")
    discrepancy_rows = [r for r in relevant_rows if r["status"] != "match"]

    discrepancies = []
    for row in discrepancy_rows:
        item: dict = {
            "payment_number": row["payment_number"],
            "status": row["status"],
            "purchase_amount": row["purchases_amount"],
            "bank_amount": row["registry_amount"],
            "amount_diff": row["amount_diff"],
        }
        if row["status"] == "amount_mismatch":
            item["reason"] = "Суммы в закупках и реестре расходятся"
        elif row["status"] == "registry_only":
            item["reason"] = "Есть в банковском реестре, отсутствует в закупках"
        elif row["status"] == "purchases_only":
            item["reason"] = "Привязан к закупке, отсутствует в банковском реестре"
        else:
            item["reason"] = row["status"]
        discrepancies.append(item)

    return {
        "subsidy_id": subsidy_id,
        "purchases_total": purchases_total,
        "bank_total": bank_total,
        "difference": difference,
        "matched_count": matched_count,
        "discrepancies": discrepancies,
    }


# ---------------------------------------------------------------------------
# Финансовый план субсидии — помесячный cash-flow
# ---------------------------------------------------------------------------

@router.get("/{subsidy_id}/financial-plan")
async def financial_plan(
    subsidy_id: int,
    year: Optional[int] = Query(None, description="Год (по умолчанию текущий)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Помесячный финансовый план субсидии.

    Слои данных:
      plan        — плановые выплаты из ФЭО (expand_planned_item)
      obligations — принятые обязательства (contract_price) по месяцу obligation_date
      paid        — оплачено (payment_amount) по месяцу payment_doc_date, статус paid
      debt_cumul  — накопленный долг = Σ(obligations) − Σ(paid) нарастающим итогом
      var_plan_obl, var_plan_paid — отклонения план−обяз, план−факт за месяц

    Также возвращает разбивку по directions (level-1 ФЭО).
    """
    from datetime import date as _date
    from decimal import Decimal as _Dec
    from app.auth.visibility import get_visible_subsidy_ids
    from app.services.plan_cashflow import (
        cashflow_for_subsidy,
        cashflow_with_directions,
    )
    from app.routers.dashboard import obligation_date as _obligation_date

    target_year = year or _date.today().year

    # ----- авторизация: видимость субсидии -----
    visible = await get_visible_subsidy_ids(current_user, db)
    if visible is not None and subsidy_id not in visible:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # ----- Плановые выплаты (plan) -----
    plan_monthly = await cashflow_for_subsidy(db, subsidy_id)
    # Разбивка по directions
    dir_monthly = await cashflow_with_directions(db, subsidy_id)

    # Загрузить names level-1 категорий
    dir_cat_ids = [cid for cid in dir_monthly if cid != 0]
    dir_names: dict[int, str] = {}
    if dir_cat_ids:
        dir_cats = (await db.execute(
            select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(dir_cat_ids))
        )).all()
        dir_names = {r.id: r.name for r in dir_cats}

    # ----- Закупки (obligations + paid) -----
    OBL_STATUSES = ("contracted", "delivered", "paid")
    purchases_q = select(Purchase).where(
        Purchase.subsidy_id == subsidy_id,
        Purchase.status.in_(OBL_STATUSES),
    )
    purchases = (await db.execute(purchases_q)).scalars().all()

    # Разбиваем по месяцам за target_year
    obligations_monthly: dict[int, _Dec] = {}   # month -> Decimal
    paid_monthly: dict[int, _Dec] = {}

    for p in purchases:
        # obligations — по obligation_date, только contracted/delivered/paid
        obl_d = _obligation_date(p)
        if obl_d and obl_d.year == target_year:
            amt = _Dec(str(p.contract_price or 0))
            obligations_monthly[obl_d.month] = (
                obligations_monthly.get(obl_d.month, _Dec(0)) + amt
            )
        # paid — по payment_doc_date, только status=paid
        if p.status == "paid" and p.payment_doc_date:
            pd = p.payment_doc_date
            if hasattr(pd, 'date'):
                pd = pd.date()
            if pd.year == target_year:
                amt_p = _Dec(str(p.payment_amount or 0))
                paid_monthly[pd.month] = paid_monthly.get(pd.month, _Dec(0)) + amt_p

    # ----- Сборка ответа: 12 месяцев -----
    months_out = []
    cum_obl = _Dec(0)
    cum_paid = _Dec(0)
    annual_plan = _Dec(0)
    annual_obl = _Dec(0)
    annual_paid = _Dec(0)

    quarter_plan: dict[int, _Dec] = {}
    quarter_obl: dict[int, _Dec]  = {}
    quarter_paid: dict[int, _Dec] = {}

    for m in range(1, 13):
        q = (m - 1) // 3 + 1
        plan_amt  = plan_monthly.get((target_year, m), _Dec(0))
        obl_amt   = obligations_monthly.get(m, _Dec(0))
        paid_amt  = paid_monthly.get(m, _Dec(0))

        cum_obl  += obl_amt
        cum_paid += paid_amt
        debt_cum  = cum_obl - cum_paid

        annual_plan += plan_amt
        annual_obl  += obl_amt
        annual_paid += paid_amt

        quarter_plan[q]  = quarter_plan.get(q, _Dec(0)) + plan_amt
        quarter_obl[q]   = quarter_obl.get(q, _Dec(0)) + obl_amt
        quarter_paid[q]  = quarter_paid.get(q, _Dec(0)) + paid_amt

        # Разбивка по directions для этого месяца
        dir_breakdown = {}
        for dir_id, dir_data in dir_monthly.items():
            dir_val = dir_data.get((target_year, m), _Dec(0))
            if dir_val:
                dir_breakdown[str(dir_id)] = {
                    "name": dir_names.get(dir_id, ""),
                    "plan": float(dir_val),
                }

        months_out.append({
            "month": m,
            "plan": float(plan_amt),
            "obligations": float(obl_amt),
            "paid": float(paid_amt),
            "debt_cumulative": float(debt_cum),
            "variance_plan_obligation": float(plan_amt - obl_amt),
            "variance_plan_paid": float(plan_amt - paid_amt),
            "directions": dir_breakdown,
        })

    # Квартальные подытоги
    quarters_out = []
    for q in range(1, 5):
        q_plan = quarter_plan.get(q, _Dec(0))
        q_obl  = quarter_obl.get(q, _Dec(0))
        q_paid = quarter_paid.get(q, _Dec(0))
        quarters_out.append({
            "quarter": q,
            "plan": float(q_plan),
            "obligations": float(q_obl),
            "paid": float(q_paid),
            "variance_plan_obligation": float(q_plan - q_obl),
            "variance_plan_paid": float(q_plan - q_paid),
        })

    return {
        "subsidy_id": subsidy_id,
        "year": target_year,
        "months": months_out,
        "quarters": quarters_out,
        "annual": {
            "plan": float(annual_plan),
            "obligations": float(annual_obl),
            "paid": float(annual_paid),
            "variance_plan_obligation": float(annual_plan - annual_obl),
            "variance_plan_paid": float(annual_plan - annual_paid),
        },
    }
