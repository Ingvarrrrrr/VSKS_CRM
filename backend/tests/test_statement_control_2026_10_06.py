"""Тесты плана .planning/quick/2026-10-06-statement-control/PLAN.md (пп.2-6).

Переиспользует фикстуры/хелперы стиля tests/test_subsidy_payment_control.py
(ПРАВИЛО №6 — тот же _make_subsidy/_make_contractor/_bp, второй набор не
заводится)."""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.payment_control_near_miss import build_near_miss
from app.services.payment_lookup import attach
from app.services.payment_target import PaymentGroup
from app.services.purchase_payments import find_manual_match_same_period
from app.services.subsidy_payment_control import build_payment_control
from app.services.subsidy_statement_sheet import build_statement_sheet


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _make_subsidy(db_session, org_id=None, agreement_number=None):
    s = Subsidy(
        name=f"Субсидия-{_uid()}", year=2026, require_planned_dates=False,
        org_id=org_id, agreement_number=agreement_number,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_contractor(db_session, inn=None):
    c = Contractor(name=f"Контрагент-{_uid()}", inn=inn or f"77{uuid.uuid4().int % 10**8:08d}")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _bp(subsidy_id=None, agreement="091-10-2026-008", amount="1000.00", status="ИСПОЛНЕН",
        payee_inn=None, payee_name=None, payment_number=None, expense_code=None, payment_date=None,
        purpose_text=None):
    return BankPayment(
        payment_number=payment_number or f"ПП-{_uid()}",
        payee_inn=payee_inn,
        payee_name=payee_name,
        amount=Decimal(amount),
        status=status,
        purpose_text=purpose_text or f"Оплата по Соглашению № {agreement} от 28.01.2026 за товар",
        subsidy_id=subsidy_id,
        expense_code=expense_code,
        payment_date=payment_date or datetime.date(2026, 5, 1),
    )


# ---------------------------------------------------------------------------
# П.2 — выписка замещает отметку, даже при другой сумме
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_statement_absorbs_manual_mark_different_amount(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-2")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("29700.00"), status="delivered",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    manual = Payment(
        purchase_id=purchase.id, amount=Decimal("25650.00"),
        payment_source="manual", confirmed_by_statement=False,
        document_number="РУЧ-1", payment_date=datetime.date(2026, 4, 1),
    )
    db_session.add(manual)
    await db_session.commit()

    bp = _bp(agreement="СК-2", amount="29700.00", payee_inn=contractor.inn, payee_name=contractor.name)
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    group = PaymentGroup(
        group_key=f"test-{purchase.id}", subsidy_id=sub.id, registry_number=None,
        contract_number=None, is_framework=False, contractor_id=contractor.id,
        contractor_inn=contractor.inn, contractor_name=contractor.name,
        goods_amount=Decimal(0), services_amount=Decimal(0), unspecified_amount=Decimal(0),
        purchase_ids=[purchase.id], payments=[],
    )
    await attach(db_session, group, [bp.id], allocations={purchase.id: Decimal("29700.00")})
    await db_session.commit()

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(payments) == 1, "выписка должна была поглотить отметку, а не завести вторую запись"
    assert payments[0].amount == Decimal("29700.00")
    assert payments[0].confirmed_by_statement is True
    assert payments[0].bank_payment_id == bp.id


@pytest.mark.asyncio
async def test_find_manual_match_same_period_ignores_amount(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-2б")
    purchase = Purchase(subsidy_id=sub.id, contract_price=Decimal("100.00"), status="delivered")
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    manual = Payment(
        purchase_id=purchase.id, amount=Decimal("50.00"),
        payment_source="manual", confirmed_by_statement=False,
    )
    db_session.add(manual)
    await db_session.commit()

    found = await find_manual_match_same_period(db_session, purchase.id, service_period=None)
    assert found is not None
    assert found.id == manual.id


# ---------------------------------------------------------------------------
# П.4 — near_miss: amount_close (Δ 0,08) и same_act
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_near_miss_amount_close(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-4а")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("270.00"), status="delivered",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    hints = await build_near_miss(
        db_session, sub.id, Decimal("270.08"), contractor.inn, "Страхование", set(),
    )
    assert len(hints) == 1
    assert hints[0]["purchase_id"] == purchase.id
    assert hints[0]["reason"] == "amount_close"
    assert round(hints[0]["delta"], 2) == 0.08
    assert hints[0]["can_fix_amount"] is True


@pytest.mark.asyncio
async def test_near_miss_same_act(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-4б")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("5000.00"), status="delivered",
        acceptance_doc_number="УПД-777",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    hints = await build_near_miss(
        db_session, sub.id, Decimal("4200.00"), contractor.inn,
        "Оплата по УПД-777 от 01.04.2026", set(),
    )
    assert len(hints) == 1
    assert hints[0]["reason"] == "same_act"
    assert hints[0]["purchase_id"] == purchase.id


# ---------------------------------------------------------------------------
# registry_only rows в build_payment_control несут near_miss
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payment_control_registry_only_row_has_near_miss(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-row")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("1000.08"), status="delivered",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    bp = _bp(agreement="СК-row", amount="1000.00", payee_inn=contractor.inn, payee_name=contractor.name)
    db_session.add(bp)
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    row = next(r for r in result["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row["status"] == "registry_only"
    assert any(h["reason"] == "amount_close" for h in row["near_miss"])
    assert "sheet_ref" in (row["purchases"][0] if row["purchases"] else {"sheet_ref": None})


# ---------------------------------------------------------------------------
# П.3 — totals: statement_count/attached/unattached
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payment_control_totals_attached_unattached(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-totals")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("500.00"), status="delivered",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    bp_attached = _bp(agreement="СК-totals", amount="500.00", payee_inn=contractor.inn, payment_number="A-1")
    bp_unattached = _bp(agreement="СК-totals", amount="999.00", payment_number="A-2")
    db_session.add_all([bp_attached, bp_unattached])
    await db_session.commit()
    await db_session.refresh(bp_attached)

    pay = Payment(
        purchase_id=purchase.id, amount=Decimal("500.00"),
        payment_source="statement", confirmed_by_statement=True, bank_payment_id=bp_attached.id,
    )
    db_session.add(pay)
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    totals = result["totals"]
    assert totals["statement_count"] == 2
    assert totals["attached_count"] == 1
    assert totals["unattached_count"] == 1
    assert totals["unattached_total"] == 999.0
    assert "A-2" in totals["unattached_numbers"]


# ---------------------------------------------------------------------------
# П.6 — лист «Выписка»: только строки своей субсидии
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_statement_sheet_only_own_subsidy(db_session, test_org):
    sub_a = await _make_subsidy(db_session, test_org.id, agreement_number="СК-6а")
    sub_b = await _make_subsidy(db_session, test_org.id, agreement_number="СК-6б")

    bp_a = _bp(agreement="СК-6а", amount="111.00", payment_number="П-А")
    bp_b = _bp(agreement="СК-6б", amount="222.00", payment_number="П-Б")
    db_session.add_all([bp_a, bp_b])
    await db_session.commit()

    result = await build_statement_sheet(db_session, sub_a)
    numbers = {r["payment_number"] for r in result["rows"]}
    assert "П-А" in numbers
    assert "П-Б" not in numbers


# ---------------------------------------------------------------------------
# Экспорт xlsx
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payment_control_export_returns_xlsx(db_session, test_org):
    from openpyxl import load_workbook
    from app.services.payment_control_export import build_payment_control_xlsx

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-export")
    bp = _bp(agreement="СК-export", amount="100.00")
    db_session.add(bp)
    await db_session.commit()

    data = await build_payment_control(db_session, sub)
    buf = build_payment_control_xlsx(data, sub.name)
    wb = load_workbook(buf)
    assert "Контрольный лист" in wb.sheetnames
    assert "Не привязаны" in wb.sheetnames
    assert "Отмечено, не подтверждено" in wb.sheetnames


# ---------------------------------------------------------------------------
# П.5 — автосопоставление после импорта (вызов общей функции)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_match_after_import_attaches_payment(db_session, test_org):
    from app.services.payment_control_import_hook import auto_match_after_import

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-5")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("300.00"), status="delivered",
    )
    item = None
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    pitem = PurchaseItem(
        purchase_id=purchase.id, item_name="товар", item_type="товар",
        quantity=1, unit_price=Decimal("300.00"), total_price=Decimal("300.00"),
    )
    db_session.add(pitem)
    await db_session.commit()

    bp = _bp(agreement="СК-5", amount="300.00", payee_inn=contractor.inn, payee_name=contractor.name)
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    report = await auto_match_after_import(db_session, [bp])
    assert not report["errors"]
    assert str(sub.id) in report["auto_matched"]

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].bank_payment_id == bp.id


# ---------------------------------------------------------------------------
# П.4 — attach(fix_amount=true): одна позиция → правит сумму штатным пересчётом
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fix_purchase_amount_single_item(db_session, test_org):
    from app.services.payment_control_fix_amount import fix_purchase_amount

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-fix")
    contractor = await _make_contractor(db_session)
    purchase = Purchase(
        subsidy_id=sub.id, contractor_id=contractor.id,
        contract_price=Decimal("1000.00"), status="delivered",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="товар", item_type="товар",
        quantity=1, unit_price=Decimal("1000.00"), total_price=Decimal("1000.00"),
    )
    db_session.add(item)
    await db_session.commit()

    result = await fix_purchase_amount(db_session, purchase, Decimal("1234.56"))
    await db_session.commit()
    assert result == {"from": 1000.0, "to": 1234.56}
    await db_session.refresh(purchase)
    assert purchase.contract_price == Decimal("1234.56")


@pytest.mark.asyncio
async def test_fix_purchase_amount_rejected_multi_item_big_delta(db_session, test_org):
    from app.services.payment_control_fix_amount import fix_purchase_amount, AmountFixNotAllowed

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="СК-fix2")
    purchase = Purchase(subsidy_id=sub.id, contract_price=Decimal("1000.00"), status="delivered")
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    db_session.add_all([
        PurchaseItem(purchase_id=purchase.id, item_name="товар1", item_type="товар",
                     quantity=1, unit_price=Decimal("600.00"), total_price=Decimal("600.00")),
        PurchaseItem(purchase_id=purchase.id, item_name="товар2", item_type="товар",
                     quantity=1, unit_price=Decimal("400.00"), total_price=Decimal("400.00")),
    ])
    await db_session.commit()

    with pytest.raises(AmountFixNotAllowed):
        await fix_purchase_amount(db_session, purchase, Decimal("5000.00"))
