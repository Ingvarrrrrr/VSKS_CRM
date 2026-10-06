"""subsidy_money_summary.py — ОДНА функция денежной сводки субсидии (владелец,
02.10.2026, план .planning/quick/2026-10-02-money-redistribution/PLAN.md, шаг 5,
п.5 отчёта сессии: «Один показатель — один источник истины», ПРАВИЛО №6).

До этого модуля «Свободно» (remaining = effective_budget − planned_tree),
planned_not_committed и redistributable считались ПРЯМО в
app.routers.dashboard_charts.dashboard_charts — три отдельных выражения внутри
одного большого роутера. Эта функция — единственное место, где они собираются
вместе; dashboard_charts.py теперь ТОЛЬКО читает её результат и раскладывает по
полям ответа (имена и значения полей ответа НЕ меняются — byte-совместимость с
фронтом и с test_money_committed.py/test_dashboard_analytics.py).

НИКАКИХ новых формул здесь не вводится — каждое поле читается из уже
существующего источника (см. аргумент каждой переменной ниже):
  budget                        — effective_subsidy_budget(calculate_budgets_bulk, Subsidy.budget)
                                   (app.services.subsidy_budget — та же точка,
                                   что dashboard_charts/subsidies.py list/detail/
                                   create/approve/update).
  planned                       — _calculate_feo_planned_tree_bulk (app.routers.
                                   subsidies, тонкая обёртка над
                                   feo_plan_subsidy_totals) — то же «Запланировано»,
                                   что и панель ФЭО вкладки «Субсидии».
  committed/committed_by_kind/
  committed_missing_fact_items/
  planned_not_committed_by_kind — subsidy_committed_totals (app.services.
                                   committed_amounts, шаг 1 плана — единственная
                                   точка правила статусов «законтрактовано»).
  plan_floor_added              — compute_feo_plan_tree (app.services.
                                   feo_plan_tree) root-узлы, Σ node['plan_floor_added']
                                   — ТА ЖЕ техника чтения готового typed-поля
                                   узла, что subsidy_committed_totals применяет
                                   к committed/plan_* (не вторая формула «пола
                                   плана» — plan_floor_addition определена
                                   только в app.services.feo_plan_common).
  redistributable_by_kind       — subsidy_type_totals (app.services.type_totals,
                                   feo_goods/feo_services/feo_unspecified —
                                   «бюджет ФЭО по типу») минус committed_by_kind,
                                   когда у субсидии есть разбивка дерева
                                   по типам (feo_filled, та же проверка, что
                                   dashboard_charts.py budget_* ветка type_split);
                                   без бюджета (budget <= 0) — тот же фолбэк,
                                   что у redistributable: берём уже готовый
                                   planned_not_committed_by_kind (см. выше);
                                   когда ни бюджета, ни плана по типам нет —
                                   None (в проекте нет отдельного «бюджета по
                                   типу» без дерева ФЭО и без плана, см.
                                   dashboard_charts.py docstring про
                                   feo_filled/budget_unspecified).

Производные (считаются один раз здесь, НЕ читаются ниоткуда — это и есть их
единственная точка):
  free                   = budget − planned
  planned_not_committed  = planned − committed
  redistributable        = budget − committed, ПОКА задан официальный бюджет
                            (budget > 0 после effective_subsidy_budget). Без
                            бюджета «перераспределять» нечего ОТ бюджета — та
                            же логика, что уже применена к узлам дерева
                            (app.services.feo_plan_tree ~стр.1493-1496:
                            redistributable=None без бюджета) и к фронту
                            (frontend/src/composables/subsidies/
                            useFeoTreeAmounts.ts ~стр.400-425: без бюджета
                            показывается planned_not_committed «из плана без
                            договоров»). Здесь — тот же фолбэк, не вторая
                            формула: redistributable = planned_not_committed,
                            redistributable_by_kind = planned_not_committed_by_kind.

redistributable_unplanned           = free, когда задан бюджет (budget > 0);
                            иначе 0.0 — «не запланировано от бюджета» не
                            определено без бюджета (та же ветка budget>0/else,
                            что у redistributable выше; не вторая формула —
                            просто то же free, подставленное в карточку
                            «Можно перераспределить» вместо prop, который
                            фронт раньше считал сам от РАСЧЁТНОЙ оценки
                            бюджета — владелец, 04.10.2026, задача про три
                            строки карточки, которые не сходились в сумме).

Инвариант (проверен test_subsidy_money_summary.py и совпадением с subsidy_stats
/api/dashboard/charts): redistributable_unplanned + not_committed_nice +
not_committed_likely == redistributable — ДЛЯ ЛЮБОЙ субсидии, с бюджетом и без,
с точностью до копейки. При заданном бюджете free + planned_not_committed ==
redistributable == budget − committed. Без бюджета (budget <= 0) инвариант
иной: redistributable == planned_not_committed (budget в формулу не входит,
free всё равно считается как budget − planned, т.е. может быть
отрицательным/нулевым — это отдельное поле, не трогается;
redistributable_unplanned в этой ветке — 0.0, не free).

РЕШЕНИЕ ВЛАДЕЛЬЦА (06.10.2026, «бюджет = план, когда ФЭО не введён»): у
субсидии без сумм «по ФЭО» и без ручного budget (effective budget = "budget"
выше, <= 0) «бюджет ФЭО» для ПОКАЗА на экране временно = planned_tree
(«Запланировано») — владелец потом поправит суммы руками. Это решение
коснулось ТОЛЬКО того, что видно на карточках «Бюджет (ФЭО)»/«Остаток
субсидии»; "budget" (поле выше, effective_subsidy_budget) НЕ меняется —
его продолжают читать app.services.subsidy_revision_preview.py и
subsidy_revision_floor.py (корректировка утверждённой субсидии), трогать их
поведение этой задачей не нужно и запрещено владельцем.

Новые поля (эта же точка, не вторая формула):
  budget_basis   = budget, если budget > 0, иначе planned_tree. «Бюджет для
                   показа» — то единственное число, которое теперь читают
                   dashboard_charts.py (calculated_budget/feo_budget_total/
                   budget_discrepancy) и фронт (useFeoTreeAmounts.selectedBudget,
                   SubsidyKpiCards.vue/SubsidyMoneyCards.vue карточки).
  budget_from_plan = True, когда budget <= 0 И planned > 0 (т.е. budget_basis
                   пришлось взять из плана, не из ФЭО/ручного бюджета) — флаг
                   для подписи «по плану — суммы ФЭО не введены» на фронте.
  free_basis     = budget_basis − planned. Для budget_from_plan это 0.0
                   (budget_basis == planned в этой ветке) — используется
                   ТОЛЬКО для показа («Свободно»/«не запланировано» на
                   карточках); "free" выше (budget − planned, может быть
                   отрицательным без бюджета) НЕ меняется — его читает
                   корректировка через effective_subsidy_budget, формула та же.
  balance_by_marks/balance_by_statement — теперь budget_basis − paid_marked/
                   paid_confirmed, None только если budget_basis <= 0 (раньше
                   было от budget — для budget_from_plan budget<=0 всегда
                   давало None, хотя план и оплата есть; теперь считается от
                   budget_basis, тот же paid_marked/paid_confirmed источник).
  redistributable_unplanned — теперь read как free_basis, когда budget_basis
                   > 0 (при budget_from_plan это 0.0 автоматически, т.к.
                   free_basis == 0 в этой ветке — не отдельная формула).
                   redistributable (budget_basis − committed, тот же фолбэк
                   planned − committed без budget_basis) и инвариант
                   unplanned+nice+likely == redistributable не меняются.

ИЗМЕНЕНО (06.10.2026, план sleepy-fluttering-walrus.md, п.1, «ФАДМ 2026_2»):
not_committed_nice/not_committed_likely/redistributable_by_kind больше НЕ
читаются из compute_feo_plan_tree root-узлов (та версия клэмпит каждый узел в
[0, planned_not_committed] — при перезаконтрактованном направлении дефицит
одного направления «съедал» избыток других при роллапе, карточка расходилась
с простой Σ по листу Excel). Теперь — app.services.redistributable_raw (raw Σ
по ВСЕМ плановым позициям субсидии, без клэмпа, см. её докстринг за формулой);
"redistributable" (сумма трёх строк) не меняется — алгебраически то же число,
просто собранное иначе (см. test_redistributable_raw.py). Новые поля
contracted_not_ordered/over_plan_categories — см. докстринг
app.services.redistributable_raw/app.services.stage_cumulative.

ИСПРАВЛЕНО (находка координатора 06.10.2026, двойной счёт): «договоры без
заказа» (ранее поле monthly_future_to_redistribute) считались через
is_monthly_payment-график платежей — на проде id=89 реальный разрыв «Ведётся
работа»−«Заказано» целиком состоял из дочерних заказов рамочных договоров в
статусе 'contracted' (is_monthly_payment=False у всех), график тут ни при
чём. Источник теперь — app.services.stage_cumulative.
contracted_not_ordered_by_subsidy/contracted_not_ordered_need_level_split;
поле переименовано в contracted_not_ordered и ВЫЧИТАЕТСЯ из
not_committed_nice/not_committed_likely (по need_level), а не прибавляется
поверх — см. комментарий у места сборки ниже."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy
from app.services.committed_amounts import subsidy_committed_totals
from app.services.redistributable_raw import (
    not_committed_raw_by_subsidy as _not_committed_raw_fn,
    over_plan_categories_by_subsidy as _over_plan_categories_fn,
)
from app.services.stage_cumulative import (
    contracted_not_ordered_need_level_split as _contracted_not_ordered_split_fn,
)
from app.services.subsidy_budget import calculate_budgets_bulk, effective_subsidy_budget


async def _plan_floor_added_by_subsidy(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"plan_floor_added", "not_committed_likely", "not_committed_nice",
    "paid_marked", "paid_confirmed"}} — Σ по КОРНЕВЫМ узлам compute_feo_plan_tree,
    на субсидию — та же техника root-узлов, что subsidy_committed_totals
    применяет к committed/plan_* (не вторая формула «пола плана»/«нужности»/
    «оплаты» — все поля уже посчитаны деревом: plan_floor_added через
    plan_floor_addition, app.services.feo_plan_common; not_committed_likely/
    not_committed_nice — Задача 2, владелец 04.10.2026; paid_marked/
    paid_confirmed — app.services.feo_plan_payments.paid_consumption_by_category,
    см. compute_feo_plan_tree). Все разбивки читаются ОДНИМ вызовом дерева,
    второй раз его строить не нужно.

    ВНИМАНИЕ (задача «Остаток субсидии», владелец 06.10.2026): paid_marked/
    paid_confirmed здесь — ТОТ ЖЕ источник данных (Purchase.payment_amount/
    payment_amount_declared), что и app.services.subsidy_paid_breakdown.
    paid_breakdown_by_subsidy (который кормит dashboard_charts.py::paid_declared/
    paid_confirmed — карточку «Оплачено» на вкладке «Субсидии»), НО другая
    техника агрегации (Σ по корням дерева ФЭО с распределением по ratio
    категорий, а не прямой SQL по Purchase с PLANNED_STATUSES/scope). На живых
    данных числа могут не совпадать копейка-в-копейку — задача явно требует
    остаток считать ОТСЮДА (корни дерева), это задокументированное решение
    владельца, а не вторая формула «по ошибке» (см. отчёт сессии с цифрами
    live-сверки)."""
    result: dict[int, dict] = {
        sid: {
            "plan_floor_added": 0.0, "not_committed_likely": 0.0, "not_committed_nice": 0.0,
            "paid_marked": 0.0, "paid_confirmed": 0.0,
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result
    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    for node in tree.values():
        if node.get("parent_id") is not None:
            continue
        sid = node.get("subsidy_id")
        if sid in result:
            result[sid]["plan_floor_added"] += float(node.get("plan_floor_added", 0.0) or 0.0)
            result[sid]["not_committed_likely"] += float(node.get("not_committed_likely", 0.0) or 0.0)
            result[sid]["not_committed_nice"] += float(node.get("not_committed_nice", 0.0) or 0.0)
            result[sid]["paid_marked"] += float(node.get("paid_marked", 0.0) or 0.0)
            result[sid]["paid_confirmed"] += float(node.get("paid_confirmed", 0.0) or 0.0)
    return result


async def subsidy_money_summary(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {
        "budget": float,                      # эффективный бюджет субсидии (дерево ФЭО, фолбэк — ручное значение)
        "planned": float,                     # «Запланировано» = план дерева ФЭО (ручные позиции + заявки)
        "committed": float,                   # «Законтрактовано» (шаг 1 плана — committed_amounts.py)
        "committed_by_kind": {"goods","services","unspecified"},
        "free": float,                        # budget − planned («Свободно»)
        "planned_not_committed": float,       # planned − committed («В плане без договоров»)
        "planned_not_committed_by_kind": {"goods","services","unspecified"},
        "redistributable": float,             # budget − committed («Можно перераспределить»)
        "redistributable_by_kind": {"goods","services","unspecified"},  # RAW (06.10.2026) — см. app.services.redistributable_raw
        "redistributable_unplanned": float,   # free, если budget > 0, иначе 0.0 («не запланировано» в карточке «Можно перераспределить»)
        "contracted_not_ordered": float,  # «договоры без заказа» (06.10.2026, переименовано из monthly_future_to_redistribute)
        "over_plan_categories": [{"category_id","name","excess_amount"}],  # направления с committed > plan (06.10.2026)
        "committed_missing_fact_items": int,  # позиций в договоре без суммы договора (fallback по плановой цене)
        "plan_floor_added": float,            # сумма «пола плана» (закрытые позиции без собственного плана) узлов субсидии
        "balance_paid_marked": float,         # оплачено по отметке (включает подтверждённое выпиской) — Σ paid_marked корней дерева
        "balance_paid_confirmed": float,      # подтверждено выпиской — Σ paid_confirmed корней дерева
        "balance_by_marks": float | None,     # «Остаток субсидии» по отметке = budget_basis − balance_paid_marked; None, если budget_basis <= 0
        "balance_by_statement": float | None, # «Остаток субсидии» по выписке = budget_basis − balance_paid_confirmed; None, если budget_basis <= 0
        "budget_basis": float,                # budget, если budget > 0, иначе planned («бюджет для показа», решение владельца 06.10.2026)
        "budget_from_plan": bool,             # True, когда budget <= 0 и planned > 0 (budget_basis взят из плана)
        "free_basis": float,                  # budget_basis − planned (для показа; "free" не трогается)
    }} — см. докстринг модуля для источника каждого поля (ПРАВИЛО №6: ни одно
    поле здесь не пересчитывается заново, только собирается воедино и
    комбинируется в three производных free/planned_not_committed/redistributable)."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    subsidy_rows = (await db.execute(
        select(Subsidy.id, Subsidy.budget).where(Subsidy.id.in_(subsidy_ids))
    )).all()
    manual_budget_by_sid = {r.id: r.budget for r in subsidy_rows}

    calc_budget_map = await calculate_budgets_bulk(db, subsidy_ids)
    committed_map = await subsidy_committed_totals(db, subsidy_ids)
    plan_floor_map = await _plan_floor_added_by_subsidy(db, subsidy_ids)

    # redistributable_by_kind — только если у субсидии есть разбивка бюджета ФЭО
    # по типу (дерево заполнено); иначе «бюджет по типу» не определён (см.
    # докстринг модуля) — для этого нужен ТОТ ЖЕ признак feo_filled, что
    # dashboard_charts.py использует (calc_budget_map[sid] > 0).
    filled_sids = [sid for sid in subsidy_ids if float(calc_budget_map.get(sid, 0.0) or 0.0) > 0]
    type_totals_map: dict = {}
    if filled_sids:
        from app.services.type_totals import subsidy_type_totals
        type_totals_map = await subsidy_type_totals(db, filled_sids)

    # planned_tree одним batch-вызовом на весь список.
    from app.routers.subsidies import _calculate_feo_planned_tree_bulk
    planned_tree_map = await _calculate_feo_planned_tree_bulk(db, subsidy_ids)

    # Карточка «Можно перераспределить» БЕЗ обрезки по направлениям (владелец,
    # 06.10.2026, план sleepy-fluttering-walrus.md п.1) — см. докстринг
    # app.services.redistributable_raw. not_committed_nice/not_committed_likely
    # ниже теперь читаются ОТСЮДА (raw, без клэмпа компute_feo_plan_tree), а не
    # из _plan_floor_added_by_subsidy (та клэмпнутая версия остаётся только для
    # дерева/узлов — ничего в ней не меняем, см. docstring модуля там).
    raw_not_committed_map = await _not_committed_raw_fn(db, subsidy_ids)
    # «Договоры без заказа» (дочерние заказы рамочных договоров 'contracted',
    # ещё не оформленные как отдельная закупка) — ИСПРАВЛЕНО 06.10.2026, см.
    # докстринг модуля и app.services.stage_cumulative.
    contracted_not_ordered_split_map = await _contracted_not_ordered_split_fn(db, subsidy_ids=subsidy_ids)
    over_plan_categories_map = await _over_plan_categories_fn(db, subsidy_ids)

    for sid in subsidy_ids:
        calc = calc_budget_map.get(sid, 0.0)
        budget = effective_subsidy_budget(calc, manual_budget_by_sid.get(sid))
        planned = planned_tree_map.get(sid, 0.0)
        _committed = committed_map.get(sid) or {}
        committed = _committed.get("committed", 0.0)
        committed_by_kind = {
            "goods": _committed.get("committed_goods", 0.0),
            "services": _committed.get("committed_services", 0.0),
            "unspecified": _committed.get("committed_unspecified", 0.0),
        }
        planned_not_committed_by_kind = {
            "goods": _committed.get("plan_goods", 0.0) - committed_by_kind["goods"],
            "services": _committed.get("plan_services", 0.0) - committed_by_kind["services"],
            "unspecified": _committed.get("plan_unspecified", 0.0) - committed_by_kind["unspecified"],
        }
        redistributable_by_kind: Optional[dict] = None
        if sid in type_totals_map:
            tt = type_totals_map[sid]
            redistributable_by_kind = {
                "goods": tt.get("feo_goods", 0.0) - committed_by_kind["goods"],
                "services": tt.get("feo_services", 0.0) - committed_by_kind["services"],
                "unspecified": tt.get("feo_unspecified", 0.0) - committed_by_kind["unspecified"],
            }

        # budget_basis — «бюджет для показа» (решение владельца 06.10.2026,
        # см. докстринг модуля): budget, если задан официальный бюджет,
        # иначе planned (пока владелец не введёт суммы по ФЭО). budget САМ
        # не меняется — его продолжают читать subsidy_revision_preview.py/
        # subsidy_revision_floor.py байт-в-байт как раньше.
        budget_from_plan = budget <= 0 and planned > 0
        budget_basis = budget if budget > 0 else planned
        free_basis = budget_basis - planned  # = 0.0 при budget_from_plan (budget_basis == planned)

        # Без budget_basis budget_basis − committed не несёт смысла
        # («перераспределить от бюджета», которого нет) — та же логика фолбэка,
        # что в feo_plan_tree.py (redistributable=None без бюджета, фронт
        # подставляет planned_not_committed). Здесь всегда отдаём число (не
        # None — это НЕ узел дерева, а готовая карточка), поэтому фолбэк сразу
        # на planned_not_committed/planned_not_committed_by_kind (см. докстринг
        # модуля). Ветка теперь по budget_basis (а не budget напрямую) — это
        # ТА ЖЕ формула budget_basis − committed, которая при budget>0 даёт
        # budget − committed байт-в-байт как раньше (budget_basis == budget),
        # а при budget_from_plan — planned − committed (то же число, что и
        # раньше давала ветка budget<=0, см. докстринг модуля, проверено
        # test_subsidy_money_summary.py).
        if budget_basis > 0:
            redistributable = budget_basis - committed
            redistributable_unplanned = free_basis  # = budget_basis − planned, 0.0 при budget_from_plan
            if budget_from_plan and redistributable_by_kind is None:
                # budget_basis взят из плана (нет официального бюджета и нет
                # заполненного дерева по типам) — та же точка фолбэка, что и
                # раньше применялась в ветке "budget <= 0" (см. ниже), просто
                # budget_from_plan уже отдельно отличает её от «ни бюджета, ни
                # плана» случая.
                redistributable_by_kind = dict(planned_not_committed_by_kind)
        else:
            redistributable = planned - committed
            redistributable_unplanned = 0.0  # нет бюджета и плана — «не запланировано от бюджета» не определено
            if redistributable_by_kind is None:
                redistributable_by_kind = dict(planned_not_committed_by_kind)

        # Карточка «Можно перераспределить» (план sleepy-fluttering-walrus.md
        # п.1) — подстроки и разбивка по типу БЕЗ клэмпа дерева по направлениям,
        # см. докстринг app.services.redistributable_raw.
        #
        # ИСПРАВЛЕНО (находка координатора 06.10.2026, двойной счёт): «договоры
        # без заказа» (дочерние заказы рамочных договоров, status='contracted' —
        # контракт заключён, заказ как отдельная закупка ещё не создан) НЕ
        # считаются committed_status_predicate для framework-закупок
        # (FRAMEWORK_COMMITTED_STATUSES = {ordered, delivered, paid}, БЕЗ
        # 'contracted' — committed_amounts.py) — поэтому их плановая позиция
        # целиком остаётся «не законтрактовано» в not_committed_raw_by_subsidy
        # (обычно в 'likely'). Это и есть ВЫРЕЗКА (отдельная строка), а не
        # ДОБАВКА: redistributable = not_planned + nice_raw' + likely_raw' +
        # contracted_not_ordered, где nice_raw'/likely_raw' — raw МИНУС свою
        # долю contracted_not_ordered (по need_level плановой позиции заказа,
        # app.services.stage_cumulative.contracted_not_ordered_need_level_split)
        # — алгебраически та же Σ nice_raw+likely_raw, просто поделённая на 3
        # строки вместо 2 (см. test_redistributable_raw.py). redistributable_by_kind
        # ниже читает raw_by_kind КАК ЕСТЬ — contracted_not_ordered НЕ
        # прибавляется и НЕ вычитается там (по п.2 задачи — by_kind не трогаем,
        # товары/услуги уже включают эту сумму целиком внутри nice_raw/likely_raw).
        _raw = raw_not_committed_map.get(sid) or {"nice_raw": 0.0, "likely_raw": 0.0, "by_kind": {}}
        _contracted_not_ordered = contracted_not_ordered_split_map.get(sid) or {"nice": 0.0, "likely": 0.0}
        contracted_not_ordered = _contracted_not_ordered["nice"] + _contracted_not_ordered["likely"]
        # «Хотелось бы»/«Скорее всего» БЕЗ договоров-без-заказа (вырезаем по
        # need_level заказа, не прибавляем — см. комментарий выше).
        not_committed_nice_raw = _raw["nice_raw"] - _contracted_not_ordered["nice"]
        not_committed_likely_raw = _raw["likely_raw"] - _contracted_not_ordered["likely"]
        _raw_by_kind = dict(_raw.get("by_kind") or {})
        # «Не запланировано» (redistributable_unplanned) не привязано к
        # конкретной категории/типу — кладём в «без типа», чтобы Σ by_kind всё
        # равно сходилась с redistributable (видно на карточке отдельной
        # строкой "не запланировано", не задваивается с товары/услуги).
        if abs(redistributable_unplanned) > 0.005:
            _raw_by_kind["unspecified"] = _raw_by_kind.get("unspecified", 0.0) + redistributable_unplanned
        redistributable_by_kind_raw = {
            "goods": _raw_by_kind.get("goods", 0.0),
            "services": _raw_by_kind.get("services", 0.0),
            "unspecified": _raw_by_kind.get("unspecified", 0.0),
        }

        result[sid] = {
            "budget": budget,
            "planned": planned,
            "committed": committed,
            "committed_by_kind": committed_by_kind,
            "free": budget - planned,
            "planned_not_committed": planned - committed,
            "planned_not_committed_by_kind": planned_not_committed_by_kind,
            "redistributable": redistributable,
            # ИЗМЕНЕНО (06.10.2026, план sleepy-fluttering-walrus.md п.1):
            # redistributable_by_kind теперь = raw Σ по позициям (товар/услуга),
            # НЕ бюджет-минус-законтрактовано-по-типу — см. докстринг
            # app.services.redistributable_raw. redistributable_by_kind_old
            # (прежняя формула) никому отдельно не нужен — Правило №6, не
            # оставляем второе поле ради обратной совместимости, фронт читает
            # ОДНО имя redistributable_by_kind.
            "redistributable_by_kind": redistributable_by_kind_raw,
            "redistributable_unplanned": redistributable_unplanned,
            "committed_missing_fact_items": _committed.get("committed_missing_fact_items", 0),
            "plan_floor_added": plan_floor_map.get(sid, {}).get("plan_floor_added", 0.0),
            # «Договоры без заказа» (план sleepy-fluttering-walrus.md п.1,
            # переименовано 06.10.2026 из monthly_future_to_redistribute —
            # находка координатора, см. докстринг модуля и
            # app.services.stage_cumulative.contracted_not_ordered_by_subsidy).
            "contracted_not_ordered": contracted_not_ordered,
            # Красная строка «законтрактовано сверх плана по направлению X» —
            # см. docstring over_plan_categories_by_subsidy.
            "over_plan_categories": over_plan_categories_map.get(sid, []),
            # Задача 2 (владелец, 04.10.2026) — разбивка planned_not_committed
            # по статусу плановой позиции (need_level). ИЗМЕНЕНО 06.10.2026
            # (план sleepy-fluttering-walrus.md п.1): raw Σ по плановым позициям
            # субсидии, БЕЗ клэмпа дерева по направлениям — см. докстринг
            # app.services.redistributable_raw.not_committed_raw_by_subsidy
            # (compute_feo_plan_tree node['not_committed_nice']/['not_committed_likely']
            # остаются как есть — та клэмпнутая версия нужна ТОЛЬКО самому дереву/узлам).
            # not_committed_likely/not_committed_nice — УЖЕ БЕЗ «договоров без
            # заказа» (см. вырезку выше, находка координатора 06.10.2026) —
            # contracted_not_ordered показывается отдельной строкой, не
            # прибавляется поверх likely/nice.
            "not_committed_likely": not_committed_likely_raw,
            "not_committed_nice": not_committed_nice_raw,
            "budget_basis": budget_basis,
            "budget_from_plan": budget_from_plan,
            "free_basis": free_basis,
        }
        # «Остаток субсидии» (владелец, 06.10.2026) = бюджет для показа − уже
        # проведённые оплаты. Поступление на счёт пока = бюджету ФЭО (ввода
        # поступлений нет), поэтому это же число — «остаток на счёте».
        # budget_basis <= 0 (ни бюджета, ни плана) — оба поля None («бюджет не
        # введён», та же ветка budget_basis>0/else, что у redistributable
        # выше). При budget_from_plan budget_basis = planned > 0, поэтому
        # остаток теперь считается (раньше был None из-за budget <= 0 — тот
        # самый разрыв, который решает эта задача).
        balance_paid_marked = plan_floor_map.get(sid, {}).get("paid_marked", 0.0)
        balance_paid_confirmed = plan_floor_map.get(sid, {}).get("paid_confirmed", 0.0)
        result[sid]["balance_paid_marked"] = balance_paid_marked
        result[sid]["balance_paid_confirmed"] = balance_paid_confirmed
        if budget_basis > 0:
            result[sid]["balance_by_marks"] = budget_basis - balance_paid_marked
            result[sid]["balance_by_statement"] = budget_basis - balance_paid_confirmed
        else:
            result[sid]["balance_by_marks"] = None
            result[sid]["balance_by_statement"] = None

    return result
