"""plan_funding_sources.py — «Где взять деньги» при превышении плана (владелец,
план .planning/quick/2026-10-05-funding-sources/PLAN.md).

Запрос владельца: при превышении плана показывать, откуда можно безболезненно
взять деньги — сначала «хотелось бы, можно отказаться», потом «скорее всего
понадобится», у каждой строки кнопка «уменьшить на эту сумму».

ПРАВИЛО №6 — НЕ вторая формула:
  - незаконтрактованный остаток позиции = planned_item_contributions(...)[item]
    ['amount'] − committed_by_planned_item(...)[item]['amount'], БЕЗ клэмпа —
    ТА ЖЕ формула, что not_committed_raw в GET /api/feo-categories/plan-positions
    (app/routers/feo_plan_reads_tree.py) и в
    committed_amounts.leaf_items_not_committed_by_need_level;
  - превышения узла дерева (excess_amount) — ТОЛЬКО из
    app.services.feo_plan_tree.compute_feo_plan_tree, не пересчитываются здесь;
  - правка суммы позиции — ТОЛЬКО через app.services.feo_item_write.update_planned_item
    (пишет историю ФЭО, см. reduce_planned_item_amount ниже);
  - гейт утверждённой субсидии — app.services.subsidy_revision_guard.assert_direct_edit.

nearest_limited_ancestor — по образцу цепочки предков из
app.services.feo_plan_excess.assert_no_unapproved_excess (тот же проход
«узел → parent_id», но здесь ищет ПЕРВЫЙ узел СНИЗУ ВВЕРХ, включая сам
нарушенный узел, у которого задана сумма ФЭО (node['budget'] is not None —
уже нормализовано compute_feo_plan_tree, 0 трактуется как «не задано»).
Нет такого узла до корня — область поиска источников — вся субсидия.
"""
import json
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy
from app.services import feo_history
from app.services.committed_amounts import committed_by_planned_item, planned_item_contributions
from app.services.feo_item_write import update_planned_item as _write_update_planned_item
from app.services.feo_plan import build_category_path, compute_feo_plan_tree
from app.services.plan_need_level import NEED_LEVEL_LABELS, NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE
from app.schemas.feo import FeoPlannedItemCreate
from app.services.subsidy_revision_guard import assert_direct_edit


def nearest_limited_ancestor(tree: dict, start_category_id: Optional[int]) -> Optional[int]:
    """Первый узел (сам `start_category_id` ИЛИ его предок), у которого задана
    сумма ФЭО (node['budget'] is not None) — см. docstring модуля. None, если
    такого узла нет до корня (область — вся субсидия)."""
    cur = start_category_id
    seen: set = set()
    while cur is not None and cur in tree and cur not in seen:
        seen.add(cur)
        if tree[cur].get("budget") is not None:
            return cur
        cur = tree[cur].get("parent_id")
    return None


def _root_ancestor(tree: dict, category_id: Optional[int]) -> Optional[int]:
    """Корневой (parent_id is None) предок узла — для определения «того же
    направления» (same_branch) при сортировке кандидатов ниже."""
    cur = category_id
    seen: set = set()
    while cur is not None and cur in tree and cur not in seen:
        seen.add(cur)
        parent = tree[cur].get("parent_id")
        if parent is None:
            return cur
        cur = parent
    return cur


def _subtree_ids(tree: dict, root_id: int) -> set:
    """Все id узла root_id и его потомков (по parent_id в tree)."""
    children: dict = {}
    for cid, node in tree.items():
        p = node.get("parent_id")
        if p is not None:
            children.setdefault(p, []).append(cid)
    out = {root_id}
    stack = [root_id]
    while stack:
        cur = stack.pop()
        for ch in children.get(cur, []):
            if ch not in out:
                out.add(ch)
                stack.append(ch)
    return out


def build_funding_hint_header(planned_item_id: Optional[int], category_id: Optional[int], amount) -> dict:
    """ЕДИНАЯ точка формирования заголовка `X-Funding-Hint` (владелец, доп.
    контракт 05.10.2026) — отдаётся на жёстких 409 «ТЗ/договор над плановой
    позицией» (app.services.feo_plan_tz_checks.assert_tz_not_over_plan,
    app.services.tz_excess_approval.assert_no_pending_tz_excess,
    app.services.contract_excess_approval.assert_no_pending_contract_excess),
    чтобы фронт сразу открыл диалог «Где взять деньги» на нужную цель — БЕЗ
    похода на GET /api/purchases/{id}/funding-hint (в момент ПЕРВОГО сохранения
    закупки она может ещё не существовать как строка БД). detail самого 409 НЕ
    меняется (фронт показывает его как есть) — заголовок несёт ТОЛЬКО
    структурированную подсказку. ASCII-safe (ensure_ascii=True) — HTTP-заголовки
    не гарантируют UTF-8 транспорт."""
    payload = {
        "planned_item_id": planned_item_id,
        "category_id": category_id,
        "amount": float(amount) if amount is not None else None,
    }
    return {"X-Funding-Hint": json.dumps(payload, ensure_ascii=True)}


async def _planned_item_excess(db: AsyncSession, item: FeoPlannedItem) -> float:
    """Превышение ТЗ/договора над КОНКРЕТНОЙ плановой позицией — committed
    (законтрактовано) минус contribution (вклад позиции в план), если
    положительно; иначе 0.0. ОДНА формула (см. докстринг модуля) с
    not_committed_raw, здесь просто взятая со знаком «перебор», а не «остаток»."""
    contrib_map = await planned_item_contributions(db, [item.feo_category_id])
    committed_map = await committed_by_planned_item(db, [item.id])
    contribution = (contrib_map.get(item.id) or {"amount": float(item.amount or 0)})["amount"]
    committed = (committed_map.get(item.id) or {"amount": 0.0})["amount"]
    diff = committed - contribution
    return diff if diff > 0.005 else 0.0


async def _resolve_target(
    db: AsyncSession,
    tree: dict,
    cat_by_id: dict,
    *,
    subsidy_id: int,
    category_id: Optional[int],
    planned_item_id: Optional[int],
) -> dict:
    """Общая точка для GET /funding-sources и POST /reduce (пересчёт
    target_remaining_excess) — один и тот же способ описать «цель»
    превышения. category_id=None И planned_item_id=None — цель САМА субсидия
    целиком (владелец, доп. контракт 05.10.2026): превышение = план субсидии
    над её бюджетом, ТО ЖЕ число, что карточка «Можно перераспределить» в
    минусе — app.services.subsidy_money_summary.subsidy_money_summary
    (redistributable), НЕ пересчитывается заново (ПРАВИЛО №6)."""
    if category_id is not None:
        node = tree.get(category_id)
        if node is None:
            raise HTTPException(404, "Категория ФЭО не найдена в дереве плана этой субсидии")
        cat = cat_by_id.get(category_id)
        return {
            "kind": "category",
            "id": category_id,
            "name": cat.name if cat else f"#{category_id}",
            "path": build_category_path(cat, cat_by_id) if cat else "",
            "excess_amount": float(node.get("excess_amount") or 0.0),
            "search_start_category_id": category_id,
            "exclude_item_id": None,
        }

    if planned_item_id is not None:
        item = await db.get(FeoPlannedItem, planned_item_id)
        if item is None:
            raise HTTPException(404, "Плановая позиция не найдена")
        cat = cat_by_id.get(item.feo_category_id)
        excess = await _planned_item_excess(db, item)
        return {
            "kind": "planned_item",
            "id": planned_item_id,
            "name": item.name,
            "path": build_category_path(cat, cat_by_id) if cat else "",
            "excess_amount": excess,
            "search_start_category_id": item.feo_category_id,
            "exclude_item_id": planned_item_id,
        }

    from app.services.subsidy_money_summary import subsidy_money_summary

    summary = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id) or {}
    redistributable = float(summary.get("redistributable") or 0.0)
    subsidy = await db.get(Subsidy, subsidy_id)
    return {
        "kind": "subsidy",
        "id": subsidy_id,
        "name": subsidy.name if subsidy else f"#{subsidy_id}",
        "path": "",
        "excess_amount": -redistributable if redistributable < 0 else 0.0,
        "search_start_category_id": None,
        "exclude_item_id": None,
    }


async def find_funding_sources(
    db: AsyncSession,
    subsidy_id: int,
    *,
    category_id: Optional[int] = None,
    planned_item_id: Optional[int] = None,
    amount: Optional[float] = None,
) -> dict:
    """Собирает «откуда взять деньги» — см. докстринг модуля и контракт API
    (PLAN.md). НЕ БОЛЕЕ одного из category_id/planned_item_id (оба —
    ошибка); ОБА отсутствуют — цель вся субсидия целиком (доп. контракт
    владельца 05.10.2026, см. _resolve_target)."""
    if category_id is not None and planned_item_id is not None:
        raise HTTPException(422, "Укажите не более одного из параметров: category_id или planned_item_id")

    all_cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    cat_by_id = {c.id: c for c in all_cats}
    if not all_cats:
        raise HTTPException(404, "У субсидии нет дерева ФЭО")

    tree = await compute_feo_plan_tree(db, [subsidy_id])
    target = await _resolve_target(
        db, tree, cat_by_id, subsidy_id=subsidy_id, category_id=category_id, planned_item_id=planned_item_id,
    )

    need_amount = float(amount) if amount is not None else float(target["excess_amount"] or 0.0)

    limited_ancestor = nearest_limited_ancestor(tree, target["search_start_category_id"])
    if limited_ancestor is not None:
        scope_ids = _subtree_ids(tree, limited_ancestor)
        scope_cat = cat_by_id.get(limited_ancestor)
        scope = {
            "kind": "branch",
            "category_id": limited_ancestor,
            "name": scope_cat.name if scope_cat else f"#{limited_ancestor}",
        }
    else:
        scope_ids = set(cat_by_id.keys())
        subsidy = await db.get(Subsidy, subsidy_id)
        scope = {
            "kind": "subsidy",
            "category_id": None,
            "name": subsidy.name if subsidy else f"#{subsidy_id}",
        }

    branch_root = _root_ancestor(tree, target["search_start_category_id"])

    # Кандидаты: активные плановые позиции области поиска с незаконтрактованным
    # остатком > 0 (та же формула, что not_committed_raw), кроме самой нарушенной
    # позиции (exclude_item_id).
    items_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id.in_(scope_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )).scalars().all()
    items_rows = [it for it in items_rows if it.id != target["exclude_item_id"]]

    contrib_map = await planned_item_contributions(db, list(scope_ids))
    committed_map = await committed_by_planned_item(db, [it.id for it in items_rows])

    candidates: list[dict] = []
    for it in items_rows:
        info = contrib_map.get(it.id)
        if info is None:
            continue
        committed_amt = (committed_map.get(it.id) or {"amount": 0.0})["amount"]
        residual = info["amount"] - committed_amt
        if residual <= 0.005:
            continue
        cat = cat_by_id.get(it.feo_category_id)
        candidates.append({
            "planned_item_id": it.id,
            "name": it.name,
            "category_id": it.feo_category_id,
            "category_path": build_category_path(cat, cat_by_id) if cat else "",
            "need_level": it.need_level,
            "residual": residual,
            "same_branch": _root_ancestor(tree, it.feo_category_id) == branch_root,
        })

    def _sort_key(c: dict):
        return (0 if c["same_branch"] else 1, -c["residual"])

    groups_order = (NEED_LEVEL_NICE_TO_HAVE, NEED_LEVEL_LIKELY)
    groups: list[dict] = []
    cumulative = 0.0
    covered = 0.0
    for level in groups_order:
        level_items = sorted((c for c in candidates if c["need_level"] == level), key=_sort_key)
        out_items = []
        for c in level_items:
            remaining_need = max(need_amount - cumulative, 0.0)
            suggested_take = min(c["residual"], remaining_need)
            cumulative += suggested_take
            covered += suggested_take
            out_items.append({
                **c,
                "suggested_take": suggested_take,
                "cumulative_after": cumulative,
            })
        groups.append({
            "need_level": level,
            "label": NEED_LEVEL_LABELS[level],
            "items": out_items,
        })

    return {
        "target": {
            "kind": target["kind"],
            "id": target["id"],
            "name": target["name"],
            "path": target["path"],
            "excess_amount": target["excess_amount"],
        },
        "scope": scope,
        "need_amount": need_amount,
        "covered_amount": covered,
        "groups": groups,
    }


def _build_data_from_item(item: FeoPlannedItem, new_amount: Decimal) -> FeoPlannedItemCreate:
    """Собирает FeoPlannedItemCreate, воспроизводящий ВСЕ текущие поля позиции
    (feo_item_write.update_planned_item безусловно перезаписывает их из data —
    см. её докстринг), меняя ТОЛЬКО amount. item_type/is_feo_breakdown/
    is_internal_plan/need_level сознательно НЕ передаются — update_planned_item
    трогает их, только если они есть в data.model_fields_set, так старые
    значения остаются нетронутыми без лишней синхронизации каталога."""
    new_unit_price = item.unit_price
    if item.unit_price is not None and item.quantity is not None and item.quantity > 0:
        # Позиция «полного плана» (unit_price задан) — сумма ОБЯЗАНА
        # оставаться quantity × unit_price (иначе контроль «ТЗ не выше плана»,
        # assert_tz_not_over_plan, начнёт сравниваться с устаревшей ценой за
        # единицу) — пересчитываем цену под новую сумму при неизменном
        # количестве.
        new_unit_price = (new_amount / item.quantity).quantize(Decimal("0.01"))
    return FeoPlannedItemCreate(
        feo_category_id=item.feo_category_id,
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        amount=new_amount,
        unit_price=new_unit_price,
        notes=item.notes,
        is_active=item.is_active,
        sort_order=item.sort_order,
        payment_mode=item.payment_mode or "one_time",
        planned_date=item.planned_date,
        monthly_start_date=item.monthly_start_date,
        monthly_end_date=item.monthly_end_date,
        months_count=item.months_count,
        monthly_amount=item.monthly_amount,
    )


async def reduce_planned_item_amount(
    db: AsyncSession,
    user,
    item: FeoPlannedItem,
    amount: Decimal,
    *,
    target_category_id: Optional[int] = None,
    target_planned_item_id: Optional[int] = None,
    target_subsidy: bool = False,
    comment: Optional[str] = None,
) -> dict:
    """Тело POST /feo-planned-items/{id}/reduce — см. контракт API (PLAN.md):
    уменьшает `item` на `amount`, не ниже уже законтрактованного; если указан
    target_planned_item_id — в ТОЙ ЖЕ транзакции переносит `amount` на целевую
    позицию (увеличивает её). Гейт `assert_direct_edit` — обязателен (та же
    матрица, что и у прямой правки плановой позиции). commit НЕ делает —
    ответственность роутера.

    target_subsidy=True (доп. контракт владельца 05.10.2026) — цель была
    субсидия целиком (GET /funding-sources без category_id/planned_item_id):
    target_category_id/target_planned_item_id ОБА отсутствуют (нечего
    увеличивать — «свободно» по субсидии растёт само собой от уменьшения
    ЛЮБОЙ позиции), но target_remaining_excess в ответе обязан пересчитаться
    (иначе фронт не узнает, закрыто ли превышение бюджета субсидии)."""
    if amount is None or amount <= 0:
        raise HTTPException(422, "Сумма уменьшения должна быть положительной")

    cat = await db.get(FeoCategory, item.feo_category_id)
    if cat is None:
        raise HTTPException(404, "Категория ФЭО позиции не найдена")
    await assert_direct_edit(db, user, cat.subsidy_id)

    current_amount = Decimal(str(item.amount or 0))
    committed_map = await committed_by_planned_item(db, [item.id])
    floor = Decimal(str((committed_map.get(item.id) or {"amount": 0.0})["amount"]))
    new_amount = current_amount - amount
    if new_amount < floor - Decimal("0.005"):
        max_reduce = current_amount - floor
        raise HTTPException(
            422,
            {
                "code": "PLANNED_ITEM_REDUCE_BELOW_COMMITTED",
                "message": (
                    f"По позиции «{item.name}» уже законтрактовано {floor:,.2f} ₽, "
                    f"можно уменьшить не больше чем на {max(max_reduce, Decimal('0')):,.2f} ₽."
                ),
                "committed": float(floor),
                "max_reduce": float(max(max_reduce, Decimal("0"))),
            },
        )
    if new_amount < 0:
        new_amount = Decimal("0")

    target_name = None
    if target_planned_item_id is not None:
        target_item = await db.get(FeoPlannedItem, target_planned_item_id)
        if target_item is None:
            raise HTTPException(404, "Целевая плановая позиция не найдена")
        target_name = target_item.name
    elif target_category_id is not None:
        target_cat = await db.get(FeoCategory, target_category_id)
        target_name = target_cat.name if target_cat else f"#{target_category_id}"

    data = _build_data_from_item(item, new_amount)
    await _write_update_planned_item(db, user, item, data, create_version=False)
    _reduce_note = (
        f"перераспределение: −{amount:,.2f} ₽" + (f" в пользу «{target_name}»" if target_name else "")
        + (f" ({comment})" if comment else "")
    )
    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_ITEM, item.id, user,
        {"redistribution": None}, {"redistribution": _reduce_note},
        source=feo_history.SOURCE_MANUAL, commit=False,
    )

    if target_planned_item_id is not None:
        target_item = await db.get(FeoPlannedItem, target_planned_item_id)
        target_new_amount = Decimal(str(target_item.amount or 0)) + amount
        target_data = _build_data_from_item(target_item, target_new_amount)
        await _write_update_planned_item(db, user, target_item, target_data, create_version=False)
        _target_note = f"+{amount:,.2f} ₽ за счёт «{item.name}»" + (f" ({comment})" if comment else "")
        await feo_history.record_updated(
            db, feo_history.ENTITY_FEO_ITEM, target_item.id, user,
            {"redistribution": None}, {"redistribution": _target_note},
            source=feo_history.SOURCE_MANUAL, commit=False,
        )

    # ОДНА авто-версия плана на всю операцию (а не по одной на source/target —
    # update_planned_item вызывается с create_version=False выше ИМЕННО ради
    # этого; см. app.routers.purchases._create_plan_graph_version).
    from app.routers.purchases import _create_plan_graph_version
    await _create_plan_graph_version(
        subsidy_id=cat.subsidy_id, db=db, user=user, note="Авто-версия: перераспределение плановых позиций",
    )
    await db.flush()

    # Пересчитанное превышение цели (category_id ИЛИ planned_item_id ИЛИ вся
    # субсидия целиком при target_subsidy=True — тот же разбор, что и у GET
    # /funding-sources, ПРАВИЛО №6: один _resolve_target). Ни target_* не
    # передан И target_subsidy=False (вызов reduce вне диалога «Где взять
    # деньги», без привязки к конкретному превышению) — target_remaining_excess
    # =None, пересчитывать нечего.
    target_remaining_excess = None
    if target_category_id is not None or target_planned_item_id is not None or target_subsidy:
        all_cats = (await db.execute(
            select(FeoCategory).where(FeoCategory.subsidy_id == cat.subsidy_id)
        )).scalars().all()
        cat_by_id = {c.id: c for c in all_cats}
        tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
        target_after = await _resolve_target(
            db, tree, cat_by_id, subsidy_id=cat.subsidy_id,
            category_id=target_category_id, planned_item_id=target_planned_item_id,
        )
        target_remaining_excess = target_after["excess_amount"]

    return {
        "ok": True,
        "reduced_by": float(amount),
        "item": {
            "id": item.id,
            "amount": float(new_amount),
            "residual": float(new_amount - floor),
        },
        "target_remaining_excess": target_remaining_excess,
        "warnings": [],
    }


async def purchase_funding_hint(db: AsyncSession, purchase_id: int) -> Optional[dict]:
    """Для отказа 409 «ТЗ/договор над плановой позицией» (app.services.
    tz_excess_approval.assert_no_pending_tz_excess / app.services.
    contract_excess_approval.assert_no_pending_contract_excess) — по закупке
    находит позицию/сумму превышения, чтобы фронт мог сразу открыть диалог
    «Где взять деньги» на нужную цель, БЕЗ повторной записи в БД («сухая»
    проверка — переиспользует уже существующие НЕ бросающие сборщики нарушений,
    ПРАВИЛО №6: формула сравнения ТЗ/договора с планом не пишется второй раз).

    Возвращает {planned_item_id, category_id, amount} первого найденного
    нарушения (сначала ТЗ-над-позицией, затем договор-над-ТЗ) или None, если
    нарушений нет."""
    from app.models.purchase import Purchase
    from app.services.contract_excess_approval import _contract_vs_purchase_violation
    from app.services.tz_excess_approval import collect_tz_over_plan_violations

    purchase = await db.get(Purchase, purchase_id)
    if purchase is None:
        raise HTTPException(404, "Закупка не найдена")

    items = list(purchase.items or [])
    tz_violations = await collect_tz_over_plan_violations(
        db, items, fallback_category_id=purchase.feo_category_id,
    )
    for v in tz_violations:
        if v.get("feo_planned_item_id"):
            # excess_amount — превышение ТЗ над планом (НЕ сама сумма ТЗ,
            # которую несёт "amount" — см. комментарий у этого поля в
            # app.services.tz_excess_approval.collect_tz_over_plan_violations).
            return {
                "planned_item_id": v["feo_planned_item_id"],
                "category_id": v.get("feo_category_id"),
                "amount": v.get("excess_amount", v["amount"]),
            }

    purchase_items_by_id = {pi.id: pi for pi in items}
    for ci in (purchase.contract_items or []):
        if not ci.source_item_id:
            continue
        pi = purchase_items_by_id.get(ci.source_item_id)
        if pi is None:
            continue
        v = _contract_vs_purchase_violation(ci, pi, purchase.feo_category_id)
        if v and pi.feo_planned_item_id:
            return {
                "planned_item_id": pi.feo_planned_item_id,
                "category_id": v.get("feo_category_id"),
                "amount": v["amount"],
            }

    return None
