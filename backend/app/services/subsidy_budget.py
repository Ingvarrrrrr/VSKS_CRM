# -*- coding: utf-8 -*-
"""Единый источник истины (Правило №6) для «бюджета субсидии из дерева ФЭО».

Формула узла: budget = собственный FeoCategory.budget, если задан вручную,
иначе сумма feo_amount СОБСТВЕННЫХ плановых позиций (FeoPlannedItem) узла
плюс сумма budget прямых детей (рекурсивно). Бюджет субсидии = сумма этой
величины по корневым узлам (level == 1).

Решение владельца (2026-09-16, боевой инцидент — субсидия «Абхазия_2»,
189 позиций на 30 274 896 ₽ с is_feo_breakdown=true, карточка субсидии
показывала «по ФЭО» 4 484 400 ₽): позиции ЛЮБОГО узла — не только листового —
обязаны попадать в «по ФЭО» узла, если у узла самого нет явной Суммы по ФЭО.
Явная сумма узла по-прежнему ГЛАВНЕЕ и позиции поверх нее НЕ прибавляются
(без этого правила узел вроде «Катер» — сам одновременно и подраздел, и
плановая позиция с тем же именем и той же суммой, см. item_name_equals_category
в feo_import_apply.py — задвоил бы сумму: budget родителя = сумма ФЭО строки
+ ЕЩЁ РАЗ feo_amount позиции с той же суммой внутри). Позиции без feo_amount
(NULL — это план, не ФЭО, см. докстринг FeoPlannedItem.feo_amount) в счёт
«по ФЭО» не идут.

До этой правки формула была продублирована ТРИ раза:
  1) app.routers.subsidies._budget_from_tree — агрегат по субсидии (роуты
     list/detail/create/approve/update).
  2) app.routers.feo_plan_reads.calc_budget (эндпоинт /budget-residuals) —
     та же рекурсия, но по требованию для конкретного узла (направления и
     листья с ancestors), не только сумма корней.
  3) app.routers.dashboard — копия формулы фолбэка «расчёт из дерева, а
     если дерево пустое (0) — ручное subsidy.budget» (effective_budget).

Теперь обе части (рекурсия по дереву + фолбэк на ручной budget) живут
здесь. app.routers.subsidies.calculate_budget_from_categories/
calculate_budgets_bulk остаются тонкими обёртками — их продолжают
импортировать app.routers.dashboard, app.routers.feo_tree_ops,
app.routers.purchase_budget, app.services.feo_plan, и монкипатчить тесты
(test_subsidy_draft.py: `monkeypatch.setattr(subsidies,
"calculate_budget_from_categories", ...)`).

⚠️ НЕ путать с app.services.feo_plan.compute_feo_plan_tree — та функция
считает СОВСЕМ ДРУГУЮ величину: «план/факт/заказ» дерева (plan_manual,
ordered, over, display — с заменой плана заказом при наборе количества),
а не агрегат «финансирование по дереву ФЭО». Её узловое поле "budget" —
это СОБСТВЕННОЕ (не рекурсивное) значение FeoCategory.budget, читаемое
напрямую из строки категории и используемое только для сравнения
план vs финансирование на каждом узле (excess-проверки). Рекурсии
«сумма детей, если NULL» там нет — дублирования с этим файлом нет.
Если это когда-либо изменится (compute_feo_plan_tree начнёт считать
агрегат по дереву сама), её нужно перевести на compute_budget_map()
отсюда, а не заводить четвёртую копию.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


def normalize_feo_category_budget(raw_budget) -> Optional[float]:
    """Явный FeoCategory.budget узла — «задано ли вручную» или None.

    ЕДИНСТВЕННОЕ место с этой нормализацией (Правило №6) — перенесено сюда
    2026-09-21 из app.services.feo_plan_tree (там ЖЕ было заведено раньше,
    для _feo_by_kind/compute_feo_plan_tree, но оставлено НЕприменённым здесь,
    в compute_budget_map — единственном источнике feo_budget_total, см.
    докстринг модуля выше). Из-за этого расхождения scalar (calculate_budgets_bulk)
    и дерево/типовой split (feo_plan_tree.py) расходились на категориях с
    budget=0: явный ноль в _calc() ниже трактовался как «финансирование = 0»
    (Excel-импорт пишет 0 в пустую ячейку вместо NULL), а дерево уже считало
    0 как «не задано» — боевой замер, субсидия «Тестовая» (id 59):
    feo_budget_total=0, split по типу=100 000 (найдены typed ФЭО-строки,
    которые compute_budget_map тут же отбрасывал явным budget=0 узла).

    Владелец, Волна 1 п.8 (2026-09-13), дословно: «Когда в поле финансирование
    по ФЭО введено „0", то в моём понимании это значит, что не задана сумма.
    ... Ведь если нет жёстко заданной суммы, то и сравнивать не с чем.» — то
    же поле (FeoCategory.budget), та же семантика везде, где оно читается как
    «задано вручную» (compute_budget_map._calc ниже, app.services.feo_plan_tree
    ._feo_by_kind/_visit, app.services.type_totals.subsidy_type_totals — ВСЕ
    импортируют эту функцию, а не переопределяют собственную проверку
    `budget is not None`)."""
    if raw_budget is None:
        return None
    val = float(raw_budget)
    return val if val != 0.0 else None


def compute_budget_map(categories: Iterable, items: Iterable | None = None) -> dict:
    """budget по КАЖДОМУ узлу переданного набора категорий одного дерева
    (не только по корням): собственный FeoCategory.budget, если задан,
    иначе — сумма feo_amount СОБСТВЕННЫХ плановых позиций узла (`items`,
    активных, с непустым feo_amount) плюс сумма budget прямых детей
    (рекурсивно, с мемоизацией).

    `items` — необязательный итерируемый набор FeoPlannedItem (или любых
    объектов с атрибутами feo_category_id/feo_amount/is_active) ЛЮБЫХ
    категорий, не обязательно только переданного дерева — элементы, чей
    feo_category_id не входит в `categories`, тихо игнорируются. Не передан
    (или пуст) — поведение как раньше, ДО задачи владельца 2026-09-16
    (только budget, без учёта позиций); это сохраняет обратную совместимость
    для вызывающих кода, которым позиции не нужны или недоступны (например,
    feo_import_plan.py — там сверяется budget родителя vs budget детей, эта
    проверка про позиции не спрашивает).

    Общая для:
      - subsidy_budget_from_categories (сумма по корневым узлам, агрегат
        бюджета субсидии);
      - app.routers.feo_plan_reads /budget-residuals (точечный budget
        любого узла — направления/листа/предка).
    """
    cats = list(categories)
    by_id = {c.id: c for c in cats}
    children_map: dict = {}
    for c in cats:
        children_map.setdefault(c.id, [])
        if c.parent_id is not None and c.parent_id in by_id:
            children_map.setdefault(c.parent_id, []).append(c)

    items_by_cat: dict = {}
    for it in (items or ()):
        cid = getattr(it, "feo_category_id", None)
        if cid in by_id:
            items_by_cat.setdefault(cid, []).append(it)

    def _own_items_feo_sum(cat_id) -> float:
        total = 0.0
        for it in items_by_cat.get(cat_id, ()):
            if not getattr(it, "is_active", True):
                continue
            fa = getattr(it, "feo_amount", None)
            if fa is not None:
                total += float(fa)
        return total

    memo: dict = {}

    def _calc(cat) -> float:
        if cat.id in memo:
            return memo[cat.id]
        _own_budget = normalize_feo_category_budget(cat.budget)
        if _own_budget is not None:
            # Явная сумма узла — главнее (Правило владельца, задача (в)):
            # собственные позиции узла (если есть) НЕ прибавляются поверх —
            # иначе узел вроде «Катер» (сам себе и подраздел, и позиция с той
            # же суммой) задвоил бы «по ФЭО». 0 == «не задано» (Волна 1 п.8,
            # см. normalize_feo_category_budget) — падает в ветку else.
            val = _own_budget
        else:
            kids = children_map.get(cat.id, [])
            val = _own_items_feo_sum(cat.id) + sum(_calc(k) for k in kids)
        memo[cat.id] = val
        return val

    for c in cats:
        _calc(c)
    return memo


def subsidy_budget_from_categories(categories: Iterable, items: Iterable | None = None) -> float:
    """Агрегат «бюджет субсидии из дерева ФЭО» — сумма budget (см.
    compute_budget_map) по корневым узлам (level == 1). Единственная
    реализация рекурсии для этой величины в проекте."""
    cats = list(categories)
    if not cats:
        return 0.0
    budget_map = compute_budget_map(cats, items)
    roots = [c for c in cats if c.level == 1]
    return sum(budget_map.get(r.id, 0.0) for r in roots)


def effective_subsidy_budget(calc: float, manual_budget: Optional[float]) -> float:
    """Формула фолбэка: расчёт из дерева ФЭО, а если дерево пустое
    (calc <= 0, категорий ещё нет/не заполнены) — ручное значение
    subsidy.budget. Решение 14.07: budget — ручное значение, деревом
    ФЭО НЕ перезаписывается — но при пустом дереве оно единственный
    источник для "бюджет субсидии"."""
    calc = float(calc or 0.0)
    return calc if calc > 0 else float(manual_budget or 0)


async def _active_feo_items_with_amount(db: AsyncSession, cat_ids: list) -> list:
    """Собственные плановые позиции узлов дерева, участвующие в «по ФЭО»
    (задача владельца 2026-09-16): активные, с непустым feo_amount — позиции
    без feo_amount (NULL) являются планом, не ФЭО (см. докстринг
    FeoPlannedItem.feo_amount), в счёт не идут. Отфильтровано в SQL, а не в
    compute_budget_map, чтобы не таскать по сети позиции, заведомо не
    участвующие в сумме."""
    if not cat_ids:
        return []
    result = await db.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active == True,  # noqa: E712
            FeoPlannedItem.feo_amount.isnot(None),
        )
    )
    return result.scalars().all()


async def calculate_budget_from_categories(db: AsyncSession, subsidy_id: int) -> float:
    result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    cats = result.scalars().all()
    items = await _active_feo_items_with_amount(db, [c.id for c in cats])
    return subsidy_budget_from_categories(cats, items)


async def calculate_budgets_bulk(db: AsyncSession, subsidy_ids: list) -> dict:
    """Бюджеты для набора субсидий одним запросом (вместо N запросов в списках)."""
    if not subsidy_ids:
        return {}
    result = await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )
    by_subsidy: dict = {}
    for c in result.scalars().all():
        by_subsidy.setdefault(c.subsidy_id, []).append(c)
    # Одна выборка позиций на ВСЕ субсидии сразу (вместо N) — compute_budget_map
    # сама отфильтрует по feo_category_id внутри дерева каждой субсидии
    # (categories, переданные для этой субсидии, не пересекаются с id категорий
    # других субсидий).
    all_cat_ids = [c.id for cats in by_subsidy.values() for c in cats]
    items = await _active_feo_items_with_amount(db, all_cat_ids)
    return {
        sid: subsidy_budget_from_categories(by_subsidy.get(sid, []), items)
        for sid in subsidy_ids
    }
