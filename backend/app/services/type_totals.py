"""План B (ancient-prancing-music.md, раздел B/2) — «Бюджет (ФЭО)» и «План» по
типам (товары/услуги/без типа) для дашборда и списка/карточки субсидий.

Правило №6 проекта — этот модуль ЕДИНСТВЕННОЕ место, где считаются
план/ФЭО-суммы, разбитые по типу позиции. dashboard_charts.py и
app.routers.subsidies._calculate_feo_planned_tree_bulk ТОЛЬКО читают отсюда.

Тип позиции и доли — из app.services.item_type_split (kind_of), тоже
единственный источник, не переопределяется здесь.

ПЕРЕРАБОТАНО 2026-09-21 (Правило №6, боевые расхождения на живой БД —
GET /api/dashboard/charts?type_split=true): ДО этой правки subsidy_type_totals
считала план и ФЭО ДВУМЯ собственными формулами (плоский Σ FeoPlannedItem.amount
для плана — БЕЗ order-substitution/over/budget-клэмпа, которые применяет дерево;
рекурсия по FeoCategory для ФЭО — c фильтром is_feo_breakdown=true, которого
НЕТ у scalar'а calculate_budgets_bulk, и БЕЗ 0-нормализации budget, которая
ЕСТЬ у дерева) — обе формулы расходились со своими scalar'ами на живых данных:
  - «ДНР» (id 61): split 63 477 577,92 vs feo_budget_total 64 312 577,92
    (diff 835 000 — строки с feo_amount, но is_feo_breakdown=false, scalar их
    учитывает, старый split — нет);
  - «Тестовая» (id 59): split 100 000 vs feo_budget_total 0 (категория с
    budget=0: calculate_budgets_bulk трактовал explicit-ноль как «финансирование
    = 0» — 0-нормализация Волны 1 п.8 была применена только в дереве, НЕ в
    subsidy_budget.py);
  - «ЦентрПоиск_2026»: split (план) 94 712 790 vs planned_tree 75 896 105
    (diff 18,8 млн — старый _plan_by_kind суммировал Σ amount БЕЗ замещения
    «заказ вместо плана» и без «over», которые применяет node['display']).

Оба источника расхождения устранены НЕ вторыми формулами, а тем, что
subsidy_type_totals теперь ЧИТАЕТ готовые числа из ОДНОГО общего дерева
(app.services.feo_plan_tree.compute_feo_plan_tree) — того самого, что
считает и planned_tree (app.services.feo_plan_totals.feo_plan_subsidy_totals,
Σ node['display'] корней), и (после переноса normalize_feo_category_budget
в app.services.subsidy_budget и синхронизации compute_budget_map с той же
0-нормализацией) byte-в-byte совпадает с feo_budget_total
(app.services.subsidy_budget.calculate_budgets_bulk). Σ по корневым узлам
(parent_id IS NULL) node['plan_goods'/'plan_services'/'plan_unspecified'/
'feo_goods'/'feo_services'/'feo_unspecified'] — вот и весь расчёт, второго
прохода по FeoCategory/FeoPlannedItem здесь больше нет.

Инвариант «Σ трёх корзин == scalar» теперь ГАРАНТИРОВАН построением (общий
источник), а не отдельной сверкой — test_type_totals.py и
test_dashboard_charts_type_split.py всё равно проверяют его на фикстурах и
через GET /api/dashboard/charts, чтобы дрейф формулы дерева был виден тестом.

effective_item_types() ниже — ОТДЕЛЬНАЯ, не связанная с subsidy_type_totals,
функция («тип позиции, унаследованный от связанных позиций закупок») —
единственная реализация, её импортируют и app.routers.feo_planned_items_reports,
и app.services.feo_plan_tree.resolve_effective_item_types — не трогается этой
переработкой.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

_EMPTY_TOTALS = {
    "plan_goods": 0.0, "plan_services": 0.0, "plan_unspecified": 0.0,
    "feo_goods": 0.0, "feo_services": 0.0, "feo_unspecified": 0.0,
}


async def effective_item_types(db: AsyncSession, planned_item_ids: List[int]) -> Dict[int, Optional[str]]:
    """Тип, унаследованный плановой позицией от связанных позиций закупок —
    ЕДИНСТВЕННАЯ реализация (см. докстринг модуля). Возвращает только те id, у
    которых нашлась хоть одна связанная позиция закупки; вызывающий код обязан
    использовать собственный item_type позиции ПЕРВЫМ приоритетом, это — только
    фолбэк для позиций с пустым item_type.

    Один и тот же непустой тип у ВСЕХ связанных позиций закупок — наследуем;
    разные типы — не выдумываем за пользователя, id в результат не попадает
    (эквивалент None у вызывающего).
    """
    if not planned_item_ids:
        return {}
    # Локальный импорт — как и в feo_planned_items_reports.py, избежать цикла
    # на уровне модуля (purchase_budget.py тянет собственный набор роутеров).
    from app.routers.purchase_budget import PLANNED_STATUSES

    rows = (await db.execute(
        select(PurchaseItem.feo_planned_item_id, PurchaseItem.item_type)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(planned_item_ids))
        .where(Purchase.status.in_(PLANNED_STATUSES))
        .where(Purchase.stopped_at.is_(None))
        .distinct()
    )).all()

    types_by_planned: Dict[int, set] = {}
    for fpi_id, itype in rows:
        if not itype:
            continue
        types_by_planned.setdefault(fpi_id, set()).add(itype)

    return {
        fpi_id: (next(iter(types)) if len(types) == 1 else None)
        for fpi_id, types in types_by_planned.items()
    }


async def subsidy_type_totals(db: AsyncSession, subsidy_ids: List[int]) -> Dict[int, dict]:
    """{sid: {"plan_goods","plan_services","plan_unspecified",
              "feo_goods","feo_services","feo_unspecified"}} для набора субсидий.

    ЕДИНСТВЕННЫЙ проход — compute_feo_plan_tree (общий источник и для
    planned_tree, и, транзитивно, для feo_budget_total, см. докстринг модуля
    выше) + Σ по корневым узлам готовых typed-полей. Второй формулы здесь
    больше нет — если она понадобится, значит разошлось само дерево, чинить
    там (app.services.feo_plan_tree), а не заводить копию тут."""
    if not subsidy_ids:
        return {}
    result: Dict[int, dict] = {sid: dict(_EMPTY_TOTALS) for sid in subsidy_ids}

    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    for node in tree.values():
        if node.get("parent_id") is not None:
            continue  # только корневые узлы — та же выборка, что planned_tree/feo_budget_total
        sid = node.get("subsidy_id")
        if sid not in result:
            continue
        d = result[sid]
        d["plan_goods"] += node["plan_goods"]
        d["plan_services"] += node["plan_services"]
        d["plan_unspecified"] += node["plan_unspecified"]
        d["feo_goods"] += node["feo_goods"]
        d["feo_services"] += node["feo_services"]
        d["feo_unspecified"] += node["feo_unspecified"]

    return result
