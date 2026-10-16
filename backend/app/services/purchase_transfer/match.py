"""Ключ сопоставления закупки и классификация пар источник↔целевая.

Ключ (ПЕРЕНЕСЕНО из scripts/fadm_sheet_load/sheet_v2_enrich.py::build_purchase_key
и pair_old_to_target.py::key — ПРАВИЛО №6, один разбор ключа на весь проект,
оба скрипта переведены на импорт отсюда):
  - ИНН контрагента + «эффективная сумма» (app.services.purchase_amounts.
    load_purchase_amounts — единственный источник истины по сумме закупки);
  - у авансовых (purchase_method == 'advance') вместо ИНН — сотрудник, которому
    возмещаем (reimbursement_user_id, иначе assigned_user_id).

classify() — три состояния для превью /api/purchase-transfer/preview:
  'same'        — совпали И ключ (ИНН/сотрудник), И сумма;
  'amount_only' — совпала только сумма, ключ другой;
  'none'        — нет совпадения.
Одинаковые суммы у нескольких кандидатов — по порядку id (вызывающий код
обязан передавать source/target уже отсортированными по id, как и прежние
find_pairs/pair_old_to_target.py::key делали через `.order_by(Purchase.id)`).
Одна целевая закупка матчится ровно одной исходной.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.models.purchase import Purchase


@dataclass(frozen=True)
class PurchaseKey:
    purchase_id: int
    inn: str
    supplier_key: str
    amount: Decimal
    # Не используется ни classify(), ни build_purchase_key (всегда ""),
    # оставлено с дефолтом для обратной совместимости с
    # tests/test_fadm_enrich.py::_key, которая передаёт его как keyword
    # (унаследовано от старого PurchaseKey в sheet_v2_enrich.py, ПРАВИЛО №6 —
    # не плодить второй dataclass из-за одного поля теста).
    registry_number: str = ""


def build_purchase_key(
    p: Purchase, *, contractor_inn: Optional[str], effective_amount: Optional[Decimal],
) -> PurchaseKey:
    """inn — пустая строка у авансовых (чек выписан на организацию, не на
    сотрудника) — supplier_key различает их по сотруднику, чтобы два разных
    авансовых с пустым inn не считались одним и тем же поставщиком."""
    is_advance = getattr(p, "purchase_method", None) == "advance"
    if is_advance:
        inn = ""
        who = p.reimbursement_user_id or p.assigned_user_id
        supplier_key = f"employee:{who}" if who else ""
    else:
        inn = (contractor_inn or "").strip()
        supplier_key = ""
    amount = effective_amount if effective_amount is not None else Decimal("0")
    return PurchaseKey(purchase_id=p.id, inn=inn, supplier_key=supplier_key, amount=amount)


@dataclass
class ClassifyResult:
    state: str  # 'same' | 'amount_only' | 'none'
    match_purchase_id: Optional[int] = None


def classify(source: list[PurchaseKey], target: list[PurchaseKey]) -> dict[int, ClassifyResult]:
    """{source_purchase_id: ClassifyResult}. source/target — ключи, уже
    построенные build_purchase_key, по порядку id возрастания (одинаковые
    суммы/ключи у нескольких исходных — первой достаётся первому кандидату по
    этому порядку). Одна целевая закупка используется не более одного раза."""
    by_full_key: dict[tuple, list[PurchaseKey]] = defaultdict(list)
    by_amount: dict[Decimal, list[PurchaseKey]] = defaultdict(list)
    for t in sorted(target, key=lambda x: x.purchase_id):
        if not t.amount:  # без суммы сопоставлять не по чему — пара только вручную
            continue
        by_amount[t.amount].append(t)
        if t.inn or t.supplier_key:
            by_full_key[(t.inn, t.supplier_key, t.amount)].append(t)

    used_target_ids: set[int] = set()
    result: dict[int, ClassifyResult] = {}
    source_sorted = sorted(source, key=lambda x: x.purchase_id)

    # Проход 1 — точное совпадение (ключ + сумма) -> 'same'.
    for s in source_sorted:
        if not (s.inn or s.supplier_key) or not s.amount:
            continue
        cands = [t for t in by_full_key.get((s.inn, s.supplier_key, s.amount), [])
                 if t.purchase_id not in used_target_ids]
        if cands:
            match = cands[0]
            used_target_ids.add(match.purchase_id)
            result[s.purchase_id] = ClassifyResult(state="same", match_purchase_id=match.purchase_id)

    # Проход 2 — только сумма -> 'amount_only'; иначе 'none'.
    for s in source_sorted:
        if s.purchase_id in result:
            continue
        cands = [t for t in by_amount.get(s.amount, []) if t.purchase_id not in used_target_ids] if s.amount else []
        if cands:
            match = cands[0]
            used_target_ids.add(match.purchase_id)
            result[s.purchase_id] = ClassifyResult(state="amount_only", match_purchase_id=match.purchase_id)
        else:
            result[s.purchase_id] = ClassifyResult(state="none", match_purchase_id=None)

    return result
