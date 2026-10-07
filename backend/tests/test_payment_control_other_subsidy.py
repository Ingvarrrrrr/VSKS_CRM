"""Строка выписки, уже «пойманная» закупкой ДРУГОЙ субсидии с тем же номером
соглашения, не должна считаться «без закупки» у первой субсидии — инцидент
06.10.2026 (ФАДМ 2026_2/id 89 и ФАДМ_2026/id 7, общий agreement_number)."""
import uuid
from decimal import Decimal

import pytest

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.subsidy_payment_control import build_payment_control


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _make_subsidy(db_session, org_id, agreement_number):
    s = Subsidy(
        name=f"ФАДМ-{_uid()}", year=2026, require_planned_dates=False,
        org_id=org_id, agreement_number=agreement_number,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_contractor(db_session):
    c = Contractor(name=f"Контрагент-{_uid()}", inn=f"77{uuid.uuid4().int % 10**8:08d}")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.mark.asyncio
async def test_row_caught_by_other_subsidy_purchase_not_registry_only(db_session, test_org):
    agreement = f"АГР-ДРУГАЯ-{_uid()}"
    sub1 = await _make_subsidy(db_session, test_org.id, agreement_number=agreement)
    sub2 = await _make_subsidy(db_session, test_org.id, agreement_number=agreement)
    contractor = await _make_contractor(db_session)

    bp = BankPayment(
        payment_number=f"ПП-{_uid()}",
        amount=Decimal("1000.00"),
        status="ИСПОЛНЕН",
        purpose_text=f"Оплата по Соглашению № {agreement} от 28.01.2026 за товар",
        payment_date=__import__("datetime").date(2026, 5, 1),
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    # Закупка и Payment — у ВТОРОЙ субсидии, ссылается на ту же строку выписки.
    purchase2 = Purchase(
        subsidy_id=sub2.id, contractor_id=contractor.id,
        contract_price=Decimal("1000.00"), status="paid",
    )
    db_session.add(purchase2)
    await db_session.commit()
    await db_session.refresh(purchase2)

    payment2 = Payment(
        purchase_id=purchase2.id, amount=Decimal("1000.00"),
        bank_payment_id=bp.id, confirmed_by_statement=True,
        payment_source="manual",
    )
    db_session.add(payment2)
    await db_session.commit()

    result1 = await build_payment_control(db_session, sub1)
    assert result1["counts"]["registry_only"] == 0
    assert result1["alarm"] is False
    assert abs(result1["totals"]["difference"]) < 0.01
    assert result1["totals"]["in_other_subsidies_count"] == 1
    assert abs(result1["totals"]["in_other_subsidies_total"] - 1000.0) < 0.01
    assert len(result1["other_subsidies"]) == 1
    assert result1["other_subsidies"][0]["id"] == sub2.id
    assert result1["other_subsidies"][0]["name"] == sub2.name
    row1 = next(r for r in result1["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row1["status"] == "in_other_subsidy"
    assert row1["other_subsidy"]["id"] == sub2.id

    result2 = await build_payment_control(db_session, sub2)
    row2 = next(r for r in result2["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row2["status"] == "match"
    assert result2["counts"]["match"] == 1


@pytest.mark.asyncio
async def test_not_reconciled_code_with_other_subsidy_payment_stays_not_reconciled(db_session, test_org):
    """Строка с кодом, который эта субсидия НЕ ищет среди закупок
    (search_purchase=False → not_reconciled), но у которой платёж всё же есть
    у закупки ДРУГОЙ субсидии — не должна попадать в other_subsidies/
    in_other_subsidies_total: там её и не было в reconciled_total, вычитание
    увело бы difference в минус и включило alarm (баг, исправлено 06.10)."""
    agreement = f"АГР-НЕСВЕРЯЕТСЯ-{_uid()}"
    sub1 = await _make_subsidy(db_session, test_org.id, agreement_number=agreement)
    sub2 = await _make_subsidy(db_session, test_org.id, agreement_number=agreement)
    contractor = await _make_contractor(db_session)

    bp = BankPayment(
        payment_number=f"ПП-{_uid()}",
        amount=Decimal("500.00"),
        status="ИСПОЛНЕН",
        purpose_text=f"Оплата по Соглашению № {agreement} от 28.01.2026 за прочее",
        payment_date=__import__("datetime").date(2026, 5, 1),
        expense_code="0810004",  # известный код, is_procurement=false → не ищется
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    purchase2 = Purchase(
        subsidy_id=sub2.id, contractor_id=contractor.id,
        contract_price=Decimal("500.00"), status="paid",
    )
    db_session.add(purchase2)
    await db_session.commit()
    await db_session.refresh(purchase2)

    payment2 = Payment(
        purchase_id=purchase2.id, amount=Decimal("500.00"),
        bank_payment_id=bp.id, confirmed_by_statement=True,
        payment_source="manual",
    )
    db_session.add(payment2)
    await db_session.commit()

    result1 = await build_payment_control(db_session, sub1)
    row1 = next(r for r in result1["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row1["status"] == "not_reconciled"
    assert result1["totals"]["in_other_subsidies_count"] == 0
    assert result1["totals"]["in_other_subsidies_total"] == 0.0
    assert result1["other_subsidies"] == []
    assert abs(result1["totals"]["difference"]) < 0.01
    assert result1["alarm"] is False
