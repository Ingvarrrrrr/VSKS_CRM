"""Phase 27.4-20 — кандидаты для матчинга платежа с закупками.

Алгоритм (по бизнес-логике пользователя):
1. Кандидаты — Purchase'и того же контракта (либо ВСЕ закупки contractor если контракт не определён)
2. Exact amount match: purchase.contract_price == bp.amount → score 100, single suggestion
3. Subset-sum: комбинация из N (≤6) закупок где SUM(contract_price) == bp.amount → score 90
4. Partial delivery: SUM(acceptance_docs[].amount) ≈ bp.amount для ОДНОЙ закупки → score 85
5. Split payment (N→1): sum_existing_payments + bp.amount == purchase.contract_price → score 80
6. Text similarity: токены из bp.purpose_text vs purchase.subject (Jaccard) → бонус +10

Возвращает топ-N кандидатов отсортированных по score (desc). UI показывает с preselected
вариантом для нажатия «Подтвердить» одним кликом.
"""
from __future__ import annotations
from decimal import Decimal
from itertools import combinations
from typing import Optional
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.purchase import Purchase
from app.models.payment import Payment

# Tolerance for sum match — копейки от округления
AMOUNT_TOL = Decimal("0.02")
# Subset-sum limit
MAX_COMBINATION_SIZE = 6
# Top candidates returned
TOP_N = 5

_PUNCT = re.compile(r'[\"\'«»()\[\],.;:!?@#%&*=+/\\—–\-_…№#]')
_WS = re.compile(r'\s+')
_STOP = {
    'и','в','с','на','для','из','по','к','от','до','за','над','под','или','либо',
    'но','а','же','ли','бы','оплата','платеж','платёж','счет','счёт','счету',
    'договор','договору','контракт','контракту','оказание','услуг','услуги',
    'поставка','поставки','товар','товара','товары','работ','работа','работы',
}


def _tokens(s: str) -> set:
    if not s:
        return set()
    s = s.lower().replace('ё', 'е')
    s = _PUNCT.sub(' ', s)
    s = _WS.sub(' ', s).strip()
    return {t for t in s.split(' ') if t and len(t) > 2 and t not in _STOP and not t.isdigit()}


def _text_similarity(a: str, b: str) -> float:
    """Jaccard similarity по токенам (после нормализации + stopwords)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union) if union else 0.0


def _amounts_match(a: Decimal, b: Decimal, tol: Decimal = AMOUNT_TOL) -> bool:
    return abs(a - b) <= tol


def _purchase_amount(p: Purchase) -> Optional[Decimal]:
    for fld in (p.contract_price, p.planned_total_price, p.total_nmck):
        if fld is not None:
            return Decimal(str(fld))
    return None


def _purchase_delivered_amount(p: Purchase) -> Decimal:
    """SUM acceptance_docs[].amount (Phase 26-H JSONB) ИЛИ legacy."""
    docs = p.acceptance_docs or []
    total = Decimal(0)
    if isinstance(docs, list):
        for d in docs:
            if isinstance(d, dict) and d.get('amount') is not None:
                try:
                    total += Decimal(str(d['amount']))
                except Exception:
                    pass
    if total == 0 and p.delivery_payment_amount is not None:
        total = Decimal(str(p.delivery_payment_amount))
    return total


async def _existing_payments_sum(db: AsyncSession, purchase_id: int) -> Decimal:
    """Сумма уже подтверждённых платежей по закупке."""
    res = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.purchase_id == purchase_id, Payment.matched_confirmed == True)  # noqa
    )
    val = res.scalar()
    return Decimal(str(val or 0))


async def build_candidates(bp: BankPayment, db: AsyncSession) -> list[dict]:
    """Вернёт список кандидатов: [{purchase_ids:[...], score:int, kind:str, label:str, ...}].

    Отсортировано по score desc. Топ TOP_N.
    """
    if bp.amount is None:
        return []
    bp_amt = Decimal(str(bp.amount))

    # Сначала по контракту, fallback на contractor
    purchases: list[Purchase] = []
    if bp.matched_contract_id:
        res = await db.execute(
            select(Purchase).where(Purchase.contract_id == bp.matched_contract_id)
        )
        purchases = list(res.scalars().all())
    if not purchases and bp.matched_contractor_id:
        res = await db.execute(
            select(Purchase).where(Purchase.contractor_id == bp.matched_contractor_id)
        )
        purchases = list(res.scalars().all())
    if not purchases:
        return []

    candidates: list[dict] = []
    purpose = bp.purpose_text or ''

    # A. Exact single match
    for p in purchases:
        amt = _purchase_amount(p)
        if amt and _amounts_match(amt, bp_amt):
            sim = _text_similarity(purpose, p.subject or '')
            score = 100 + int(sim * 10)
            candidates.append({
                "purchase_ids": [p.id],
                "purchase_names": [p.subject or p.item_name or f"#{p.id}"],
                "purchase_amounts": [float(amt)],
                "score": score,
                "kind": "exact_amount",
                "label": f"Точное совпадение суммы ({amt:.2f} ₽)" + (f" + текст {int(sim*100)}%" if sim > 0.1 else ""),
            })

    # B. Subset-sum (N покупок дают сумму платежа)
    if not any(c["kind"] == "exact_amount" for c in candidates):
        purchases_with_amt = [(p, _purchase_amount(p)) for p in purchases]
        purchases_with_amt = [(p, a) for p, a in purchases_with_amt if a is not None]
        for size in range(2, min(MAX_COMBINATION_SIZE, len(purchases_with_amt)) + 1):
            for combo in combinations(purchases_with_amt, size):
                total = sum((a for _, a in combo), Decimal(0))
                if _amounts_match(total, bp_amt):
                    pids = [p.id for p, _ in combo]
                    names = [(p.subject or p.item_name or f"#{p.id}") for p, _ in combo]
                    amts = [float(a) for _, a in combo]
                    sim = max([_text_similarity(purpose, p.subject or '') for p, _ in combo] + [0])
                    candidates.append({
                        "purchase_ids": pids,
                        "purchase_names": names,
                        "purchase_amounts": amts,
                        "score": 90 + int(sim * 10) - (size - 2),
                        "kind": "subset_sum",
                        "label": f"Сумма {size} закупок ({total:.2f} ₽)" + (f" + текст {int(sim*100)}%" if sim > 0.1 else ""),
                    })
            if any(c["kind"] == "subset_sum" for c in candidates):
                break  # found combinations at this size — don't try bigger

    # C. Partial delivery match (SUM acceptance_docs ≈ bp.amount для ОДНОЙ закупки)
    for p in purchases:
        delivered = _purchase_delivered_amount(p)
        if delivered > 0 and _amounts_match(delivered, bp_amt):
            sim = _text_similarity(purpose, p.subject or '')
            candidates.append({
                "purchase_ids": [p.id],
                "purchase_names": [p.subject or p.item_name or f"#{p.id}"],
                "purchase_amounts": [float(delivered)],
                "score": 85 + int(sim * 10),
                "kind": "delivered_amount",
                "label": f"Совпадение с поставкой ({delivered:.2f} ₽)" + (f" + текст {int(sim*100)}%" if sim > 0.1 else ""),
            })

    # D. Split payment: bp.amount + existing_payments == purchase.contract_price
    for p in purchases:
        amt = _purchase_amount(p)
        if not amt:
            continue
        existing = await _existing_payments_sum(db, p.id)
        new_total = existing + bp_amt
        if existing > 0 and _amounts_match(new_total, amt):
            remaining = amt - existing
            sim = _text_similarity(purpose, p.subject or '')
            candidates.append({
                "purchase_ids": [p.id],
                "purchase_names": [p.subject or p.item_name or f"#{p.id}"],
                "purchase_amounts": [float(remaining)],
                "score": 80 + int(sim * 10),
                "kind": "split_payment",
                "label": f"Часть платежа: уже {existing:.2f} + {bp_amt:.2f} = {amt:.2f} ₽",
            })

    # E. Fallback: text similarity на одной закупке (когда суммы вообще не сходятся)
    if not candidates:
        for p in purchases:
            sim = _text_similarity(purpose, p.subject or '')
            if sim > 0.2:
                amt = _purchase_amount(p) or Decimal(0)
                candidates.append({
                    "purchase_ids": [p.id],
                    "purchase_names": [p.subject or p.item_name or f"#{p.id}"],
                    "purchase_amounts": [float(amt)],
                    "score": int(sim * 50),
                    "kind": "text_only",
                    "label": f"Только по тексту ({int(sim*100)}%) — суммы не сходятся",
                })

    # Дедуп: одинаковые purchase_ids → keep max score
    seen: dict[tuple, dict] = {}
    for c in candidates:
        key = tuple(sorted(c["purchase_ids"]))
        if key not in seen or c["score"] > seen[key]["score"]:
            seen[key] = c
    candidates = list(seen.values())

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:TOP_N]
