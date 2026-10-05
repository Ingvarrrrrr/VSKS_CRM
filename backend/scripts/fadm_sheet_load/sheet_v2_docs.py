"""--copy-docs: документы (файлы договора/акты/служебки — purchase_files;
чеки — purchase_receipts) двойника в СТАРОЙ ФАДМ_2026 → соответствующая
закупка новой «ФАДМ 2026_2» (владелец, доп. задание 05.10.2026, после того
как v2 уже записана на прод). Работает ПОСТФАКТУМ, на уже существующей
новой субсидии — ничего не создаёт/не удаляет из закупок, только документы.

Прод-находка 05.10.2026: подавляющее большинство закупок с документами —
АВАНСОВЫЕ, а у авансовых контрагент старой закупки — КОНКРЕТНЫЙ МАГАЗИН
(ОЗОН/Яндекс.Маркет/...), у новой — СОТРУДНИК (ПРАВИЛО №6 advance.py:
contractor_id авансовой закупки — не сам сотрудник, а штатный «магазин twin»
из _apply_source_executor/_load_source_advance_contractors ИЛИ пусто) —
contractor_id у пары почти никогда не совпадает. Поэтому ТРИ прохода,
очередь важна (каждый следующий работает только с тем, что осталось
несопоставленным после предыдущего — «одна старая закупка → максимум одна
новая» выполняется ГЛОБАЛЬНО по всем трём проходам, как Matcher._used в
match.py):

  1) contractor_id + сумма (_canonical_amount, допуск 0,01 ₽) — основной путь,
     работает для обычных (не авансовых) закупок, где contractor twin общий.
  2) авансовые — сотрудник-возмещатель: новая reimbursement_user_id ==
     старая assigned_user_id ИЛИ reimbursement_user_id, + та же сумма
     (допуск 0,01 ₽) — ОБЕ закупки должны быть ещё свободны после прохода 1.
  3) «только сумма» — ПРАВИЛО match.py::Matcher.match_amount_only буквально:
     сумма ≥1000 ₽, точное (Decimal ==, не с допуском — та же логика, что в
     match_amount_only) совпадение, которое среди ВСЕХ ЕЩЁ СВОБОДНЫХ старых
     закупок и ВСЕХ ЕЩЁ НЕСОПОСТАВЛЕННЫХ новых встречается РОВНО один раз с
     каждой стороны. Для сумм <1000 этот проход НЕ применяется (владелец:
     «для сумм < 1000 — только если совпадает сотрудник/ИНН» — это ровно
     проход 2 и проход 1, оба уже отработали раньше прохода 3).

Тай-брейк внутри прохода 1 — STATUS_RANK старой закупки (выше статус
побеждает), затем меньший id, как в match.py::match_contractor.

Сама копия — штатный files_copy.py::copy_purchase_documents (единственный
писатель PurchaseFile/PurchaseReceipt-копий, идемпотентный сам по себе)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

from .files_copy import DocCopyCounters, copy_purchase_documents
from .match import MIN_AMOUNT_ONLY, STATUS_RANK, _canonical_amount, find_source_subsidy

AMOUNT_TOLERANCE = Decimal("0.01")


@dataclass
class _PurchaseAmount:
    id: int
    contractor_id: Optional[int]
    amount: Decimal
    status: str
    purchase_method: Optional[str]
    assigned_user_id: Optional[int]
    reimbursement_user_id: Optional[int]


async def _load_purchase_amounts(db: AsyncSession, subsidy_id: int) -> list[_PurchaseAmount]:
    purchases = (await db.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy_id)
    )).scalars().all()
    if not purchases:
        return []
    items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_([p.id for p in purchases]))
    )).scalars().all()
    items_by_purchase: dict[int, list[Decimal]] = {}
    for it in items:
        if it.total_price is not None:
            items_by_purchase.setdefault(it.purchase_id, []).append(Decimal(str(it.total_price)))

    out: list[_PurchaseAmount] = []
    for p in purchases:
        out.append(_PurchaseAmount(
            id=p.id, contractor_id=p.contractor_id,
            amount=_canonical_amount(p, items_by_purchase.get(p.id, [])),
            status=p.status, purchase_method=p.purchase_method,
            assigned_user_id=p.assigned_user_id, reimbursement_user_id=p.reimbursement_user_id,
        ))
    return out


@dataclass
class DocPair:
    new_purchase_id: int
    old_purchase_id: int
    contractor_id: Optional[int]
    amount_new: Decimal
    amount_old: Decimal
    method: str
    tie_break: bool = False


def _match_contractor_amount(new_purchases: list[_PurchaseAmount], old_purchases: list[_PurchaseAmount],
                              used_old: set[int], matched_new: set[int]) -> list[DocPair]:
    """Проход 1 — см. docstring модуля."""
    by_contractor: dict[int, list[_PurchaseAmount]] = {}
    for op in old_purchases:
        if op.contractor_id and op.amount > 0:
            by_contractor.setdefault(op.contractor_id, []).append(op)

    pairs: list[DocPair] = []
    for np in sorted(new_purchases, key=lambda p: p.id):
        if not np.contractor_id:
            continue
        candidates = [
            op for op in by_contractor.get(np.contractor_id, [])
            if op.id not in used_old and abs(op.amount - np.amount) <= AMOUNT_TOLERANCE
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda op: (abs(op.amount - np.amount), -STATUS_RANK.get(op.status or "", 0), op.id))
        best = candidates[0]
        tied = [c for c in candidates if abs(c.amount - np.amount) == abs(best.amount - np.amount)]
        used_old.add(best.id)
        matched_new.add(np.id)
        pairs.append(DocPair(
            new_purchase_id=np.id, old_purchase_id=best.id, contractor_id=np.contractor_id,
            amount_new=np.amount, amount_old=best.amount, method="contractor+сумма", tie_break=len(tied) > 1,
        ))
    return pairs


def _match_advance_employee(new_purchases: list[_PurchaseAmount], old_purchases: list[_PurchaseAmount],
                             used_old: set[int], matched_new: set[int]) -> list[DocPair]:
    """Проход 2 — авансовые: сотрудник-возмещатель новой == assigned_user_id
    ИЛИ reimbursement_user_id старой (владелец, уточнение 05.10.2026 —
    двойник часто был заведён ДО разделения полей, исполнитель мог осесть в
    любом из двух), + та же сумма (допуск 0,01 ₽). Обе стороны — ещё
    свободные после прохода 1."""
    by_employee: dict[int, list[_PurchaseAmount]] = {}
    for op in old_purchases:
        if op.id in used_old or op.amount <= 0:
            continue
        for uid in (op.assigned_user_id, op.reimbursement_user_id):
            if uid:
                by_employee.setdefault(uid, []).append(op)

    pairs: list[DocPair] = []
    for np in sorted(new_purchases, key=lambda p: p.id):
        if np.id in matched_new or np.purchase_method != "advance" or not np.reimbursement_user_id:
            continue
        candidates = [
            op for op in by_employee.get(np.reimbursement_user_id, [])
            if op.id not in used_old and abs(op.amount - np.amount) <= AMOUNT_TOLERANCE
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda op: (abs(op.amount - np.amount), -STATUS_RANK.get(op.status or "", 0), op.id))
        best = candidates[0]
        used_old.add(best.id)
        matched_new.add(np.id)
        pairs.append(DocPair(
            new_purchase_id=np.id, old_purchase_id=best.id, contractor_id=np.contractor_id,
            amount_new=np.amount, amount_old=best.amount, method="сотрудник+сумма",
        ))
    return pairs


def _match_amount_only(new_purchases: list[_PurchaseAmount], old_purchases: list[_PurchaseAmount],
                        used_old: set[int], matched_new: set[int]) -> list[DocPair]:
    """Проход 3 — буквально match.py::Matcher.match_amount_only: точное
    (Decimal ==) совпадение суммы ≥1000 ₽, ровно один раз с каждой стороны
    среди ещё свободных/несопоставленных."""
    from collections import Counter

    avail_old = [op for op in old_purchases if op.id not in used_old and op.amount >= MIN_AMOUNT_ONLY]
    old_count: Counter = Counter(op.amount for op in avail_old)
    old_by_amount: dict[Decimal, _PurchaseAmount] = {op.amount: op for op in avail_old}

    avail_new = [np for np in new_purchases if np.id not in matched_new and np.amount >= MIN_AMOUNT_ONLY]
    new_count: Counter = Counter(np.amount for np in avail_new)

    pairs: list[DocPair] = []
    for np in sorted(avail_new, key=lambda p: p.id):
        if old_count.get(np.amount) == 1 and new_count.get(np.amount) == 1:
            op = old_by_amount[np.amount]
            used_old.add(op.id)
            matched_new.add(np.id)
            pairs.append(DocPair(
                new_purchase_id=np.id, old_purchase_id=op.id, contractor_id=np.contractor_id,
                amount_new=np.amount, amount_old=op.amount, method="только сумма",
            ))
    return pairs


def find_doc_pairs(new_purchases: list[_PurchaseAmount], old_purchases: list[_PurchaseAmount]) -> list[DocPair]:
    used_old: set[int] = set()
    matched_new: set[int] = set()
    pairs: list[DocPair] = []
    pairs += _match_contractor_amount(new_purchases, old_purchases, used_old, matched_new)
    pairs += _match_advance_employee(new_purchases, old_purchases, used_old, matched_new)
    pairs += _match_amount_only(new_purchases, old_purchases, used_old, matched_new)
    return pairs


async def run_copy_docs(db: AsyncSession, *, target_name: str, source_name: str) -> tuple[list[DocPair], DocCopyCounters]:
    """Копирование происходит ВСЕГДА (--dry-run не пропускает его) — как и у
    run_build_v2/run_build, вся работа идёт в транзакции, а __main__.py сам
    делает rollback в конце при --dry-run; иначе --dry-run не смог бы честно
    посчитать «сколько скопировалось бы» (идемпотентность по content_hash
    требует реальной вставки, чтобы увидеть дубли)."""
    from .sheet_v2_build import find_existing_target_subsidy

    source = await find_source_subsidy(db, source_name)
    target = await find_existing_target_subsidy(db, target_name, source.id)
    if not target:
        raise ValueError(f"Целевая субсидия {target_name!r} (copied_from_id={source.id}) не найдена — сначала --goodsservice.")

    old_purchases = await _load_purchase_amounts(db, source.id)
    new_purchases = await _load_purchase_amounts(db, target.id)
    pairs = find_doc_pairs(new_purchases, old_purchases)

    counters = DocCopyCounters()
    for pair in pairs:
        await copy_purchase_documents(db, pair.old_purchase_id, pair.new_purchase_id, counters)
    await db.flush()
    return pairs, counters
