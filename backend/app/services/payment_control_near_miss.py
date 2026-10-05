"""«Почти совпало» — подсказки к непривязанной строке выписки (контрольный
лист субсидии, окно «Сверка»).

План .planning/quick/2026-10-06-statement-control/PLAN.md, п.4. Вызывается
из app/services/subsidy_payment_control.py для каждой строки со статусом
registry_only — ПРАВИЛО №6, единственное место этой эвристики (экспорт в
Excel переиспользует тот же build_near_miss(), не считает заново).

Причины (reason), по владельцу:
  - amount_close  — тот же ИНН контрагента и |Δ| ≤ 1 ₽ (или ≤ 0.5% от суммы
                     платежа — для крупных сумм 1 ₽ слишком строгий порог);
  - same_act      — тот же ИНН и номер акта/УПД из acceptance_doc_number
                     закупки встречается в назначении платежа;
  - orders_sum    — сумма платежа равна сумме НЕСКОЛЬКИХ заказов одного
                     договора (общий Purchase.contract_id), ещё не
                     привязанных ни к одной строке выписки.

can_fix_amount — закупку можно поправить штатным пересчётом при attach()
(см. POST .../attach, fix_amount=true): только когда у неё ОДНА позиция
ИЛИ |Δ| ≤ 1 ₽ (условие совпадает с тем, что проверяет сам attach-эндпоинт,
см. app/routers/subsidy_payment_control.py::attach_bank_payment).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

AMOUNT_CLOSE_ABS = Decimal("1.00")
AMOUNT_CLOSE_PCT = Decimal("0.005")


@dataclass
class _PurchaseCandidate:
    purchase: Purchase
    contractor_name: Optional[str]


async def _candidate_pool(
    db: AsyncSession, subsidy_id: int, matched_purchase_ids: set[int],
) -> list[_PurchaseCandidate]:
    rows = (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.stopped_at.is_(None),
            Purchase.contract_price.isnot(None),
        )
    )).scalars().all()
    rows = [p for p in rows if p.id not in matched_purchase_ids]
    if not rows:
        return []
    contractor_ids = {p.contractor_id for p in rows if p.contractor_id}
    contractor_map: dict[int, str] = {}
    if contractor_ids:
        crows = (await db.execute(
            select(Contractor.id, Contractor.inn, Contractor.name).where(Contractor.id.in_(contractor_ids))
        )).all()
        contractor_map = {r.id: (r.inn, r.name) for r in crows}
    out = []
    for p in rows:
        inn_name = contractor_map.get(p.contractor_id) if p.contractor_id else None
        out.append(_PurchaseCandidate(purchase=p, contractor_name=inn_name[1] if inn_name else None))
    return out


async def build_near_miss(
    db: AsyncSession,
    subsidy_id: int,
    bp_amount: Decimal,
    bp_payee_inn: Optional[str],
    bp_purpose_text: Optional[str],
    matched_purchase_ids: set[int],
    limit: int = 3,
) -> list[dict]:
    """Лучшие ``limit`` подсказок для одной непривязанной строки выписки."""
    if not bp_payee_inn:
        return []

    rows = (await db.execute(
        select(Purchase, Contractor.inn, Contractor.name)
        .join(Contractor, Contractor.id == Purchase.contractor_id)
        .where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.stopped_at.is_(None),
            Purchase.contract_price.isnot(None),
            Contractor.inn == bp_payee_inn,
        )
    )).all()
    same_inn = [(p, name) for (p, _inn, name) in rows if p.id not in matched_purchase_ids]
    if not same_inn:
        return []

    hints: list[dict] = []
    tol = max(AMOUNT_CLOSE_ABS, (bp_amount * AMOUNT_CLOSE_PCT).quantize(Decimal("0.01")))
    purpose_norm = (bp_purpose_text or "").replace(" ", "").upper()

    for p, contractor_name in same_inn:
        price = Decimal(str(p.contract_price or 0))
        delta = bp_amount - price
        item_count = (await db.execute(
            select(PurchaseItem.id).where(PurchaseItem.purchase_id == p.id)
        )).scalars().all()
        can_fix_amount = len(item_count) <= 1 or abs(delta) <= Decimal("1.00")

        if p.acceptance_doc_number and purpose_norm:
            act_norm = str(p.acceptance_doc_number).replace(" ", "").upper()
            if act_norm and act_norm in purpose_norm:
                hints.append({
                    "purchase_id": p.id,
                    "registry_number": p.registry_number,
                    "subject": p.subject or p.item_name,
                    "contractor_name": contractor_name,
                    "amount": float(price),
                    "delta": float(delta),
                    "reason": "same_act",
                    "can_fix_amount": can_fix_amount,
                })
                continue

        if abs(delta) <= tol:
            hints.append({
                "purchase_id": p.id,
                "registry_number": p.registry_number,
                "subject": p.subject or p.item_name,
                "contractor_name": contractor_name,
                "amount": float(price),
                "delta": float(delta),
                "reason": "amount_close",
                "can_fix_amount": can_fix_amount,
            })

    # orders_sum — сумма НЕСКОЛЬКИХ заказов одного договора (общий contract_id)
    # равна сумме платежа; до 4 заказов в комбинации, чтобы не взрывать перебор.
    by_contract: dict[int, list] = {}
    for p, contractor_name in same_inn:
        if p.contract_id:
            by_contract.setdefault(p.contract_id, []).append((p, contractor_name))
    for contract_id, plist in by_contract.items():
        if len(plist) < 2:
            continue
        for n in range(2, min(4, len(plist)) + 1):
            for combo in combinations(plist, n):
                total = sum((Decimal(str(p.contract_price or 0)) for p, _ in combo), Decimal(0))
                if abs(total - bp_amount) <= AMOUNT_CLOSE_ABS:
                    for p, contractor_name in combo:
                        hints.append({
                            "purchase_id": p.id,
                            "registry_number": p.registry_number,
                            "subject": p.subject or p.item_name,
                            "contractor_name": contractor_name,
                            "amount": float(p.contract_price or 0),
                            "delta": float(total - bp_amount),
                            "reason": "orders_sum",
                            "can_fix_amount": False,
                        })
                    break  # одной найденной комбинации на этот contract_id достаточно

    # Дедуп по purchase_id (приоритет первого найденного основания), затем
    # сортировка — сначала точные (меньший |delta|), ограничиваем limit.
    seen: set[int] = set()
    unique: list[dict] = []
    for h in sorted(hints, key=lambda h: abs(h["delta"])):
        if h["purchase_id"] in seen:
            continue
        seen.add(h["purchase_id"])
        unique.append(h)
    return unique[:limit]
