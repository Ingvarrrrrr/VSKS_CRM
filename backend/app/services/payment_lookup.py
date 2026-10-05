"""Третья очередь утверждённого плана (`synchronous-knitting-thacker.md`), Этап 5 —
поиск и загрузка казначейских платежей в группу закупки (см. app/services/payment_target.py).

Платёж подходит группе, когда сходятся ВСЕ четыре признака:
  1. субсидия  — строка видна субсидии группы по правилу
                 app/services/bank_payment_subsidy_scope.py::subsidy_scope_clause
                 (bp.subsidy_id == субсидии ИЛИ номер соглашения субсидии встречается
                 в назначении/основании строки — план 2026-10-04-fadm-statement, п.1:
                 subsidy_id у строки может остаться NULL, если номер соглашения был
                 пуст в момент импорта выписки);
  2. ИНН       — payee_inn контрагента == ИНН контрагента группы;
  3. сумма     — abs(bp.amount - сумма группы по типу) <= 0.02;
  4. код       — kind='товар' → товарная сумма, kind in ('услуга','работа') → сумма услуг;
                 нераспознанный код НЕ блокирует.

Плюс: только исполненные (EXECUTED_STATUSES), уже разнесённый платёж (есть Payment
с этим bank_payment_id — по закупке ТОЙ ЖЕ субсидии, см. _attached_bank_payment_ids_in_subsidy)
не предлагается вовсе. Одна и та же строка МОЖЕТ быть разнесена на закупки ДВУХ разных
субсидий с общим номером соглашения (план, п.2) — занятость считается внутри
субсидии, не глобально.

Задача 2026-10-05 («разбор сверки ФАДМ 2026_2», п.1): занятость — ТОЛЬКО по
идентичности строки выписки (bank_payment_id / внешний external_doc_id строки,
см. _attached_bank_payment_ids_in_subsidy), а НЕ по тексту назначения
(basis_key). Раньше _used_basis_index блокировал привязку ВТОРОЙ, другой строки
выписки, если её назначение (нормализованный текст/документ-основание)
текстуально совпадало с уже разнесённым платежом — реальный случай: два разных
п/п одного контрагента по одному и тому же договору/УПД (частичная оплата
двумя траншами) получали ОДИНАКОВЫЙ basis_key и вторая строка ложно считалась
«уже использованным назначением». basis_key остаётся как human-readable
метаданные платежа (см. Payment.basis_key), но дублем теперь считается только
повторная попытка разнести ТУ ЖЕ строку (bank_payment_id) — см.
_attached_bank_payment_ids_in_subsidy ниже, единственная проверка занятости.

Автозагрузка (см. find_candidates): среди свободных (неиспользованных) кандидатов
берётся первый по дате платежа — это и есть правило «для ежемесячных» из плана:
несколько одинаковых по сумме платежей (аренда за разные месяцы) разбираются по
одному за проход. Если у самых ранних дата совпадает (настоящая, неразрешимая
тем же способом неоднозначность) — авто не срабатывает, кандидаты помечаются
причиной «два равнозначных кандидата».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_basis import (
    expense_code as _expense_code,
    expense_kind,
    extract_basis,
    basis_key as _basis_key,
)
from app.services.item_type_split import kind_of
from app.services.payment_matcher import apply_advance_report_override
from app.services.payment_service_period import resolve_service_period
from app.services.payment_target import PaymentGroup
from app.services.purchase_payments import recompute_purchase_payments, find_manual_match

AMOUNT_TOL = Decimal("0.02")


class PaymentAttachError(Exception):
    """Платёж нельзя разнести — конфликт занятости (уже привязан к другой
    закупке, либо назначение уже использовано в этой группе), либо платёж не
    найден/не исполнен. Router превращает в HTTP 409 с текстом .args[0]."""


class ServicePeriodAttachConflict(PaymentAttachError):
    """Частный случай PaymentAttachError — конкретно конфликт месяца оказания
    (см. app/services/payment_service_period.py::resolve_service_period). Несёт
    purchase_id/occupied_period для структурированного detail 409-ответа (см.
    service_period_conflict_detail, ПРАВИЛО №6); остальные причины
    PaymentAttachError («уже разнесён», «назначение уже использовано» и т.п.)
    этим подклассом НЕ заводятся — у них остаётся обычный текстовый detail."""

    def __init__(self, message: str, purchase_id: int, occupied_period=None):
        super().__init__(message)
        self.purchase_id = purchase_id
        self.occupied_period = occupied_period


@dataclass
class Candidate:
    bank_payment_id: int
    amount: Decimal
    kind: str                       # 'goods' | 'services'
    checks: list[str] = field(default_factory=list)
    auto: bool = False
    free: bool = True
    reason: Optional[str] = None
    basis_label: Optional[str] = None
    payment_number: Optional[str] = None
    payment_date: Optional[_date] = None
    # Задача 04.10.2026 («Помесячные платежи — разные месяцы»): для кандидата на
    # помесячную закупку (Purchase.is_monthly_payment=True) — вычисленный месяц
    # оказания ИЛИ причина, почему он неоднозначен, той же функцией
    # resolve_service_period, что и app/services/match_candidates.py::build_candidates
    # (ПРАВИЛО №6 — не вторая логика). Кандидат не убирается ни в каком случае —
    # это только подсказка для менеджера перед подтверждением/загрузкой.
    service_period: Optional[str] = None
    service_period_conflict: Optional[str] = None
    # Доработка плана 2026-10-04-fadm-statement: пара (эта строка выписки, эта
    # закупка) уже была отклонена согласующим субсидии при подтверждении
    # «Оплачено» (см. app/models/purchase_paid_confirmation_rejection.py) —
    # кандидат НЕ убирается (ручная привязка остаётся доступна), но никогда не
    # получает auto=True, чтобы match-payments не переоткрывал тот же запрос.
    previously_rejected: bool = False


async def _monthly_purchase(db: AsyncSession, purchase_ids: list[int]) -> Optional[Purchase]:
    """Помесячная закупка (is_monthly_payment=True) среди закупок группы, если
    есть — для неё и показывается service_period/service_period_conflict у
    кандидатов (см. Candidate)."""
    if not purchase_ids:
        return None
    rows = (await db.execute(
        select(Purchase).where(
            Purchase.id.in_(purchase_ids),
            Purchase.is_monthly_payment == True,  # noqa: E712
        )
    )).scalars().all()
    return rows[0] if rows else None


async def _rejected_bank_payment_ids(
    db: AsyncSession, bank_payment_ids: list[int], purchase_ids: list[int],
) -> set[int]:
    """bank_payment_id, отклонённые РАНЕЕ хотя бы для одной из закупок группы
    (см. app/models/purchase_paid_confirmation_rejection.py — доработка плана
    2026-10-04-fadm-statement: без этой памяти авто-match-payments тут же
    снова предлагал ту же пару после reject, переоткрывая тот же запрос по
    кругу). Не убирает кандидата из списка — только не даёт auto=True (см.
    find_candidates) и возвращается в attach() как warnings_out для ручной
    привязки человеком."""
    if not bank_payment_ids or not purchase_ids:
        return set()
    from app.models.purchase_paid_confirmation_rejection import PurchasePaidConfirmationRejection
    rows = (await db.execute(
        select(PurchasePaidConfirmationRejection.bank_payment_id).where(
            PurchasePaidConfirmationRejection.bank_payment_id.in_(bank_payment_ids),
            PurchasePaidConfirmationRejection.purchase_id.in_(purchase_ids),
        )
    )).scalars().all()
    return {r for r in rows if r is not None}


async def _attached_bank_payment_ids_in_subsidy(
    db: AsyncSession, bank_payment_ids: list[int], subsidy_id: int,
) -> set[int]:
    """bank_payment_id, у которых УЖЕ есть Payment на закупке ЭТОЙ субсидии —
    план 2026-10-04-fadm-statement, п.2: занятость строки выписки считается
    ВНУТРИ субсидии, не глобально (закупка другой субсидии с тем же номером
    соглашения, см. bank_payment_subsidy_scope.py, вправе опереться на ту же
    строку). Раньше (_attached_bank_payment_ids, до этой задачи) проверка была
    глобальной по ЛЮБОЙ закупке — именно это блокировало вторую субсидию."""
    if not bank_payment_ids:
        return set()
    rows = (await db.execute(
        select(Payment.bank_payment_id)
        .join(Purchase, Purchase.id == Payment.purchase_id)
        .where(
            Payment.bank_payment_id.in_(bank_payment_ids),
            Purchase.subsidy_id == subsidy_id,
        )
    )).scalars().all()
    return {r for r in rows if r is not None}


async def _eligible_bank_payments(
    db: AsyncSession, group: PaymentGroup, target_amount: Decimal, target_kind: str,
) -> list[BankPayment]:
    """Признаки 1-4 (субсидия/ИНН/сумма/код), кроме занятости — та проверяется
    отдельно после (см. find_candidates), т.к. занятые всё равно показываются
    (с причиной), а не молча выкидываются."""
    if not target_amount or target_amount <= 0 or not group.contractor_inn or group.subsidy_id is None:
        return []
    subsidy = await db.get(Subsidy, group.subsidy_id)
    if subsidy is None:
        return []
    lo, hi = target_amount - AMOUNT_TOL, target_amount + AMOUNT_TOL
    rows = (await db.execute(
        select(BankPayment).where(
            subsidy_scope_clause(subsidy),
            BankPayment.payee_inn == group.contractor_inn,
            BankPayment.amount >= lo,
            BankPayment.amount <= hi,
        )
    )).scalars().all()

    out = []
    for bp in rows:
        if (bp.status or "").upper().strip() not in EXECUTED_STATUSES:
            continue
        code = _expense_code(bp)
        kind = await expense_kind(db, code)
        if kind is not None:
            if target_kind == "goods" and kind != "товар":
                continue
            if target_kind == "services" and kind not in ("услуга", "работа"):
                continue
        out.append(bp)
    return out


def _fmt_amount(v) -> str:
    try:
        return f"{Decimal(str(v)):,.2f}".replace(",", " ").replace(".", ",")
    except Exception:
        return str(v)


async def find_candidates(db: AsyncSession, group: PaymentGroup) -> dict[str, list[Candidate]]:
    """{'goods': [...], 'services': [...]} — кандидаты для каждой из двух сумм
    группы (пустая/нулевая сумма не ищется — искать нечего)."""
    result: dict[str, list[Candidate]] = {"goods": [], "services": []}
    if group.subsidy_id is None or not group.contractor_inn:
        return result

    monthly_purchase = await _monthly_purchase(db, group.purchase_ids)

    for kind, target_amount in (("goods", group.goods_amount), ("services", group.services_amount)):
        if not target_amount or target_amount <= 0:
            continue
        bps = await _eligible_bank_payments(db, group, target_amount, kind)
        if not bps:
            continue
        attached_ids = await _attached_bank_payment_ids_in_subsidy(
            db, [bp.id for bp in bps], group.subsidy_id
        )
        bps = [bp for bp in bps if bp.id not in attached_ids]
        if not bps:
            continue
        rejected_ids = await _rejected_bank_payment_ids(
            db, [bp.id for bp in bps], group.purchase_ids,
        )

        candidates: list[Candidate] = []
        for bp in bps:
            basis = extract_basis(bp)
            code = _expense_code(bp)
            code_kind = await expense_kind(db, code)

            checks = ["ИНН ✓", f"Сумма {_fmt_amount(bp.amount)} ✓"]
            if code:
                checks.append(f"Код {code} — {code_kind} ✓" if code_kind else f"Код {code} (нет в справочнике)")
            if basis.label:
                checks.append(f"Назначение: {basis.label}")

            cand = Candidate(
                bank_payment_id=bp.id,
                amount=Decimal(str(bp.amount)),
                kind=kind,
                checks=checks,
                basis_label=basis.label,
                payment_number=bp.payment_number,
                payment_date=bp.payment_date,
            )

            if bp.id in rejected_ids:
                cand.previously_rejected = True
                if not cand.reason:
                    cand.reason = (
                        "эту пару (строка выписки/закупка) уже отклоняли при подтверждении "
                        "«Оплачено» — привяжите вручную, только если уверены"
                    )

            if monthly_purchase is not None:
                sp_result = await resolve_service_period(db, monthly_purchase, bp)
                if sp_result.period:
                    cand.service_period = sp_result.period.isoformat()
                elif sp_result.conflict:
                    cand.service_period_conflict = sp_result.conflict

            candidates.append(cand)

        candidates.sort(key=lambda c: (c.payment_date or _date.min, c.bank_payment_id))

        # Отклонённые ранее пары не участвуют в авто-выборе (см. previously_rejected
        # выше) — иначе match-payments тут же переоткрыл бы тот же запрос подтверждения.
        free = [c for c in candidates if c.free and not c.previously_rejected]
        if len(free) == 1:
            free[0].auto = True
        elif len(free) >= 2:
            earliest_date = free[0].payment_date
            tied = [c for c in free if c.payment_date == earliest_date]
            if len(tied) == 1:
                tied[0].auto = True
            else:
                for c in tied:
                    c.reason = "два равнозначных кандидата"

        result[kind] = candidates

    return result


async def _purchase_kind_totals(db: AsyncSession, purchase_ids: list[int], kind: str) -> dict[int, Decimal]:
    items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).scalars().all()
    totals: dict[int, Decimal] = {pid: Decimal(0) for pid in purchase_ids}
    for it in items:
        if kind_of(it.item_type) == kind:
            totals[it.purchase_id] += Decimal(str(it.total_price)) if it.total_price is not None else Decimal(0)
    return totals


def _infer_kind(group: PaymentGroup, bp_amount: Decimal, code_kind: Optional[str]) -> str:
    if code_kind == "товар":
        return "goods"
    if code_kind in ("услуга", "работа"):
        return "services"
    # Код не распознан — определяем тип по тому, к какой сумме группы ближе платёж.
    goods_diff = abs(bp_amount - group.goods_amount) if group.goods_amount else None
    services_diff = abs(bp_amount - group.services_amount) if group.services_amount else None
    if goods_diff is not None and (services_diff is None or goods_diff <= services_diff):
        return "goods"
    return "services"


async def attach(
    db: AsyncSession,
    group: PaymentGroup,
    bank_payment_ids: list[int],
    allocations: Optional[dict[int, Decimal]] = None,
    service_periods: Optional[dict[int, _date]] = None,
    warnings_out: Optional[list[str]] = None,
) -> list[Payment]:
    """Создаёт Payment(ы) для каждого bank_payment_id, разнося сумму платежа между
    заказами группы. allocations — явное {purchase_id: сумма}, применимо ТОЛЬКО
    когда bank_payment_ids состоит из одного элемента (иначе неоднозначно, кому
    из нескольких платежей оно принадлежит). Без allocations — по умолчанию
    пропорционально сумме заказов по этому типу (не поровну).

    Занятость (bank_payment уже привязан / назначение уже использовано)
    проверяется ДО записи; IntegrityError на частичных уникальных индексах (race
    condition backstop) ловится и превращается в PaymentAttachError — router
    отвечает 409 с понятным текстом, а не 500. Пересчитывает агрегаты закупок
    через recompute_purchase_payments по завершении.

    Для помесячных закупок (Purchase.is_monthly_payment=True) каждому Payment
    проставляется service_period — см. app/services/payment_service_period.py.
    При конфликте (месяц уже занят / свободных не осталось) платёж НЕ создаётся
    молча — PaymentAttachError (тот же механизм, что «занято другим платежом»
    выше), если только человек не передал месяц явно в service_periods={purchase_id: date}.

    warnings_out — необязательный список (мутируется in-place): ручная привязка
    пары, отклонённой РАНЕЕ при подтверждении «Оплачено» (см.
    app/models/purchase_paid_confirmation_rejection.py), РАЗРЕШЕНА — платёж
    создаётся как обычно, но сюда дописывается предупреждение, чтобы router
    (app/routers/purchase_payment_matching.py) вернул его в ответе."""
    if not bank_payment_ids:
        return []
    if allocations is not None and len(bank_payment_ids) > 1:
        raise PaymentAttachError("allocations можно передать только для одного bank_payment_id за раз")

    # Занятость строки — ВНУТРИ субсидии группы (план 2026-10-04-fadm-statement,
    # п.2): закупка другой субсидии с тем же номером соглашения уже могла
    # опереться на эту же строку — это не конфликт. Задача 2026-10-05, п.1:
    # единственный признак занятости — bank_payment_id (эта же строка выписки),
    # НЕ текст назначения (basis_key) — см. докстринг модуля.
    attached_ids = await _attached_bank_payment_ids_in_subsidy(db, bank_payment_ids, group.subsidy_id)
    rejected_ids = await _rejected_bank_payment_ids(db, bank_payment_ids, group.purchase_ids)

    created: list[Payment] = []
    affected_purchases: set[int] = set()

    for bp_id in bank_payment_ids:
        if bp_id in attached_ids:
            raise PaymentAttachError(f"Платёж №{bp_id} уже разнесён по другой закупке этой субсидии")

        if bp_id in rejected_ids and warnings_out is not None:
            warnings_out.append(
                f"Платёж №{bp_id}: эту пару (строка выписки/закупка) уже отклоняли при "
                "подтверждении «Оплачено» — проверьте перед подтверждением заново"
            )

        bp = await db.get(BankPayment, bp_id)
        if not bp:
            raise PaymentAttachError(f"Платёж №{bp_id} не найден")
        if (bp.status or "").upper().strip() not in EXECUTED_STATUSES:
            raise PaymentAttachError(f"Платёж №{bp_id} не исполнен (статус «{bp.status}»)")

        code = _expense_code(bp)
        code_kind = await expense_kind(db, code)
        kind = _infer_kind(group, Decimal(str(bp.amount)), code_kind)

        if allocations is not None:
            purchase_alloc = {int(pid): Decimal(str(amt)) for pid, amt in allocations.items()}
            alloc_sum = sum(purchase_alloc.values(), Decimal(0))
            if abs(alloc_sum - Decimal(str(bp.amount))) > AMOUNT_TOL:
                raise PaymentAttachError(
                    f"Сумма распределения ({alloc_sum:.2f}) не совпадает с суммой платежа ({bp.amount:.2f})"
                )
        else:
            totals = await _purchase_kind_totals(db, group.purchase_ids, kind)
            positive = {pid: amt for pid, amt in totals.items() if amt > 0}
            if not positive:
                positive = {group.purchase_ids[0]: Decimal(1)}  # fallback: единственный заказ группы
            total_sum = sum(positive.values(), Decimal(0))
            bp_amt = Decimal(str(bp.amount))
            purchase_alloc = {}
            allocated_so_far = Decimal(0)
            pids_sorted = sorted(positive.keys())
            for i, pid in enumerate(pids_sorted):
                if i == len(pids_sorted) - 1:
                    share = bp_amt - allocated_so_far  # последнему — остаток, без потери копеек на округлении
                else:
                    share = (bp_amt * positive[pid] / total_sum).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                purchase_alloc[pid] = share
                allocated_so_far += share

        basis = extract_basis(bp)
        bk = _basis_key(bp)
        new_payment = None
        for pid, amount in purchase_alloc.items():
            if amount == 0:
                continue
            purchase = await db.get(Purchase, pid)
            # Этап 0 (попутная гигиена): аванс-отчёт платежа авторитетнее уже
            # сохранённого contract_number/date закупки — но только СЕЙЧАС, в
            # момент реального разнесения (не на каждый auto_match/rematch,
            # см. app/services/payment_matcher.py::apply_advance_report_override).
            apply_advance_report_override(purchase, bp)

            # Владелец (2026-08-19): «поставленная человеком галочка... не
            # является подтверждением» — если на этой закупке уже есть РУЧНОЙ
            # неподтверждённый платёж с тем же номером/датой/суммой, что и эта
            # строка выписки — подтверждаем ЕГО, а не заводим вторую запись
            # (иначе сумма закупки после загрузки выписки удвоится).
            existing_manual = await find_manual_match(db, pid, bp.payment_number, bp.payment_date, amount)

            # Задача 04.10.2026 («Помесячные платежи — разные месяцы»): месяц
            # оказания для помесячной закупки — явный выбор человека приоритетнее
            # авто-резолва; конфликт без выбора → не создаём платёж молча.
            sp_override = (service_periods or {}).get(pid)
            if sp_override is not None:
                service_period = sp_override
            elif purchase is not None and purchase.is_monthly_payment:
                exclude_id = existing_manual.id if existing_manual is not None else None
                sp_result = await resolve_service_period(db, purchase, bp, exclude_payment_id=exclude_id)
                if sp_result.conflict:
                    raise ServicePeriodAttachConflict(
                        f"Закупка №{pid}: не удалось однозначно определить месяц оказания — {sp_result.conflict}",
                        purchase_id=pid,
                        occupied_period=sp_result.occupied_period,
                    )
                service_period = sp_result.period
            else:
                service_period = None

            if existing_manual is not None:
                existing_manual.bank_payment_id = bp.id
                existing_manual.payment_source = "statement"
                existing_manual.confirmed_by_statement = True
                existing_manual.matched_confirmed = True
                existing_manual.document_number = bp.payment_number
                existing_manual.payment_date = bp.payment_date
                existing_manual.amount = amount
                existing_manual.payment_purpose = (bp.purpose_text or "")[:500]
                existing_manual.contract_id = purchase.contract_id if purchase else None
                existing_manual.expense_code = code
                existing_manual.basis_kind = basis.kind
                existing_manual.basis_number = basis.number
                existing_manual.basis_date = basis.date
                existing_manual.basis_key = bk
                existing_manual.basis_label = basis.label
                existing_manual.service_period = service_period
                new_payment = existing_manual
                created.append(existing_manual)
                affected_purchases.add(pid)
                continue

            new_payment = Payment(
                contract_id=purchase.contract_id if purchase else None,
                purchase_id=pid,
                document_number=bp.payment_number,
                payment_purpose=(bp.purpose_text or "")[:500],
                payment_date=bp.payment_date,
                amount=amount,
                bank_payment_id=bp.id,
                matched_confirmed=True,
                payment_source="statement",
                confirmed_by_statement=True,
                expense_code=code,
                basis_kind=basis.kind,
                basis_number=basis.number,
                basis_date=basis.date,
                basis_key=bk,
                basis_label=basis.label,
                service_period=service_period,
            )
            db.add(new_payment)
            created.append(new_payment)
            affected_purchases.add(pid)

        try:
            await db.flush()
        except IntegrityError as exc:
            raise PaymentAttachError(
                f"Платёж №{bp_id} конфликтует с уже существующей записью (занято другим платежом)"
            ) from exc

        attached_ids.add(bp_id)

    for pid in affected_purchases:
        await recompute_purchase_payments(db, pid)

    return created
