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
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.services.bank_statement_parser_maps import EXECUTED_STATUSES
from app.services.payment_lookup import attach as attach_payment, PaymentAttachError
from app.services.payment_target import build_groups
from app.services.purchase_payments import recompute_purchase_payments

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


def _dedup_by_purchase(pending: list[PendingPayment]) -> list[PendingPayment]:
    """Один элемент pending — одна СТРОКА листа, но платёж ищется на пару
    (закупка D, заказ E, ИНН) — ОДИН раз, не по разу на каждую строку-позицию
    внутри заказа (прод-находка 05.10.2026: «ЦЕНТРАВТО» заказ 5 — 17 строк
    общей поставки P=89 360,02 — без дедупликации это 17 одинаковых попыток
    поиска и 17 одинаковых «не найдено» в отчёте вместо одной). Все строки
    одного purchase_id делят один P (delivery_payment_target) — берём первую."""
    seen: set[int] = set()
    out: list[PendingPayment] = []
    for item in pending:
        if item.purchase_id in seen:
            continue
        seen.add(item.purchase_id)
        out.append(item)
    return out


async def attach_pending_payments(db: AsyncSession, subsidy_id: int, pending: list[PendingPayment],
                                   counters) -> None:
    """Платежи привязываются ОДНИМ проходом после того, как ВСЕ закупки
    субсидии созданы — build_groups(db, subsidy_id) перечитывает ВСЕ закупки
    субсидии заново при каждом вызове (см. app/services/payment_target.py),
    поэтому вызывать её на каждую строку (было в первой версии) — O(n²) и
    на 217 строках реально не завершается за разумное время (прод-находка
    дневного прогона 05.10.2026). Один вызов на всю субсидию — тот же набор
    групп, что видел бы router в проде.

    Несколько кандидатов с одинаковой суммой/ИНН (владелец, уточнение
    05.10.2026, п.3): «если сумма у этого ИНН уже занята — следующая
    незанятая строка выписки». app/services/payment_lookup.py::attach сам
    отказывает («уже разнесён другой закупке» / «назначение уже использовано»)
    — это НЕ правится в app/* (запрещено задачей), а обходится ЗДЕСЬ: при
    отказе пробуем СЛЕДУЮЩЕГО кандидата (уже отсортированы по дате), а не
    сдаёмся после первого же.

    counters — build.BuildCountersV2, не импортируется типом здесь (вынесло
    бы циклическим импортом build.py↔payments.py); duck-typing достаточно —
    пишем только в payments_attached/payments_attached_amount/payments_not_found/
    payments_u_mismatch/contract_filled_from_payment."""
    groups = await build_groups(db, subsidy_id)
    by_purchase: dict[int, object] = {}
    for g in groups:
        for pid in g.purchase_ids:
            by_purchase[pid] = g

    used_bp_ids: set[int] = set()

    for item in _dedup_by_purchase(pending):
        row, label = item.row, item.label
        if not (row.paid or row.delivered):
            continue  # нечего привязывать — поставки не было

        candidates = await find_bank_payment_candidates(db, row, used_bp_ids)
        if not candidates:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers) or "(нет в листе)", "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label,
                "reason": "не найдено (ИНН+сумма+соглашение+исполнен)",
            })
            continue

        group = by_purchase.get(item.purchase_id)
        if group is None:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers), "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label,
                "reason": "закупка не входит ни в одну платёжную группу",
            })
            continue

        last_error: Optional[str] = None
        attached_ok = False
        for bp in candidates:
            try:
                created = await attach_payment(db, group, [bp.id])
            except PaymentAttachError as e:
                last_error = str(e)
                continue  # следующий кандидат по дате (владелец, п.3)
            if created:
                counters.payments_attached += 1
                counters.payments_attached_amount += sum((p.amount or Decimal("0")) for p in created)
                used_bp_ids.add(bp.id)
                note = _u_control_note(row, bp)
                if note:
                    counters.payments_u_mismatch.append({"label": label, "note": note})
                await _backfill_contract_from_payment(db, created, bp, counters)
            attached_ok = True
            break

        if not attached_ok:
            counters.payments_not_found.append({
                "doc_no": ",".join(row.payment_numbers), "inn": row.inn,
                "amount": str(row.delivery_payment_target), "label": label,
                "reason": last_error or "не найдено",
            })


def _order_target_amounts(paid_rows: list[PendingPayment]) -> dict[int, Decimal]:
    """{purchase_id: Σ P по ВСЕМ различным заказам E этой закупки}.

    Находка владельца (dry-run 05.10.2026, п.1): sheet_v2_parse.py::
    group_rows_v2 группирует закупки ТОЛЬКО по (ИНН, D «№ закупки») — БЕЗ E
    «№ заказа» (см. её докстринг) — поэтому ОДНА Purchase может объединять
    НЕСКОЛЬКО разных заказов, каждый со своим P («Текстиль М» №81 — заказы 2 и
    3 с P=72840 и P=1167160; «УНИВЕРСИС» №100 — заказы 1 и 2 с P=4000 и
    P=8000). _dedup_by_purchase (выше) намеренно берёт ОДНУ строку на
    purchase_id — она чинит дубли строк-ПОЗИЦИЙ внутри одного заказа, но
    ошибочно схлопывала бы и РАЗНЫЕ заказы одной закупки до первого
    встреченного P, теряя остальные. Здесь дедуп — по (purchase_id, E), с
    суммированием P по всем уникальным E данной закупки — то и значение,
    которое должно получить «оплачено по отметке» этой Purchase."""
    seen_pairs: set[tuple[int, str]] = set()
    totals: dict[int, Decimal] = {}
    for item in paid_rows:
        pair = (item.purchase_id, item.row.order_no)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        amt = item.row.delivery_payment_target
        if not amt or amt <= 0:
            continue
        totals[item.purchase_id] = totals.get(item.purchase_id, Decimal("0")) + amt
    return totals


async def create_declared_payments_for_paid_rows(
    db: AsyncSession, subsidy_id: int, pending: list[PendingPayment], counters, current_user,
) -> int:
    """Задание владельца (05.10.2026, п.3): строки с галочкой AW (row.paid) —
    «оплачено по отметке сотрудников», ТЕМ ЖЕ штатным способом, каким
    сотрудник сам отмечает оплату вручную (app/routers/payments.py::
    create_payment — Payment(payment_source='manual', confirmed_by_statement=
    False), ПРАВИЛО №6: не второй механизм).

    import_run_id (FactImportRun) ОБЯЗАТЕЛЕН — это ровно тот же приём, что уже
    умеет app/services/purchase_payments.py::find_manual_match (заглушка
    «Импорта факта»: payment_source='manual' + confirmed_by_statement=False +
    import_run_id задан + document_number/payment_date оба NULL матчатся по
    СУММЕ, без номера/даты документа — их в листе GoodsService для оплаты «по
    отметке» просто нет). Без import_run_id последующая привязка выписки
    (attach_pending_payments ниже, тот же прогон) не нашла бы эту запись и
    завела бы ВТОРОЙ платёж — задвоив сумму субсидии.

    Status закупки НЕ меняется на 'paid' — resolve_status (sheet_v2_parse.py)
    уже останавливается на 'delivered' для AW (решение владельца: «оплачено
    только через подтверждение согласующим»), эта функция платёж только
    заводит, статус не трогает.

    Сумма на закупку — Σ P (delivery_payment_target) по ВСЕМ различным
    заказам E этой закупки (_order_target_amounts выше) — ОДНА Purchase может
    объединять несколько заказов (group_rows_v2 группирует только по (ИНН,
    D), без E), у каждого свой P."""
    paid_rows = [item for item in pending if item.row.paid]
    if not paid_rows:
        return None

    from app.models.fact_import_run import FactImportRun

    run = FactImportRun(
        subsidy_id=subsidy_id,
        user_id=getattr(current_user, "id", None),
        filename="fadm_sheet_load: GoodsService (AW — оплачено по отметке)",
        format="columns",
        mapping={},
        decisions={},
        status="committed",
    )
    db.add(run)
    await db.flush()

    targets = _order_target_amounts(paid_rows)
    created = 0
    created_amount = Decimal("0")
    for purchase_id, amount in targets.items():
        db.add(Payment(
            purchase_id=purchase_id,
            amount=amount,
            payment_source="manual",
            confirmed_by_statement=False,
            import_run_id=run.id,
        ))
        created += 1
        created_amount += amount
    await db.flush()
    for purchase_id in targets:
        await recompute_purchase_payments(db, purchase_id)

    run.payments_created = created
    counters.declared_payments_created = getattr(counters, "declared_payments_created", 0) + created
    counters.declared_payments_amount = getattr(counters, "declared_payments_amount", Decimal("0")) + created_amount
    return run.id


async def ensure_declared_floor_after_statement(
    db: AsyncSession, pending: list[PendingPayment], counters, run_id: Optional[int],
) -> None:
    """Подстраховка ПОСЛЕ attach_pending_payments: корень находки dry-run
    05.10.2026 (п.1, «Текстиль М» №81 / «УНИВЕРСИС» №100 — у каждой закупки
    по ДВА разных заказа E со своим P, см. _order_target_amounts) уже починен
    выше — create_declared_payments_for_paid_rows теперь заводит Σ P по ВСЕМ
    заказам закупки, а не P первого встреченного. Этот шаг — дополнительная
    защита на случай, если payment_lookup.py::attach (её трогать ЗАПРЕЩЕНО
    заданием — независимая сессия) всё же распределит найденный bank_payment
    НЕ на ту заявленную сумму (например, частичная allocation по группе
    payment_target.py::build_groups): довосполняет (confirmed+declared) этой
    закупки обратно до Σ P ещё одним manual-платежом (ПРАВИЛО №6 — тот же
    Payment(payment_source='manual', confirmed_by_statement=False), что и
    create_declared_payments_for_paid_rows, не новый механизм).

    «Отметка по каждой поставке с AW должна остаться = P независимо от
    выписки» (формулировка владельца) — после этого шага (confirmed +
    declared) для такой закупки РОВНО Σ P её заказов, чем бы ни закончилось
    распределение банковского платежа."""
    paid_rows = [item for item in pending if item.row.paid]
    if not paid_rows:
        return
    targets = _order_target_amounts(paid_rows)
    for purchase_id, target in targets.items():
        p = await db.get(Purchase, purchase_id)
        if p is None:
            continue
        current = Decimal(str(p.payment_amount or 0)) + Decimal(str(p.payment_amount_declared or 0))
        shortfall = target - current
        if shortfall > Decimal("0.01"):
            db.add(Payment(
                purchase_id=purchase_id,
                amount=shortfall,
                payment_source="manual",
                confirmed_by_statement=False,
                import_run_id=run_id,
            ))
            await db.flush()
            await recompute_purchase_payments(db, purchase_id)
            counters.declared_payments_topup = getattr(counters, "declared_payments_topup", 0) + 1
            counters.declared_payments_topup_amount = getattr(counters, "declared_payments_topup_amount", Decimal("0")) + shortfall


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
