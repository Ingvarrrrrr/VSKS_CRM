"""27.4-21 — сверка платежей: BankPayment (реестр) vs Payment (привязанные к закупкам).

Алгоритм пользователя:
1. Берём все номера платёжных поручений из реестра (BankPayment)
2. Берём все номера привязанных платежей из закупок (Payment, confirmed_by_statement=True)
3. Группируем по payment_number, сравниваем суммы
4. Выводим статус каждого номера:
   - match: есть в обоих, суммы совпадают → зелёный
   - amount_mismatch: есть в обоих, суммы разные → красный
   - registry_only: есть в реестре, нет в закупках → красный (orphan)
   - purchases_only: привязан к закупке (подтверждено выпиской), нет в реестре → жёлтый

Владелец (2026-08-19): ручные НЕподтверждённые платежи («по нашим данным
оплачено», payment_source='manual', confirmed_by_statement=False) — раньше
matched_confirmed==True ставился и для них, поэтому они молча попадали в
purchases_only наравне с реально сопоставленными. После разделения флагов они
из этого запроса выпадают (см. pay_q ниже) — вместо тихого исчезновения им
заведена ОТДЕЛЬНАЯ категория declared_unconfirmed («у нас отмечено, в выписке
нет») — см. блок в build_reconciliation ниже.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.payment import Payment
from app.models.purchase import Purchase

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
    org_ids: Optional[list[int]] = None,
    include_null_org: bool = False,
) -> list[dict]:
    """Возвращает строки сверки.

    Если import_id указан — только платежи этого импорта (срез по выгрузке).
    Иначе — весь реестр.

    org_ids/include_null_org — Этап 1 SaaS-изоляция: если org_ids передан
    (не None), реестровая сторона (BankPayment) ограничивается этими org_id
    (+ NULL, если include_null_org=True — роли уровня админа аккаунта).
    org_ids=None — фильтр не накладывается (SaaS-роли).
    """
    from sqlalchemy import or_ as _or

    # 1. Все BankPayment с номерами
    bp_q = select(BankPayment).where(BankPayment.payment_number.isnot(None))
    if import_id is not None:
        bp_q = bp_q.where(BankPayment.import_id == import_id)
    if org_ids is not None:
        if include_null_org:
            bp_q = bp_q.where(_or(BankPayment.org_id.in_(org_ids), BankPayment.org_id.is_(None)))
        else:
            bp_q = bp_q.where(BankPayment.org_id.in_(org_ids))
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

    # 2. Все Payment с document_number, ПОДТВЕРЖДЁННЫЕ выпиской (привязанные)
    pay_q = select(Payment).where(
        Payment.document_number.isnot(None),
        Payment.confirmed_by_statement == True,  # noqa
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

    # 4. Владелец (2026-08-19): ручные НЕподтверждённые платежи — отдельная
    # категория «у нас отмечено, в выписке нет» (declared_unconfirmed), а не
    # молчаливое отсутствие. Не группируем по номеру с реестром/подтверждёнными
    # (это ДРУГОЙ факт — заявление человека, а не сопоставленная строка выписки),
    # каждая запись — отдельная строка сверки.
    declared_q = select(Payment).where(
        Payment.payment_source == "manual",
        Payment.confirmed_by_statement == False,  # noqa
    )
    if org_ids is not None:
        # У Payment нет своего org_id — область видимости через орг закупки.
        declared_q = declared_q.join(Purchase, Purchase.id == Payment.purchase_id)
        from app.models.subsidy import Subsidy
        declared_q = declared_q.join(Subsidy, Subsidy.id == Purchase.subsidy_id, isouter=True)
        if include_null_org:
            declared_q = declared_q.where(_or(Subsidy.org_id.in_(org_ids), Subsidy.org_id.is_(None)))
        else:
            declared_q = declared_q.where(Subsidy.org_id.in_(org_ids))
    if import_id is not None:
        # У ручных платежей нет import_id (не из выписки вообще) — при срезе по
        # конкретному импорту эта категория неприменима, скрываем полностью.
        declared_q = declared_q.where(Payment.id.is_(None))
    declared_rows = (await db.execute(declared_q)).scalars().all()
    for pay in declared_rows:
        amount = float(Decimal(str(pay.amount or 0)))
        out.append({
            "payment_number": pay.document_number or f"(без номера, платёж #{pay.id})",
            "registry_amount": 0.0,
            "registry_ids": [],
            "registry_dates": [],
            "registry_payees": [],
            "purchases_amount": amount,
            "purchases_ids": [pay.id],
            "linked_purchase_ids": [pay.purchase_id] if pay.purchase_id else [],
            "status": "declared_unconfirmed",
            "amount_diff": 0.0,
        })

    # Сортируем: сначала проблемные (mismatch / orphan / заявлено-не-подтв.), потом match, по номеру
    status_order = {
        "amount_mismatch": 0, "registry_only": 1, "declared_unconfirmed": 2,
        "purchases_only": 3, "match": 4,
    }
    out.sort(key=lambda r: (status_order.get(r["status"], 99), r["payment_number"]))
    return out
