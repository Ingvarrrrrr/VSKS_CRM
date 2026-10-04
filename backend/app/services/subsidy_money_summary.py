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
redistributable_unplanned в этой ветке — 0.0, не free)."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy
from app.services.committed_amounts import subsidy_committed_totals
from app.services.subsidy_budget import calculate_budgets_bulk, effective_subsidy_budget


async def _plan_floor_added_by_subsidy(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"plan_floor_added", "not_committed_likely", "not_committed_nice"}}
    — Σ по КОРНЕВЫМ узлам compute_feo_plan_tree, на субсидию — та же техника
    root-узлов, что subsidy_committed_totals применяет к committed/plan_* (не
    вторая формула «пола плана»/«нужности» — оба поля уже посчитаны деревом:
    plan_floor_added через plan_floor_addition, app.services.feo_plan_common;
    not_committed_likely/not_committed_nice — Задача 2, владелец 04.10.2026,
    см. compute_feo_plan_tree). Обе разбивки читаются ОДНИМ вызовом дерева,
    второй раз его строить не нужно."""
    result: dict[int, dict] = {
        sid: {"plan_floor_added": 0.0, "not_committed_likely": 0.0, "not_committed_nice": 0.0}
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
        "redistributable_by_kind": {"goods","services","unspecified"} | None,
        "redistributable_unplanned": float,   # free, если budget > 0, иначе 0.0 («не запланировано» в карточке «Можно перераспределить»)
        "committed_missing_fact_items": int,  # позиций в договоре без суммы договора (fallback по плановой цене)
        "plan_floor_added": float,            # сумма «пола плана» (закрытые позиции без собственного плана) узлов субсидии
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

        # Без официального бюджета budget − committed не несёт смысла
        # («перераспределить от бюджета», которого нет) — та же логика фолбэка,
        # что в feo_plan_tree.py (redistributable=None без бюджета, фронт
        # подставляет planned_not_committed). Здесь всегда отдаём число (не
        # None — это НЕ узел дерева, а готовая карточка), поэтому фолбэк сразу
        # на planned_not_committed/planned_not_committed_by_kind (см. докстринг
        # модуля).
        if budget > 0:
            redistributable = budget - committed
            redistributable_unplanned = budget - planned  # = free, та же ветка budget>0
        else:
            redistributable = planned - committed
            redistributable_unplanned = 0.0  # нет бюджета — «не запланировано от бюджета» не определено
            if redistributable_by_kind is None:
                redistributable_by_kind = dict(planned_not_committed_by_kind)

        result[sid] = {
            "budget": budget,
            "planned": planned,
            "committed": committed,
            "committed_by_kind": committed_by_kind,
            "free": budget - planned,
            "planned_not_committed": planned - committed,
            "planned_not_committed_by_kind": planned_not_committed_by_kind,
            "redistributable": redistributable,
            "redistributable_by_kind": redistributable_by_kind,
            "redistributable_unplanned": redistributable_unplanned,
            "committed_missing_fact_items": _committed.get("committed_missing_fact_items", 0),
            "plan_floor_added": plan_floor_map.get(sid, {}).get("plan_floor_added", 0.0),
            # Задача 2 (владелец, 04.10.2026) — разбивка planned_not_committed
            # по статусу плановой позиции (need_level), см. compute_feo_plan_tree.
            "not_committed_likely": plan_floor_map.get(sid, {}).get("not_committed_likely", 0.0),
            "not_committed_nice": plan_floor_map.get(sid, {}).get("not_committed_nice", 0.0),
        }

    return result
