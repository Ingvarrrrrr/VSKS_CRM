"""Задача 05.10.2026 («три расширения штатного сопоставления выписки») —
РАСШИРЕНИЕ app/services/payment_lookup.py (ПРАВИЛО №6: один источник привязки —
везде пишет app/services/payment_lookup.py::attach(), здесь только ПОИСК
кандидатов для трёх случаев, которые основной find_candidates не берёт, потому
что он ищет РОВНО ОДИН платёж, сумма которого равна ПОЛНОЙ сумме группы):

  1. Помесячные (Purchase.is_monthly_payment) — несколько платежей одного
     получателя по одному договору, каждый на свой месяц
     (app/services/payment_service_period.py::resolve_service_period —
     единственное место, где определяется месяц, см. его докстринг).
  2. Рамочные (purchase_contract_type in FRAMEWORK_TYPES) — несколько платежей
     на один дочерний заказ ИЛИ один платёж на несколько заказов одной рамки
     (subset-sum, ограничен max_n заказов/платежей).
  3. Авансовые (purchase_method='advance') — получатель платежа это СОТРУДНИК
     (Purchase.reimbursement_user_id), не контрагент закупки, сравнение ФИО —
     app/services/person_name.py::normalize_person_name (единственное место
     этой нормализации).

Все три функции только НАХОДЯТ, что привязать; запись делает
app/services/payment_lookup.py::attach() (или не делает — dry_run=True, тот же
контракт, что и router.match_payments_endpoint). Ничего не привязывается к
занятым (_attached_bank_payment_ids_in_subsidy) или ранее отклонённым
(_rejected_bank_payment_ids) строкам — те же проверки, что в payment_lookup.py.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_basis import normalize_doc_number
from app.services.payment_lookup import (
    AMOUNT_TOL,
    PaymentAttachError,
    ServicePeriodAttachConflict,
    _attached_bank_payment_ids_in_subsidy,
    _rejected_bank_payment_ids,
    attach,
)
from app.services.payment_service_period import resolve_service_period
from app.services.payment_target import PaymentGroup
from app.services.person_name import normalize_person_name

MAX_SUBSET_N = 12  # ограничение перебора subset-sum (2б/2в, задание владельца)


def _group_total(g: PaymentGroup) -> Decimal:
    return (
        Decimal(str(g.goods_amount or 0))
        + Decimal(str(g.services_amount or 0))
        + Decimal(str(g.unspecified_amount or 0))
    )


def _group_remaining(g: PaymentGroup) -> Decimal:
    already = sum((Decimal(str(p.amount)) for p in g.payments if p.amount is not None), Decimal(0))
    return _group_total(g) - already


async def _executed_candidates(
    db: AsyncSession, subsidy: Subsidy, payee_inn: Optional[str] = None, payee_name_norm: Optional[str] = None,
) -> list[BankPayment]:
    q = select(BankPayment).where(subsidy_scope_clause(subsidy))
    if payee_inn:
        q = q.where(BankPayment.payee_inn == payee_inn)
    rows = (await db.execute(q)).scalars().all()
    out = [bp for bp in rows if (bp.status or "").upper().strip() in EXECUTED_STATUSES]
    if payee_name_norm is not None:
        out = [bp for bp in out if normalize_person_name(bp.payee_name) == payee_name_norm]
    return out


async def _free_candidates(
    db: AsyncSession, candidates: list[BankPayment], subsidy_id: int, purchase_ids: list[int],
) -> list[BankPayment]:
    attached = await _attached_bank_payment_ids_in_subsidy(db, [bp.id for bp in candidates], subsidy_id)
    rejected = await _rejected_bank_payment_ids(db, [bp.id for bp in candidates], purchase_ids)
    busy = attached | rejected
    return [bp for bp in candidates if bp.id not in busy]


def _subset_sum_unique(
    items: list, value_fn, target: Decimal, tol: Decimal = AMOUNT_TOL, max_n: int = MAX_SUBSET_N,
) -> Optional[list]:
    """Единственное подмножество items (не длиннее max_n — перебор ограничен
    заданием владельца), суммирующееся в target ± tol. Возвращает None, если
    подходящих подмножеств 0 ИЛИ больше одного (настоящая неоднозначность —
    не привязываем, см. докстринг модуля)."""
    pool = list(items)[:max_n]
    matches = []
    for r in range(1, len(pool) + 1):
        for combo in itertools.combinations(pool, r):
            total = sum((value_fn(x) for x in combo), Decimal(0))
            if abs(total - target) <= tol:
                matches.append(list(combo))
                if len(matches) > 1:
                    return None  # неоднозначно — можно выйти раньше
    if len(matches) == 1:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# 1. Помесячные
# ---------------------------------------------------------------------------

async def match_monthly(
    db: AsyncSession, group: PaymentGroup, purchase: Purchase, dry_run: bool = False,
) -> dict:
    """Несколько платежей того же получателя (ИНН) по тому же договору — каждый
    на свой месяц (resolve_service_period). Сумма каждого платежа произвольна,
    Σ привязанных не обязана достигать contract_price/суммы группы сразу (на
    следующей выписке придут ещё). dry_run=True — ничего не пишет, только
    отчёт о том, что было бы привязано (как match_payments_endpoint)."""
    result: dict = {"attached": [], "ambiguous": []}
    if not purchase.is_monthly_payment or group.subsidy_id is None or not group.contractor_inn:
        return result
    subsidy = await db.get(Subsidy, group.subsidy_id)
    if subsidy is None:
        return result

    remaining = _group_remaining(group)
    if remaining <= AMOUNT_TOL:
        return result

    candidates = await _executed_candidates(db, subsidy, payee_inn=group.contractor_inn)

    contract_num_norm = normalize_doc_number(purchase.contract_number or "")
    if contract_num_norm:
        by_contract = [
            bp for bp in candidates
            if bp.parsed_contract_number and normalize_doc_number(bp.parsed_contract_number) == contract_num_norm
        ]
        if by_contract:
            candidates = by_contract

    candidates = await _free_candidates(db, candidates, group.subsidy_id, group.purchase_ids)
    candidates.sort(key=lambda bp: (bp.payment_date or _date.min, bp.id))

    for bp in candidates:
        if remaining <= AMOUNT_TOL:
            break
        amt = Decimal(str(bp.amount))
        if amt > remaining + AMOUNT_TOL:
            continue  # крупнее того, что ещё не оплачено по этому договору — не наш платёж
        sp_result = await resolve_service_period(db, purchase, bp)
        if sp_result.conflict:
            result["ambiguous"].append({
                "bank_payment_id": bp.id, "amount": float(amt), "reason": sp_result.conflict,
            })
            continue
        if dry_run:
            result["attached"].append({
                "bank_payment_id": bp.id, "amount": float(amt),
                "service_period": sp_result.period.isoformat() if sp_result.period else None,
            })
            remaining -= amt
            continue
        try:
            created = await attach(db, group, [bp.id])
        except ServicePeriodAttachConflict as exc:
            result["ambiguous"].append({"bank_payment_id": bp.id, "reason": str(exc)})
            continue
        except PaymentAttachError as exc:
            result["ambiguous"].append({"bank_payment_id": bp.id, "reason": str(exc)})
            continue
        remaining -= amt
        result["attached"].append({
            "bank_payment_id": bp.id, "amount": float(amt),
            "payment_ids": [p.id for p in created],
        })
    return result


# ---------------------------------------------------------------------------
# 2. Рамочные
# ---------------------------------------------------------------------------

async def match_framework(db: AsyncSession, groups: list[PaymentGroup], dry_run: bool = False) -> dict:
    """groups — ВСЕ группы субсидии (отфильтровываем is_framework сами), чтобы
    видеть всех «братьев» одной рамки сразу (контракт+ИНН). (а) несколько
    платежей → один заказ: subset-sum кандидатов против остатка заказа.
    (б) один платёж → несколько заказов: subset-sum остатков заказов против
    суммы платежа. Оба перебора ограничены MAX_SUBSET_N (задание владельца)."""
    result: dict = {"attached": [], "ambiguous": []}
    by_contract: dict[tuple, list[PaymentGroup]] = {}
    for g in groups:
        if not g.is_framework or not g.contract_number or not g.contractor_inn or g.subsidy_id is None:
            continue
        by_contract.setdefault((g.subsidy_id, g.contract_number, g.contractor_inn), []).append(g)

    for (subsidy_id, contract_number, inn), fw_groups in by_contract.items():
        subsidy = await db.get(Subsidy, subsidy_id)
        if subsidy is None:
            continue

        remainders: dict[str, tuple[PaymentGroup, Decimal]] = {}
        for g in fw_groups:
            rem = _group_remaining(g)
            if rem > AMOUNT_TOL:
                remainders[g.group_key] = (g, rem)
        if not remainders:
            continue

        all_purchase_ids = [pid for g, _ in remainders.values() for pid in g.purchase_ids]
        candidates = await _executed_candidates(db, subsidy, payee_inn=inn)
        contract_num_norm = normalize_doc_number(contract_number)
        by_contract_num = [
            bp for bp in candidates
            if bp.parsed_contract_number and normalize_doc_number(bp.parsed_contract_number) == contract_num_norm
        ]
        if by_contract_num:
            candidates = by_contract_num
        candidates = await _free_candidates(db, candidates, subsidy_id, all_purchase_ids)
        if not candidates:
            continue
        candidates.sort(key=lambda bp: (bp.payment_date or _date.min, bp.id))

        used_bp_ids: set[int] = set()

        # (а) несколько платежей → один заказ
        for group_key, (g, rem) in list(remainders.items()):
            pool = [bp for bp in candidates if bp.id not in used_bp_ids]
            if len(pool) < 2:
                continue  # один подходящий платёж уже нашёл бы обычный find_candidates
            subset = _subset_sum_unique(pool, lambda bp: Decimal(str(bp.amount)), rem)
            if not subset or len(subset) < 2:
                continue
            if dry_run:
                result["attached"].append({
                    "group_key": group_key,
                    "bank_payment_ids": [bp.id for bp in subset],
                    "amount": float(rem),
                    "case": "framework_many_to_one",
                })
                used_bp_ids.update(bp.id for bp in subset)
                continue
            try:
                created_ids = []
                for bp in subset:
                    created = await attach(db, g, [bp.id])
                    created_ids.extend(p.id for p in created)
                used_bp_ids.update(bp.id for bp in subset)
                result["attached"].append({
                    "group_key": group_key,
                    "bank_payment_ids": [bp.id for bp in subset],
                    "payment_ids": created_ids,
                    "case": "framework_many_to_one",
                })
            except PaymentAttachError as exc:
                result["ambiguous"].append({"group_key": group_key, "reason": str(exc)})

        # (б) один платёж → несколько заказов
        closed_keys = {a["group_key"] for a in result["attached"] if "group_key" in a}
        open_remainders = [(g, rem) for key, (g, rem) in remainders.items() if key not in closed_keys]
        pool = [bp for bp in candidates if bp.id not in used_bp_ids]
        for bp in pool:
            if len(open_remainders) < 2:
                break
            amt = Decimal(str(bp.amount))
            subset = _subset_sum_unique(open_remainders, lambda pair: pair[1], amt)
            if not subset or len(subset) < 2:
                continue
            alloc: dict[int, Decimal] = {}
            allocated = Decimal(0)
            for i, (g, rem) in enumerate(subset):
                pid = g.purchase_ids[0]
                share = rem if i < len(subset) - 1 else (amt - allocated)
                alloc[pid] = share
                allocated += share if i < len(subset) - 1 else Decimal(0)
            group_keys = [g.group_key for g, _ in subset]
            if dry_run:
                result["attached"].append({
                    "bank_payment_id": bp.id, "group_keys": group_keys,
                    "amount": float(amt), "case": "framework_one_to_many",
                })
                used_bp_ids.add(bp.id)
                open_remainders = [pair for pair in open_remainders if pair[0].group_key not in group_keys]
                continue
            try:
                created = await attach(db, subset[0][0], [bp.id], allocations=alloc)
                used_bp_ids.add(bp.id)
                open_remainders = [pair for pair in open_remainders if pair[0].group_key not in group_keys]
                result["attached"].append({
                    "bank_payment_id": bp.id, "group_keys": group_keys,
                    "payment_ids": [p.id for p in created], "case": "framework_one_to_many",
                })
            except PaymentAttachError as exc:
                result["ambiguous"].append({"bank_payment_id": bp.id, "reason": str(exc)})
    return result


# ---------------------------------------------------------------------------
# 3. Авансовые
# ---------------------------------------------------------------------------

async def _employee_inn(db: AsyncSession, user: User) -> Optional[str]:
    """ИНН сотрудника для сопоставления авансового платежа. Правка 05.10.2026:
    на живой выгрузке (прод + локальная копия) payee_name у ВСЕХ строк пустой
    — дефект разбора двухстрочной шапки (чинится отдельно, см. сообщение
    координатора; payment parser/bank_payment_dedup.py здесь не трогаем) —
    поэтому ИНН первичен, ФИО (ниже, в match_advance) — запасной признак,
    когда payee_name всё же заполнен.

    Источники, по приоритету:
      1. users.inn, если проставлен (источник истины для сотрудника);
      2. payee_inn уже привязанных РАНЕЕ платежей этого сотрудника (другая
         его авансовая закупка, где платёж уже нашёлся и у строки есть ИНН)."""
    if user.inn:
        return user.inn
    rows = (await db.execute(
        select(BankPayment.payee_inn)
        .join(Payment, Payment.bank_payment_id == BankPayment.id)
        .join(Purchase, Purchase.id == Payment.purchase_id)
        .where(
            Purchase.reimbursement_user_id == user.id,
            Purchase.purchase_method == "advance",
            BankPayment.payee_inn.isnot(None),
        )
    )).scalars().all()
    for inn in rows:
        if inn:
            return inn
    return None


async def match_advance(
    db: AsyncSession, groups_with_purchase: list[tuple[PaymentGroup, Purchase]], dry_run: bool = False,
) -> dict:
    """groups_with_purchase — пары (группа, её авансовая закупка с
    reimbursement_user_id). Получатель платежа — СОТРУДНИК, не контрагент
    закупки, но живая выгрузка 05.10.2026 приходит с пустым payee_name (см.
    _employee_inn выше) — поэтому первичный признак ИНН сотрудника
    (users.inn либо ИНН из уже привязанных авансовых платежей этого же
    сотрудника), ФИО (normalize_person_name) — запасной, только когда
    payee_name у строки реально заполнен. Сначала точное попадание 1 платёж =
    1 закупка; остаток (несколько закупок одного сотрудника против одного
    платежа «Авансовый отчёт N») — subset-sum, как в match_framework."""
    result: dict = {"attached": [], "ambiguous": []}
    by_user: dict[tuple, list[tuple[PaymentGroup, Decimal]]] = {}
    for g, purchase in groups_with_purchase:
        if purchase.purchase_method != "advance" or not purchase.reimbursement_user_id or g.subsidy_id is None:
            continue
        rem = _group_remaining(g)
        if rem <= AMOUNT_TOL:
            continue
        by_user.setdefault((g.subsidy_id, purchase.reimbursement_user_id), []).append((g, rem))

    for (subsidy_id, user_id), remainders in by_user.items():
        subsidy = await db.get(Subsidy, subsidy_id)
        user = await db.get(User, user_id)
        if subsidy is None or user is None:
            continue

        employee_inn = await _employee_inn(db, user)
        name_norm = normalize_person_name(user.full_name) if user.full_name else ""

        all_purchase_ids = [pid for g, _ in remainders for pid in g.purchase_ids]
        if employee_inn:
            candidates = await _executed_candidates(db, subsidy, payee_inn=employee_inn)
        elif name_norm:
            candidates = await _executed_candidates(db, subsidy, payee_name_norm=name_norm)
        else:
            continue
        candidates = await _free_candidates(db, candidates, subsidy_id, all_purchase_ids)
        if not candidates:
            continue
        candidates.sort(key=lambda bp: (bp.payment_date or _date.min, bp.id))

        used_bp_ids: set[int] = set()
        open_remainders = list(remainders)

        # точное попадание: 1 платёж == 1 закупка
        for g, rem in list(open_remainders):
            exact = [
                bp for bp in candidates
                if bp.id not in used_bp_ids and abs(Decimal(str(bp.amount)) - rem) <= AMOUNT_TOL
            ]
            if len(exact) != 1:
                continue
            bp = exact[0]
            if dry_run:
                result["attached"].append({
                    "group_key": g.group_key, "bank_payment_id": bp.id,
                    "amount": float(rem), "case": "advance_exact",
                })
            else:
                try:
                    created = await attach(db, g, [bp.id])
                    result["attached"].append({
                        "group_key": g.group_key, "bank_payment_id": bp.id,
                        "payment_ids": [p.id for p in created], "case": "advance_exact",
                    })
                except PaymentAttachError as exc:
                    result["ambiguous"].append({"group_key": g.group_key, "reason": str(exc)})
                    continue
            used_bp_ids.add(bp.id)
            open_remainders = [pair for pair in open_remainders if pair[0].group_key != g.group_key]

        # один платёж «Авансовый отчёт N» на несколько закупок этого сотрудника
        pool = [bp for bp in candidates if bp.id not in used_bp_ids]
        for bp in pool:
            if len(open_remainders) < 2:
                break
            amt = Decimal(str(bp.amount))
            subset = _subset_sum_unique(open_remainders, lambda pair: pair[1], amt)
            if not subset or len(subset) < 2:
                continue
            alloc: dict[int, Decimal] = {}
            allocated = Decimal(0)
            for i, (g, rem) in enumerate(subset):
                pid = g.purchase_ids[0]
                share = rem if i < len(subset) - 1 else (amt - allocated)
                alloc[pid] = share
                allocated += share if i < len(subset) - 1 else Decimal(0)
            group_keys = [g.group_key for g, _ in subset]
            if dry_run:
                result["attached"].append({
                    "bank_payment_id": bp.id, "group_keys": group_keys,
                    "amount": float(amt), "case": "advance_multi",
                })
                used_bp_ids.add(bp.id)
                open_remainders = [pair for pair in open_remainders if pair[0].group_key not in group_keys]
                continue
            try:
                created = await attach(db, subset[0][0], [bp.id], allocations=alloc)
                used_bp_ids.add(bp.id)
                open_remainders = [pair for pair in open_remainders if pair[0].group_key not in group_keys]
                result["attached"].append({
                    "bank_payment_id": bp.id, "group_keys": group_keys,
                    "payment_ids": [p.id for p in created], "case": "advance_multi",
                })
            except PaymentAttachError as exc:
                result["ambiguous"].append({"bank_payment_id": bp.id, "reason": str(exc)})
    return result
