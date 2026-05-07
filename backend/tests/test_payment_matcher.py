"""Phase 22 Plan 03 — unit tests for payment_matcher and purchase_payments services.

Tests use a real AsyncSession connected to the app database (same pattern as
test_wish_approve_distribution). Data is committed so cross-session reads work.

Run with: pytest backend/tests/test_payment_matcher.py -v
NOTE: requires a running PostgreSQL configured via DATABASE_URL env var.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.bank_statement import BankPayment, BankStatementImport
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.services.payment_matcher import auto_match, match_all_in_import
from app.services.purchase_payments import (
    create_payments_from_bank,
    recompute_purchase_payments,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Fixtures — reuse db_session from conftest.py
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def contractor(db_session):
    """Contractor с фиксированным ИНН 2315176820."""
    c = Contractor(
        name=f"ТестКонтрагент-{_uid()}",
        inn="2315176820",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def contract(db_session, contractor):
    """Contract с номером '11-26-1', привязан к contractor."""
    ct = Contract(
        number="11-26-1",
        contract_type="single",
        contractor_id=contractor.id,
    )
    db_session.add(ct)
    await db_session.commit()
    await db_session.refresh(ct)
    return ct


@pytest_asyncio.fixture
async def import_run(db_session):
    """BankStatementImport — нужен для BankPayment.import_id FK."""
    imp = BankStatementImport(
        file_name=f"test_{_uid()}.xlsx",
        sheet_name="Лист1",
    )
    db_session.add(imp)
    await db_session.commit()
    await db_session.refresh(imp)
    return imp


@pytest_asyncio.fixture
async def bank_payment(db_session, import_run):
    """BankPayment без матча (payee_inn + parsed_contract_number выставлены)."""
    bp = BankPayment(
        import_id=import_run.id,
        payment_number=f"ПП-{_uid()}",
        payee_inn="2315176820",
        parsed_contract_number="11-26-1",
        amount=Decimal("100000.00"),
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)
    return bp


@pytest_asyncio.fixture
async def purchase_delivered(db_session, contract):
    """Purchase в статусе delivered с contract_price=100000."""
    p = Purchase(
        item_name=f"Товар-{_uid()}",
        status="delivered",
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        contract_price=Decimal("100000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Test 1 — auto_match: contractor by INN exact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_match_by_inn(db_session, contractor, bank_payment):
    """После auto_match bp.matched_contractor_id должен стать равен contractor.id."""
    result = await auto_match(db_session, bank_payment)
    assert result["contractor"] is not None
    assert bank_payment.matched_contractor_id == contractor.id


# ---------------------------------------------------------------------------
# Test 2 — auto_match: contract by number + contractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_match_contract_by_number(db_session, contractor, contract, bank_payment):
    """После auto_match bp.matched_contract_id должен быть != None."""
    result = await auto_match(db_session, bank_payment)
    assert result["contract"] is not None
    assert bank_payment.matched_contract_id == contract.id


# ---------------------------------------------------------------------------
# Test 3 — recompute aggregates: full payment → auto-paid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_full_payment_becomes_paid(db_session, contract, purchase_delivered):
    """2 Payment по 60k и 40k с matched_confirmed=true → status='paid', payment_amount=100k."""
    pay1 = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-001",
        amount=Decimal("60000.00"),
        matched_confirmed=True,
    )
    pay2 = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-002",
        amount=Decimal("40000.00"),
        matched_confirmed=True,
    )
    db_session.add_all([pay1, pay2])
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, purchase_delivered.id)
    assert updated.payment_amount == Decimal("100000.00")
    assert updated.status == "paid"


# ---------------------------------------------------------------------------
# Test 4 — partial payment does NOT transition to paid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_partial_stays_delivered(db_session, contract, purchase_delivered):
    """1 Payment 60k при contract_price=100k → status остаётся 'delivered'."""
    pay = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-003",
        amount=Decimal("60000.00"),
        matched_confirmed=True,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, purchase_delivered.id)
    assert updated.payment_amount == Decimal("60000.00")
    assert updated.status == "delivered"


# ---------------------------------------------------------------------------
# Test 5 — create_payments_from_bank: equal split between 2 purchases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_payments_split(db_session, contract, import_run):
    """BankPayment(amount=100k) → 2 purchases → 2 Payment по 50k, matched_confirmed=True."""
    bp = BankPayment(
        import_id=import_run.id,
        payment_number=f"ПП-{_uid()}",
        payee_inn="2315176820",
        amount=Decimal("100000.00"),
        matched_contract_id=contract.id,
    )
    db_session.add(bp)

    p1 = Purchase(
        item_name=f"Товар-А-{_uid()}",
        status="delivered",
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        contract_price=Decimal("50000.00"),
    )
    p2 = Purchase(
        item_name=f"Товар-Б-{_uid()}",
        status="delivered",
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        contract_price=Decimal("50000.00"),
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(bp)
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    created = await create_payments_from_bank(
        db_session,
        bank_payment_id=bp.id,
        purchase_ids=[p1.id, p2.id],
    )
    await db_session.commit()

    assert len(created) == 2
    for pay in created:
        assert pay.amount == Decimal("50000.00")
        assert pay.matched_confirmed is True

    # Обе закупки должны перейти в paid (50k >= contract_price 50k)
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.status == "paid"
    assert p2.status == "paid"
