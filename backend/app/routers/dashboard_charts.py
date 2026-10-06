"""GET /api/dashboard/charts — сосед dashboard.py (Правило №5, резка 1641→core, 2026-09-08).

Виджеты/сводки закупок и субсидий для дашборда: статусы (pie), per-subsidy
агрегаты, «Заключено договоров», накопительные виджеты (plan_schedule/work/
ordered/delivered/paid/contracts), «субсидии у потолка». Помесячное начисление
«Заказано» по ежемесячным закупкам вынесено в
app/services/dashboard_monthly_accrual.py (чистый агрегат без своей логики
видимости — фильтр передаётся вызовом снаружи).
"""
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, and_
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
# ИСПРАВЛЕНИЕ пункта E (ревью 02.10.2026, PLAN.md шаг 1): рамочный договор
# занимает деньги только с РАЗМЕЩЁННОГО заказа (ordered/delivered/paid), не с
# самого факта заключения (contracted) — единая точка committed_amounts.py.
# ПРАВИЛО №6 (2026-09-05): единый расчёт «суммы закупки» по стадии — см. dashboard.py
# для полного пояснения; effective_amount_expr/aggregate_scope_expr уже применены
# во всех местах ниже, где раньше были точечные COALESCE(...).
from app.services.purchase_amounts import effective_amount_expr
from app.services.dashboard_monthly_accrual import compute_monthly_ordered_map, compute_monthly_future_map
# План B (ancient-prancing-music.md, раздел B) — товары/услуги/без типа по этапам
# (?type_split=true) и по «Бюджет (ФЭО)»/«Запланировано» — оба читаются отсюда,
# единственный источник (Правило №6), никакой второй копии формул типа/долей.
from app.services.dashboard_type_split import compute_type_split_raw, reconcile_split, STAGE_KEYS
from app.routers.dashboard import _apply_purchase_org_filter
# Расшифровка строки «товары/услуги/без типа» карточки этапа (2026-09-21) —
# отдельный файл (Правило №5), подключается под-роутером БЕЗ своего prefix
# здесь: type_drill_router уже несёт prefix="/type-drill" сам по себе, полный
# путь = "/api/dashboard" (этот router) + "/type-drill". routes.py не трогается.
from app.routers.dashboard_type_drill import router as type_drill_router
# Расшифровка карточки «Заключено договоров» по ДОГОВОРАМ (владелец, 06.10.2026,
# план sleepy-fluttering-walrus.md п.2) — тот же приём подключения под-роутера.
from app.routers.dashboard_contracts_drill import router as contracts_drill_router

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
router.include_router(type_drill_router)
router.include_router(contracts_drill_router)


@router.get("/charts")
async def dashboard_charts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None),
    # План B (2026-09-21): при true — к каждому накопительному этапу добавляются
    # <stage>_goods/_services/_unspecified (товары/услуги/без типа), а к каждой
    # субсидии — budget_goods/services/unspecified («Бюджет (ФЭО)» по типу) и
    # planned_goods/services/unspecified («Запланировано» = Σ FeoPlannedItem.amount
    # по типу). Ленивая догрузка — без флага ответ БАЙТ-В-БАЙТ прежний (доп.
    # вычисления просто не выполняются, ни одно существующее поле не трогается).
    type_split: bool = Query(False),
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
    # «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б):
    # единый предикат — app.services.sandbox_guard.not_sandbox_subsidy_ids();
    # применяется только для scope=dashboard/radar/plan, НЕ для managed (страница
    # «Субсидии» обязана продолжать показывать копию, иначе ею нечем управлять).
    from app.services.sandbox_guard import not_sandbox_subsidy_ids
    _not_sandbox_ids = not_sandbox_subsidy_ids()

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
    if dashboard:
        # На странице «Субсидии» (scope=managed) копия ОСТАЁТСЯ в списке —
        # иначе ею нечем было бы управлять.
        subsidy_q = subsidy_q.where(Subsidy.id.in_(_not_sandbox_ids))
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
    if dashboard:
        feo_planned_q = feo_planned_q.where(FeoCategory.subsidy_id.in_(_not_sandbox_ids))
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
    # Ускорение 06.10.2026 (координатор, боевой замер: ?type_split=true отвечал
    # 7,3 с) — дерево ФЭО (compute_feo_plan_tree) самое дорогое место запроса
    # (десятки under-the-hood запросов на субсидию), а строилось ТРИЖДЫ за
    # один HTTP-запрос: здесь (planned_tree_map) + дважды ниже в
    # type_totals_map (type_split=True). Строим ОДИН раз (только когда
    # ?type_split=true — иначе дерево ВТОРОЙ раз никому не нужно, тот же
    # результат без него) и передаём готовое tree обоим вызовам
    # _calculate_feo_planned_tree_bulk (см. её докстринг и docstring
    # feo_plan_subsidy_totals/subsidy_type_totals — опциональный `tree`).
    _shared_feo_tree = None
    if type_split and sid_list:
        from app.services.feo_plan_tree import compute_feo_plan_tree as _compute_feo_plan_tree
        _shared_feo_tree = await _compute_feo_plan_tree(db, sid_list)
    planned_tree_map = await _calculate_feo_planned_tree_bulk(db, sid_list, tree=_shared_feo_tree)
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
    # «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б,
    # правка после приёмки): на scope=managed subsidy_q/sub_objs ВКЛЮЧАЮТ копию
    # (строка должна остаться в списке — её нужно удалить/сделать настоящей), но
    # «итого» страницы (contracts_amt/contracts_cnt/monthly_payments_total ниже)
    # обязаны исключать её — тот же not_sandbox-принцип (ПРАВИЛО №6), только на
    # уровне финальной агрегации, а не SQL-фильтра (SQL-фильтр убрал бы и
    # собственные цифры строки копии, которые должны остаться «как обычно»).
    sandbox_ids_in_scope = {sid for sid, obj in sub_objs.items() if obj.is_sandbox}
    contractor_ids = {s.contractor_id for s in sub_objs.values() if s.contractor_id}
    contractors = {}
    if contractor_ids:
        contractors = {
            c.id: c for c in (await db.execute(
                select(Contractor).where(Contractor.id.in_(contractor_ids))
            )).scalars().all()
        }

    # Виджет «Заключено договоров» — ЕДИНЫЙ источник
    # app.services.stage_cumulative.contracted_total_by_subsidy() (Правило №6,
    # 2026-10-06): та же функция считает итог вкладки «Договоры»
    # (routers/contracts.py::get_contracted_total), раньше вкладка суммировала
    # голый Contract.max_amount без greatest()/топ-апов/framework_cumulative —
    # расхождение 9 315 271 (вкладка) vs 12 983 362 (эта карточка) на
    # ФАДМ 2026_2 (прод id=88). Подробности формулы — докстринг функции.
    from app.services.stage_cumulative import contracted_total_by_subsidy
    _contracted_map = await contracted_total_by_subsidy(db, subsidy_ids=sid_list)
    contracts_map: dict[int, float] = {sid: d["amount"] for sid, d in _contracted_map.items()}
    contracts_cnt_map: dict[int, int] = {sid: d["count"] for sid, d in _contracted_map.items()}

    # Глобальные итоги — сумма по регруппированным строкам, КРОМЕ копий для
    # экспериментов (sandbox_ids_in_scope — см. выше; на scope=dashboard эта
    # сумма уже пуста для них благодаря SQL-фильтру contract_single_q/
    # contract_fc_q, здесь исключение актуально для scope=managed).
    contracts_amt = sum(v for sid, v in contracts_map.items() if sid not in sandbox_ids_in_scope)
    contracts_cnt = sum(v for sid, v in contracts_cnt_map.items() if sid not in sandbox_ids_in_scope)

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
    if dashboard:
        mp_q = mp_q.where(Contract.subsidy_id.in_(_not_sandbox_ids))
    mp_map: dict = {}
    for r in (await db.execute(mp_q)).all():
        mp_map[r.subsidy_id] = mp_map.get(r.subsidy_id, 0.0) + float(r.amt)
    # Глобальный итог — сумма по регруппированным строкам (бит-в-бит эквивалентно прежнему скаляру,
    # включая договоры с subsidy_id IS NULL — они попадают в mp_map под ключом None),
    # КРОМЕ копий для экспериментов (см. sandbox_ids_in_scope выше).
    monthly_payments_total = float(sum(v for sid, v in mp_map.items() if sid not in sandbox_ids_in_scope))

    # ── Ежемесячные закупки: начисление «Заказано» по прошедшим месяцам ──────────────
    # Логика вынесена в app.services.dashboard_monthly_accrual.compute_monthly_ordered_map
    # (чистый агрегат, без своей логики видимости, см. докстринг там) — здесь только
    # тот же _apply_purchase_org_filter/use_sids/visible_subsidy_ids/org_ids фильтр, что
    # и остальная часть /charts (basket_q, subsidy_q и т.д.), передан колбэком.
    if use_sids:
        monthly_ordered_map = await compute_monthly_ordered_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids)
        )
        # Задача 3 (владелец, 04.10.2026) — будущие помесячные платежи до конца
        # года субсидии, тот же фильтр видимости, что и monthly_ordered_map.
        monthly_future_map = await compute_monthly_future_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids)
        )
    else:
        monthly_ordered_map = await compute_monthly_ordered_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, org_ids)
        )
        monthly_future_map = await compute_monthly_future_map(
            db, lambda q: _apply_purchase_org_filter(q, current_user, org_ids)
        )
    # Общий итог — та же техника, что monthly_payments_total выше (Σ по
    # субсидиям в scope, без песочниц — monthly_future_map строится по уже
    # отфильтрованным apply_filter строкам, второй фильтр не нужен).
    monthly_future_to_year_end_total = float(sum(monthly_future_map.values()))

    # Контракт API (PLAN.md шаг 1-2/5, п. A, ревью 02.10.2026): «Свободно»/
    # «законтрактовано»/«В плане без договоров»/«Можно перераспределить» —
    # ОДНА функция (app.services.subsidy_money_summary, ПРАВИЛО №6 — она сама
    # не считает НИЧЕГО заново, только собирает effective_subsidy_budget/
    # planned_tree/committed_amounts.subsidy_committed_totals воедино).
    # «Экономия» — отдельная точка (purchase_economy.py), не входит в сводку
    # денег субсидии (разные экраны/формулы).
    from app.services.subsidy_money_summary import subsidy_money_summary as _money_summary_fn
    from app.services.purchase_economy import purchase_economy_by_subsidy as _economy_by_subsidy_fn
    money_summary_map = await _money_summary_fn(db, sid_list, tree=_shared_feo_tree)
    economy_by_subsidy_map = await _economy_by_subsidy_fn(db, sid_list)
    # Карточка «Оплачено» (владелец, 05.10.2026) — ДВЕ величины: «по отметке
    # сотрудников» и «подтверждено выпиской» (+ товары/услуги). ПРАВИЛО №6 —
    # тот же источник, что дерево ФЭО (см. докстринг subsidy_paid_breakdown.py);
    # существующие total_paid/widget.paid (status='paid' only) НЕ трогаются.
    from app.services.subsidy_paid_breakdown import paid_breakdown_by_subsidy as _paid_breakdown_fn
    paid_breakdown_map = await _paid_breakdown_fn(db, sid_list)
    # Карточка «Поставлено, не оплачено» (владелец, 06.10.2026, ФАДМ 2026_2 —
    # см. докстринг delivered_unpaid_residual.py): раньше total_delivered_unpaid
    # вычитал Σ «Оплачено по отметке» субсидии ИЗ Σ «Поставлено» субсидии —
    # переплата по одной закупке гасила долг за другую. Теперь — Σ остатков
    # ПО ЗАКУПКЕ (max(0, поставлено_закупки − оплачено_закупки)), ОДНА функция,
    # которой пользуется и карточка, и drill (dashboard_type_drill.py), и Excel.
    from app.services.delivered_unpaid_residual import delivered_unpaid_residual_by_subsidy as _residual_fn
    delivered_unpaid_residual_map = await _residual_fn(db, sid_list)

    subsidy_stats = []
    for row in subsidy_rows:
        calc = budgets.get(row.id, 0.0)
        _money = money_summary_map.get(row.id) or {}
        # effective_budget/planned_tree/remaining — ТЕ ЖЕ числа, что раньше
        # считались прямо здесь (effective_subsidy_budget + budget−planned_tree),
        # теперь читаются из subsidy_money_summary (ПРАВИЛО №6, одна точка —
        # см. докстринг модуля). Байт-в-байт то же значение: _money["budget"]/
        # ["planned"] построены ИЗ ТЕХ ЖЕ calculate_budgets_bulk/
        # _calculate_feo_planned_tree_bulk, что и planned_tree_map/budgets ниже.
        effective_budget = _money.get("budget", effective_subsidy_budget(calc, row.budget))
        spent = spent_map.get(row.id, 0.0)
        planned_amt = planned_amounts_map.get(row.id, 0.0)
        # planned_tree = правильное «Запланировано» = план дерева ФЭО (= «Свободно» = budget − planned_tree)
        planned_tree = planned_tree_map.get(row.id, 0.0)
        # budget_basis/budget_from_plan — решение владельца 06.10.2026 (см.
        # докстринг subsidy_money_summary.py): «бюджет для показа» — budget,
        # если задан, иначе planned_tree. ПОКАЗ (calculated_budget/
        # feo_budget_total/remaining/budget_discrepancy ниже) читает
        # budget_basis; "budget"/effective_budget САМИ не меняются — их
        # продолжают читать subsidy_revision_preview.py/subsidy_revision_floor.py.
        budget_basis = _money.get("budget_basis", effective_budget if effective_budget > 0 else planned_tree)
        budget_from_plan = bool(_money.get("budget_from_plan", effective_budget <= 0 and planned_tree > 0))
        # «Свободно» для показа = budget_basis − planned_tree (= free_basis; при
        # budget_from_plan это 0.0, т.к. budget_basis == planned_tree)
        remaining = _money.get("free_basis", budget_basis - planned_tree)
        # discrepancy-чип показывается только при превышении (planned_tree > budget_basis)
        discrepancy = (budget_basis - planned_tree) if planned_tree > budget_basis else None
        _economy = economy_by_subsidy_map.get(row.id) or {}
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
            # «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md,
            # Часть Б, правка после приёмки): строка копии остаётся в списке
            # (scope=managed) — фронт должен узнать её, чтобы показать плашку
            # «копия» и кнопки «Удалить копию»/«Сделать настоящей» вместо
            # «Скопировать для эксперимента» (см. SubsidyCardsGrid.vue/
            # SubsidyListTable.vue).
            "is_sandbox": bool(sub_obj.is_sandbox) if sub_obj else False,
            "copied_from_id": sub_obj.copied_from_id if sub_obj else None,
            # budget теперь nullable (владелец 2026-09-15: «ещё не определён»,
            # см. app/models/subsidy.py) — float(None) валил бы /dashboard/charts
            # целиком для ВСЕХ пользователей, если хотя бы одна субсидия без
            # бюджета. effective_budget (ниже, из effective_subsidy_budget)
            # остаётся числом — это то, что реально используется для расчётов.
            "budget": float(row.budget) if row.budget is not None else None,
            "calculated_budget": budget_basis,
            "total_planned": float(row.total_planned),
            "total_confirmed": float(row.total_confirmed),
            "total_paid": float(row.total_paid),
            # Задача (владелец, 05.10.2026) — карточка «Оплачено» на вкладке
            # «Субсидии»: paid_declared («по отметке сотрудников») и
            # paid_confirmed («подтверждено выпиской») — см. докстринг
            # app/services/subsidy_paid_breakdown.py (ПРАВИЛО №6, тот же
            # источник, что paid_marked/paid_confirmed дерева ФЭО). НЕ
            # заменяет total_paid/widget.paid (status='paid' only) — те
            # остаются как есть для мест, которые уже их используют.
            "paid_declared": (_paid_breakdown_map_entry := paid_breakdown_map.get(row.id) or {}).get("declared", 0.0),
            "paid_confirmed": _paid_breakdown_map_entry.get("confirmed", 0.0),
            # План 2026-10-06-statement-control, п.1: разница для подсветки на
            # карточке «Оплачено» — выписка (confirmed) минус отметка
            # сотрудников (declared); ПРАВИЛО №6, считается тут же из двух
            # полей выше, второй источник не заводится.
            # «по отметке − по выписке» (план 2026-10-06 п.1; фронт показывает так же).
            "paid_diff": round(_paid_breakdown_map_entry.get("declared", 0.0) - _paid_breakdown_map_entry.get("confirmed", 0.0), 2),
            "paid_declared_by_kind": _paid_breakdown_map_entry.get("declared_by_kind") or {"goods": 0.0, "services": 0.0, "unspecified": 0.0},
            "paid_confirmed_by_kind": _paid_breakdown_map_entry.get("confirmed_by_kind") or {"goods": 0.0, "services": 0.0, "unspecified": 0.0},
            # «Остаток субсидии» (владелец, 06.10.2026) — budget − оплачено,
            # ДВЕ версии (по отметке/по выписке). Σ paid_marked/paid_confirmed
            # КОРНЕЙ дерева ФЭО — источник subsidy_money_summary (см. докстринг
            # subsidy_money_summary.py про расхождение этой техники с
            # paid_declared/paid_confirmed выше — задача явно требует источник
            # дерева для остатка).
            # ИСПРАВЛЕНИЕ (найдено 2026-10-06, ФАДМ 2026_2, прод id=88):
            # раньше balance_by_marks/balance_by_statement читались ТОЛЬКО как
            # _money.get(...) без фолбэка — если sid отсутствует в
            # money_summary_map (пустой _money = {}), получали None → карточка
            # «бюджет не введён», хотя «Бюджет (ФЭО)» в ЭТОЙ ЖЕ строке
            # (calculated_budget/feo_budget_total, см. budget_basis выше)
            # ПОКАЗЫВАЛА 15 880 100 ₽ — budget_basis уже прошёл фолбэк
            # (effective_budget/planned_tree), а balance_by_marks — нет. ТЕПЕРЬ
            # оба поля читают budget_basis (ПРАВИЛО №6, один и тот же источник
            # для «Бюджет (ФЭО)» и «Остаток субсидии») — None только когда
            # budget_basis <= 0 (бюджет действительно не введён и не выведен
            # из плана), а не из-за отсутствия ключа в _money.
            "balance_paid_marked": _money.get("balance_paid_marked", 0.0),
            "balance_paid_confirmed": _money.get("balance_paid_confirmed", 0.0),
            "balance_by_marks": (budget_basis - _money.get("balance_paid_marked", 0.0)) if budget_basis > 0 else None,
            "balance_by_statement": (budget_basis - _money.get("balance_paid_confirmed", 0.0)) if budget_basis > 0 else None,
            "total_plan_schedule": float(row.total_plan_schedule),  # SUM work_in_progress planned_total_price
            # total_ordered = SQL-агрегат по НЕежемесячным (row.total_ordered) + начисление по
            # ежемесячным (monthly_ordered_map) — обязаны складываться в одно число: карточка
            # «Заказано» должна включать месяц, за который услуга уже оказывается прямо сейчас.
            "total_ordered": float(row.total_ordered) + monthly_ordered_map.get(row.id, 0.0),
            # Справочно: какая часть total_ordered выше — из помесячного начисления (для отладки/подписи).
            # УЖЕ ВХОДИТ в total_ordered, не складывать повторно.
            "monthly_ordered_accrued": monthly_ordered_map.get(row.id, 0.0),
            # Задача 3 (владелец, 04.10.2026) — оставшиеся помесячные платежи
            # ДО КОНЦА ГОДА субсидии (app.services.dashboard_monthly_accrual.
            # compute_monthly_future_map, ПРАВИЛО №6 — тот же разбор графика,
            # что и monthly_ordered_accrued, не вторая формула).
            "monthly_future_to_year_end": monthly_future_map.get(row.id, 0.0),
            "total_feo_planned": feo_planned_map.get(row.id, 0.0),  # NEW 12-01: SUM FeoPlannedItem.amount
            "planned_tree": planned_tree,  # единый источник: план дерева ФЭО (ручные + заявки)
            "feo_budget_total": budget_basis,
            "feo_filled": calc > 0,
            # Решение владельца 06.10.2026 (см. докстринг subsidy_money_summary.py):
            # True, когда официального бюджета нет, а calculated_budget/
            # feo_budget_total выше временно = план. Подпись «по плану — суммы
            # ФЭО не введены» на карточках «Бюджет (ФЭО)»/«Остаток субсидии».
            "budget_from_plan": budget_from_plan,
            "contractor_id": sub_obj.contractor_id if sub_obj else None,
            "contractor_name": contractor_name,
            "contractor_inn": contractor_inn,
            # Phase 31-05: canonical budget fields (D-17)
            "remaining": remaining,  # = «Свободно» = budget − planned_tree
            "planned_amount": planned_amt,
            "budget_discrepancy": discrepancy,
            # Контракт API (PLAN.md шаг 1-2/5, п. A, ревью 02.10.2026): «законтрактовано»,
            # «В плане без договоров», «Можно перераспределить» — ОДНА точка
            # расчёта (app.services.subsidy_money_summary, см. импорт выше);
            # «Экономия по закупкам» — отдельно, purchase_economy.py.
            # Инвариант: remaining + planned_not_committed == redistributable
            # (покрыт test_dashboard_analytics.py / test_money_committed.py).
            "committed": _money.get("committed", 0.0),
            "committed_by_kind": _money.get("committed_by_kind") or {"goods": 0.0, "services": 0.0, "unspecified": 0.0},
            "planned_not_committed": _money.get("planned_not_committed", planned_tree - _money.get("committed", 0.0)),
            "planned_not_committed_by_kind": _money.get("planned_not_committed_by_kind") or {"goods": 0.0, "services": 0.0, "unspecified": 0.0},
            # Задача 2 (владелец, 04.10.2026) — разбивка «В плане без договоров»
            # по статусу плановой позиции (need_level: likely/nice_to_have),
            # ОДНА точка расчёта — subsidy_money_summary (см. импорт выше).
            "not_committed_likely": _money.get("not_committed_likely", 0.0),
            "not_committed_nice": _money.get("not_committed_nice", 0.0),
            "redistributable": _money.get("redistributable", effective_budget - _money.get("committed", 0.0)),
            # ИСПРАВЛЕНО 04.10.2026: раньше здесь жёстко стояло None (комментарий
            # «байт-в-байт прежнее поведение») — из-за этого «Можно
            # перераспределить по типам» выглядело пустым для ЛЮБОЙ субсидии,
            # хотя subsidy_money_summary уже умеет его считать (через
            # subsidy_type_totals при заполненном дереве, фолбэком на
            # planned_not_committed_by_kind без официального бюджета — см.
            # докстринг subsidy_money_summary.py). Читаем как остальные поля
            # этого блока — ОДНА точка расчёта, без второго механизма здесь.
            "redistributable_by_kind": _money.get("redistributable_by_kind"),
            # Задача (владелец, 04.10.2026) — «не запланировано» строкой карточки
            # «Можно перераспределить»: free, если бюджет задан, иначе 0.0 — ОДНА
            # точка расчёта, см. докстринг subsidy_money_summary.py.
            "redistributable_unplanned": _money.get("redistributable_unplanned", 0.0),
            # Новые поля карточки «Можно перераспределить» (владелец, 06.10.2026,
            # план sleepy-fluttering-walrus.md п.1) — см. докстринг
            # app.services.redistributable_raw/subsidy_money_summary.py.
            # ИЗМЕНЕНО (находка координатора): переименовано из
            # monthly_future_to_redistribute в contracted_not_ordered —
            # реальный источник не is_monthly_payment-график, а дочерние
            # заказы рамочных договоров в статусе 'contracted'.
            "contracted_not_ordered": _money.get("contracted_not_ordered", 0.0),
            "over_plan_categories": _money.get("over_plan_categories", []),
            # ИСПРАВЛЕНО 02.10.2026: economy_total=None (ни одна позиция субсидии
            # не измерена) пропускается как null, не форсится в 0.0 — см.
            # purchase_economy.py docstring.
            "economy_total": (
                float(_economy["economy_total"])
                if _economy.get("economy_total") is not None
                else None
            ),
            "economy_no_planned_price_items": _economy.get("economy_no_planned_price_items", 0),
            "economy_unmeasured_by_reason": _economy.get("economy_unmeasured_by_reason"),
            "committed_missing_fact_items": _money.get("committed_missing_fact_items", 0),
            # Per-subsidy work/delivery baskets (зеркала глобальных widgets)
            "total_work": float(row.total_plan_schedule) + float(row.w_ordered) + float(row.w_delivered) + float(row.w_paid),
            "total_contracts": contracts_map.get(row.id, 0.0),
            # ИСПРАВЛЕНО (владелец, 06.10.2026, ФАДМ 2026_2, прод id=89) — раньше
            # вычиталось Σ «Оплачено по отметке» субсидии из Σ «Поставлено»
            # субсидии целиком (переплата одной закупки гасила долг другой).
            # Теперь — Σ остатков ПО ЗАКУПКЕ (delivered_unpaid_residual.py,
            # ПРАВИЛО №6 — одна функция и для карточки, и для drill/Excel).
            "delivered_unpaid_declared_by_kind": (delivered_unpaid_residual_map.get(row.id) or {}).get(
                "by_kind", {"goods": 0.0, "services": 0.0, "unspecified": 0.0},
            ),
            "total_delivered": float(row.w_delivered) + float(row.w_paid),
            # total_delivered_unpaid — единственный потребитель SubsidiesView.vue →
            # SubsidyRow.delivered_unpaid → SubsidyKpiCards.vue (grep подтверждён).
            # widget["delivered_unpaid"] (ниже) НЕ трогается: его читает ещё и
            # useDashboardData.ts (effectiveWidgets/stageTypeSplit) для
            # дашборда — там сохраняется прежний смысл (status='delivered', без
            # вычета оплаты).
            "total_delivered_unpaid": (delivered_unpaid_residual_map.get(row.id) or {}).get("total", 0.0),
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
            # Задача 3 (владелец, 04.10.2026) — общий итог «оставшиеся помесячные
            # платежи до конца года», рядом с monthly_payments_total.
            "monthly_future_to_year_end": monthly_future_to_year_end_total,
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

    # ── План B (?type_split=true): товары/услуги/без типа по этапам + «Бюджет
    # (ФЭО)»/«Запланировано» по типу — см. app.services.dashboard_type_split /
    # app.services.type_totals (единственный источник, Правило №6). Ленивая
    # догрузка: без флага этот блок не выполняется вовсе, существующие ключи
    # widgets/subsidy_stats выше уже полностью посчитаны и не трогаются здесь. ──
    dashboard_type_totals: Optional[dict] = None
    if type_split:
        def _purchase_filter(q):
            if use_sids:
                return _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids)
            return _apply_purchase_org_filter(q, current_user, org_ids)

        raw_split = await compute_type_split_raw(
            db, apply_filter=_purchase_filter, use_sids=use_sids,
            visible_subsidy_ids=visible_subsidy_ids, org_ids=org_ids,
        )
        # ИСПРАВЛЕНО (находка координатора 06.10.2026, жалоба владельца «ХО
        # (копия)»): _purchase_filter выше — ТОТ ЖЕ _apply_purchase_org_filter,
        # что и basket_q/monthly_ordered_map/monthly_future_map, БЕЗ
        # explicit_subsidy_ids — он намеренно исключает is_sandbox-копии
        # ВСЕГДА (тот же not_sandbox_subsidy_ids(None), что держит ГЛОБАЛЬНЫЕ
        # widgets[stage] без песочницы — см. contracts_amt/monthly_payments_total
        # чуть выше, тот же sandbox_ids_in_scope). Поэтому raw_split["per_subsidy"]
        # для копии оставался ПУСТЫМ (ни одной её закупки не прошло фильтр) —
        # reconcile_split(raw=[0,0,0], target=amount>0) форсил ВСЮ сумму в
        # "без типа" на КАЖДОМ накопительном этапе ("Ведётся работа"/
        # "Заказано"/"Поставлено" и т.д.), хотя сами widget[stage]["amount"]
        # (из subsidy_q, строка копии) и split "contracts" (fc_q/contract_q/
        # contractless_q/single_active_q внутри compute_type_split_raw — те
        # фильтруют ПРЯМО по visible_subsidy_ids, без sandbox-исключения
        # вообще) копию НЕ исключают — отсюда «"Заключено договоров" разбито
        # верно, остальные — нет» из жалобы владельца.
        #
        # Та же политика, что docstring _apply_purchase_org_filter описывает
        # для explicit_subsidy_ids («карточка копии дёргает те же виджеты с
        # явным subsidy_id — ей нужны реальные числа, не нули») — здесь
        # применяем её к sandbox_ids_in_scope (уже готовый список копий В
        # SCOPE этого ответа, см. его определение выше): пересчитываем
        # per-subsidy split ТОЛЬКО для них отдельным вызовом с
        # explicit_subsidy_ids, и подменяем ТОЛЬКО per_subsidy-часть — global
        # (widgets[stage]) НЕ трогаем, он обязан остаться без песочницы
        # (та же величина, что уже выверена contracts_amt/monthly_payments_total).
        if sandbox_ids_in_scope:
            def _sandbox_purchase_filter(q):
                return _apply_purchase_org_filter(
                    q, current_user, subsidy_ids=sandbox_ids_in_scope,
                    explicit_subsidy_ids=list(sandbox_ids_in_scope),
                )
            sandbox_split = await compute_type_split_raw(
                db, apply_filter=_sandbox_purchase_filter, use_sids=True,
                visible_subsidy_ids=sandbox_ids_in_scope, org_ids=None,
            )
            raw_split["per_subsidy"].update(sandbox_split["per_subsidy"])
        _zero_raw = [Decimal(0), Decimal(0), Decimal(0)]
        for stage in STAGE_KEYS:
            reconciled = reconcile_split(raw_split["global"].get(stage, _zero_raw), widgets[stage]["amount"])
            widgets[stage][f"{stage}_goods"] = reconciled["goods"]
            widgets[stage][f"{stage}_services"] = reconciled["services"]
            widgets[stage][f"{stage}_unspecified"] = reconciled["unspecified"]

        # «Бюджет (ФЭО)» и «Запланировано» по типу — per-subsidy, через
        # _calculate_feo_planned_tree_bulk(type_split=True) (subsidies.py), тот
        # же единственный вход, что читает app.services.type_totals. ДРУГАЯ
        # величина, чем widgets.plan_schedule выше (тот — сумма закупок по
        # статусу; budget_*/planned_* — дерево ФЭО/плановые позиции).
        # budget_* = feo_* оттуда, planned_* = plan_*. tree=_shared_feo_tree —
        # ТО ЖЕ дерево, что уже построено для planned_tree_map выше (не второй
        # раз, см. комментарий там).
        type_totals_map = await _calculate_feo_planned_tree_bulk(
            db, sid_list, type_split=True, tree=_shared_feo_tree,
        )
        _agg = {k: 0.0 for k in (
            "budget_goods", "budget_services", "budget_unspecified",
            "planned_goods", "planned_services", "planned_unspecified",
        )}
        for row in subsidy_stats:
            sid = row["id"]
            per_sub_raw = raw_split["per_subsidy"].get(sid, {})
            for stage in STAGE_KEYS:
                reconciled = reconcile_split(per_sub_raw.get(stage, _zero_raw), row["widget"][stage]["amount"])
                row["widget"][stage][f"{stage}_goods"] = reconciled["goods"]
                row["widget"][stage][f"{stage}_services"] = reconciled["services"]
                row["widget"][stage][f"{stage}_unspecified"] = reconciled["unspecified"]
            # delivered_unpaid_declared_by_kind уже заполнен выше (ПРАВИЛО №6,
            # delivered_unpaid_residual_by_subsidy — одна точка расчёта
            # независимо от ?type_split) — второй раз здесь не считается.
            tt = type_totals_map.get(sid, {})
            row["budget_goods"] = tt.get("feo_goods", 0.0)
            row["budget_services"] = tt.get("feo_services", 0.0)
            row["budget_unspecified"] = tt.get("feo_unspecified", 0.0)
            # Исправление 2026-09-21 (боевой замер, субсидия «Тестовая» id 59:
            # feo_budget_total=100 000, split=0) — субсидия БЕЗ дерева ФЭО, но
            # с РУЧНЫМ subsidy.budget (100 000), НЕ равным плану (20 000):
            # ручная сумма типа не несёт, Σ goods+services+unspecified должна
            # остаться = feo_budget_total, второго источника не заводим — всё
            # в unspecified.
            #
            # ИСПРАВЛЕНО 06.10.2026 (координатор, боевой замер ХО id 75,
            # /api/dashboard/charts?type_split=true): это УЖЕ НЕ единственный
            # случай not feo_filled — с тех пор как _feo_by_kind
            # (app.services.feo_plan_tree, Правило №6) научился фолбэку «budget
            # по типу = план по типу» для узлов СУБСИДИИ БЕЗ единой суммы ФЭО
            # (см. её докстринг), tt ВЫШЕ уже возвращает ПРАВИЛЬНУЮ типовую
            # разбивку САМ, когда budget_basis = planned_tree (row["budget_
            # from_plan"] — тот же флаг, что и subsidy_money_summary.py). Старое
            # «всё в unspecified» здесь слепо перезаписывало уже-верный tt,
            # получалось Σ > budget_basis (12 096 152,67 + 3 628 012,18 +
            # 35 817 440,43 для ХО — тройной счёт товаров/услуг). Триггерим
            # override ТОЛЬКО когда budget_basis взят НЕ из плана (ручной
            # budget без дерева, как у «Тестовой») — budget_from_plan=False —
            # ручное число типа не несёт и tt в этом случае честно 0/0/0.
            if not row["feo_filled"] and not row["budget_from_plan"] and row["feo_budget_total"] > 0:
                # ОБЯЗАТЕЛЬНО обнулить goods/services тоже — tt здесь уже НЕ
                # всегда 0/0/0 (plan-фолбэк _feo_by_kind может дать typed-план,
                # напр. «Тестовая» id 59: tt.feo_goods=20 000); без обнуления
                # Σ превышала budget (20 000 + 100 000 unspecified = 120 000 >
                # 100 000). Ручной budget тип не несёт — целиком в unspecified.
                row["budget_goods"] = 0.0
                row["budget_services"] = 0.0
                row["budget_unspecified"] = row["feo_budget_total"]
            row["planned_goods"] = tt.get("plan_goods", 0.0)
            row["planned_services"] = tt.get("plan_services", 0.0)
            row["planned_unspecified"] = tt.get("plan_unspecified", 0.0)
            for k in _agg:
                _agg[k] += row[k]

        if use_sids:
            # Только scope=dashboard/managed (задача B/2) — агрегат по видимым
            # субсидиям, простая Σ уже посчитанных per-subsidy значений (не
            # второй расчёт).
            dashboard_type_totals = _agg

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

    payload = {
        "status_counts": status_counts,
        "subsidy_stats": subsidy_stats,
        "widgets": widgets,
        "subsidies_near_ceiling": subsidies_near_ceiling,
    }
    if dashboard_type_totals is not None:
        payload.update(dashboard_type_totals)
    return payload
