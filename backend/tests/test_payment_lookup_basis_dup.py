"""Задача 2026-10-05 («разбор сверки ФАДМ 2026_2», п.1) — дубль назначения
(basis_key) НЕ должен блокировать привязку ДРУГОЙ строки выписки с тем же
текстом назначения; единственный признак занятости — bank_payment_id (та же
строка), см. app/services/payment_lookup.py::attach docstring.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_lookup import attach
from app.services.payment_target import build_groups


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _status() -> str:
    return next(iter(EXECUTED_STATUSES))


async def _subsidy(db_session):
    s = Subsidy(name=f"Субсидия-{_uid()}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _contractor(db_session):
    c = Contractor(name=f"Контрагент-{_uid()}", inn=f"77{uuid.uuid4().int % 10**8:08d}")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.mark.asyncio
async def test_same_purpose_text_different_rows_both_attach_to_different_orders(db_session, test_org):
    """Текстиль М, п/п 297 / п/п 379 (прод-пример) — одинаковый текст назначения
    («Договор 26-03 от 26.03.2026, УПД 48 от 16.04.2026»), РАЗНЫЕ строки выписки,
    РАЗНЫЕ заказы одного рамочного договора. Раньше _used_basis_index блокировал
    вторую по тексту (basis_key), хотя они — разные заказы (разные purchase_id)
    одной группы. Теперь обе должны привязаться."""
    subsidy = await _subsidy(db_session)
    contractor = await _contractor(db_session)
    status = _status()
    contract_number = f"26-03-{_uid()}"
    registry_number = f"REG-{_uid()}"  # один registry_number -> один PaymentGroup

    order1 = Purchase(
        item_name="Заказ 2", status="delivered", contractor_id=contractor.id,
        subsidy_id=subsidy.id, registry_number=registry_number,
        contract_number=contract_number, purchase_contract_type="framework_with_amount",
    )
    order2 = Purchase(
        item_name="Заказ 3", status="delivered", contractor_id=contractor.id,
        subsidy_id=subsidy.id, registry_number=registry_number,
        contract_number=contract_number, purchase_contract_type="framework_with_amount",
    )
    db_session.add_all([order1, order2])
    await db_session.commit()
    for p in (order1, order2):
        await db_session.refresh(p)

    db_session.add_all([
        PurchaseItem(purchase_id=order1.id, item_name="Товар", item_type="товар",
                     quantity=1, unit_price=Decimal("72840.00"), total_price=Decimal("72840.00")),
        PurchaseItem(purchase_id=order2.id, item_name="Товар", item_type="товар",
                     quantity=1, unit_price=Decimal("1167160.00"), total_price=Decimal("1167160.00")),
    ])
    await db_session.commit()

    purpose = "Договор 26-03 от 26.03.2026, УПД 48 от 16.04.2026"
    bp1 = BankPayment(
        payee_inn=contractor.inn, amount=Decimal("72840.00"), status=status,
        payment_number="297", payment_date=date(2026, 4, 20), purpose_text=purpose,
        subsidy_id=subsidy.id,
    )
    bp2 = BankPayment(
        payee_inn=contractor.inn, amount=Decimal("1167160.00"), status=status,
        payment_number="379", payment_date=date(2026, 4, 25), purpose_text=purpose,
        subsidy_id=subsidy.id,
    )
    db_session.add_all([bp1, bp2])
    await db_session.commit()
    for bp in (bp1, bp2):
        await db_session.refresh(bp)

    groups = await build_groups(db_session, subsidy.id)
    group = next(g for g in groups if order1.id in g.purchase_ids and order2.id in g.purchase_ids)

    # allocations явно указывает, какому заказу группы принадлежит платёж —
    # без него attach() распределил бы сумму пропорционально МЕЖДУ ОБОИМИ
    # заказами группы (это не тестируемое здесь поведение, см. attach()
    # docstring про allocations).
    created1 = await attach(db_session, group, [bp1.id], allocations={order1.id: Decimal("72840.00")})
    await db_session.commit()
    assert len(created1) == 1
    assert created1[0].purchase_id == order1.id

    # Раньше здесь падало PaymentAttachError («назначение уже использовано»).
    created2 = await attach(db_session, group, [bp2.id], allocations={order2.id: Decimal("1167160.00")})
    await db_session.commit()
    assert len(created2) == 1
    assert created2[0].purchase_id == order2.id

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id.in_([order1.id, order2.id]))
    )).scalars().all()
    assert len(payments) == 2
    assert {p.bank_payment_id for p in payments} == {bp1.id, bp2.id}
