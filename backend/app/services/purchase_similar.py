"""Поиск похожих/дублирующихся закупок — тот же контрагент + та же сумма
(с точностью до округления до 2 знаков), в рамках субсидии или без неё.

ПРАВИЛО №6 (один источник истины): раньше эта проверка была реализована
отдельно в ДВУХ местах — `app/routers/purchase_duplicates.py::duplicate_check`
(один контрагент + одна сумма, разовый запрос) и
`app/services/purchase_import_parser_group.py` (построение индекса
(contractor_id, amount) → [закупка...] по всей субсидии одним запросом,
включая отдельные суммы платежей `Payment.amount`, не только три поля
Purchase). План breezy-mixing-lovelace.md, Часть А («Похожие закупки в
импорте факта») добавляет ТРЕТЬЕГО потребителя —
`historical_fact_import/existing_link.py` — и требует свести все три к
одному месту.

`_AMOUNT_FIELDS` + `_eligible_purchases_query` — общая часть («какие закупки
вообще участвуют»): не `is_monthly_payment`, не `split` (если явно не
попросили `include_statuses_split`), опционально своя субсидия. Два публичных
входа построены НАД этой общей частью:

  - `find_similar_purchases()` — «живой» запрос под один/несколько
    contractor_id + (опционально) одну сумму — именно то, что нужно
    `duplicate_check` (разовый HTTP-запрос с одной парой контрагент+сумма) и
    `historical_fact_import.existing_link` (на предпросмотр импорта обычно
    приходится считанное число групп файла, не сотни).
  - `build_similar_purchases_index()` — ОДИН bulk-запрос на всю субсидию,
    индекс (contractor_id, round(amount,2)) → [запись...]; нужен
    `purchase_import_parser_group.py`, где лукап идёт в цикле по каждой
    строке файла (сотни строк) — одиночные запросы в цикле были бы N+1.

Обе функции собирают запись одинаковой формы и одинаковым правилом
`match_reason` (НМЦК → цена договора → платёж — порядок совпадает с
прежним `_dup_reason` в purchase_duplicates.py), чтобы поведение старых двух
мест не изменилось после перевода.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import Payment
from app.models.purchase import Purchase

# Поля Purchase, по которым ищется совпадение суммы — порядок = приоритет
# match_reason (первое подошедшее поле определяет подпись).
_AMOUNT_FIELDS = (
    ("total_nmck", "НМЦК"),
    ("contract_price", "цена договора"),
    ("payment_amount", "платёж"),
)


def _round2(value) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _purchase_match_reason(p: Purchase, amount: Decimal) -> str:
    for field, label in _AMOUNT_FIELDS:
        v = getattr(p, field)
        if v is not None and _round2(v) == amount:
            return label
    return "платёж"


async def find_similar_purchases(
    db: AsyncSession,
    *,
    subsidy_id: Optional[int],
    contractor_ids: Sequence[int],
    amount: Optional[Decimal] = None,
    exclude_ids: Optional[Sequence[int]] = None,
    include_payment_rows: bool = False,
    exclude_statuses: Sequence[str] = (),
    exclude_stopped: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    """Закупки той же субсидии (если указана) с contractor_id из
    `contractor_ids`, не ежемесячные, не в `exclude_statuses`
    (`exclude_statuses=()` по умолчанию — ТО ЖЕ, что у прежнего
    duplicate_check: split НЕ исключается, если явно не попросить).

    `amount=None` — вернуть ВСЕ подходящие закупки контрагента (поиск «тот
    же поставщик» без требования совпадения суммы — Часть А плана, kind=
    'same_supplier'). `amount` задан — только те, где хотя бы одно из
    total_nmck/contract_price/payment_amount (и, если `include_payment_rows`,
    хотя бы одна строка Payment.amount) округляется до той же суммы —
    фильтр по сумме выполняется в SQL (OR по трём полям), `limit` применяется
    К УЖЕ ОТФИЛЬТРОВАННОМУ набору (как в прежнем duplicate_check: ORDER BY id
    DESC LIMIT 10 по совпавшим), а не к произвольным последним закупкам
    контрагента. `include_payment_rows` добавляет НАДмножество — закупки,
    совпавшие ТОЛЬКО по сумме отдельного Payment (не по трём полям Purchase),
    отдельным запросом (не ломает LIMIT основной выборки).

    Возвращает [{id, registry_number, purchase_number, subject, item_name,
    name, status, contract_date, contractor_id, contractor_name, total_nmck,
    contract_price, payment_amount, amount, match_reason}], отсортировано по
    id desc."""
    if not contractor_ids:
        return []

    from sqlalchemy import func, or_

    amt = _round2(amount) if amount is not None else None

    base_filters = [
        Purchase.contractor_id.in_(list(contractor_ids)),
        Purchase.is_monthly_payment.isnot(True),
    ]
    if subsidy_id is not None:
        base_filters.append(Purchase.subsidy_id == subsidy_id)
    if exclude_statuses:
        base_filters.append(Purchase.status.notin_(list(exclude_statuses)))
    if exclude_stopped:
        base_filters.append(Purchase.stopped_at.is_(None))
    if exclude_ids:
        base_filters.append(Purchase.id.notin_(list(exclude_ids)))

    stmt = (
        select(Purchase)
        .where(*base_filters)
        .options(selectinload(Purchase.contractor))
        .order_by(Purchase.id.desc())
    )
    if amt is not None:
        stmt = stmt.where(or_(
            func.round(func.coalesce(Purchase.total_nmck, 0), 2) == amt,
            func.round(func.coalesce(Purchase.contract_price, 0), 2) == amt,
            func.round(func.coalesce(Purchase.payment_amount, 0), 2) == amt,
        ))
    if limit:
        stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    out = [
        _serialize_purchase(
            p,
            amount=float(amt) if amt is not None else None,
            match_reason=_purchase_match_reason(p, amt) if amt is not None else None,
        )
        for p in rows
    ]

    if amt is not None and include_payment_rows:
        matched_ids = {p.id for p in rows}
        pay_stmt = (
            select(Purchase)
            .join(Payment, Payment.purchase_id == Purchase.id)
            .where(*base_filters, func.round(Payment.amount, 2) == amt)
            .options(selectinload(Purchase.contractor))
            .distinct()
        )
        extra = (await db.execute(pay_stmt)).scalars().all()
        for p in extra:
            if p.id in matched_ids:
                continue
            out.append(_serialize_purchase(p, amount=float(amt), match_reason="платёж"))

    return out


def _serialize_purchase(p: Purchase, *, amount: Optional[float], match_reason: Optional[str]) -> dict:
    return {
        "id": p.id,
        "registry_number": p.registry_number,
        "purchase_number": p.purchase_number,
        "subject": p.subject,
        "item_name": p.item_name,
        "name": p.subject or p.item_name,
        "status": p.status,
        "contract_date": p.contract_date.isoformat() if p.contract_date else None,
        "contractor_id": p.contractor_id,
        "contractor_name": p.contractor.name if p.contractor else None,
        "total_nmck": float(p.total_nmck) if p.total_nmck is not None else None,
        "contract_price": float(p.contract_price) if p.contract_price is not None else None,
        "payment_amount": float(p.payment_amount) if p.payment_amount is not None else None,
        "amount": amount,
        "match_reason": match_reason,
    }


async def build_similar_purchases_index(
    db: AsyncSession,
    subsidy_id: int,
    *,
    exclude_statuses: Sequence[str] = (),
) -> dict:
    """Один bulk-запрос на всю субсидию: индекс (contractor_id,
    round(amount,2)) → [{source:'db', id, purchase_number, name, status,
    contract_date, amount, match_reason}] — ТА ЖЕ форма записи, что раньше
    строилась инлайн в `purchase_import_parser_group.py` (existing_dup_index,
    строки ~150-184 до выноса), поведение не меняется: разовые (не
    ежемесячные) закупки субсидии с известным contractor_id, совпадение по
    total_nmck/contract_price/payment_amount ИЛИ по любой сумме Payment."""
    from collections import defaultdict

    q = select(
        Purchase.id, Purchase.purchase_number, Purchase.item_name,
        Purchase.subject, Purchase.status, Purchase.contract_date,
        Purchase.contractor_id, Purchase.total_nmck,
        Purchase.contract_price, Purchase.payment_amount,
    ).where(
        Purchase.subsidy_id == subsidy_id,
        Purchase.is_monthly_payment.isnot(True),
        Purchase.contractor_id.isnot(None),
    )
    if exclude_statuses:
        q = q.where(Purchase.status.notin_(list(exclude_statuses)))
    rows = (await db.execute(q)).fetchall()

    ids = [r.id for r in rows]
    pay_amounts: dict[int, list] = defaultdict(list)
    if ids:
        pay_rows = (await db.execute(
            select(Payment.purchase_id, Payment.amount).where(
                Payment.purchase_id.in_(ids),
                Payment.amount.isnot(None),
            )
        )).fetchall()
        for pr in pay_rows:
            pay_amounts[pr.purchase_id].append(pr.amount)

    index: dict = defaultdict(list)
    for r in rows:
        base = {
            "source": "db",
            "id": r.id,
            "purchase_number": r.purchase_number,
            "name": r.item_name or r.subject or "",
            "status": r.status,
            "contract_date": r.contract_date.isoformat() if r.contract_date else None,
        }
        pairs = [("НМЦК", r.total_nmck), ("цена договора", r.contract_price), ("платёж", r.payment_amount)]
        pairs += [("платёж", a) for a in pay_amounts.get(r.id, [])]
        for reason, val in pairs:
            if val is None:
                continue
            fv = float(val)
            if fv <= 0:
                continue
            index[(r.contractor_id, round(fv, 2))].append({**base, "amount": fv, "match_reason": reason})
    return index
