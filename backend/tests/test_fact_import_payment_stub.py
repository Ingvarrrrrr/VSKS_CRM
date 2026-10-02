"""find_manual_match подтверждает заглушку «Импорта факта» (без номера и
даты документа) по сумме, не заводя вторую запись при загрузке выписки.
Частичное совпадение — уменьшает заглушку, а не задваивает (план
breezy-mixing-lovelace.md часть 3, п.2)."""
import uuid
from decimal import Decimal

from app.models.subsidy import Subsidy
from app.models.purchase import Purchase
from app.models.payment import Payment
from app.models.fact_import_run import FactImportRun
from app.services.purchase_payments import find_manual_match, create_payments_from_bank


async def _make_purchase_with_stub(db_session, test_org, stub_amount):
    subsidy = Subsidy(name=f"Stub-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    run = FactImportRun(subsidy_id=subsidy.id, filename="t.xlsx", status="committed")
    db_session.add(run)
    await db_session.flush()
    purchase = Purchase(subsidy_id=subsidy.id, status="paid")
    db_session.add(purchase)
    await db_session.flush()
    stub = Payment(
        purchase_id=purchase.id, amount=stub_amount, payment_source="manual",
        confirmed_by_statement=False, import_run_id=run.id,
        document_number=None, payment_date=None,
    )
    db_session.add(stub)
    await db_session.commit()
    return purchase, stub


async def test_find_manual_match_confirms_import_stub_by_amount(db_session, test_org):
    purchase, stub = await _make_purchase_with_stub(db_session, test_org, Decimal("50000"))
    match = await find_manual_match(db_session, purchase.id, "б/н", None, Decimal("50000"))
    assert match is not None
    assert match.id == stub.id


async def test_create_payments_from_bank_confirms_stub_without_duplicate(db_session, test_org):
    from app.models.bank_statement import BankPayment

    purchase, stub = await _make_purchase_with_stub(db_session, test_org, Decimal("50000"))

    bp = BankPayment(
        import_id=None, payment_number="", payment_date=None,
        amount=Decimal("50000"), purpose_text="оплата по закупке",
        matched_contract_id=None,
    )
    db_session.add(bp)
    await db_session.commit()

    created = await create_payments_from_bank(db_session, bp.id, [purchase.id])
    assert len(created) == 1
    assert created[0].id == stub.id

    from sqlalchemy import select
    all_payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(all_payments) == 1
    assert all_payments[0].confirmed_by_statement is True
    assert float(all_payments[0].amount) == 50000


async def test_create_payments_from_bank_partial_reduces_stub(db_session, test_org):
    from app.models.bank_statement import BankPayment
    from sqlalchemy import select

    purchase, stub = await _make_purchase_with_stub(db_session, test_org, Decimal("50000"))

    bp = BankPayment(
        import_id=None, payment_number="", payment_date=None,
        amount=Decimal("20000"), purpose_text="частичная оплата",
        matched_contract_id=None,
    )
    db_session.add(bp)
    await db_session.commit()

    created = await create_payments_from_bank(db_session, bp.id, [purchase.id])
    assert len(created) == 1

    all_payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(all_payments) == 2  # заглушка (уменьшенная) + новая подтверждённая
    confirmed = [p for p in all_payments if p.confirmed_by_statement]
    unconfirmed = [p for p in all_payments if not p.confirmed_by_statement]
    assert len(confirmed) == 1 and float(confirmed[0].amount) == 20000
    assert len(unconfirmed) == 1 and float(unconfirmed[0].amount) == 30000
