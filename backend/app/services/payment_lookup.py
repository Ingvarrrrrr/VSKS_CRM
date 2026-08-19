"""Третья очередь утверждённого плана (`synchronous-knitting-thacker.md`), Этап 5 —
поиск и загрузка казначейских платежей в группу закупки (см. app/services/payment_target.py).

Платёж подходит группе, когда сходятся ВСЕ четыре признака:
  1. субсидия  — bank_payments.subsidy_id == субсидия закупки (чужие/NULL не рассматриваются);
  2. ИНН       — payee_inn контрагента == ИНН контрагента группы;
  3. сумма     — abs(bp.amount - сумма группы по типу) <= 0.02;
  4. код       — kind='товар' → товарная сумма, kind in ('услуга','работа') → сумма услуг;
                 нераспознанный код НЕ блокирует.

Плюс: только исполненные (EXECUTED_STATUSES), уже разнесённый платёж (есть Payment
с этим bank_payment_id — по любой закупке) не предлагается вовсе, а платёж со
свободной суммой, но уже использованным «назначением» (basis_key) в ЭТОЙ группе —
предлагается с явной причиной, не автозагружается.

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
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_basis import (
    expense_code as _expense_code,
    expense_kind,
    extract_basis,
    basis_key as _basis_key,
)
from app.services.payment_matcher import apply_advance_report_override
from app.services.payment_target import PaymentGroup
from app.services.purchase_payments import recompute_purchase_payments, find_manual_match

AMOUNT_TOL = Decimal("0.02")


class PaymentAttachError(Exception):
    """Платёж нельзя разнести — конфликт занятости (уже привязан к другой
    закупке, либо назначение уже использовано в этой группе), либо платёж не
    найден/не исполнен. Router превращает в HTTP 409 с текстом .args[0]."""


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


async def _used_basis_index(db: AsyncSession, purchase_ids: list[int]) -> dict[str, Payment]:
    """basis_key → Payment, уже занявший это назначение среди закупок группы."""
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(Payment).where(
            Payment.purchase_id.in_(purchase_ids),
            Payment.matched_confirmed == True,  # noqa: E712
            Payment.basis_key.isnot(None),
        )
    )).scalars().all()
    return {p.basis_key: p for p in rows}


async def _attached_bank_payment_ids(db: AsyncSession, bank_payment_ids: list[int]) -> set[int]:
    """bank_payment_id, у которых УЖЕ есть Payment (неважно, на какую закупку) —
    такие не предлагаются повторно нигде."""
    if not bank_payment_ids:
        return set()
    rows = (await db.execute(
        select(Payment.bank_payment_id).where(Payment.bank_payment_id.in_(bank_payment_ids))
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
    lo, hi = target_amount - AMOUNT_TOL, target_amount + AMOUNT_TOL
    rows = (await db.execute(
        select(BankPayment).where(
            BankPayment.subsidy_id == group.subsidy_id,
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

    used_basis = await _used_basis_index(db, group.purchase_ids)

    for kind, target_amount in (("goods", group.goods_amount), ("services", group.services_amount)):
        if not target_amount or target_amount <= 0:
            continue
        bps = await _eligible_bank_payments(db, group, target_amount, kind)
        if not bps:
            continue
        attached_ids = await _attached_bank_payment_ids(db, [bp.id for bp in bps])
        bps = [bp for bp in bps if bp.id not in attached_ids]
        if not bps:
            continue

        candidates: list[Candidate] = []
        for bp in bps:
            basis = extract_basis(bp)
            bk = _basis_key(bp)
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

            used_payment = used_basis.get(bk) if bk else None
            if used_payment:
                cand.free = False
                doc = used_payment.document_number or "?"
                dt = used_payment.payment_date.strftime("%d.%m.%Y") if used_payment.payment_date else "?"
                cand.reason = f"назначение уже использовано платежом №{doc} от {dt}"

            candidates.append(cand)

        candidates.sort(key=lambda c: (c.payment_date or _date.min, c.bank_payment_id))

        free = [c for c in candidates if c.free]
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
    wanted = {"товар"} if kind == "goods" else {"услуга", "работа"}
    totals: dict[int, Decimal] = {pid: Decimal(0) for pid in purchase_ids}
    for it in items:
        if (it.item_type or "").strip() in wanted:
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
    """
    if not bank_payment_ids:
        return []
    if allocations is not None and len(bank_payment_ids) > 1:
        raise PaymentAttachError("allocations можно передать только для одного bank_payment_id за раз")

    used_basis = await _used_basis_index(db, group.purchase_ids)
    attached_ids = await _attached_bank_payment_ids(db, bank_payment_ids)

    created: list[Payment] = []
    affected_purchases: set[int] = set()

    for bp_id in bank_payment_ids:
        if bp_id in attached_ids:
            raise PaymentAttachError(f"Платёж №{bp_id} уже разнесён по другой закупке")

        bp = await db.get(BankPayment, bp_id)
        if not bp:
            raise PaymentAttachError(f"Платёж №{bp_id} не найден")
        if (bp.status or "").upper().strip() not in EXECUTED_STATUSES:
            raise PaymentAttachError(f"Платёж №{bp_id} не исполнен (статус «{bp.status}»)")

        bk = _basis_key(bp)
        used_payment = used_basis.get(bk) if bk else None
        if used_payment:
            doc = used_payment.document_number or "?"
            dt = used_payment.payment_date.strftime("%d.%m.%Y") if used_payment.payment_date else "?"
            raise PaymentAttachError(f"Назначение уже использовано платежом №{doc} от {dt}")

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

        if bk:
            used_basis[bk] = new_payment  # тот же вызов не сможет занять то же назначение повторно
        attached_ids.add(bp_id)

    for pid in affected_purchases:
        await recompute_purchase_payments(db, pid)

    return created
