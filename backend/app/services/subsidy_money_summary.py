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
not_committed_likely + monthly_future_not_started + manual_plan_gap ==
redistributable — ДЛЯ ЛЮБОЙ субсидии, с бюджетом и без, с точностью до копейки
(manual_plan_gap — шаг 2 плана humble-stirring-emerson.md, 23.10.2026,
«задано на категорию, но не расписано позициями» — ДО этой правки инвариант
не держался на статьях plan_source='manual_sum' без (или с неполными)
плановыми позициями, см. feo_plan_common.manual_plan_gap). При заданном
бюджете free + planned_not_committed == redistributable == budget − committed.
Без бюджета (budget <= 0) инвариант иной: redistributable == planned_not_committed
(budget в формулу не входит, free всё равно считается как budget − planned,
т.е. может быть отрицательным/нулевым — это отдельное поле, не трогается;
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
monthly_future_not_started/over_plan_categories — см. докстринг
app.services.redistributable_raw/app.services.monthly_future_payments.

ИСПРАВЛЕНО (находка координатора 06.10.2026, двойной счёт): «договоры без
заказа» (ранее поле monthly_future_to_redistribute) считались через
is_monthly_payment-график платежей — на проде id=89 реальный разрыв «Ведётся
работа»−«Заказано» целиком состоял из дочерних заказов рамочных договоров в
статусе 'contracted' (is_monthly_payment=False у всех), график тут ни при
чём.

ИЗМЕНЕНО (🟡/🟢/🔵 правки плана abstract-noodling-pelican.md, 15.10.2026,
п.B/C): поле переименовано в `monthly_future_not_started` («ещё уйдёт
помесячно до конца года, ещё не начато») — источник теперь
app.services.monthly_future_payments (ЕДИНОЕ место правила «занято»/«ещё
уйдёт», см. её докстринг), НЕ app.services.stage_cumulative.
contracted_not_ordered_*: та старая пара функций (contracted_not_ordered_
by_subsidy/_need_level_split/_split_by_kind) ОСТАЁТСЯ в stage_cumulative.py —
её продолжают читать app.services.feo_row_contracted (разрез по категории
ФЭО) и app.services.subsidy_summary_by_kind (лист «Сводная» экспорта), которые
в этой задаче НЕ переведены на новый модуль (вне рамок правки карточек
«Заключено»/«Можно перераспределить» — см. отчёт сессии, сознательно
отложенный долг, не второе правило «занято» по сути, а неперенесённый
читатель старого). ВЫЧИТАНИЕ из not_committed_nice/not_committed_likely
здесь БОЛЬШЕ НЕ НУЖНО: not_committed_raw_by_subsidy (redistributable_raw.py)
теперь САМА исключает эти строки целиком (committed_by_planned_item(...,
month_aware=True) уже видит начавшийся месяц как committed, а не начавшийся —
флагом monthly_future_not_started уходит в свою сумму) — см. комментарий у
места сборки ниже.

ОТМЕНЕНО (владелец, 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/
PLAN.md шаг 1, решение №3): РЕШЕНИЕ 06.10.2026 выше («бюджет = план, когда ФЭО
не введён») — ОТМЕНЕНО целиком. Повод — субсидия «ДНР» (409 плановых позиций,
63 232 213,82 ₽, ФЭО не введено ни у одной из 41 статьи): подмена плана
бюджетом не только маскировала «ФЭО не введено» как настоящий бюджет, но и
из-за отдельного бага в feo_plan_tree.py (_feo_by_kind — убран там же, см. её
докстринг) расходилась с «Запланировано» на 8 191,49 ₽ (позиции прямо на
статье с подкатегориями). Теперь budget<=0 → budget_basis/free_basis/
redistributable/redistributable_unplanned/redistributable_by_kind/
balance_by_marks/balance_by_statement — ВСЕ None; новое поле feo_entered
(= budget > 0, тот же effective_subsidy_budget, что и budget выше — не вторая
формула) говорит фронту, что показывать «ФЭО не введено» вместо чисел.
budget_from_plan остаётся полем выдачи, но теперь ВСЕГДА False — подмена
больше не происходит; поле не удалено ТОЛЬКО ради старых потребителей (grep
подтвердил чтение в dashboard_charts.py и нескольких местах фронта — правит
фронт другой исполнитель, см. отчёт сессии)."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy
from app.services.committed_amounts import subsidy_committed_totals
from app.services.redistributable_raw import (
    not_committed_raw_by_subsidy as _not_committed_raw_fn,
    over_plan_categories_by_subsidy as _over_plan_categories_fn,
)
from app.services.subsidy_budget import calculate_budgets_bulk, effective_subsidy_budget


async def _plan_floor_added_by_subsidy(
    db: AsyncSession, subsidy_ids: list[int], *, tree: Optional[dict] = None,
) -> dict[int, dict]:
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
            "paid_marked": 0.0, "paid_confirmed": 0.0, "manual_plan_gap": 0.0,
            # Правка 23.10.2026 (владелец) — manual_plan_gap по виду, см.
            # комментарий у суммирования ниже.
            "manual_plan_gap_goods": 0.0, "manual_plan_gap_services": 0.0,
            "manual_plan_gap_payroll": 0.0, "manual_plan_gap_unspecified": 0.0,
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result
    if tree is None:
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
            # Шаг 2 плана humble-stirring-emerson.md (23.10.2026) — Σ по
            # корням, та же техника, что и у остальных аддитивных полей этой
            # функции (node['manual_plan_gap'] уже рекурсивно считает
            # поддерево, см. compute_feo_plan_tree).
            result[sid]["manual_plan_gap"] += float(node.get("manual_plan_gap", 0.0) or 0.0)
            # Правка 23.10.2026 (владелец, после живой проверки) — та же Σ,
            # разложенная по виду (ПРАВИЛО №6 — читаем уже готовые поля узла,
            # не вторая формула, см. feo_plan_common.manual_plan_gap_by_kind).
            result[sid]["manual_plan_gap_goods"] += float(node.get("manual_plan_gap_goods", 0.0) or 0.0)
            result[sid]["manual_plan_gap_services"] += float(node.get("manual_plan_gap_services", 0.0) or 0.0)
            result[sid]["manual_plan_gap_payroll"] += float(node.get("manual_plan_gap_payroll", 0.0) or 0.0)
            result[sid]["manual_plan_gap_unspecified"] += float(node.get("manual_plan_gap_unspecified", 0.0) or 0.0)
    return result


async def subsidy_money_summary(
    db: AsyncSession, subsidy_ids: list[int], *, tree: Optional[dict] = None,
    budgets: Optional[dict] = None,
) -> dict[int, dict]:
    """`tree` — опционально уже посчитанный compute_feo_plan_tree(db,
    subsidy_ids) ЭТОГО ЖЕ вызова (ускорение 06.10.2026 — см. комментарий у
    _tree ниже; dashboard_charts.py передаёт сюда свой _shared_feo_tree, когда
    он уже построен для ?type_split=true, вместо второй сборки). Без
    аргумента — строит сама, поведение прежнее.

    `budgets` — опционально уже посчитанный calculate_budgets_bulk(db,
    subsidy_ids) ЭТОГО ЖЕ вызова (ускорение 2026-10-12, координатор:
    dashboard_charts.py уже строит budgets сам для subsidy_stats и звал эту
    функцию без него — calculate_budgets_bulk пересчитывался второй раз на
    тот же subsidy_ids). Без аргумента — строит сама, поведение прежнее.

    {subsidy_id: {
        "budget": float,                      # эффективный бюджет субсидии (дерево ФЭО, фолбэк — ручное значение)
        "planned": float,                     # «Запланировано» = план дерева ФЭО (ручные позиции + заявки)
        "planned_full": float,                # то же, БЕЗ урезания до ФЭО (владелец, 27.10.2026) — Σ full_display корней
        "committed": float,                   # «Законтрактовано» (шаг 1 плана — committed_amounts.py)
        "committed_by_kind": {"goods","services","unspecified"},
        "free": float,                        # budget − planned («Свободно»)
        "planned_not_committed": float,       # planned − committed («В плане без договоров»)
        "planned_not_committed_by_kind": {"goods","services","unspecified"},
        "redistributable": float | None,      # budget_basis − committed («Можно перераспределить»); None, если не feo_entered
        "redistributable_by_kind": {"goods","services","unspecified"} | None,  # RAW (06.10.2026) — см. app.services.redistributable_raw; None, если не feo_entered
        "redistributable_unplanned": float | None,  # free_basis, если feo_entered, иначе None («не запланировано» в карточке «Можно перераспределить»)
        "monthly_future_not_started": float,  # «ещё уйдёт помесячно, не начато» (15.10.2026, переименовано из contracted_not_ordered)
        "not_committed_nice_payroll": float,  # D7 21.10.2026 — payroll-доля not_committed_nice (ТОЛЬКО для payroll_visibility, не отдаётся API)
        "not_committed_likely_payroll": float,  # D7 21.10.2026 — payroll-доля not_committed_likely (ТОЛЬКО для payroll_visibility)
        "monthly_future_not_started_payroll": float,  # D7 21.10.2026 — payroll-доля monthly_future_not_started (ТОЛЬКО для payroll_visibility)
        "redistributable_unplanned_payroll": float,  # D7 21.10.2026 — payroll-доля redistributable_unplanned (ТОЛЬКО для payroll_visibility)
        "over_plan_categories": [{"category_id","name","excess_amount"}],  # направления с committed > plan (06.10.2026)
        "committed_missing_fact_items": int,  # позиций в договоре без суммы договора (fallback по плановой цене)
        "plan_floor_added": float,            # сумма «пола плана» (закрытые позиции без собственного плана) узлов субсидии
        "balance_paid_marked": float,         # оплачено по отметке (включает подтверждённое выпиской) — Σ paid_marked корней дерева
        "balance_paid_confirmed": float,      # подтверждено выпиской — Σ paid_confirmed корней дерева
        "balance_by_marks": float | None,     # «Остаток субсидии» по отметке = budget_basis − balance_paid_marked; None, если не feo_entered
        "balance_by_statement": float | None, # «Остаток субсидии» по выписке = budget_basis − balance_paid_confirmed; None, если не feo_entered
        "budget_basis": float | None,          # = budget, если feo_entered, иначе None («ФЭО не введено» — решение владельца 07.10.2026, подмена планом ОТМЕНЕНА)
        "budget_from_plan": bool,             # ВСЕГДА False теперь (поле выдачи сохранено только для совместимости старых потребителей — см. докстринг модуля)
        "free_basis": float | None,            # budget_basis − planned, если feo_entered, иначе None (для показа; "free" не трогается)
        "feo_entered": bool,                  # budget > 0 (официальный бюджет ИЛИ хоть одна сумма ФЭО) — решение владельца 07.10.2026
        "plan_over_ceiling_amount": float,    # на сколько «Запланировано» выше жёсткого потолка ФЭО (0, если в пределах) — app.services.subsidy_ceiling, задача владельца 15.10.2026
        "feo_ceiling": float,                  # сам жёсткий потолок (Σ ФЭО по «верхним введённым» узлам), 0 если ФЭО нигде не введено
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

    # Ускорение 06.10.2026 (координатор, боевой замер GET /dashboard/charts:
    # 7,3с, из которых ~4,6с — эта функция): дерево ФЭО (compute_feo_plan_tree,
    # 699 узлов на локальной БД, ~0,8с на сборку) строилось здесь ПЯТЬ раз —
    # в subsidy_committed_totals, _plan_floor_added_by_subsidy,
    # subsidy_type_totals, _calculate_feo_planned_tree_bulk и
    # over_plan_categories_by_subsidy. Строим ОДИН раз и передаём готовое tree
    # во все пять (каждая функция опционально принимает `tree=`, см. их
    # докстринги; без аргумента — поведение прежнее, ничего не меняется).
    _tree = tree
    if _tree is None:
        from app.services.feo_plan_tree import compute_feo_plan_tree as _compute_feo_plan_tree
        _tree = await _compute_feo_plan_tree(db, subsidy_ids)

    calc_budget_map = budgets if budgets is not None else await calculate_budgets_bulk(db, subsidy_ids)
    committed_map = await subsidy_committed_totals(db, subsidy_ids, tree=_tree)
    plan_floor_map = await _plan_floor_added_by_subsidy(db, subsidy_ids, tree=_tree)

    # redistributable_by_kind — только если у субсидии есть разбивка бюджета ФЭО
    # по типу (дерево заполнено); иначе «бюджет по типу» не определён (см.
    # докстринг модуля) — для этого нужен ТОТ ЖЕ признак feo_filled, что
    # dashboard_charts.py использует (calc_budget_map[sid] > 0).
    filled_sids = [sid for sid in subsidy_ids if float(calc_budget_map.get(sid, 0.0) or 0.0) > 0]
    type_totals_map: dict = {}
    if filled_sids:
        from app.services.type_totals import subsidy_type_totals
        type_totals_map = await subsidy_type_totals(db, filled_sids, tree=_tree)

    # planned_tree одним batch-вызовом на весь список.
    from app.routers.subsidies import _calculate_feo_planned_tree_bulk
    planned_tree_map = await _calculate_feo_planned_tree_bulk(db, subsidy_ids, tree=_tree)
    # planned_full — Σ full_display корней, та же _tree (ПРАВИЛО №6, не
    # вторая сборка дерева) — карточка «Запланировано» (владелец,
    # 27.10.2026): полная сумма плановых позиций, БЕЗ урезания до ФЭО, см.
    # docstring feo_plan_subsidy_full_totals. planned/display-контроли выше
    # не трогаются.
    from app.services.feo_plan_totals import feo_plan_subsidy_full_totals
    planned_full_map = await feo_plan_subsidy_full_totals(db, subsidy_ids, tree=_tree)

    # Карточка «Можно перераспределить» БЕЗ обрезки по направлениям (владелец,
    # 06.10.2026, план sleepy-fluttering-walrus.md п.1) — см. докстринг
    # app.services.redistributable_raw. not_committed_nice/not_committed_likely
    # ниже теперь читаются ОТСЮДА (raw, без клэмпа компute_feo_plan_tree), а не
    # из _plan_floor_added_by_subsidy (та клэмпнутая версия остаётся только для
    # дерева/узлов — ничего в ней не меняем, см. docstring модуля там).
    # not_committed_raw_by_subsidy НЕ строит дерево сама (прямые запросы по
    # FeoPlannedItem) — tree ей не передаём, передавать нечего.
    raw_not_committed_map = await _not_committed_raw_fn(db, subsidy_ids)
    over_plan_categories_map = await _over_plan_categories_fn(db, subsidy_ids, tree=_tree)

    for sid in subsidy_ids:
        calc = calc_budget_map.get(sid, 0.0)
        budget = effective_subsidy_budget(calc, manual_budget_by_sid.get(sid))
        planned = planned_tree_map.get(sid, 0.0)
        planned_full = planned_full_map.get(sid, 0.0)
        _committed = committed_map.get(sid) or {}
        committed = _committed.get("committed", 0.0)
        committed_by_kind = {
            "goods": _committed.get("committed_goods", 0.0),
            "services": _committed.get("committed_services", 0.0),
            "payroll": _committed.get("committed_payroll", 0.0),
            "unspecified": _committed.get("committed_unspecified", 0.0),
        }
        planned_not_committed_by_kind = {
            "goods": _committed.get("plan_goods", 0.0) - committed_by_kind["goods"],
            "services": _committed.get("plan_services", 0.0) - committed_by_kind["services"],
            "payroll": _committed.get("plan_payroll", 0.0) - committed_by_kind["payroll"],
            "unspecified": _committed.get("plan_unspecified", 0.0) - committed_by_kind["unspecified"],
        }
        # ОТМЕНЕНО (владелец, 07.10.2026, план .planning/quick/2026-10-07-dnr-
        # feo-cards/PLAN.md шаг 1, решение №3): раньше при budget<=0 (ни
        # официального бюджета, ни суммы ФЭО) budget_basis подставлял planned
        # («бюджет = план») — на субсидии «ДНР» (409 плановых позиций,
        # 63 232 213,82 ₽, ФЭО не введено ни у одной из 41 статьи) карточка
        # «Бюджет (ФЭО)» показывала ПОДМЕНУ плана вместо честного «ФЭО не
        # введено», и из-за отдельного бага в feo_plan_tree.py (см. её
        # докстринг _feo_by_kind) эта подмена даже расходилась с «Запланировано»
        # на 8 191,49 ₽ (чайник+термопот). Теперь: budget<=0 → budget_basis/
        # free_basis/redistributable/redistributable_unplanned/
        # redistributable_by_kind/balance_by_marks/balance_by_statement — ВСЕ
        # None («ФЭО не введено», карточки «Бюджет (ФЭО)»/«Свободно»/«Можно
        # перераспределить» пустые), feo_entered=False. budget_from_plan
        # остаётся полем выдачи (всегда False теперь — подмена плана больше не
        # происходит ни при каких условиях) ТОЛЬКО для совместимости старых
        # потребителей (см. отчёт сессии — grep читателей). budget САМ (выше)
        # не меняется — его продолжают читать subsidy_revision_preview.py/
        # subsidy_revision_floor.py байт-в-байт как раньше.
        feo_entered = budget > 0
        budget_from_plan = False

        # Шаг 2 плана humble-stirring-emerson.md (23.10.2026) — формула
        # владельца: Можно перераспределить = ФЭО − законтрактовано =
        # (ФЭО − Запланировано) + (Запланировано − законтрактовано). ОБЕ
        # половины читают ТЕ ЖЕ числа, что уже показывают карточки
        # «Свободно»/«Запланировано»/«Законтрактовано» — ни одного нового
        # расчёта плана.
        #   not_planned (redistributable_unplanned) = free_basis = budget_basis
        #     − planned — ТО ЖЕ число, что карточка «Свободно». ИСПРАВЛЕНО
        #     (находка владельца 23.10.2026): раньше отсюда вычитался
        #     pending_excess («несогласованная прибавка»), из-за чего «не
        #     запланировано» расходилось со «Свободно» — на синтетической
        #     30871: 9 997,90 ≠ 19 997,90; на копии прода ФАДМ 2026_3 id 100:
        #     −326 492,00 ≠ 0,00. «Одно число — один источник» (ПРАВИЛО №6):
        #     теперь буквально то же free_basis, без поправок.
        #   R = planned − committed («Запланировано минус законтрактовано»)
        #     раскладывается на «хотелось бы» (nice, позиции need_level=
        #     nice_to_have, клэмп в [0, R]), «ещё уйдёт помесячно» (monthly —
        #     как раньше, monthly_future_not_started_raw), «задано на
        #     категорию, но не расписано позициями» (manual_plan_gap — как
        #     раньше, node['manual_plan_gap']), а «скорее всего понадобится»
        #     (likely) — ОСТАТОК R минус три предыдущие строки (владелец,
        #     пример 100/80/70/54: likely = 70 − 54 = 16). Отрицательный
        #     остаток — не прячем, показываем как есть (бывает на floor-
        #     артефактах/несогласованном превышении, см. отчёт).
        # Σ(not_planned+nice+likely+monthly+manual_gap) == free_basis + R ==
        # (budget_basis−planned) + (planned−committed) == budget_basis−committed
        # == redistributable ВСЕГДА, чисто алгебраически — больше не зависит
        # от floor-артефактов позиционных сумм (pending_excess-поправка не
        # нужна, удалена вместе с _plan_floor_added_by_subsidy.pending_excess).
        if feo_entered:
            budget_basis = budget
            free_basis = budget_basis - planned
            redistributable = budget_basis - committed
            redistributable_unplanned = free_basis
        else:
            budget_basis = None
            free_basis = None
            redistributable = None
            redistributable_unplanned = None

        _raw = raw_not_committed_map.get(sid) or {
            "nice_raw": 0.0, "likely_raw": 0.0, "by_kind": {}, "monthly_future_not_started_raw": 0.0,
            "nice_payroll_raw": 0.0, "likely_payroll_raw": 0.0, "monthly_future_not_started_payroll_raw": 0.0,
        }
        _gap_map = plan_floor_map.get(sid) or {}
        monthly_future_not_started = _raw.get("monthly_future_not_started_raw", 0.0) or 0.0
        manual_plan_gap = _gap_map.get("manual_plan_gap", 0.0) or 0.0
        R = planned - committed
        not_committed_nice_raw = max(0.0, min(_raw.get("nice_raw", 0.0) or 0.0, R))
        not_committed_likely_raw = R - not_committed_nice_raw - monthly_future_not_started - manual_plan_gap

        # payroll-доля той же remainder-конструкции (D7, живая приёмка
        # 21.10.2026, ДНР id 61) — ТОЛЬКО для payroll_visibility.
        # scrub_payroll_from_dashboard_charts (ПРАВИЛО №6 — тот же приём,
        # что и у R/nice/likely выше, restricted к kind=='payroll').
        R_payroll = (_committed.get("plan_payroll", 0.0) or 0.0) - committed_by_kind["payroll"]
        _nice_payroll = max(0.0, min(_raw.get("nice_payroll_raw", 0.0) or 0.0, R_payroll))
        _monthly_payroll = _raw.get("monthly_future_not_started_payroll_raw", 0.0) or 0.0
        _manual_gap_payroll = _gap_map.get("manual_plan_gap_payroll", 0.0) or 0.0
        _likely_payroll = R_payroll - _nice_payroll - _monthly_payroll - _manual_gap_payroll
        _free_payroll = 0.0
        if sid in type_totals_map:
            _free_payroll = type_totals_map[sid].get("feo_payroll", 0.0) - (_committed.get("plan_payroll", 0.0) or 0.0)

        # Строки по видам (п.4 Шаг 2 плана) = feo_<вид> − committed_<вид> —
        # бюджет вида минус законтрактовано вида, из уже существующих
        # type_totals/committed_amounts (ПРАВИЛО №6 — ни одна сумма здесь не
        # считается заново, raw-строки позиций для этого больше не нужны).
        # Σ видов == budget_basis − committed == redistributable ПО
        # ПОСТРОЕНИЮ (Σ feo_<вид> по корням дерева == budget_basis, Σ
        # committed_<вид> == committed, обе Σ уже проверены test_type_totals.py/
        # test_money_committed.py) — не зависит от floor/pending_excess-
        # артефактов, которые ломали старую raw+поправки формулу на ХРО_2026
        # (id 55 на стенде: Σ by_kind переоценивала ФОТ на ~11 млн).
        #
        # Товары/услуги НЕ показываются отрицательными (находка на копии
        # прода ФАДМ 2026_3 id 100: «товары −1 276 407,01 / услуги
        # −6 696 081,73 / без типа +11 087 752,04» — минус здесь означает не
        # «превышение по товару», а что реально законтрактованные товары/
        # услуги лежат в категориях, чей бюджет ФЭО никогда не был размечен
        # по виду (вся его сумма — в «без типа»); долг переносится в «без
        # типа» — ту же Σ видов это не меняет, убирает только обманчивый
        # минус из строки, которую владелец читает как конкретный план по
        # товару/услуге).
        if sid in type_totals_map:
            tt = type_totals_map[sid]
            _by_kind = {
                "goods": tt.get("feo_goods", 0.0) - committed_by_kind["goods"],
                "services": tt.get("feo_services", 0.0) - committed_by_kind["services"],
                "payroll": tt.get("feo_payroll", 0.0) - committed_by_kind["payroll"],
                "unspecified": tt.get("feo_unspecified", 0.0) - committed_by_kind["unspecified"],
            }
            for _k in ("goods", "services"):
                if _by_kind[_k] < 0:
                    _by_kind["unspecified"] += _by_kind[_k]
                    _by_kind[_k] = 0.0
            redistributable_by_kind_raw = _by_kind if feo_entered else None
        elif feo_entered:
            # Нет разбивки бюджета ФЭО по видам (sid не в type_totals_map) —
            # ПОВЕДЕНИЕ НЕ МЕНЯЕТСЯ (байт-в-байт, как раньше): товары/услуги
            # читаются построчно из redistributable_raw.py (нечем читать
            # feo_<вид>, делить нечего), «не запланировано»/manual_gap
            # целиком уходят в «без типа» — ЭТУ ветку проверяют
            # test_redistributable_drill.py и test_monthly_future_payments.py
            # построчной сверкой, не ослаблять.
            _raw_by_kind = dict(_raw.get("by_kind") or {})
            if abs(redistributable_unplanned or 0.0) > 0.005:
                _raw_by_kind["unspecified"] = _raw_by_kind.get("unspecified", 0.0) + redistributable_unplanned
            for _k in ("goods", "services", "payroll", "unspecified"):
                _gap_k = _gap_map.get(f"manual_plan_gap_{_k}", 0.0) or 0.0
                if abs(_gap_k) > 0.005:
                    _raw_by_kind[_k] = _raw_by_kind.get(_k, 0.0) + _gap_k
            redistributable_by_kind_raw = {
                "goods": _raw_by_kind.get("goods", 0.0),
                "services": _raw_by_kind.get("services", 0.0),
                "payroll": _raw_by_kind.get("payroll", 0.0),
                "unspecified": _raw_by_kind.get("unspecified", 0.0),
            }
        else:
            redistributable_by_kind_raw = None

        result[sid] = {
            "budget": budget,
            "planned": planned,
            # «Запланировано» без урезания до ФЭО (владелец, 27.10.2026) — см.
            # docstring feo_plan_subsidy_full_totals. Чисто справочное поле
            # карточки, НЕ заменяет planned/free/redistributable выше.
            "planned_full": planned_full,
            "committed": committed,
            "committed_by_kind": committed_by_kind,
            "free": budget - planned,
            "planned_not_committed": planned - committed,
            "planned_not_committed_by_kind": planned_not_committed_by_kind,
            "redistributable": redistributable,
            # ИЗМЕНЕНО (23.10.2026, Шаг 2 плана humble-stirring-emerson.md):
            # redistributable_by_kind = feo_<вид> − committed_<вид>, когда у
            # субсидии есть разбивка бюджета ФЭО по видам (sid в
            # type_totals_map); иначе — старое raw-построение по позициям
            # (см. ветку выше). Фронт читает ОДНО имя redistributable_by_kind.
            "redistributable_by_kind": redistributable_by_kind_raw,
            "redistributable_unplanned": redistributable_unplanned,
            "committed_missing_fact_items": _committed.get("committed_missing_fact_items", 0),
            "plan_floor_added": plan_floor_map.get(sid, {}).get("plan_floor_added", 0.0),
            # «Ещё уйдёт помесячно, не начато» (переименовано 15.10.2026 из
            # contracted_not_ordered — план abstract-noodling-pelican.md, п.C) —
            # app.services.monthly_future_payments, источник (а) ТОЛЬКО, см.
            # докстринг redistributable_raw.not_committed_raw_by_subsidy.
            "monthly_future_not_started": monthly_future_not_started,
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
            # not_committed_likely/not_committed_nice — УЖЕ БЕЗ «ещё уйдёт
            # помесячно, не начато» (not_committed_raw_by_subsidy исключила эти
            # строки целиком, см. её докстринг) — monthly_future_not_started
            # показывается отдельной строкой, не прибавляется поверх likely/nice.
            "not_committed_likely": not_committed_likely_raw,
            "not_committed_nice": not_committed_nice_raw,
            # D7 (живая приёмка 21.10.2026, ДНР id 61) — payroll-доля этой и
            # трёх соседних подстрок карточки «Можно перераспределить», ТА ЖЕ
            # Σ, что уже вычтена из redistributable_by_kind['payroll'] выше
            # (не вторая формула — просто отдельные накопители того же
            # прохода not_committed_raw_by_subsidy/_free_k). Используется
            # ТОЛЬКО payroll_visibility.scrub_payroll_from_dashboard_charts —
            # dashboard_charts.py эти 4 ключа в subsidy_stats НЕ отдаёт
            # (не нужны пользователю с правом, он их не видит).
            "not_committed_likely_payroll": _likely_payroll,
            "not_committed_nice_payroll": _nice_payroll,
            "monthly_future_not_started_payroll": _monthly_payroll,
            "redistributable_unplanned_payroll": _free_payroll,
            # Шаг 2 плана humble-stirring-emerson.md (23.10.2026) — «задано на
            # категорию, но не расписано позициями», строка карточки «Можно
            # перераспределить» (пример владельца ФЭО 100/задано 80/позиции 70/
            # законтрактовано 54 → эта строка = 80−70 = 10). Источник — ОДНА
            # точка feo_plan_common.manual_plan_gap через node['manual_plan_gap']
            # (compute_feo_plan_tree), Σ по корням уже готова в plan_floor_map
            # (см. _plan_floor_added_by_subsidy выше, ПРАВИЛО №6 — не вторая
            # формула). Делает ТОЧНЫМ инвариант (см. докстринг модуля):
            # redistributable == redistributable_unplanned + not_committed_nice
            # + not_committed_likely + monthly_future_not_started + manual_plan_gap.
            "manual_plan_gap": manual_plan_gap,
            # Правка 23.10.2026 (владелец) — payroll-доля manual_plan_gap, ТА
            # ЖЕ Σ, что уже вошла в redistributable_by_kind['payroll'] выше
            # (не вторая формула) — нужна ТОЛЬКО payroll_visibility.
            # scrub_payroll_from_dashboard_charts, чтобы «manual_plan_gap»
            # (скаляр строки карточки) тоже уменьшался у пользователя без
            # права «Видеть ФОТ» — иначе Σ(подстрок) ≠ redistributable
            # (уже вычищенный) ровно на эту долю. dashboard_charts.py этот
            # ключ в subsidy_stats НЕ отдаёт (не нужен пользователю с правом).
            "manual_plan_gap_payroll": plan_floor_map.get(sid, {}).get("manual_plan_gap_payroll", 0.0),
            "budget_basis": budget_basis,
            "budget_from_plan": budget_from_plan,
            "free_basis": free_basis,
            # feo_entered (решение владельца 07.10.2026, план .planning/quick/
            # 2026-10-07-dnr-feo-cards/PLAN.md шаг 1) — True, если у субсидии
            # задан официальный бюджет ИЛИ хоть у одной статьи ФЭО (budget>0,
            # effective_subsidy_budget уже объединил оба источника выше).
            # False → budget_basis/free_basis/redistributable*/balance_* = None,
            # фронт пишет «ФЭО не введено» на карточках «Бюджет (ФЭО)»/
            # «Свободно»/«Можно перераспределить»/«Остаток субсидии».
            "feo_entered": feo_entered,
        }
        # «Остаток субсидии» (владелец, 06.10.2026) = бюджет для показа − уже
        # проведённые оплаты. Поступление на счёт пока = бюджету ФЭО (ввода
        # поступлений нет), поэтому это же число — «остаток на счёте».
        # budget_basis is None (ФЭО не введено, см. feo_entered выше) — оба
        # поля None («бюджет не введён»), та же ветка feo_entered/else, что у
        # redistributable выше.
        balance_paid_marked = plan_floor_map.get(sid, {}).get("paid_marked", 0.0)
        balance_paid_confirmed = plan_floor_map.get(sid, {}).get("paid_confirmed", 0.0)
        result[sid]["balance_paid_marked"] = balance_paid_marked
        result[sid]["balance_paid_confirmed"] = balance_paid_confirmed
        if feo_entered:
            result[sid]["balance_by_marks"] = budget_basis - balance_paid_marked
            result[sid]["balance_by_statement"] = budget_basis - balance_paid_confirmed
        else:
            result[sid]["balance_by_marks"] = None
            result[sid]["balance_by_statement"] = None

        # Задача владельца 15.10.2026 (ФАДМ 2026_3: «Запланировано» 15 920 830 >
        # «Бюджет (ФЭО)» 15 880 100, карточка никак не кричала об этом) —
        # жёсткий потолок субсидии, ОДНА функция с assert_subsidy_ceiling/
        # app.routers.plan_excess (ПРАВИЛО №6, см. app.services.subsidy_ceiling)
        # — здесь БЕЗ исключения, только числа для карточки «Запланировано».
        # adding_amount=0: это просто текущее состояние, не проверка действия.
        from app.services.subsidy_ceiling import subsidy_ceiling_state
        _ceiling_state = await subsidy_ceiling_state(db, sid, tree=_tree)
        result[sid]["plan_over_ceiling_amount"] = _ceiling_state["over_amount"]
        result[sid]["feo_ceiling"] = _ceiling_state["ceiling"]

    return result
