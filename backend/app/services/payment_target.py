"""Третья очередь утверждённого плана (`synchronous-knitting-thacker.md`), Этап 4 —
суммы группы оплаты и чистка данных под неё.

Группа оплаты собирается из закупок (Purchase) одной субсидии:
  - рамочный договор (purchase_contract_type in FRAMEWORK_TYPES) → ключ
    (contract_number, registry_number);
  - разовый / авансовый (всё остальное) → ключ (registry_number,).
На группу считаются ДВЕ суммы — по позициям-товарам и по позициям-услугам/работам
(purchase_items.item_type), просуммированные по ВСЕМ заказам группы. Позиции без
item_type не теряются — идут в unspecified_amount отдельной строкой.

«Рамочный головной» (аналог владельческой формулы «M <> Установка предельной суммы
договора» — закупка, которой ТОЛЬКО фиксируется предельная сумма договора, без
собственных товарных/сервисных позиций) в сумму группы НЕ входит — но не за счёт
отдельного фильтра-исключения: см. докстринг is_framework_head() ниже — на реальных
данных её единственный доступный признак (parent_purchase_id IS NULL) ложно
срабатывает на импортированных закупках С содержимым (проверено на закупке 773 и
11 других). Пустая закупка без единой purchase_items и так даёт нулевую сумму по
обоим типам естественным путём — этого достаточно.

Данные под группировку сейчас не чисты (см. suspicious_groups) — 23 registry_number
повторяются у визуально неотличимых мусорных строк (одинаковая contract_price,
пустой subject, subsidy_id IS NULL). Такие закупки в build_groups не участвуют.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.routers.purchase_budget import FRAMEWORK_TYPES  # {"framework_cumulative", "framework_with_amount"}


@dataclass
class PaymentGroup:
    group_key: str                       # человекочитаемый техн.ключ (для API/лога)
    subsidy_id: int
    registry_number: Optional[str]
    contract_number: Optional[str]       # заполнен только для рамочных
    is_framework: bool
    contractor_id: Optional[int]
    contractor_inn: Optional[str]
    contractor_name: Optional[str]
    goods_amount: Decimal
    services_amount: Decimal
    unspecified_amount: Decimal          # позиции без item_type — не теряем
    purchase_ids: list[int] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)   # уже разнесённые на закупки группы


@dataclass
class SuspiciousGroup:
    registry_number: str
    purchase_ids: list[int]
    row_count: int
    shared_amount: Optional[Decimal]
    reason: str = "похоже на дубликаты, требуется разбор"


def is_framework_head(p: Purchase) -> bool:
    """«Рамочный головной» — та же проверка, что уже используется в
    purchase_transitions.py::pre_transition_hook и purchases.py (contract_price
    recompute guard): рамочный договор без родителя, только фиксирует предельную
    сумму, своих purchase_items не несёт.

    ВАЖНО (проверено на реальных данных 2026-08-19): эта проверка (по
    parent_purchase_id) годится ТОЛЬКО для закупок, созданных через собственный
    флоу приложения «дочерний заказ рамочного» — там parent_purchase_id
    проставляется явно. У ВСЕХ 12 рамочных закупок локальной базы (включая
    закупку 773, purchase_contract_type='framework_with_amount',
    contract_price=47 262,50, 1 позиция) parent_purchase_id пуст, потому что
    это импортированные данные, а импорт эту связь никогда не заполнял — по
    этой проверке ВСЕ 12 ложно определились бы как «пустые головные» и
    полностью выпали бы из группировки, хотя у каждой реально есть
    purchase_items. Поэтому build_groups эту функцию НЕ использует как фильтр:
    закупка без единой позиции и так даёт нулевую сумму по обоим типам
    естественным образом (см. build_groups) — исключать её явно незачем,
    а для данных, где parent_purchase_id реально проставлен, она безопасно
    ничего не меняет. Функция оставлена для консистентности с остальным кодом
    (может понадобиться, если бэкенд начнёт сам создавать «пустые головные»)."""
    return (
        p.purchase_contract_type in FRAMEWORK_TYPES
        and p.parent_purchase_id is None
    )


def _group_key_for(p: Purchase) -> Optional[tuple]:
    """Ключ группировки (план, раздел «Целевая модель»): рамочный → номер
    договора + реестровый номер; разовый/авансовый — только реестровый номер.
    Без registry_number группировать нечем — такая закупка не должна молча
    потеряться, поэтому ей позже присваивается собственный «orphan»-ключ."""
    reg = (p.registry_number or "").strip()
    if not reg:
        return None
    if p.purchase_contract_type in FRAMEWORK_TYPES:
        contract = (p.contract_number or "").strip()
        return ("framework", contract, reg)
    return ("single", reg)


async def _suspicious_registry_numbers(
    db: AsyncSession, subsidy_id: Optional[int] = None,
) -> dict[str, list[Purchase]]:
    """registry_number, повторяющийся у ≥2 закупок, где строки неотличимы:
    одна и та же (не NULL) contract_price, пустой subject, subsidy_id IS NULL.

    Критерий сверен с реальными данными (2026-08-19): даёт РОВНО 23 группы / 229
    строк из 449 закупок локально, включая registry_number='11' (88 строк,
    contract_price=229 951,68 у каждой). Проверка идёт по группе в целом, а не
    построчно по каждому полю — у части строк группы contract_number всё же
    заполнен (напр. «СЧЕТ 107056/КОР»), но группа остаётся неотличимой по
    сумме/предмету/субсидии, что и роднит её с остальными дублями."""
    q = select(Purchase).where(
        Purchase.registry_number.isnot(None),
        Purchase.registry_number != "",
    )
    if subsidy_id is not None:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    rows = (await db.execute(q)).scalars().all()

    by_reg: dict[str, list[Purchase]] = {}
    for p in rows:
        by_reg.setdefault(p.registry_number, []).append(p)

    suspicious: dict[str, list[Purchase]] = {}
    for reg, purchases in by_reg.items():
        if len(purchases) < 2:
            continue
        prices = {p.contract_price for p in purchases}
        if len(prices) != 1 or None in prices:
            continue
        if any((p.subject or "").strip() for p in purchases):
            continue
        if any(p.subsidy_id is not None for p in purchases):
            continue
        suspicious[reg] = purchases
    return suspicious


async def suspicious_groups(
    db: AsyncSession, subsidy_id: Optional[int] = None,
) -> list[SuspiciousGroup]:
    """Отчёт «подозрительные группы» — дубли по registry_number, требующие
    ручного разбора ДО того, как их закупки смогут участвовать в сопоставлении
    платежей (см. build_groups, которая эти закупки полностью исключает)."""
    raw = await _suspicious_registry_numbers(db, subsidy_id=subsidy_id)
    out = []
    for reg, plist in raw.items():
        amt = plist[0].contract_price
        out.append(SuspiciousGroup(
            registry_number=reg,
            purchase_ids=[p.id for p in plist],
            row_count=len(plist),
            shared_amount=Decimal(str(amt)) if amt is not None else None,
        ))
    out.sort(key=lambda g: -g.row_count)
    return out


async def build_groups(db: AsyncSession, subsidy_id: int) -> list[PaymentGroup]:
    """Группы оплаты по закупкам одной субсидии — см. докстринг модуля."""
    purchases = (
        await db.execute(select(Purchase).where(Purchase.subsidy_id == subsidy_id))
    ).scalars().all()
    if not purchases:
        return []

    suspicious = await _suspicious_registry_numbers(db, subsidy_id=subsidy_id)
    suspicious_ids = {p.id for plist in suspicious.values() for p in plist}

    groups: dict[tuple, list[Purchase]] = {}
    for p in purchases:
        if p.id in suspicious_ids:
            continue
        # is_framework_head() НЕ применяется как фильтр здесь — см. её докстринг:
        # на реальных (импортированных) данных она ложно исключает закупки с
        # содержимым. Пустая закупка и так даёт нулевую сумму естественным путём.
        key = _group_key_for(p) or ("orphan", f"purchase:{p.id}")
        groups.setdefault(key, []).append(p)

    if not groups:
        return []

    purchase_ids_all = [p.id for plist in groups.values() for p in plist]

    items = (
        await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids_all)))
    ).scalars().all()
    items_by_purchase: dict[int, list[PurchaseItem]] = {}
    for it in items:
        items_by_purchase.setdefault(it.purchase_id, []).append(it)

    payments = (
        await db.execute(
            select(Payment).where(
                Payment.purchase_id.in_(purchase_ids_all),
                Payment.matched_confirmed == True,  # noqa: E712
            )
        )
    ).scalars().all()
    payments_by_purchase: dict[int, list[Payment]] = {}
    for pay in payments:
        payments_by_purchase.setdefault(pay.purchase_id, []).append(pay)

    contractor_ids = {p.contractor_id for plist in groups.values() for p in plist if p.contractor_id}
    contractors: dict[int, Contractor] = {}
    if contractor_ids:
        c_rows = (
            await db.execute(select(Contractor).where(Contractor.id.in_(contractor_ids)))
        ).scalars().all()
        contractors = {c.id: c for c in c_rows}

    result: list[PaymentGroup] = []
    for key, plist in groups.items():
        goods = Decimal(0)
        services = Decimal(0)
        unspecified = Decimal(0)
        for p in plist:
            for it in items_by_purchase.get(p.id, []):
                amt = Decimal(str(it.total_price)) if it.total_price is not None else Decimal(0)
                kind = (it.item_type or "").strip()
                if kind == "товар":
                    goods += amt
                elif kind in ("услуга", "работа"):
                    services += amt
                else:
                    unspecified += amt

        is_fw = key[0] == "framework"
        first = plist[0]
        contractor_id = next((p.contractor_id for p in plist if p.contractor_id), None)
        contractor = contractors.get(contractor_id) if contractor_id else None

        group_payments: list[Payment] = []
        for p in plist:
            group_payments.extend(payments_by_purchase.get(p.id, []))

        result.append(PaymentGroup(
            group_key="|".join(str(k) for k in key),
            subsidy_id=subsidy_id,
            registry_number=first.registry_number,
            contract_number=first.contract_number if is_fw else None,
            is_framework=is_fw,
            contractor_id=contractor_id,
            contractor_inn=contractor.inn if contractor else None,
            contractor_name=contractor.name if contractor else None,
            goods_amount=goods,
            services_amount=services,
            unspecified_amount=unspecified,
            purchase_ids=[p.id for p in plist],
            payments=group_payments,
        ))

    result.sort(key=lambda g: (g.registry_number or "", g.group_key))
    return result


async def find_group(db: AsyncSession, subsidy_id: int, group_key: str) -> Optional[PaymentGroup]:
    """Найти одну группу по её group_key (см. build_groups) — используется API
    /payment-candidates и /attach-payments, чтобы не пересобирать список групп
    на клиенте."""
    for g in await build_groups(db, subsidy_id):
        if g.group_key == group_key:
            return g
    return None
