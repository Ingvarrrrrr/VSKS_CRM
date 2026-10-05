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
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.subsidy import Subsidy
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
    """Contractor с уникальным на прогон ИНН (contractors.inn уникален в общей БД —
    фиксированный '2315176820' коллизирует с накопленными за прошлые прогоны
    строками и падает UniqueViolationError; см. отчёт по долгу тестов)."""
    c = Contractor(
        name=f"ТестКонтрагент-{_uid()}",
        inn=f"77{uuid.uuid4().int % 10**8:08d}",
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
async def bank_payment(db_session, import_run, contractor):
    """BankPayment без матча (payee_inn = ИНН тестового contractor, чтобы
    auto_match находил именно его; parsed_contract_number выставлен)."""
    bp = BankPayment(
        import_id=import_run.id,
        payment_number=f"ПП-{_uid()}",
        payee_inn=contractor.inn,
        parsed_contract_number="11-26-1",
        amount=Decimal("100000.00"),
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)
    return bp


@pytest_asyncio.fixture
async def subsidy(db_session):
    """Субсидия нужна, чтобы recompute_purchase_payments заводил
    PurchasePaidConfirmation (план 2026-10-04-fadm-statement, п.3) —
    _request_paid_confirmation без subsidy_id на закупке молча выходит
    (некого спрашивать), см. app/services/purchase_payments.py."""
    s = Subsidy(name=f"ТестСубсидия-{_uid()}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture
async def purchase_delivered(db_session, contract, subsidy):
    """Purchase в статусе delivered с contract_price=100000."""
    p = Purchase(
        item_name=f"Товар-{_uid()}",
        status="delivered",
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        contract_price=Decimal("100000.00"),
        subsidy_id=subsidy.id,
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
    """После auto_match bp.matched_contractor_id должен стать равен contractor.id.

    auto_match(bp, db) заполняет bp in-place и не возвращает dict (сигнатура
    была изменена, тест раньше вызывал auto_match(db_session, bank_payment) с
    перепутанным порядком аргументов и читал несуществующий result[...] —
    см. app/services/payment_matcher.py:111 и реальные вызовы в
    app/routers/bank_statements_imports.py:196)."""
    await auto_match(bank_payment, db_session)
    assert bank_payment.matched_contractor_id == contractor.id


# ---------------------------------------------------------------------------
# Test 2 — auto_match: contract by number + contractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_match_contract_by_number(db_session, contractor, contract, bank_payment):
    """После auto_match bp.matched_contract_id должен быть != None.

    Тот же порядок аргументов/return-dict fix, что и в test_auto_match_by_inn
    выше (одинаковый устаревший вызов auto_match)."""
    await auto_match(bank_payment, db_session)
    assert bank_payment.matched_contract_id == contract.id


# ---------------------------------------------------------------------------
# Test 3 — recompute aggregates: полная сумма «подтверждено выпиской» → запрос
# подтверждения «Оплачено» (план 2026-10-04-fadm-statement, п.3), НЕ auto-paid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_full_payment_requests_paid_confirmation(db_session, contract, purchase_delivered):
    """2 Payment по 60k и 40k, «подтверждено выпиской»
    (payment_source='statement', confirmed_by_statement=True) →
    payment_amount=100k, статус ОСТАЁТСЯ 'delivered' (владелец, 04.10.2026:
    «нашлась закупка в выгрузке → в Оплаченные, но с уведомлением и
    согласованием»), вместо молчаливого paid заводится pending
    PurchasePaidConfirmation на сумму payment_amount — перевод в paid только
    через app/routers/purchase_paid_confirmations.py::confirm.

    Двухступенчатая модель оплаты (решение владельца 19.08.2026): в payment_amount
    попадают только платежи, подтверждённые банковской выпиской — см.
    app/services/purchase_payments.py."""
    pay1 = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-001",
        amount=Decimal("60000.00"),
        matched_confirmed=True,
        payment_source="statement",
        confirmed_by_statement=True,
    )
    pay2 = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-002",
        amount=Decimal("40000.00"),
        matched_confirmed=True,
        payment_source="statement",
        confirmed_by_statement=True,
    )
    db_session.add_all([pay1, pay2])
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, purchase_delivered.id)
    assert updated.payment_amount == Decimal("100000.00")
    assert updated.status == "delivered"

    confirmation = (await db_session.execute(
        select(PurchasePaidConfirmation).where(
            PurchasePaidConfirmation.purchase_id == purchase_delivered.id,
        )
    )).scalar_one()
    assert confirmation.status == "pending"
    assert confirmation.subsidy_id == purchase_delivered.subsidy_id
    assert confirmation.amount_confirmed == Decimal("100000.00")

    # Повторный recompute (например, после ещё одного пересчёта тем же прогоном)
    # не плодит вторую pending-запись на ту же закупку.
    await recompute_purchase_payments(db_session, purchase_delivered.id)
    count = (await db_session.execute(
        select(PurchasePaidConfirmation).where(
            PurchasePaidConfirmation.purchase_id == purchase_delivered.id,
        )
    )).scalars().all()
    assert len(count) == 1


# ---------------------------------------------------------------------------
# Test 4 — частичная сумма «подтверждено выпиской» НЕ переводит в paid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_partial_stays_delivered(db_session, contract, purchase_delivered):
    """1 Payment 60k, «подтверждено выпиской», при contract_price=100k →
    payment_amount=60k, status остаётся 'delivered' (порог не достигнут)."""
    pay = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-003",
        amount=Decimal("60000.00"),
        matched_confirmed=True,
        payment_source="statement",
        confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, purchase_delivered.id)
    assert updated.payment_amount == Decimal("60000.00")
    assert updated.status == "delivered"


# ---------------------------------------------------------------------------
# Test 4.1 — «оплачено по отметке» (без выписки) не закрывает закупку
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_marked_only_does_not_close(db_session, contract, purchase_delivered):
    """1 Payment 100k, «оплачено по отметке» (payment_source='manual',
    confirmed_by_statement=False) → уходит в payment_amount_declared («заявлено,
    ждёт подтверждения»), payment_amount остаётся None, status НЕ меняется —
    закупку закрывает только «подтверждено выпиской»."""
    pay = Payment(
        contract_id=contract.id,
        purchase_id=purchase_delivered.id,
        document_number="ПП-004",
        amount=Decimal("100000.00"),
        matched_confirmed=True,
        payment_source="manual",
        confirmed_by_statement=False,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, purchase_delivered.id)
    assert updated.payment_amount_declared == Decimal("100000.00")
    assert updated.payment_amount is None
    assert updated.status == "delivered"


# ---------------------------------------------------------------------------
# Test 5 — create_payments_from_bank: equal split between 2 purchases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_payments_split(db_session, contract, import_run, subsidy):
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
        subsidy_id=subsidy.id,
    )
    p2 = Purchase(
        item_name=f"Товар-Б-{_uid()}",
        status="delivered",
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        contract_price=Decimal("50000.00"),
        subsidy_id=subsidy.id,
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

    # План 2026-10-04-fadm-statement, п.3: обе закупки ОСТАЮТСЯ 'delivered' —
    # 50k >= contract_price 50k заводит pending PurchasePaidConfirmation на
    # КАЖДУЮ, не переводит в paid молча.
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.status == "delivered"
    assert p2.status == "delivered"

    for pid in (p1.id, p2.id):
        confirmation = (await db_session.execute(
            select(PurchasePaidConfirmation).where(
                PurchasePaidConfirmation.purchase_id == pid,
            )
        )).scalar_one()
        assert confirmation.status == "pending"
        assert confirmation.amount_confirmed == Decimal("50000.00")
