"""GET /api/dashboard/charts — сосед dashboard.py (Правило №5, резка 1641→core, 2026-09-08).

Виджеты/сводки закупок и субсидий для дашборда: статусы (pie), per-subsidy
агрегаты, «Заключено договоров», накопительные виджеты (plan_schedule/work/
ordered/delivered/paid/contracts), «субсидии у потолка». Помесячное начисление
«Заказано» по ежемесячным закупкам вынесено в
app/services/dashboard_monthly_accrual.py (чистый агрегат без своей логики
видимости — фильтр передаётся вызовом снаружи).
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, and_, or_, literal
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.routers.subsidies import calculate_budgets_bulk, _calculate_spent_bulk, _calculate_planned_amounts_bulk, _calculate_feo_planned_tree_bulk
from app.services.feo_plan import calculate_ceiling_forecasts_bulk
# Правило №6: та же формула фолбэка, что subsidies.py list/detail/create/approve/update.
from app.services.subsidy_budget import effective_subsidy_budget
# ПРАВИЛО №6 (2026-09-05): единый расчёт «суммы закупки» по стадии — см. dashboard.py
# для полного пояснения; effective_amount_expr/aggregate_scope_expr уже применены
# во всех местах ниже, где раньше были точечные COALESCE(...).
from app.services.purchase_amounts import effective_amount_expr
from app.services.dashboard_monthly_accrual import compute_monthly_ordered_map
from app.routers.dashboard import _apply_purchase_org_filter

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/charts")
async def dashboard_charts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None),
):
    org_ids = get_org_filter(current_user)
    # «Субсидии»: орг-админ-роль + гранты. «Дашборд»: двухуровневая видимость по вкладке dashboard.
    managed = scope == "managed"
    dashboard = scope in ("dashboard", "dashboard.radar", "plan")
    visible_subsidy_ids = None
    if managed:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db)
    elif dashboard:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db, scope)
    use_sids = managed or dashboard

    # Status counts for pie chart (filtered)
    status_q = select(Purchase.status, func.count(Purchase.id).label("cnt")).group_by(Purchase.status)
    if use_sids:
        status_q = _apply_purchase_org_filter(status_q, current_user, subsidy_ids=visible_subsidy_ids)
    else:
        status_q = _apply_purchase_org_filter(status_q, current_user, org_ids)
    status_result = await db.execute(status_q)
    status_counts = {row.status: row.cnt for row in status_result}

    # Per-subsidy aggregated purchase data (filtered)
    # Владелец (2026-09-06) — решение по рамочным договорам в итогах: голова
    # с предельной суммой несёт «законтрактовано» целиком (её effective уже
    # = Contract.max_amount, см. effective_amount_expr()), «заказано» — ТОЛЬКО
    # по её детям; накопительная голова (без предела) сама не несёт суммы —
    # только собирает детей. Чтобы Σ по субсидии не задваивала голову и её
    # детей — исключение реализовано ЧЕРЕЗ JOIN-условие (не WHERE), иначе
    # субсидии, у которых ВСЕ закупки внутри такого условия, пропали бы из
    # результата целиком. См. app.services.purchase_amounts.aggregate_scope_expr
    # (единый предикат, применяется тем же образом в subsidies.py::
    # _calculate_spent(_bulk) и feo_categories.py::get_purchase_totals).
    from app.services.purchase_amounts import aggregate_scope_expr as _aggregate_scope_expr
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
                case((Purchase.status == "work_in_progress", Purchase.planned_total_price), else_=None)
            ), 0).label("total_plan_schedule"),
            # «Заказано» = закупки, реально дошедшие до стадии «Заказано» и дальше
            # (ordered/delivered/paid) — НЕ 'contracted' (договор заключён, но ещё не заказано).
            # Сумма = COALESCE(contract_price, planned_total_price), без ветвления по
            # purchase_contract_type (раньше закупки с purchase_contract_type IS NULL тихо
            # выпадали из суммы — второй дефект старой формулы).
            # Ежемесячные закупки (is_monthly_payment=true) сюда НЕ входят — для них своя
            # помесячная логика начисления (см. monthly_ordered_map ниже), иначе их полная
            # сумма договора задвоилась бы с прогрессивным начислением по месяцам.
            func.coalesce(func.sum(
                case(
                    (
                        and_(
                            Purchase.status.in_(["ordered", "delivered", "paid"]),
                            Purchase.is_monthly_payment.isnot(True),
                        ),
                        effective_amount_expr()
                    ),
                    else_=None
                )
            ), 0).label("total_ordered"),
            # Per-subsidy basket mirrors (для total_work / total_delivered / total_delivered_unpaid)
            func.coalesce(func.sum(
                case(
                    (Purchase.status.in_(["contracted", "ordered"]),
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("w_ordered"),
            # Строгий «Заказано» — ТОЛЬКО статус ordered (без contracted). w_ordered выше
            # (contracted+ordered) НЕ трогаем — он используется в total_work, где заключённые
            # договоры обязаны входить в «Ведётся работа». Эта колонка — только для widget.ordered,
            # чтобы карточка «Заказано» на дашборде означала то же самое, что и total_ordered.
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "ordered",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("w_ordered_strict"),
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "delivered",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("w_delivered"),
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "paid",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("w_paid"),
            # Per-subsidy basket counts/amounts for per-subsidy widget
            func.coalesce(func.sum(
                case((Purchase.status == "plan_schedule", Purchase.planned_total_price), else_=None)
            ), 0).label("sp_amt"),
            func.coalesce(func.count(
                case((Purchase.status == "plan_schedule", Purchase.id), else_=None)
            ), 0).label("sp_cnt"),
            func.coalesce(func.count(
                case((Purchase.status == "work_in_progress", Purchase.id), else_=None)
            ), 0).label("sw_cnt"),
            func.coalesce(func.count(
                case((Purchase.status.in_(["contracted", "ordered"]), Purchase.id), else_=None)
            ), 0).label("so_cnt"),
            func.coalesce(func.count(
                case((Purchase.status == "ordered", Purchase.id), else_=None)
            ), 0).label("so_cnt_strict"),
            func.coalesce(func.count(
                case((Purchase.status == "delivered", Purchase.id), else_=None)
            ), 0).label("sd_cnt"),
            func.coalesce(func.count(
                case((Purchase.status == "paid", Purchase.id), else_=None)
            ), 0).label("spd_cnt"),
        )
        .select_from(Subsidy)
        .outerjoin(Purchase, and_(Purchase.subsidy_id == Subsidy.id, _aggregate_scope_expr()))
        .group_by(Subsidy.id, Subsidy.name, Subsidy.year, Subsidy.budget)
        .order_by(Subsidy.year.desc(), Subsidy.name)
    )
    if use_sids:
        # Двухуровневая видимость: орг-дефолт + пер-субсидийный override (managed=«Субсидии», dashboard=«Дашборд»).
        if visible_subsidy_ids is not None:
            subsidy_q = subsidy_q.where(Subsidy.id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        subsidy_q = subsidy_q.where(Subsidy.org_id.in_(org_ids))
    subsidy_result = await db.execute(subsidy_q)

    # FEO planned sum per subsidy
    feo_planned_q = (
        select(
            FeoCategory.subsidy_id,
            func.coalesce(func.sum(FeoPlannedItem.amount), 0).label("feo_planned_sum"),
        )
        .join(FeoPlannedItem, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoPlannedItem.is_active == True)
        .group_by(FeoCategory.subsidy_id)
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            feo_planned_q = feo_planned_q.where(FeoCategory.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        feo_planned_q = feo_planned_q.where(FeoCategory.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    feo_planned_result = await db.execute(feo_planned_q)
    feo_planned_map: dict[int, float] = {
        row.subsidy_id: float(row.feo_planned_sum)
        for row in feo_planned_result
    }

    subsidy_rows = subsidy_result.all()
    sid_list = [row.id for row in subsidy_rows]
    # Batch вместо N+1: бюджеты, субсидии и контрагенты одним IN-запросом каждый
    budgets = await calculate_budgets_bulk(db, sid_list)
    # Phase 31-05: canonical spent + planned_amounts for D-17 (единый источник)
    spent_map = await _calculate_spent_bulk(db, sid_list)
    planned_amounts_map = await _calculate_planned_amounts_bulk(db, sid_list)
    # Единый источник «Запланировано»: план дерева ФЭО = ручные позиции + позиции из заявок плана закупок.
    # Совпадает с KPI «Запланировано» на вкладке «Субсидии» (selectedPlannedTotal).
    planned_tree_map = await _calculate_feo_planned_tree_bulk(db, sid_list)
    # Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
    # потолку субсидии» — батчем на весь список (см. app/services/feo_plan.py
    # calculate_ceiling_forecasts_bulk).
    ceiling_forecasts = await calculate_ceiling_forecasts_bulk(db, sid_list)
    sub_objs = {}
    if subsidy_rows:
        sub_objs = {
            s.id: s for s in (await db.execute(
                select(Subsidy).where(Subsidy.id.in_(sid_list))
            )).scalars().all()
        }
    contractor_ids = {s.contractor_id for s in sub_objs.values() if s.contractor_id}
    contractors = {}
    if contractor_ids:
        contractors = {
            c.id: c for c in (await db.execute(
                select(Contractor).where(Contractor.id.in_(contractor_ids))
            )).scalars().all()
        }

    # Виджет «Заключено договоров»: active-договоры, сумма по типу.
    # Правило РАЗНОЕ для двух типов (правка 2026-08-04 — рамочные с суммой не требуют закупок):
    #   single → max_amount договора, ТОЛЬКО если EXISTS хотя бы одна привязанная закупка
    #     (purchases.contract_id) с нужным статусом. Разовый договор подписывается ПОД
    #     конкретную закупку — без неё запись осиротевшая и не должна раздувать виджет
    #     (было замечено на ЦентрПоиск_2026: 53 млн вместо фактических 402 тыс., см. баг-репорт 2026-08).
    #   framework_with_amount → max_amount договора БЕЗУСЛОВНО, просто при status='active'.
    #     Рамочный договор с суммой подписывается заранее, закупки по нему делаются постепенно
    #     позже — поэтому он уже «заключён», даже если ни одной закупки по нему ещё не заведено.
    #   framework_cumulative → SUM(COALESCE(p.contract_price, p.planned_total_price))
    #     по закупкам с contract_id=договор и status in (contracted,ordered,delivered,paid)
    _contracted_purchase_exists = (
        select(literal(1))
        .where(Purchase.contract_id == Contract.id)
        .where(Purchase.status.in_(["contracted", "ordered", "delivered", "paid"]))
    )
    contract_single_q = (
        select(
            Contract.subsidy_id,
            func.coalesce(func.sum(Contract.max_amount), 0).label("amt"),
            func.count(Contract.id).label("cnt"),
        )
        .where(Contract.status == "active")
        .where(
            or_(
                and_(Contract.contract_type == "single", _contracted_purchase_exists.exists()),
                Contract.contract_type == "framework_with_amount",
            )
        )
        .group_by(Contract.subsidy_id)
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            contract_single_q = contract_single_q.where(Contract.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        contract_single_q = contract_single_q.where(Contract.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    cs_rows = (await db.execute(contract_single_q)).all()

    # framework_cumulative: aggr по закупкам привязанным к таким договорам
    contract_fc_q = (
        select(
            Purchase.subsidy_id,
            func.coalesce(func.sum(
                effective_amount_expr()
            ), 0).label("amt"),
            # count distinct contracts (not purchases)
            func.count(func.distinct(Purchase.contract_id)).label("cnt"),
        )
        .join(Contract, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Purchase.status.in_(["contracted", "ordered", "delivered", "paid"]))
        .group_by(Purchase.subsidy_id)
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            contract_fc_q = contract_fc_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        contract_fc_q = contract_fc_q.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    cfc_rows = (await db.execute(contract_fc_q)).all()

    # Собрать contracts_map: subsidy_id → float (сумма по обеим частям)
    contracts_map: dict[int, float] = {}
    contracts_cnt_map: dict[int, int] = {}
    for r in cs_rows:
        sid = r.subsidy_id
        contracts_map[sid] = contracts_map.get(sid, 0.0) + float(r.amt)
        contracts_cnt_map[sid] = contracts_cnt_map.get(sid, 0) + int(r.cnt)
    for r in cfc_rows:
        sid = r.subsidy_id
        contracts_map[sid] = contracts_map.get(sid, 0.0) + float(r.amt)
        contracts_cnt_map[sid] = contracts_cnt_map.get(sid, 0) + int(r.cnt)

    # Глобальные итоги — сумма по регруппированным строкам (бит-в-бит эквивалентно прежнему)
    contracts_amt = sum(contracts_map.values())
    contracts_cnt = sum(contracts_cnt_map.values())

    # Накопительный SUM(planned_monthly) по active-договорам, регруппированный по subsidy_id
    mp_q = (
        select(
            Contract.subsidy_id,
            func.coalesce(func.sum(Contract.planned_monthly), 0).label("amt"),
        )
        .where(Contract.status == "active")
        .where(Contract.planned_monthly.isnot(None))
        .group_by(Contract.subsidy_id)
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            mp_q = mp_q.where(Contract.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        mp_q = mp_q.where(Contract.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    mp_map: dict = {}
    for r in (await db.execute(mp_q)).all():
        mp_map[r.subsidy_id] = mp_map.get(r.subsidy_id, 0.0) + float(r.amt)
    # Глобальный итог — сумма по регруппированным строкам (бит-в-бит эквивалентно прежнему скаляру,
    # включая договоры с subsidy_id IS NULL — они попадают в mp_map под ключом None)
    monthly_payments_total = float(sum(mp_map.values()))

    # ── Ежемесячные закупки: начисление «Заказано» по прошедшим месяцам ──────────────
    # Логика вынесена в app.services.dashboard_monthly_accrual.compute_monthly_ordered_map
    # (чистый агрегат, без своей логики видимости, см. докстринг там) — здесь только
    # тот же _apply_purchase_org_filter/use_sids/visible_subsidy_ids/org_ids фильтр, что
    # и остальная часть /charts (basket_q, subsidy_q и т.д.), передан колбэком.
    if use_sids:
        monthly_ordered_map = await compute_monthly_ordered_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids)
        )
    else:
        monthly_ordered_map = await compute_monthly_ordered_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, org_ids)
        )

    subsidy_stats = []
    for row in subsidy_rows:
        calc = budgets.get(row.id, 0.0)
        effective_budget = effective_subsidy_budget(calc, row.budget)
        spent = spent_map.get(row.id, 0.0)
        planned_amt = planned_amounts_map.get(row.id, 0.0)
        # planned_tree = правильное «Запланировано» = план дерева ФЭО (= «Свободно» = budget − planned_tree)
        planned_tree = planned_tree_map.get(row.id, 0.0)
        # «Свободно» = budget − planned_tree (совпадает с панелью ФЭО вкладки «Субсидии»)
        remaining = effective_budget - planned_tree
        # discrepancy-чип показывается только при превышении (planned_tree > budget)
        discrepancy = (effective_budget - planned_tree) if planned_tree > effective_budget else None
        sub_obj = sub_objs.get(row.id)
        contractor_name = None
        contractor_inn = None
        if sub_obj and sub_obj.contractor_id:
            contractor = contractors.get(sub_obj.contractor_id)
            if contractor:
                contractor_name = contractor.name
                contractor_inn = contractor.inn
        subsidy_stats.append({
            "id": row.id,
            "name": row.name,
            "year": row.year,
            "budget": float(row.budget),
            "calculated_budget": effective_budget,
            "total_planned": float(row.total_planned),
            "total_confirmed": float(row.total_confirmed),
            "total_paid": float(row.total_paid),
            "total_plan_schedule": float(row.total_plan_schedule),  # SUM work_in_progress planned_total_price
            # total_ordered = SQL-агрегат по НЕежемесячным (row.total_ordered) + начисление по
            # ежемесячным (monthly_ordered_map) — обязаны складываться в одно число: карточка
            # «Заказано» должна включать месяц, за который услуга уже оказывается прямо сейчас.
            "total_ordered": float(row.total_ordered) + monthly_ordered_map.get(row.id, 0.0),
            # Справочно: какая часть total_ordered выше — из помесячного начисления (для отладки/подписи).
            # УЖЕ ВХОДИТ в total_ordered, не складывать повторно.
            "monthly_ordered_accrued": monthly_ordered_map.get(row.id, 0.0),
            "total_feo_planned": feo_planned_map.get(row.id, 0.0),  # NEW 12-01: SUM FeoPlannedItem.amount
            "planned_tree": planned_tree,  # единый источник: план дерева ФЭО (ручные + заявки)
            "feo_budget_total": effective_budget,
            "feo_filled": calc > 0,
            "contractor_id": sub_obj.contractor_id if sub_obj else None,
            "contractor_name": contractor_name,
            "contractor_inn": contractor_inn,
            # Phase 31-05: canonical budget fields (D-17)
            "remaining": remaining,  # = «Свободно» = budget − planned_tree
            "planned_amount": planned_amt,
            "budget_discrepancy": discrepancy,
            # Per-subsidy work/delivery baskets (зеркала глобальных widgets)
            "total_work": float(row.total_plan_schedule) + float(row.w_ordered) + float(row.w_delivered) + float(row.w_paid),
            "total_contracts": contracts_map.get(row.id, 0.0),
            "total_delivered": float(row.w_delivered) + float(row.w_paid),
            "total_delivered_unpaid": float(row.w_delivered),
            # Per-subsidy widget basket (зеркало формул глобального widgets dict)
            "widget": {
                "plan_schedule": {
                    "amount": float(row.sp_amt) + float(row.total_plan_schedule) + float(row.w_ordered) + float(row.w_delivered) + float(row.w_paid),
                    "count": int(row.sp_cnt) + int(row.sw_cnt) + int(row.so_cnt) + int(row.sd_cnt) + int(row.spd_cnt),
                },
                "work": {
                    "amount": float(row.total_plan_schedule) + float(row.w_ordered) + float(row.w_delivered) + float(row.w_paid),
                    "count": int(row.sw_cnt) + int(row.so_cnt) + int(row.sd_cnt) + int(row.spd_cnt),
                },
                "ordered": {
                    # Строго status='ordered' (без 'contracted') — согласовано с total_ordered/
                    # глобальным widgets["ordered"] (правка 2026-08-04). w_ordered (contracted+ordered)
                    # остаётся в work/plan_schedule/total_work выше — там 'заключён договор' должен входить.
                    # + начисление по ежемесячным (monthly_ordered_map) — та же сумма, что вошла
                    # в total_ordered выше, widget.ordered обязан быть согласован с ним.
                    "amount": float(row.w_ordered_strict) + float(row.w_delivered) + float(row.w_paid)
                        + monthly_ordered_map.get(row.id, 0.0),
                    "count": int(row.so_cnt_strict) + int(row.sd_cnt) + int(row.spd_cnt),
                    "monthly_payments_total": mp_map.get(row.id, 0.0),
                },
                "delivered": {
                    "amount": float(row.w_delivered) + float(row.w_paid),
                    "count": int(row.sd_cnt) + int(row.spd_cnt),
                },
                "delivered_unpaid": {"amount": float(row.w_delivered), "count": int(row.sd_cnt)},
                "paid": {"amount": float(row.w_paid), "count": int(row.spd_cnt)},
                "contracts": {
                    "amount": contracts_map.get(row.id, 0.0),
                    "count": contracts_cnt_map.get(row.id, 0),
                },
            },
        })
        # Владелец (2026-08-30): плашка «субсидии у потолка» — прокидываем расчёт
        # прямо в subsidy_stats[i], чтобы карточка/список субсидий на дашборде
        # могли показать предупреждение без второго запроса.
        subsidy_stats[-1].update(ceiling_forecasts.get(row.id, {}))

    # ── Накопительные виджеты закупок ────────────────────────────────────────
    # Корзины: каждая закупка ровно в одной, по текущему статусу.
    # Исключаем cancelled и wishes.
    basket_q = (
        select(
            # stage_plan  : plan_schedule → planned_total_price
            func.coalesce(func.sum(
                case((Purchase.status == "plan_schedule", Purchase.planned_total_price), else_=None)
            ), 0).label("sp_amt"),
            func.coalesce(func.count(
                case((Purchase.status == "plan_schedule", Purchase.id), else_=None)
            ), 0).label("sp_cnt"),
            # stage_work  : work_in_progress → planned_total_price
            func.coalesce(func.sum(
                case((Purchase.status == "work_in_progress", Purchase.planned_total_price), else_=None)
            ), 0).label("sw_amt"),
            func.coalesce(func.count(
                case((Purchase.status == "work_in_progress", Purchase.id), else_=None)
            ), 0).label("sw_cnt"),
            # stage_ordered : contracted|ordered → COALESCE(contract_price, planned_total_price)
            func.coalesce(func.sum(
                case(
                    (Purchase.status.in_(["contracted", "ordered"]),
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("so_amt"),
            func.coalesce(func.count(
                case((Purchase.status.in_(["contracted", "ordered"]), Purchase.id), else_=None)
            ), 0).label("so_cnt"),
            # stage_ordered_strict : ТОЛЬКО ordered (без contracted) — для widget «Заказано»,
            # чтобы означать то же самое, что и total_ordered. stage_ordered (so_amt/so_cnt) выше
            # остаётся как было — используется в widget «work», где contracted обязан входить.
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "ordered",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("so_amt_strict"),
            func.coalesce(func.count(
                case((Purchase.status == "ordered", Purchase.id), else_=None)
            ), 0).label("so_cnt_strict"),
            # stage_delivered_unpaid : delivered → COALESCE(contract_price, planned_total_price)
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "delivered",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("sd_amt"),
            func.coalesce(func.count(
                case((Purchase.status == "delivered", Purchase.id), else_=None)
            ), 0).label("sd_cnt"),
            # stage_paid : paid → COALESCE(payment_amount, contract_price, planned_total_price)
            func.coalesce(func.sum(
                case(
                    (Purchase.status == "paid",
                     effective_amount_expr()),
                    else_=None
                )
            ), 0).label("spd_amt"),
            func.coalesce(func.count(
                case((Purchase.status == "paid", Purchase.id), else_=None)
            ), 0).label("spd_cnt"),
        )
        .where(Purchase.status.notin_(["cancelled", "wishes"]))
    )
    if use_sids:
        basket_q = _apply_purchase_org_filter(basket_q, current_user, subsidy_ids=visible_subsidy_ids)
    else:
        basket_q = _apply_purchase_org_filter(basket_q, current_user, org_ids)
    basket_row = (await db.execute(basket_q)).one()

    sp_amt  = float(basket_row.sp_amt);  sp_cnt  = int(basket_row.sp_cnt)
    sw_amt  = float(basket_row.sw_amt);  sw_cnt  = int(basket_row.sw_cnt)
    so_amt  = float(basket_row.so_amt);  so_cnt  = int(basket_row.so_cnt)
    so_amt_strict = float(basket_row.so_amt_strict); so_cnt_strict = int(basket_row.so_cnt_strict)
    sd_amt  = float(basket_row.sd_amt);  sd_cnt  = int(basket_row.sd_cnt)
    spd_amt = float(basket_row.spd_amt); spd_cnt = int(basket_row.spd_cnt)
    # Глобальный итог начисления по ежемесячным — СУММА уже посчитанных per-subsidy начислений
    # (monthly_ordered_map), а не отдельный пересчёт: monthly_q использует тот же use_sids/
    # visible_subsidy_ids/org_ids фильтр видимости, что и basket_q выше — числа согласованы.
    monthly_ordered_total = float(sum(monthly_ordered_map.values()))

    # ── Собираем виджеты ─────────────────────────────────────────────────────
    widgets = {
        # накопительно: stage_plan + stage_work + stage_ordered + stage_delivered_unpaid + stage_paid
        "plan_schedule": {
            "amount": sp_amt + sw_amt + so_amt + sd_amt + spd_amt,
            "count":  sp_cnt + sw_cnt + so_cnt + sd_cnt + spd_cnt,
        },
        # накопительно: stage_work + stage_ordered + stage_delivered_unpaid + stage_paid
        # (stage_ordered = contracted+ordered — «заключён договор» уже означает, что работа ведётся)
        "work": {
            "amount": sw_amt + so_amt + sd_amt + spd_amt,
            "count":  sw_cnt + so_cnt + sd_cnt + spd_cnt,
        },
        # накопительно: stage_ordered_strict (ТОЛЬКО status='ordered') + stage_delivered_unpaid + stage_paid
        # + начисление по ежемесячным (monthly_ordered_total). Согласовано с total_ordered
        # (правка 2026-08-04) — раньше здесь была contracted+ordered (so_amt) БЕЗ начисления,
        # из-за чего карточка «Заказано» на дашборде расходилась с той же меткой на
        # вкладке «Субсидии» (total_ordered). НЕ используем so_amt/so_cnt здесь — те остаются
        # в widget «work» выше, где contracted обязан входить.
        "ordered": {
            "amount": so_amt_strict + sd_amt + spd_amt + monthly_ordered_total,
            "count":  so_cnt_strict + sd_cnt + spd_cnt,
            "monthly_payments_total": monthly_payments_total,
        },
        # накопительно: stage_delivered_unpaid + stage_paid
        "delivered": {
            "amount": sd_amt + spd_amt,
            "count":  sd_cnt + spd_cnt,
        },
        # только stage_delivered_unpaid (поставлено, но не оплачено)
        "delivered_unpaid": {
            "amount": sd_amt,
            "count":  sd_cnt,
        },
        # только stage_paid
        "paid": {
            "amount": spd_amt,
            "count":  spd_cnt,
        },
        # договоры: single+framework_with_amount → max_amount;
        # framework_cumulative → SUM(COALESCE(contract_price, planned_total_price)) по закупкам
        "contracts": {
            "amount": contracts_amt,
            "count":  contracts_cnt,
        },
    }

    # Владелец (2026-08-30): блок «субсидии у потолка» — субсидии, где сумма
    # заказанного (включая ежемесячные — весь график) достигла/превысила
    # настроенный порог (ceiling_warn_percent, умолчание 90%). Отсортировано
    # по убыванию процента — сначала самые критичные (превышенные), затем
    # ближе всего к порогу.
    subsidies_near_ceiling = sorted(
        (
            {
                "subsidy_id": s["id"], "name": s["name"],
                "ceiling_total": s.get("ceiling_total", 0.0),
                "ceiling_committed_total": s.get("ceiling_committed_total", 0.0),
                "ceiling_committed_percent": s.get("ceiling_committed_percent", 0.0),
                "ceiling_warn_percent": s.get("ceiling_warn_percent", 90.0),
                "ceiling_exceeded": s.get("ceiling_exceeded", False),
            }
            for s in subsidy_stats
            if s.get("ceiling_near_warning") or s.get("ceiling_exceeded")
        ),
        key=lambda x: x["ceiling_committed_percent"], reverse=True,
    )

    return {
        "status_counts": status_counts,
        "subsidy_stats": subsidy_stats,
        "widgets": widgets,
        "subsidies_near_ceiling": subsidies_near_ceiling,
    }
