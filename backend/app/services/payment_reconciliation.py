"""27.4-21 — сверка платежей: BankPayment (реестр) vs Payment (привязанные к закупкам).

Алгоритм пользователя:
1. Берём все номера платёжных поручений из реестра (BankPayment)
2. Берём все номера привязанных платежей из закупок (Payment, matched_confirmed=True)
3. Группируем по payment_number, сравниваем суммы
4. Выводим статус каждого номера:
   - match: есть в обоих, суммы совпадают → зелёный
   - amount_mismatch: есть в обоих, суммы разные → красный
   - registry_only: есть в реестре, нет в закупках → красный (orphan)
   - purchases_only: привязан к закупке, нет в реестре → жёлтый (manual)
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.payment import Payment

AMOUNT_TOL = Decimal("0.02")


def _normalize_num(s: Optional[str]) -> str:
    """Нормализация номера: trim + lowercase + убрать ведущие нули."""
    if not s:
        return ""
    s = str(s).strip().lower()
    # Убираем ведущие нули из числовых частей
    return s.lstrip("0") or "0"


async def build_reconciliation(
    db: AsyncSession,
    import_id: Optional[int] = None,
) -> list[dict]:
    """Возвращает строки сверки.

    Если import_id указан — только платежи этого импорта (срез по выгрузке).
    Иначе — весь реестр.
    """
    # 1. Все BankPayment с номерами
    bp_q = select(BankPayment).where(BankPayment.payment_number.isnot(None))
    if import_id is not None:
        bp_q = bp_q.where(BankPayment.import_id == import_id)
    bp_rows = (await db.execute(bp_q)).scalars().all()

    by_num: dict[str, dict] = {}
    for bp in bp_rows:
        key = _normalize_num(bp.payment_number)
        if not key:
            continue
        entry = by_num.setdefault(key, {
            "payment_number": bp.payment_number,
            "registry_amount": Decimal(0),
            "registry_ids": [],
            "registry_dates": [],
            "registry_payees": [],
            "purchases_amount": Decimal(0),
            "purchases_ids": [],
            "linked_purchase_ids": [],
            "status": "",
        })
        entry["registry_amount"] += Decimal(str(bp.amount or 0))
        entry["registry_ids"].append(bp.id)
        if bp.payment_date:
            entry["registry_dates"].append(bp.payment_date.isoformat())
        if bp.payee_name:
            entry["registry_payees"].append(bp.payee_name)

    # 2. Все Payment с document_number (привязанные)
    pay_q = select(Payment).where(
        Payment.document_number.isnot(None),
        Payment.matched_confirmed == True,  # noqa
    )
    pay_rows = (await db.execute(pay_q)).scalars().all()

    for pay in pay_rows:
        # document_number может быть "510" или "510; 511" — расщепить
        parts = [p.strip() for p in str(pay.document_number).split(";") if p.strip()]
        for part in parts:
            key = _normalize_num(part)
            if not key:
                continue
            entry = by_num.setdefault(key, {
                "payment_number": part,
                "registry_amount": Decimal(0),
                "registry_ids": [],
                "registry_dates": [],
                "registry_payees": [],
                "purchases_amount": Decimal(0),
                "purchases_ids": [],
                "linked_purchase_ids": [],
                "status": "",
            })
            # Если несколько частей в document_number — делим amount поровну
            entry["purchases_amount"] += Decimal(str(pay.amount or 0)) / Decimal(len(parts))
            entry["purchases_ids"].append(pay.id)
            if pay.purchase_id:
                entry["linked_purchase_ids"].append(pay.purchase_id)

    # 3. Status каждой строки
    out = []
    for key, e in by_num.items():
        in_registry = bool(e["registry_ids"])
        in_purchases = bool(e["purchases_ids"])
        amt_diff = abs(e["registry_amount"] - e["purchases_amount"])
        if in_registry and in_purchases:
            if amt_diff <= AMOUNT_TOL:
                e["status"] = "match"
            else:
                e["status"] = "amount_mismatch"
        elif in_registry and not in_purchases:
            e["status"] = "registry_only"
        elif in_purchases and not in_registry:
            e["status"] = "purchases_only"
        e["amount_diff"] = float(amt_diff)
        e["registry_amount"] = float(e["registry_amount"])
        e["purchases_amount"] = float(e["purchases_amount"])
        # Дедуп списков
        e["registry_dates"] = sorted(set(e["registry_dates"]))
        e["registry_payees"] = sorted(set(e["registry_payees"]))
        e["linked_purchase_ids"] = sorted(set(e["linked_purchase_ids"]))
        out.append(e)

    # Сортируем: сначала проблемные (mismatch / orphan), потом match, по номеру
    status_order = {"amount_mismatch": 0, "registry_only": 1, "purchases_only": 2, "match": 3}
    out.sort(key=lambda r: (status_order.get(r["status"], 99), r["payment_number"]))
    return out
