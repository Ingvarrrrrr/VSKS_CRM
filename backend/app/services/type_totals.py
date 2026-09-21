"""План B (ancient-prancing-music.md, раздел B/2) — «Бюджет (ФЭО)» и «План» по
типам (товары/услуги/без типа) для дашборда и списка/карточки субсидий.

Правило №6 проекта — этот модуль ЕДИНСТВЕННОЕ место, где считаются
план/ФЭО-суммы, разбитые по типу позиции. dashboard_charts.py и
app.routers.subsidies._calculate_feo_planned_tree_bulk ТОЛЬКО читают отсюда.

Тип позиции и доли — из app.services.item_type_split (kind_of), тоже
единственный источник, не переопределяется здесь.

ПЛАН по типу = Σ FeoPlannedItem.amount (активные) субсидии, сгруппированная по
kind_of(эффективный_тип). Ровно тот же набор строк, что и
app.routers.subsidies._calculate_planned_amounts_bulk (Σ FeoPlannedItem.amount,
is_active=True) — сумма трёх корзин здесь обязана совпадать с её результатом
(проверено test_type_totals.py). «Эффективный тип» = собственный item_type
позиции, а если он пуст — тип, унаследованный от связанных позиций закупок
(PurchaseItem.feo_planned_item_id), если у ВСЕХ таких позиций один и тот же
тип — та же логика, что была инлайн в app.routers.feo_planned_items_reports
(строки 277-304 до этой правки); теперь единственная реализация — функция
effective_item_types() ниже, отчёт её импортирует (не дублирует).

ФЭО по типу — зеркалит рекурсию app.services.subsidy_budget.compute_budget_map
(budget узла = собственный FeoCategory.budget, если задан вручную, иначе Σ
feo_amount собственных активных плановых позиций узла [с непустым feo_amount]
плюс Σ budget прямых детей), но раскладывает те же числа на три корзины по
kind_of(эффективный_тип) вместо одного числа. Явная FeoCategory.budget без
разбивки по позициям типом не помечена — идёт целиком в feo_unspecified
(«нетипизированный бюджет категории», см. план, раздел допущений). Формула
ТА ЖЕ (тот же набор строк/условий), что и subsidy_budget.py — если она там
когда-нибудь изменится, эту рекурсию нужно обновить синхронно (см. её
докстринг про НЕ заводить четвёртую копию); прямой импорт recursion-функции
оттуда не делается только потому, что она возвращает одно число на узел, а
не триплет — test_type_totals.py проверяет расхождение с
calculate_budgets_bulk на общей фикстуре, чтобы дрейф был виден тестом.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.item_type_split import KIND_GOODS, KIND_SERVICES, KIND_UNSPECIFIED, kind_of

_EMPTY_TOTALS = {
    "plan_goods": 0.0, "plan_services": 0.0, "plan_unspecified": 0.0,
    "feo_goods": 0.0, "feo_services": 0.0, "feo_unspecified": 0.0,
}


async def effective_item_types(db: AsyncSession, planned_item_ids: List[int]) -> Dict[int, Optional[str]]:
    """Тип, унаследованный плановой позицией от связанных позиций закупок —
    ЕДИНСТВЕННАЯ реализация (см. докстринг модуля). Возвращает только те id, у
    которых нашлась хоть одна связанная позиция закупки; вызывающий код обязан
    использовать собственный item_type позиции ПЕРВЫМ приоритетом, это — только
    фолбэк для позиций с пустым item_type (см. _effective_type ниже).

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


def _effective_type(own_type: Optional[str], item_id: int, inherited: Dict[int, Optional[str]]) -> Optional[str]:
    return own_type or inherited.get(item_id)


async def subsidy_type_totals(db: AsyncSession, subsidy_ids: List[int]) -> Dict[int, dict]:
    """{sid: {"plan_goods","plan_services","plan_unspecified",
              "feo_goods","feo_services","feo_unspecified"}} для набора субсидий.

    Один bulk-запрос на план + один bulk-запрос на дерево категорий/ФЭО-позиции
    (без N+1 по субсидиям)."""
    if not subsidy_ids:
        return {}
    result: Dict[int, dict] = {sid: dict(_EMPTY_TOTALS) for sid in subsidy_ids}

    # ── ПЛАН: Σ активных FeoPlannedItem.amount по kind_of(эффективный тип) ──
    plan_rows = (await db.execute(
        select(FeoPlannedItem.id, FeoPlannedItem.item_type, FeoPlannedItem.amount, FeoCategory.subsidy_id)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(FeoPlannedItem.is_active == True)  # noqa: E712
    )).all()
    plan_inherited = await effective_item_types(db, [r.id for r in plan_rows])
    for r in plan_rows:
        eff = _effective_type(r.item_type, r.id, plan_inherited)
        kind = kind_of(eff)
        amt = float(r.amount) if r.amount is not None else 0.0
        result[r.subsidy_id][f"plan_{kind}"] += amt

    # ── ФЭО: рекурсия дерева категорий, зеркалит compute_budget_map (см. докстринг) ──
    cat_rows = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )).scalars().all()
    if not cat_rows:
        return result

    by_subsidy: Dict[int, list] = {}
    for c in cat_rows:
        by_subsidy.setdefault(c.subsidy_id, []).append(c)

    all_cat_ids = [c.id for c in cat_rows]
    # Собственные позиции узлов, участвующие в «по ФЭО» — те же условия, что
    # _active_feo_items_with_amount (subsidy_budget.py): активные, feo_amount
    # задан (NULL — это план, не ФЭО, см. докстринг FeoPlannedItem.feo_amount).
    feo_item_rows = (await db.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(all_cat_ids),
            FeoPlannedItem.is_active == True,  # noqa: E712
            FeoPlannedItem.feo_amount.isnot(None),
        )
    )).scalars().all()
    feo_inherited = await effective_item_types(db, [it.id for it in feo_item_rows])
    items_by_cat: Dict[int, list] = {}
    for it in feo_item_rows:
        items_by_cat.setdefault(it.feo_category_id, []).append(it)

    for sid, cats in by_subsidy.items():
        by_id = {c.id: c for c in cats}
        children_map: Dict[int, list] = {}
        for c in cats:
            children_map.setdefault(c.id, [])
            if c.parent_id is not None and c.parent_id in by_id:
                children_map.setdefault(c.parent_id, []).append(c)

        memo: Dict[int, tuple] = {}

        def _own_split(cat_id) -> tuple:
            g = s = u = Decimal(0)
            for it in items_by_cat.get(cat_id, ()):
                amt = Decimal(str(it.feo_amount)) if it.feo_amount is not None else Decimal(0)
                eff = _effective_type(it.item_type, it.id, feo_inherited)
                kind = kind_of(eff)
                if kind == KIND_GOODS:
                    g += amt
                elif kind == KIND_SERVICES:
                    s += amt
                else:
                    u += amt
            return g, s, u

        def _calc(cat) -> tuple:
            if cat.id in memo:
                return memo[cat.id]
            if cat.budget is not None:
                # Явная сумма узла главнее (см. compute_budget_map) — она НЕ
                # помечена типом, идёт целиком в «без типа».
                val = (Decimal(0), Decimal(0), Decimal(str(cat.budget)))
            else:
                og, os_, ou = _own_split(cat.id)
                for kid in children_map.get(cat.id, []):
                    kg, ks, ku = _calc(kid)
                    og += kg
                    os_ += ks
                    ou += ku
                val = (og, os_, ou)
            memo[cat.id] = val
            return val

        goods = services = unspecified = Decimal(0)
        for c in cats:
            if c.level == 1:
                g, s, u = _calc(c)
                goods += g
                services += s
                unspecified += u
        result[sid]["feo_goods"] = float(goods)
        result[sid]["feo_services"] = float(services)
        result[sid]["feo_unspecified"] = float(unspecified)

    return result
