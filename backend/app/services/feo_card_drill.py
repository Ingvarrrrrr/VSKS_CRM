# -*- coding: utf-8 -*-
"""feo_card_drill.py — «из чего сложено» число каждой карточки дерева ФЭО
(«Бюджет (ФЭО)» / «Запланировано» / «Свободно»), план .planning/quick/
2026-10-07-dnr-feo-cards/PLAN.md шаг 4.

ПРАВИЛО №6 владельца (жёстко): у каждой карточки РОВНО ОДНА функция, которая
отдаёт и строки, и число карточки — второго расчёта для окна не существует.
Эта функция НЕ пересчитывает бизнес-формулу заново — она читает уже готовые
per-node поля compute_feo_plan_tree (тот же источник, что и dashboard_charts.py/
subsidy_money_summary.py/type_totals.py через _feo_by_kind/_plan_by_kind) и
раскладывает их на строки арифметической декомпозицией (см. _own_contribution
ниже) — чисто комбинаторное тождество, независимое от деталей формулы узла:

    Σ_по_всем_узлам own(node) == Σ_по_корневым_узлам value(root)

потому что значение каждого НЕ-корневого узла входит в сумму ровно два раза
с противоположным знаком (раз — как own(node) самого узла, второй — внутри
own(parent) родителя, где оно вычитается) и взаимно уничтожается, а корневые
узлы входят только со знаком «+». Это верно для ЛЮБОГО числового поля узла
(plan_goods, feo_goods, ...), какой бы сложной ни была его формула внутри
compute_feo_plan_tree (order-substitution/floor/manual_sum/клэмп по budget) —
поэтому карточка и окно НЕ МОГУТ разойтись: число карточки = Σ node[field] по
корням (как считают dashboard_charts.py/subsidy_money_summary.py), число окна
= Σ own(node) по ВСЕМ узлам — то же самое число, тождественно.

Карточки:
  budget  — «Бюджет (ФЭО)»: строки — СТАТЬИ (не плановые позиции), own-доля
            node['feo_{kind}'] каждой статьи. Пусто (с reason), если ФЭО не
            введено ни у одной статьи субсидии (решение владельца 07.10.2026).
  planned — «Запланировано»: строки — ПЛАНОВЫЕ ПОЗИЦИИ (FeoPlannedItem), не
            статьи (владелец явно: окну нужны отдельные позиции, не агрегат
            по статье). own-доля node['plan_{kind}'] статьи разносится между
            её активными плановыми позициями ПРОПОРЦИОНАЛЬНО их Σ amount
            внутри той же корзины kind (см. _split_rows_proportionally) —
            сохраняет сумму строк байт-в-байт равной own-доле статьи, даже
            когда own-доля статьи отличается от голой Σ amount её позиций
            (замещение «заказ/договор вместо плана», шаг 2-3 плана «Деньги
            субсидии», или manual_sum). Для DNR (без закупок, без замещения)
            own-доля статьи ВСЕГДА равна Σ amount её позиций — пропорция
            тривиальна (просто сами позиции), это и даёт ожидаемые 368 строк
            на 63 232 213,82 ₽.
  free    — «Свободно» (ФЭО − план): строки — СТАТЬИ, own-доля разности
            node['feo_{kind}'] − node['plan_{kind}'] (та же декомпозиция).
            Пусто (с reason), если ФЭО не введено.

kind — all|goods|services|payroll|unspecified: фильтр по одной корзине (all —
строки по всем четырём, каждая строка несёт свой kind)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.item_type_split import ALL_KINDS, KIND_PAYROLL

_CENT = Decimal("0.01")
_EPS = 0.005

CARD_BUDGET = "budget"
CARD_PLANNED = "planned"
CARD_FREE = "free"
CARDS = (CARD_BUDGET, CARD_PLANNED, CARD_FREE)

_KIND_LABELS = {
    "goods": "Товары",
    "services": "Услуги",
    KIND_PAYROLL: "ФОТ и выплаты персоналу",
    "unspecified": "Без типа",
}


def _category_path(cat_id: Optional[int], cats: dict) -> str:
    """'Направление › Тип расходов › Статья' — путь от корня до cat_id
    включительно (тот же приём, что app.services.redistributable_raw._category_path
    — не вторая реализация, просто инлайн-копия 6 строк, т.к. функция там
    приватная модульная и привязана к её собственной структуре cats)."""
    if cat_id is None or cat_id not in cats:
        return ""
    names: list = []
    seen: set = set()
    cur = cat_id
    while cur is not None and cur in cats and cur not in seen:
        seen.add(cur)
        names.append(cats[cur]["name"] or "")
        cur = cats[cur]["parent_id"]
    return " › ".join(reversed(names))


def _own_contribution(cid: int, field: str, children_map: dict, tree: dict) -> float:
    """Own-доля узла cid по полю field (plan_X/feo_X узла) — узел МИНУС Σ
    ПРЯМЫХ детей по тому же полю. Комбинаторное тождество (см. докстринг
    модуля) гарантирует Σ own(cid) по ВСЕМ узлам субсидии == Σ по корневым
    узлам field — то же число, что карточка."""
    node = tree[cid]
    total = node.get(field, 0.0) or 0.0
    for kid in children_map.get(cid, []):
        total -= tree[kid].get(field, 0.0) or 0.0
    return total


def _split_rows_proportionally(own_amount: float, weighted_rows: list) -> list:
    """Делит own_amount между строками weighted_rows (каждая — dict с полем
    "weight", вес = её Σ amount в этой же корзине kind) пропорционально их
    весу, с округлением до копейки так, чтобы Σ частей была РОВНО own_amount
    (тот же принцип переноса остатка в наибольшую часть, что
    item_type_split.split_amount_by_shares/split_amount_by_kind_pool —
    применённый здесь к N строкам вместо 3-4 корзин, т.к. N здесь не
    фиксировано). Если Σ весов == 0 (позиции есть, но их Σ amount в этой
    корзине 0) — делит РАВНЫМИ долями. Возвращает НОВЫЙ список (копии входных
    dict с добавленным/перезаписанным полем "amount")."""
    if not weighted_rows:
        return []
    amt = Decimal(str(own_amount))
    target = amt.quantize(_CENT, rounding=ROUND_HALF_UP)
    weights = [Decimal(str(r.get("weight", 0.0) or 0.0)) for r in weighted_rows]
    total_w = sum(weights)
    if total_w == 0:
        n = len(weighted_rows)
        weights = [Decimal(1) for _ in weighted_rows]
        total_w = Decimal(n)
    raw = [amt * (w / total_w) for w in weights]
    rounded = [v.quantize(_CENT, rounding=ROUND_HALF_UP) for v in raw]
    diff = target - sum(rounded)
    if diff != 0 and rounded:
        idx = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[idx] += diff
    out = []
    for r, part in zip(weighted_rows, rounded):
        row = dict(r)
        row["amount"] = float(part)
        row.pop("weight", None)
        out.append(row)
    return out


async def _load_categories(db: AsyncSession, subsidy_id: int) -> tuple[dict, dict]:
    """(cats, children_map) — cats[cid] = {"name","parent_id"}; children_map[cid] =
    [прямые дети]. Общий загрузчик для всех трёх карточек этого модуля."""
    rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.parent_id, FeoCategory.name)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )).all()
    cats = {r.id: {"name": r.name, "parent_id": r.parent_id} for r in rows}
    children_map: dict = {}
    for r in rows:
        if r.parent_id is not None and r.parent_id in cats:
            children_map.setdefault(r.parent_id, []).append(r.id)
    return cats, children_map


async def _budget_basis(db: AsyncSession, subsidy_id: int) -> tuple:
    """(calc, budget_basis) — ТА ЖЕ пара, что subsidy_money_summary.py считает
    для feo_entered/budget_basis: calc = calculate_budgets_bulk (чистый расчёт
    из дерева ФЭО, 0 если дерево пустое), budget_basis = effective_subsidy_budget
    (calc, если > 0, иначе РУЧНОЙ Subsidy.budget — subsidy_money_summary.py,
    ПРАВИЛО №6, не вторая проверка). calc<=0 И budget_basis>0 — субсидия БЕЗ
    typed-разбивки дерева, но с ручным числом (пример — субсидия «Тестовая»,
    см. dashboard_charts.py и её комментарий про этот же частный случай)."""
    from app.services.subsidy_budget import calculate_budgets_bulk, effective_subsidy_budget

    calc_map = await calculate_budgets_bulk(db, [subsidy_id])
    calc = float(calc_map.get(subsidy_id, 0.0) or 0.0)
    from app.models.subsidy import Subsidy
    manual_budget = (await db.execute(
        select(Subsidy.budget).where(Subsidy.id == subsidy_id)
    )).scalar_one_or_none()
    budget_basis = effective_subsidy_budget(calc, manual_budget)
    return calc, budget_basis


async def card_drill_rows(
    db: AsyncSession, subsidy_id: int, card: str, kind: str = "all", *, tree: Optional[dict] = None,
) -> dict:
    """{"card","kind","total","rows":[...],"reason": str|None}.

    rows — для card="planned": [{"planned_item_id","name","category_path",
    "feo_category_id","kind","kind_label","item_type","quantity","amount"}];
    для card="budget"/"free": [{"feo_category_id","category_path","kind",
    "kind_label","amount"}].

    total — РОВНО то же число, что карточка на экране (см. докстринг модуля):
    budget/free читают Σ по корневым узлам node['feo_{kind}']/(feo-plan), planned
    читает Σ по корневым узлам node['plan_{kind}'] (= node['display'], KPI
    «Запланировано»). kind="all" — Σ по всем 4 корзинам."""
    if card not in CARDS:
        raise ValueError(f"unknown card {card!r}")
    kinds = list(ALL_KINDS) if kind == "all" else [kind]

    from app.services.feo_plan_tree import compute_feo_plan_tree

    _tree = tree
    if _tree is None:
        _tree = await compute_feo_plan_tree(db, [subsidy_id])
    # Узлы ЭТОЙ субсидии только (compute_feo_plan_tree может быть вызвана с
    # несколькими subsidy_ids вызывающим кодом — здесь всегда одна).
    nodes = {cid: n for cid, n in _tree.items() if n.get("subsidy_id") == subsidy_id}
    roots = [cid for cid, n in nodes.items() if n.get("parent_id") is None]

    cats, children_map = await _load_categories(db, subsidy_id)
    # children_map должен быть ОГРАНИЧЕН узлами этой субсидии (на случай, если
    # compute_feo_plan_tree вызвана batched — nodes уже отфильтрованы выше).
    children_map = {cid: [c for c in kids if c in nodes] for cid, kids in children_map.items() if cid in nodes}

    manual_fallback_amount: Optional[float] = None
    if card in (CARD_BUDGET, CARD_FREE):
        calc, budget_basis = await _budget_basis(db, subsidy_id)
        feo_entered = budget_basis > 0
        if not feo_entered:
            return {
                "card": card, "kind": kind, "total": 0.0, "rows": [],
                "reason": "ФЭО не введено ни у одной статьи субсидии",
            }
        if calc <= 0:
            # Субсидия БЕЗ typed-разбивки дерева ФЭО (ни одной статьи с budget/
            # feo_amount), но с РУЧНЫМ Subsidy.budget (пример — «Тестовая»,
            # id 59, см. тот же частный случай в dashboard_charts.py) — число
            # целиком «без типа», одной строкой без статьи (ПРАВИЛО №6: та же
            # подстановка, что видит карточка, не вторая формула).
            from app.services.feo_plan_totals import feo_plan_subsidy_totals
            if card == CARD_BUDGET:
                manual_fallback_amount = budget_basis
            else:
                planned_total = (await feo_plan_subsidy_totals(db, [subsidy_id])).get(subsidy_id, 0.0)
                manual_fallback_amount = budget_basis - planned_total

    if card == CARD_BUDGET:
        field_prefix = "feo_"
    elif card == CARD_PLANNED:
        field_prefix = "plan_"
    else:  # free
        field_prefix = None  # считается как feo_X - plan_X, см. ниже

    def _field_value(cid: int, k: str) -> float:
        node = nodes[cid]
        if card == CARD_FREE:
            return (node.get(f"feo_{k}", 0.0) or 0.0) - (node.get(f"plan_{k}", 0.0) or 0.0)
        return node.get(f"{field_prefix}{k}", 0.0) or 0.0

    def _own(cid: int, k: str) -> float:
        total = _field_value(cid, k)
        for kid in children_map.get(cid, []):
            total -= _field_value(kid, k)
        return total

    if manual_fallback_amount is not None:
        # Целиком «без типа» — только если корзина "unspecified" входит в
        # запрошенный фильтр (all или unspecified); иначе пустая выборка.
        rows = [{
            "feo_category_id": None,
            "category_path": "",
            "kind": "unspecified",
            "kind_label": _KIND_LABELS.get("unspecified"),
            "amount": manual_fallback_amount,
        }] if "unspecified" in kinds and abs(manual_fallback_amount) > _EPS else []
        total = manual_fallback_amount if "unspecified" in kinds else 0.0
        reason = None if rows else (
            "ручной бюджет субсидии без статей ФЭО — вся сумма «без типа»"
            if "unspecified" not in kinds else None
        )
        return {"card": card, "kind": kind, "total": total, "rows": rows, "reason": reason}

    total = sum(
        sum((nodes[r].get(f"feo_{k}", 0.0) if card == CARD_BUDGET
             else nodes[r].get(f"plan_{k}", 0.0) if card == CARD_PLANNED
             else (nodes[r].get(f"feo_{k}", 0.0) - nodes[r].get(f"plan_{k}", 0.0))) or 0.0
            for k in kinds)
        for r in roots
    )

    if card in (CARD_BUDGET, CARD_FREE):
        rows: list = []
        for cid in nodes:
            for k in kinds:
                own_amt = _own(cid, k)
                if abs(own_amt) < _EPS:
                    continue
                rows.append({
                    "feo_category_id": cid,
                    "category_path": _category_path(cid, cats),
                    "kind": k,
                    "kind_label": _KIND_LABELS.get(k, k),
                    "amount": own_amt,
                })
        reason = None
        if not rows:
            reason = (
                "нет статей с суммой ФЭО" if card == CARD_BUDGET
                else "ФЭО равно плану — свободных средств по типу нет"
            )
        return {"card": card, "kind": kind, "total": total, "rows": rows, "reason": reason}

    # card == "planned" — построчно по ПЛАНОВЫМ ПОЗИЦИЯМ.
    item_rows = (await db.execute(
        select(
            FeoPlannedItem.id, FeoPlannedItem.feo_category_id, FeoPlannedItem.name,
            FeoPlannedItem.item_type, FeoPlannedItem.quantity, FeoPlannedItem.amount,
        )
        .where(FeoPlannedItem.feo_category_id.in_(list(nodes.keys())))
        .where(FeoPlannedItem.is_active.is_(True))
    )).all()

    from app.services.feo_plan_tree import resolve_effective_item_types
    from app.services.feo_payroll import payroll_category_ids
    from app.services.item_type_split import kind_of_by_category_id

    eff_types = await resolve_effective_item_types(db, item_rows)
    payroll_ids = await payroll_category_ids(db, [subsidy_id])

    items_by_cat_kind: dict = {}
    for r in item_rows:
        k = kind_of_by_category_id(eff_types.get(r.id), r.feo_category_id, payroll_ids)
        items_by_cat_kind.setdefault((r.feo_category_id, k), []).append(r)

    rows: list = []
    for cid in nodes:
        for k in kinds:
            own_amt = _own(cid, k)
            cat_items = items_by_cat_kind.get((cid, k), [])
            # Нулевая own-доля статьи этого типа БЕЗ собственных позиций —
            # действительно нечего показывать, пропускаем. Но если позиции
            # ЕСТЬ (в т.ч. с нулевой суммой — "добавлено, но ещё не оценено",
            # 71 такая позиция у ДНР), они обязаны попасть в окно строками с
            # amount=0, а не пропасть молча (владелец: окно должно показывать
            # ВСЕ 368 плановых позиций ДНР, не только ненулевые).
            if abs(own_amt) < _EPS and not cat_items:
                continue
            if not cat_items:
                # own-доля статьи этого типа есть, но СВОИХ позиций этого типа
                # нет (замещение заказом/договором без собственной плановой
                # позиции, шаг 3 плана «Деньги субсидии») — одна строка на
                # статью, без planned_item_id, чтобы сумма не потерялась.
                rows.append({
                    "planned_item_id": None,
                    "name": None,
                    "feo_category_id": cid,
                    "category_path": _category_path(cid, cats),
                    "kind": k,
                    "kind_label": _KIND_LABELS.get(k, k),
                    "item_type": None,
                    "quantity": None,
                    "amount": own_amt,
                })
                continue
            weighted = [
                {
                    "planned_item_id": it.id,
                    "name": it.name,
                    "feo_category_id": cid,
                    "category_path": _category_path(cid, cats),
                    "kind": k,
                    "kind_label": _KIND_LABELS.get(k, k),
                    "item_type": it.item_type,
                    "quantity": float(it.quantity) if it.quantity is not None else None,
                    "weight": float(it.amount or 0.0),
                }
                for it in cat_items
            ]
            rows.extend(_split_rows_proportionally(own_amt, weighted))

    reason = None
    if not rows:
        reason = "плановых позиций нет"
    return {"card": card, "kind": kind, "total": total, "rows": rows, "reason": reason}
