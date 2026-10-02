"""Порог «не ниже законтрактованного» и баланс связок корректировки.

Обновление (02.10.2026, коммит 1624419d «Деньги субсидии» уже в main) —
НАСТОЯЩАЯ реализация, не заглушка. ПРАВИЛО №6 — единственные источники чисел:
  - законтрактовано по ПЛАНОВОЙ ПОЗИЦИИ: committed_amounts.committed_by_planned_item;
  - законтрактовано по СТАТЬЕ (узлу дерева, с поддеревом): node['committed']
    из compute_feo_plan_tree (читается из уже посчитанного tree_after, второй
    раз дерево здесь не считается);
  - «Свободно» СУБСИДИИ: subsidy_money_summary.subsidy_money_summary.
Второй формулы законтрактованного/свободного здесь нет — только чтение готовых
чисел и сравнение со значениями строк корректировки.

Сигнатуры функций зафиксированы (их вызывают preview.py/apply.py) — не менять.
"""
from typing import Optional

from app.services.subsidy_revision_ops import (
    ENTITY_CATEGORY, ENTITY_ITEM, ENTITY_SUBSIDY, OP_CREATE, OP_DELETE,
    _op_attr, _effective_after,
)

_EPS = 0.005


async def check_floor(db, subsidy_id: int, ops: list, tree_after: dict) -> list[dict]:
    """Нарушения порога «план/ФЭО не может уйти ниже уже законтрактованного».

    Проверяет ВХОДНЫЕ значения строк (а не то, что дерево само подстраховывает
    через plan_floor_added — тот «пол» маскирует цифру в дереве, но не
    запрещает пользователю ВВЕСТИ число ниже законтрактованного, что и
    обязана ловить эта функция):
      - плановая позиция: after.amount < законтрактованная сумма ИЛИ
        after.quantity < законтрактованное количество;
      - удаление плановой позиции, у которой законтрактовано > 0;
      - категория ФЭО: after.budget < node['committed'] (c поддеревом, из
        tree_after — ПОСЛЕ применения этой же пачки операций);
      - удаление категории, у которой committed (до удаления) > 0 — committed
        ДО удаления сохранён в SubsidyRevisionOp.before при add_op (см.
        subsidy_revision_ops.add_op, _committed/_committed_amount/
        _committed_quantity) — после удаления узла в tree_after его уже нет,
        второй раз запрашивать неоткуда;
      - субсидия: after.budget < законтрактовано по субсидии целиком
        (subsidy_money_summary, живой запрос — committed не меняется правками
        плана, можно читать в любой момент транзакции).

    Возвращает [{"op_id", "code": "below_committed", "field", "committed",
    "message"}].
    """
    from app.services.committed_amounts import committed_by_planned_item

    problems: list[dict] = []

    for op in ops:
        entity_type = _op_attr(op, "entity_type")
        op_type = _op_attr(op, "op_type")
        target_id = _op_attr(op, "target_id")
        before = _op_attr(op, "before") or {}
        op_id = op.id if hasattr(op, "id") else op.get("_key")

        if entity_type == ENTITY_ITEM:
            if op_type == OP_DELETE:
                committed_amt = float(before.get("_committed_amount") or 0.0)
                if committed_amt > _EPS:
                    problems.append({
                        "op_id": op_id, "code": "below_committed", "field": "amount",
                        "committed": committed_amt,
                        "message": f"Нельзя удалить: по этой позиции уже законтрактовано {committed_amt:,.2f} ₽",
                    })
                continue
            if op_type == OP_CREATE or target_id is None:
                continue
            after = _effective_after(op, {})
            committed_map = await committed_by_planned_item(db, [target_id])
            c = committed_map.get(target_id) or {"amount": 0.0, "quantity": 0.0}
            if "amount" in after and float(after.get("amount") or 0.0) < c["amount"] - _EPS:
                problems.append({
                    "op_id": op_id, "code": "below_committed", "field": "amount",
                    "committed": c["amount"],
                    "message": f"Ниже законтрактованного: по договорам уже {c['amount']:,.2f} ₽",
                })
            if "quantity" in after and float(after.get("quantity") or 0.0) < c["quantity"] - _EPS:
                problems.append({
                    "op_id": op_id, "code": "below_committed", "field": "quantity",
                    "committed": c["quantity"],
                    "message": f"Ниже законтрактованного количества: по договорам уже {c['quantity']:,.4g}",
                })

        elif entity_type == ENTITY_CATEGORY:
            if op_type == OP_DELETE:
                committed_amt = float(before.get("_committed") or 0.0)
                if committed_amt > _EPS:
                    problems.append({
                        "op_id": op_id, "code": "below_committed", "field": "budget",
                        "committed": committed_amt,
                        "message": f"Нельзя удалить: по статье уже законтрактовано {committed_amt:,.2f} ₽",
                    })
                continue
            if op_type == OP_CREATE or target_id is None:
                continue
            after = _effective_after(op, {})
            if "budget" not in after:
                continue
            node = tree_after.get(target_id) or {}
            committed_amt = float(node.get("committed") or 0.0)
            if float(after.get("budget") or 0.0) < committed_amt - _EPS:
                problems.append({
                    "op_id": op_id, "code": "below_committed", "field": "budget",
                    "committed": committed_amt,
                    "message": f"Ниже законтрактованного: по договорам уже {committed_amt:,.2f} ₽",
                })

        elif entity_type == ENTITY_SUBSIDY:
            after = _effective_after(op, {})
            if "budget" not in after:
                continue
            from app.services.subsidy_money_summary import subsidy_money_summary
            summary = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id) or {}
            committed_amt = float(summary.get("committed") or 0.0)
            if float(after.get("budget") or 0.0) < committed_amt - _EPS:
                problems.append({
                    "op_id": op_id, "code": "below_committed", "field": "budget",
                    "committed": committed_amt,
                    "message": f"Ниже законтрактованного по субсидии: по договорам уже {committed_amt:,.2f} ₽",
                })

    return problems


async def compute_balance(
    db, subsidy_id: int, ops: list, tree_before: dict, tree_after: dict,
    *, money_summary_after: "dict | None" = None, free_before_override: "float | None" = None,
) -> dict:
    """Баланс связок (bundle_no) + «Свободно» субсидии до/после корректировки.

    free_after = effective_budget − Σ display корневых узлов tree_after (budget
    живой — subsidy_money_summary). free_before — ТА ЖЕ формула от tree_before,
    ЕСЛИ tree_before передан (полный «живой» расчёт); preview может экономить
    двойной пересчёт дерева (compute_feo_plan_tree считается дважды — свой и
    внутри subsidy_money_summary) и передать tree_before={} + уже готовое
    `free_before_override` (число из ОДНОГО живого subsidy_money_summary,
    снятого ДО применения ops) — тогда root-sum по tree_before не считается
    вовсе. `money_summary_after` — переиспользование уже посчитанного вызывающим
    кодом subsidy_money_summary ПОСЛЕ apply (preview.py/apply.py и так его
    считают для totals "после" — второй одинаковый запрос здесь не нужен).

    budget, в свою очередь, учитывает правку субсидии ЭТОЙ ЖЕ корректировки:
    before берётся из SubsidyRevisionOp.before (живое значение на момент
    добавления строки), after — из подтверждённого efective_after.

    can_apply = free_after >= 0 ИЛИ (free_before < 0 И free_after >= free_before)
    — правки не обязаны устранить ВЕСЬ дефицит субсидии (он мог быть ДО
    корректировки), но не имеют права его УВЕЛИЧИТЬ.
    shortfall = max(0, -free_after), если can_apply ложно.

    bundles: [{"bundle_no", "added", "removed", "balance", "shortfall"}] —
    added/removed/balance как раньше (Σ изменений сумм строк связки), shortfall
    связки — простое последовательное распределение общего "запаса" free_before
    по bundle_no (связка, идущая раньше, забирает запас первой).
    """
    from app.services.subsidy_money_summary import subsidy_money_summary

    if money_summary_after is not None:
        summary_now = money_summary_after
    else:
        summary_now = (await subsidy_money_summary(db, [subsidy_id])).get(subsidy_id) or {}
    budget_after = float(summary_now.get("budget") or 0.0)

    budget_before = budget_after
    for op in ops:
        if _op_attr(op, "entity_type") != ENTITY_SUBSIDY:
            continue
        before = _op_attr(op, "before") or {}
        if "budget" not in before:
            continue
        after = _effective_after(op, {})
        before_budget = float(before.get("budget") or 0.0)
        after_budget = float(after.get("budget", before_budget) or 0.0)
        # Поправка идёт по дельте РУЧНОЙ составляющей субсидии — ФЭО-часть
        # effective-бюджета (если дерево заполнено) этой правкой не меняется.
        budget_before = budget_after - (after_budget - before_budget)
        break

    def _root_sum(tree: dict, field: str) -> float:
        return sum(float(n.get(field, 0.0) or 0.0) for n in tree.values() if n.get("parent_id") is None)

    planned_after = _root_sum(tree_after, "display")
    free_after = budget_after - planned_after
    if free_before_override is not None:
        free_before = free_before_override
    elif tree_before:
        planned_before = _root_sum(tree_before, "display")
        free_before = budget_before - planned_before
    else:
        # Ни готового числа, ни дерева "до" не передали (вызывающий код обязан
        # дать хотя бы одно) — деградируем на free_after, чтобы не падать;
        # can_apply в этом случае не сможет обнаружить ухудшение дефицита.
        free_before = free_after

    can_apply = (free_after >= -_EPS) or (free_before < -_EPS and free_after >= free_before - _EPS)
    shortfall = max(0.0, -free_after) if not can_apply else 0.0

    _AMOUNT_FIELD = {ENTITY_CATEGORY: ("budget", "planned_amount", "manual_plan_amount"), ENTITY_ITEM: ("amount",)}

    def _op_amount_delta(op) -> float:
        entity_type = _op_attr(op, "entity_type")
        after = _effective_after(op, {})
        before = _op_attr(op, "before") or {}
        candidates = _AMOUNT_FIELD.get(entity_type, ())
        delta = 0.0
        for f in candidates:
            if f in after:
                old = float(before.get(f) or 0.0) if before else 0.0
                new = float(after.get(f) or 0.0)
                delta += (new - old)
        return delta

    bundles_map: dict[int, dict] = {}
    for op in ops:
        bundle_no = _op_attr(op, "bundle_no")
        if bundle_no is None:
            continue
        delta = _op_amount_delta(op)
        b = bundles_map.setdefault(bundle_no, {"bundle_no": bundle_no, "added": 0.0, "removed": 0.0})
        if delta > 0:
            b["added"] += delta
        elif delta < 0:
            b["removed"] += -delta

    bundles = [dict(b, balance=b["removed"] - b["added"]) for b in bundles_map.values()]
    bundles.sort(key=lambda x: x["bundle_no"])

    remaining_free = max(free_before, 0.0)
    for b in bundles:
        net_need = b["added"] - b["removed"]
        if net_need > _EPS:
            b["shortfall"] = max(0.0, net_need - remaining_free)
            remaining_free = max(0.0, remaining_free - net_need)
        else:
            b["shortfall"] = 0.0
            remaining_free += -net_need

    return {
        "bundles": bundles,
        "free_before": free_before,
        "free_after": free_after,
        "shortfall": shortfall,
        "can_apply": can_apply,
    }
