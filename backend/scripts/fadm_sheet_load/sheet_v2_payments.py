"""Привязка платежей (bank_payments) к закупкам, созданным sheet_v2_build.py
— вынесено отдельным файлом (ПРАВИЛО №5, sheet_v2_build.py разрастался за
500 строк). Единственный писатель Payment — штатный
app.services.payment_lookup.attach (ПРАВИЛО №6), эта логика только находит
строку bank_payments и группу закупки (app.services.payment_target), сама
ничего не пишет напрямую в Payment.

Правило подбора (владелец, уточнение 05.10.2026 — разобрал формулы листа):
V/U/W/S/T в GoodsService ВСЕ произведены Google-таблицей из ОДНОГО поиска —
строка листа Scroller (= bank_payments) с payee_inn=R, amount=P (сумма
поставки пары закупка/заказ), status=Исполнен, «Документ-основание» содержит
номер соглашения (AGREEMENT_NUMBER). Поэтому U/W — НЕ независимые входы
матчинга, а его побочный продукт: мы ищем ПО ТЕМ ЖЕ трём признакам
(ИНН+сумма+соглашение+исполнен), что и сама таблица, а U/W используем только
для контроля (сверяем найденный платёж с тем, что уже стоит в листе, и
отчитываемся о расхождениях — см. attach_pending_payments). Несколько
кандидатов с одинаковой суммой у одного ИНН — берём первый НЕИСПОЛЬЗОВАННЫЙ
по дате (как и ежемесячные в первом загрузчике).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.services.bank_statement_parser_maps import EXECUTED_STATUSES
from app.services.payment_lookup import attach as attach_payment, PaymentAttachError
from app.services.payment_target import build_groups

from .sheet_v2_parse import AGREEMENT_NUMBER, SheetRowV2, valid_inn

PAYMENT_AMOUNT_TOLERANCE = Decimal("0.02")


@dataclass
class PendingPayment:
    purchase_id: int
    row: SheetRowV2
    label: str


async def find_bank_payment_candidates(db: AsyncSession, row: SheetRowV2,
                                        exclude_ids: set[int]) -> list[BankPayment]:
    """Кандидаты — ИНН + сумма P + «Исполнен» + соглашение в «Документ-основание»
    (см. docstring модуля); отсортированы по дате (раньше — приоритетнее, как
    ежемесячные платежи первого загрузчика), уже использованные в этом же
    прогоне (exclude_ids) не предлагаются повторно."""
    inn = valid_inn(row.inn)
    amount = row.delivery_payment_target
    if not inn or not amount:
        return []
    q = select(BankPayment).where(
        BankPayment.payee_inn == inn,
        BankPayment.status.in_(EXECUTED_STATUSES),
        BankPayment.basis_doc_text.ilike(f"%{AGREEMENT_NUMBER}%"),
    ).order_by(BankPayment.payment_date.asc().nulls_last(), BankPayment.id.asc())
    candidates = (await db.execute(q)).scalars().all()
    out = []
    for bp in candidates:
        if bp.id in exclude_ids:
            continue
        if bp.amount is None or abs(Decimal(str(bp.amount)) - amount) > PAYMENT_AMOUNT_TOLERANCE:
            continue
        out.append(bp)
    return out


def _u_control_note(row: SheetRowV2, bp: BankPayment) -> Optional[str]:
    """Контроль (не фильтр, см. docstring модуля): лист ожидал номер п/п из
    U — сверяем с тем, что реально нашла ЖЕ-формула (ИНН+сумма+соглашение).
    None — совпало или U пуст («Платёж не проходил» — ожидаемо для строк без
    зафиксированного в своё время платежа)."""
    if not row.payment_numbers:
        return None
    doc_no = (bp.payment_number or "").strip()
    if any(doc_no == n or doc_no.endswith(n) for n in row.payment_numbers):
        return None
    return f"лист ожидал №{','.join(row.payment_numbers)}, GALA нашла №{doc_no or bp.id} (по ИНН+сумме+соглашению)"


async def attach_pending_payments(db: AsyncSession, subsidy_id: int, pending: list[PendingPayment],
                                   counters) -> None:
    """Платежи привязываются ОДНИМ проходом после того, как ВСЕ закупки
    субсидии созданы — build_groups(db, subsidy_id) перечитывает ВСЕ закупки
    субсидии заново при каждом вызове (см. app/services/payment_target.py),
    поэтому вызывать её на каждую строку (было в первой версии) — O(n²) и
    на 217 строках реально не завершается за разумное время (прод-находка
    дневного прогона 05.10.2026). Один вызов на всю субсидию — тот же набор
    групп, что видел бы router в проде.

    counters — build.BuildCountersV2, не импортируется типом здесь (вынесло
    бы циклическим импортом build.py↔payments.py); duck-typing достаточно —
    пишем только в payments_attached/payments_attached_amount/payments_not_found/
    payments_u_mismatch/contract_filled_from_payment."""
    groups = await build_groups(db, subsidy_id)
    by_purchase: dict[int, object] = {}
    for g in groups:
        for pid in g.purchase_ids:
            by_purchase[pid] = g

    # Один физический платёж может быть назначением сразу НЕСКОЛЬКИХ строк
    # листа (несколько заказов рамочного, оплаченных одним п/п) — attach_payment
    # сама делит сумму платежа ПРОПОРЦИОНАЛЬНО между ВСЕМИ заказами группы за
    # один вызов, вызываем её РОВНО ОДИН раз на пару (группа, bank_payment_id);
    # used_bp_ids — вообще все уже успешно привязанные id в этом прогоне, чтобы
    # следующая строка с той же суммой/ИНН бралась со следующего неиспользованного
    # кандидата, а не повторно пыталась занять тот же (ту же роль here играет
    # exclude_ids в find_bank_payment_candidates).
    seen_group_payment: set[tuple[int, int]] = set()
    used_bp_ids: set[int] = set()

    for item in pending:
        row, label = item.row, item.label
        if not (row.paid or row.delivered):
            continue  # нечего привязывать — поставки не было

        candidates = await find_bank_payment_candidates(db, row, used_bp_ids)
        if not candidates:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers) or "(нет в листе)", "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label, "reason": "не найдено (ИНН+сумма+соглашение+исполнен)",
            })
            continue

        bp = candidates[0]
        group = by_purchase.get(item.purchase_id)
        if group is None:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers), "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label, "reason": "закупка не входит ни в одну платёжную группу",
            })
            continue

        dedup_key = (id(group), bp.id)
        if dedup_key in seen_group_payment:
            continue
        seen_group_payment.add(dedup_key)

        note = _u_control_note(row, bp)
        if note:
            counters.payments_u_mismatch.append({"label": label, "note": note})

        try:
            created = await attach_payment(db, group, [bp.id])
            if created:
                counters.payments_attached += 1
                counters.payments_attached_amount += sum((p.amount or Decimal("0")) for p in created)
                used_bp_ids.add(bp.id)
                await _backfill_contract_from_payment(db, created, bp, counters)
        except PaymentAttachError as e:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers), "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label, "reason": str(e),
            })


async def _backfill_contract_from_payment(db: AsyncSession, created_payments, bp: BankPayment, counters) -> None:
    """Владелец, уточнение 05.10.2026, п.2: если S/T («Нет данных» — лист не
    смог разобрать номер/дату договора) — разобрать из назначения платежа.
    bank_payments.parsed_contract_number/parsed_contract_date — уже готовый
    разбор (см. app/services/bank_statement_parser.py), не второй парсер
    текста назначения (ПРАВИЛО №6). Правим ТОЛЬКО закупки с временным номером
    (сгенерированным sheet_v2_build.py::generate_temp_contract_number) — так
    их Contract не спутать с чужим реальным номером."""
    if not bp.parsed_contract_number:
        return
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    purchase_ids = [p.purchase_id for p in created_payments]
    purchases = (await db.execute(
        select(Purchase).where(Purchase.id.in_(purchase_ids), Purchase.contract_number_is_temporary.is_(True))
    )).scalars().all()
    contract_ids = {p.contract_id for p in purchases if p.contract_id}
    for cid in contract_ids:
        contract = await db.get(Contract, cid)
        if not contract:
            continue
        contract.number = bp.parsed_contract_number
        if bp.parsed_contract_date:
            contract.date = bp.parsed_contract_date
        siblings = (await db.execute(
            select(Purchase).where(Purchase.contract_id == cid)
        )).scalars().all()
        for sib in siblings:
            sib.contract_number = bp.parsed_contract_number
            sib.contract_date = contract.date
            sib.contract_number_is_temporary = False
        counters.contract_filled_from_payment += 1
