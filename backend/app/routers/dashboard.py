from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, extract, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.routers.subsidies import calculate_budget_from_categories
from app.config import settings
from decimal import Decimal

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


def _apply_subsidy_org_filter(query, user: User):
    """Filter subsidies by org_ids."""
    org_ids = get_org_filter(user)
    if org_ids is not None:
        query = query.where(Subsidy.org_id.in_(org_ids))
    return query


def _apply_purchase_org_filter(query, user: User):
    """Filter purchases via subsidy.org_id."""
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
):
    org_ids = get_org_filter(current_user)

    # Get categories filtered by org
    cat_q = select(FeoCategory).order_by(FeoCategory.level, FeoCategory.id)
    if org_ids is not None:
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
    agg_q = _apply_purchase_org_filter(agg_q, current_user)
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
    total_obl_q = _apply_purchase_org_filter(total_obl_q, current_user)
    total_obligations = float((await db.execute(total_obl_q)).scalar() or 0)

    total_pay_q = select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
    total_pay_q = _apply_purchase_org_filter(total_pay_q, current_user)
    total_payments = float((await db.execute(total_pay_q)).scalar() or 0)

    return {
        "subsidy_limit": settings.SUBSIDY_LIMIT,
        "total_obligations": total_obligations,
        "total_payments": total_payments,
        "remaining": settings.SUBSIDY_LIMIT - total_obligations,
        "categories": roots
    }


@router.get("/charts")
async def dashboard_charts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_ids = get_org_filter(current_user)

    # Status counts for pie chart (filtered)
    status_q = select(Purchase.status, func.count(Purchase.id).label("cnt")).group_by(Purchase.status)
    status_q = _apply_purchase_org_filter(status_q, current_user)
    status_result = await db.execute(status_q)
    status_counts = {row.status: row.cnt for row in status_result}

    # Per-subsidy aggregated purchase data (filtered)
    subsidy_q = (
        select(
            Subsidy.id, Subsidy.name, Subsidy.year, Subsidy.budget,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total_planned"),
            func.coalesce(func.sum(
                case((Purchase.status.in_(["contracted", "delivered", "paid"]), Purchase.contract_price), else_=None)
            ), 0).label("total_confirmed"),
            func.coalesce(func.sum(
                case((Purchase.status == "paid", Purchase.payment_amount), else_=None)
            ), 0).label("total_paid"),
            func.coalesce(func.sum(
                case((Purchase.status.in_(["confirmed", "work_in_progress"]), Purchase.planned_total_price), else_=None)
            ), 0).label("total_plan_schedule"),
            func.coalesce(func.sum(
                case(
                    (
                        and_(
                            Purchase.status.in_(["contracted", "delivered", "paid"]),
                            Purchase.purchase_contract_type.in_(["framework_cumulative", "framework_with_amount"])
                        ),
                        Purchase.planned_total_price
                    ),
                    (
                        and_(
                            Purchase.status.in_(["contracted", "delivered", "paid"]),
                            Purchase.purchase_contract_type == "single"
                        ),
                        Purchase.contract_price
                    ),
                    else_=None
                )
            ), 0).label("total_ordered"),
        )
        .select_from(Subsidy)
        .outerjoin(Purchase, Purchase.subsidy_id == Subsidy.id)
        .group_by(Subsidy.id, Subsidy.name, Subsidy.year, Subsidy.budget)
        .order_by(Subsidy.year.desc(), Subsidy.name)
    )
    if org_ids is not None:
        subsidy_q = subsidy_q.where(Subsidy.org_id.in_(org_ids))
    subsidy_result = await db.execute(subsidy_q)

    subsidy_stats = []
    for row in subsidy_result:
        calc = await calculate_budget_from_categories(db, row.id)
        # Get contractor info
        sub_obj = await db.get(Subsidy, row.id)
        contractor_name = None
        contractor_inn = None
        if sub_obj and sub_obj.contractor_id:
            contractor = await db.get(Contractor, sub_obj.contractor_id)
            if contractor:
                contractor_name = contractor.name
                contractor_inn = contractor.inn
        subsidy_stats.append({
            "id": row.id,
            "name": row.name,
            "year": row.year,
            "budget": float(row.budget),
            "calculated_budget": calc,
            "total_planned": float(row.total_planned),
            "total_confirmed": float(row.total_confirmed),
            "total_paid": float(row.total_paid),
            "total_plan_schedule": float(row.total_plan_schedule),
            "total_ordered": float(row.total_ordered),
            "feo_budget_total": calc,
            "feo_filled": calc > 0,
            "contractor_id": sub_obj.contractor_id if sub_obj else None,
            "contractor_name": contractor_name,
            "contractor_inn": contractor_inn,
        })

    return {
        "status_counts": status_counts,
        "subsidy_stats": subsidy_stats,
    }


@router.get("/analytics")
async def analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    subsidy_ids: Optional[str] = Query(None),
):
    today = date.today()
    org_ids = get_org_filter(current_user)
    sid_filter = [int(x) for x in subsidy_ids.split(",") if x.strip()] if subsidy_ids else None

    def _pf(q):
        """Apply purchase org + subsidy filter inline."""
        if org_ids is not None:
            q = q.where(Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
            ))
        if sid_filter:
            q = q.where(Purchase.subsidy_id.in_(sid_filter))
        return q

    # 1. Purchase funnel
    STATUS_ORDER = ["wishes", "plan_schedule", "confirmed", "work_in_progress", "contracted", "delivered", "paid"]
    funnel_result = await db.execute(_pf(
        select(Purchase.status, func.count(Purchase.id).label("cnt"),
               func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .group_by(Purchase.status)
    ))
    funnel_raw = {r.status: {"count": r.cnt, "total": float(r.total)} for r in funnel_result}
    funnel = [{"status": s, "count": funnel_raw.get(s, {}).get("count", 0),
               "total": funnel_raw.get(s, {}).get("total", 0.0)} for s in STATUS_ORDER]

    # 2. Monthly paid amounts (last 12 months)
    monthly_result = await db.execute(_pf(
        select(
            extract("year", Purchase.payment_doc_date).label("y"),
            extract("month", Purchase.payment_doc_date).label("m"),
            func.coalesce(func.sum(Purchase.payment_amount), 0).label("total"),
        )
        .where(Purchase.payment_doc_date != None)
        .group_by("y", "m")
        .order_by("y", "m")
    ))
    monthly = [{"year": int(r.y), "month": int(r.m), "total": float(r.total)} for r in monthly_result]

    # 3. Top 10 contractors by total purchase value
    top_result = await db.execute(_pf(
        select(
            Contractor.name,
            func.count(Purchase.id).label("cnt"),
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"),
        )
        .join(Contractor, Purchase.contractor_id == Contractor.id)
        .group_by(Contractor.name)
        .order_by(func.sum(Purchase.planned_total_price).desc())
        .limit(10)
    ))
    top_contractors = [{"name": r.name, "count": r.cnt, "total": float(r.total)} for r in top_result]

    # 4. Upcoming deliveries (next 30 days)
    upcoming_result = await db.execute(_pf(
        select(func.count(Purchase.id).label("cnt"),
               func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .where(Purchase.delivery_date.between(today, today + timedelta(days=30)))
    ))
    upcoming = upcoming_result.one()

    # 5. Economy (saved money)
    economy_result = await db.execute(_pf(
        select(func.coalesce(func.sum(Purchase.planned_total_price - Purchase.contract_price), 0))
        .where(Purchase.contract_price != None)
        .where(Purchase.contract_price > 0)
    ))
    economy = float(economy_result.scalar() or 0)

    # 6. Overdue purchases (execution_term past, not paid/delivered)
    overdue_result = await db.execute(_pf(
        select(func.count(Purchase.id))
        .where(Purchase.execution_term < today)
        .where(Purchase.status.notin_(["paid", "delivered"]))
    ))
    overdue_count = overdue_result.scalar() or 0

    # 7. Upcoming deadlines (next 30 days) — detailed list
    deadlines_result = await db.execute(_pf(
        select(Purchase.id, Purchase.subject, Purchase.item_name,
               Purchase.purchase_number, Purchase.execution_term, Purchase.status)
        .where(Purchase.execution_term.between(today, today + timedelta(days=30)))
        .where(Purchase.status.notin_(["paid", "delivered"]))
        .order_by(Purchase.execution_term)
        .limit(20)
    ))
    upcoming_deadlines = [
        {"id": r.id, "name": r.subject or r.item_name or f"Закупка #{r.purchase_number or r.id}",
         "purchase_number": r.purchase_number, "execution_term": str(r.execution_term), "status": r.status}
        for r in deadlines_result
    ]

    # 8. Purchase method distribution
    method_result = await db.execute(_pf(
        select(Purchase.purchase_method, func.count(Purchase.id).label("cnt"))
        .group_by(Purchase.purchase_method)
    ))
    method_distribution = {(r.purchase_method or "unknown"): r.cnt for r in method_result}

    # 9. Plan vs Fact per subsidy
    pf_q = (
        select(
            Subsidy.name,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("plan"),
            func.coalesce(func.sum(
                case((Purchase.status.in_(["contracted", "delivered", "paid"]), Purchase.contract_price), else_=None)
            ), 0).label("contracted"),
            func.coalesce(func.sum(
                case((Purchase.status == "paid", Purchase.payment_amount), else_=None)
            ), 0).label("paid"),
        )
        .select_from(Subsidy)
        .outerjoin(Purchase, Purchase.subsidy_id == Subsidy.id)
        .group_by(Subsidy.id, Subsidy.name)
        .order_by(Subsidy.name)
    )
    if org_ids is not None:
        pf_q = pf_q.where(Subsidy.org_id.in_(org_ids))
    if sid_filter:
        pf_q = pf_q.where(Subsidy.id.in_(sid_filter))
    pf_result = await db.execute(pf_q)
    plan_fact = [
        {"subsidy": r.name, "plan": float(r.plan), "contracted": float(r.contracted), "paid": float(r.paid)}
        for r in pf_result
    ]

    return {
        "funnel": funnel,
        "monthly_payments": monthly,
        "top_contractors": top_contractors,
        "upcoming_deliveries": {"count": upcoming.cnt, "total": float(upcoming.total)},
        "economy": economy,
        "overdue_count": overdue_count,
        "upcoming_deadlines": upcoming_deadlines,
        "method_distribution": method_distribution,
        "plan_fact": plan_fact,
    }


@router.get("/financial-plan")
async def get_financial_plan(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Возвращает помесячную и поквартальную разбивку ожидаемых выплат с категориями plan/committed."""
    q = select(Purchase)
    q = _apply_purchase_org_filter(q, current_user)
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    rows = (await db.execute(q)).scalars().all()

    PLAN_STATUSES = {'planned', 'confirmed', 'wishes', 'plan_schedule'}
    COMMITTED_STATUSES = {'contracted', 'ordered', 'delivered', 'paid', 'work_in_progress'}

    by_month_plan: dict = {}
    by_month_committed: dict = {}
    by_quarter_plan: dict = {}
    by_quarter_committed: dict = {}

    for p in rows:
        d = _expected_payment_date(p)
        if not d:
            continue
        amount = float(p.contract_price or p.planned_total_price or 0)
        if amount == 0:
            continue

        ym = f"{d.year}-{d.month:02d}"
        yq = f"{d.year}-Q{(d.month - 1) // 3 + 1}"

        if p.status in PLAN_STATUSES:
            by_month_plan[ym] = by_month_plan.get(ym, 0) + amount
            by_quarter_plan[yq] = by_quarter_plan.get(yq, 0) + amount
        elif p.status in COMMITTED_STATUSES:
            by_month_committed[ym] = by_month_committed.get(ym, 0) + amount
            by_quarter_committed[yq] = by_quarter_committed.get(yq, 0) + amount

    return {
        "by_month": {
            "plan":      [{"period": k, "amount": v} for k, v in sorted(by_month_plan.items())],
            "committed": [{"period": k, "amount": v} for k, v in sorted(by_month_committed.items())],
        },
        "by_quarter": {
            "plan":      [{"period": k, "amount": v} for k, v in sorted(by_quarter_plan.items())],
            "committed": [{"period": k, "amount": v} for k, v in sorted(by_quarter_committed.items())],
        },
    }


@router.get("/financial-plan/details")
async def get_financial_plan_details(
    period: str = Query(..., description="'YYYY-MM' для месяца или 'YYYY-Qn' для квартала"),
    category: str = Query(..., regex="^(plan|committed)$"),
    granularity: str = Query("month", regex="^(month|quarter)$"),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список закупок попавших в указанный период+категорию."""
    PLAN_STATUSES = {"planned", "confirmed", "wishes", "plan_schedule"}
    COMMITTED_STATUSES = {"contracted", "ordered", "delivered", "paid", "work_in_progress"}
    target_statuses = PLAN_STATUSES if category == "plan" else COMMITTED_STATUSES

    q = select(Purchase).where(Purchase.status.in_(target_statuses))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)

    q = _apply_purchase_org_filter(q, current_user)
    q = q.options(selectinload(Purchase.contractor))

    rows = (await db.execute(q)).scalars().all()

    result = []
    for p in rows:
        d = _expected_payment_date(p)
        if not d:
            continue
        if granularity == "month":
            row_period = f"{d.year}-{d.month:02d}"
        else:
            row_period = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        if row_period != period:
            continue

        amount = float(p.contract_price or p.planned_total_price or 0)
        if amount == 0:
            continue

        result.append({
            "id": p.id,
            "purchase_number": p.purchase_number,
            "subject": p.subject or "",
            "contractor_name": (p.contractor.name if p.contractor else None) or "—",
            "amount": amount,
            "status": p.status,
            "expected_date": d.isoformat(),
            "contract_number": p.contract_number,
        })

    result.sort(key=lambda r: (r["expected_date"], -r["amount"]))
    return {"period": period, "category": category, "granularity": granularity, "items": result}


@router.get("/financial-plan/export.xlsx")
async def export_financial_plan_xlsx(
    granularity: str = Query("month", regex="^(month|quarter)$"),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Полная выгрузка всех закупок с группировкой по периоду и категории plan/committed."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from datetime import datetime as dt

    PLAN_STATUSES = {"planned", "confirmed", "wishes", "plan_schedule"}
    COMMITTED_STATUSES = {"contracted", "ordered", "delivered", "paid", "work_in_progress"}

    q = select(Purchase).where(Purchase.status.in_(PLAN_STATUSES | COMMITTED_STATUSES))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    q = _apply_purchase_org_filter(q, current_user)
    q = q.options(selectinload(Purchase.contractor))

    rows = (await db.execute(q)).scalars().all()

    STATUS_LABELS = {
        "planned": "Запланирован", "confirmed": "Подтверждён", "wishes": "Заявка",
        "plan_schedule": "План-график",
        "contracted": "Заключён договор", "ordered": "Заказано", "delivered": "Поставлено",
        "paid": "Оплачено", "work_in_progress": "В работе",
    }

    grouped: dict = {}
    for p in rows:
        d = _expected_payment_date(p)
        if not d:
            continue
        amount = float(p.contract_price or p.planned_total_price or 0)
        if amount == 0:
            continue
        if granularity == "month":
            period_key = f"{d.year}-{d.month:02d}"
        else:
            period_key = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        category = "plan" if p.status in PLAN_STATUSES else "committed"
        grouped.setdefault((period_key, category), []).append({
            "purchase_number": p.purchase_number or "",
            "subject": p.subject or "",
            "contractor_name": (p.contractor.name if p.contractor else "—"),
            "amount": amount,
            "status": STATUS_LABELS.get(p.status, p.status),
            "expected_date": d.isoformat(),
            "contract_number": p.contract_number or "",
        })

    wb = Workbook()
    ws = wb.active
    ws.title = "Финплан"

    ws['A1'] = f"Финансовый план — {'по месяцам' if granularity == 'month' else 'по кварталам'}"
    ws['A1'].font = Font(size=14, bold=True)
    ws.merge_cells('A1:H1')

    headers = ["Период", "Категория", "№ закупки", "Предмет", "Контрагент", "Дата", "Статус", "Сумма, ₽"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_idx = 4
    period_totals: dict = {}

    for (period_key, category) in sorted(grouped.keys()):
        items = grouped[(period_key, category)]
        cat_label = "Плановые" if category == "plan" else "Принятые обязательства"
        cat_color = "FEF3C7" if category == "plan" else "D1FAE5"

        for item in items:
            ws.cell(row=row_idx, column=1, value=period_key)
            ws.cell(row=row_idx, column=2, value=cat_label)
            ws.cell(row=row_idx, column=3, value=item["purchase_number"])
            ws.cell(row=row_idx, column=4, value=item["subject"])
            ws.cell(row=row_idx, column=5, value=item["contractor_name"])
            ws.cell(row=row_idx, column=6, value=item["expected_date"])
            ws.cell(row=row_idx, column=7, value=item["status"])
            ws.cell(row=row_idx, column=8, value=item["amount"])
            for col in range(1, 9):
                ws.cell(row=row_idx, column=col).fill = PatternFill(
                    start_color=cat_color, end_color=cat_color, fill_type="solid"
                )
            ws.cell(row=row_idx, column=8).number_format = '#,##0.00 ₽'
            row_idx += 1

            period_totals.setdefault(period_key, {"plan": 0.0, "committed": 0.0})
            period_totals[period_key][category] += item["amount"]

    row_idx += 1
    totals_title = ws.cell(row=row_idx, column=1, value="ИТОГО ПО ПЕРИОДАМ")
    totals_title.font = Font(bold=True, size=12)
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Период").font = Font(bold=True)
    ws.cell(row=row_idx, column=2, value="Плановые").font = Font(bold=True)
    ws.cell(row=row_idx, column=3, value="Принятые").font = Font(bold=True)
    ws.cell(row=row_idx, column=4, value="Всего").font = Font(bold=True)
    row_idx += 1

    for pk in sorted(period_totals.keys()):
        t = period_totals[pk]
        ws.cell(row=row_idx, column=1, value=pk)
        plan_cell = ws.cell(row=row_idx, column=2, value=t["plan"])
        plan_cell.number_format = '#,##0.00 ₽'
        committed_cell = ws.cell(row=row_idx, column=3, value=t["committed"])
        committed_cell.number_format = '#,##0.00 ₽'
        total_cell = ws.cell(row=row_idx, column=4, value=t["plan"] + t["committed"])
        total_cell.number_format = '#,##0.00 ₽'
        row_idx += 1

    for col_letter, width in [('A', 12), ('B', 22), ('C', 12), ('D', 50), ('E', 30), ('F', 12), ('G', 18), ('H', 16)]:
        ws.column_dimensions[col_letter].width = width

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    filename = f"finplan_{granularity}_{dt.now().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/financial-plan/details/export.xlsx")
async def export_financial_plan_details_xlsx(
    period: str = Query(...),
    category: str = Query(..., regex="^(plan|committed)$"),
    granularity: str = Query("month", regex="^(month|quarter)$"),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Excel выгрузка одной группы (период+категория) — содержимое drill-down диалога."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    PLAN_STATUSES = {"planned", "confirmed", "wishes", "plan_schedule"}
    COMMITTED_STATUSES = {"contracted", "ordered", "delivered", "paid", "work_in_progress"}
    target_statuses = PLAN_STATUSES if category == "plan" else COMMITTED_STATUSES

    q = select(Purchase).where(Purchase.status.in_(target_statuses))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    q = _apply_purchase_org_filter(q, current_user)
    q = q.options(selectinload(Purchase.contractor))

    rows = (await db.execute(q)).scalars().all()

    STATUS_LABELS = {
        "planned": "Запланирован", "confirmed": "Подтверждён", "wishes": "Заявка",
        "plan_schedule": "План-график",
        "contracted": "Заключён договор", "ordered": "Заказано", "delivered": "Поставлено",
        "paid": "Оплачено", "work_in_progress": "В работе",
    }

    items = []
    for p in rows:
        d = _expected_payment_date(p)
        if not d:
            continue
        if granularity == "month":
            row_period = f"{d.year}-{d.month:02d}"
        else:
            row_period = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        if row_period != period:
            continue
        amount = float(p.contract_price or p.planned_total_price or 0)
        if amount == 0:
            continue
        items.append({
            "purchase_number": p.purchase_number or "",
            "subject": p.subject or "",
            "contractor_name": (p.contractor.name if p.contractor else "—"),
            "amount": amount,
            "status": STATUS_LABELS.get(p.status, p.status),
            "expected_date": d.isoformat(),
            "contract_number": p.contract_number or "",
        })

    items.sort(key=lambda r: (r["expected_date"], -r["amount"]))

    wb = Workbook()
    ws = wb.active
    cat_label = "Плановые" if category == "plan" else "Принятые обязательства"
    ws.title = f"{cat_label[:20]} {period}"

    ws['A1'] = f"Финплан — {cat_label} — {period}"
    ws['A1'].font = Font(size=14, bold=True)
    ws.merge_cells('A1:G1')

    headers = ["№", "Предмет", "Контрагент", "Дата", "Статус", "№ договора", "Сумма, ₽"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    total = 0.0
    for i, item in enumerate(items, start=4):
        ws.cell(row=i, column=1, value=item["purchase_number"])
        ws.cell(row=i, column=2, value=item["subject"])
        ws.cell(row=i, column=3, value=item["contractor_name"])
        ws.cell(row=i, column=4, value=item["expected_date"])
        ws.cell(row=i, column=5, value=item["status"])
        ws.cell(row=i, column=6, value=item["contract_number"])
        amt_cell = ws.cell(row=i, column=7, value=item["amount"])
        amt_cell.number_format = '#,##0.00 ₽'
        total += item["amount"]

    total_row = 4 + len(items) + 1
    ws.cell(row=total_row, column=1, value="ИТОГО").font = Font(bold=True)
    total_cell = ws.cell(row=total_row, column=7, value=total)
    total_cell.font = Font(bold=True)
    total_cell.number_format = '#,##0.00 ₽'
    total_color = "FEF3C7" if category == "plan" else "D1FAE5"
    total_cell.fill = PatternFill(start_color=total_color, end_color=total_color, fill_type="solid")

    for col_letter, width in [('A', 12), ('B', 50), ('C', 30), ('D', 12), ('E', 18), ('F', 16), ('G', 16)]:
        ws.column_dimensions[col_letter].width = width

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    filename = f"finplan_{period}_{category}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
