"""Контрольные суммы «выписка ↔ закупки» по субсидии —
.planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1.
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.subsidy_payment_control import (
    build_payment_control,
    get_search_codes,
    set_search_codes,
)
from app.services.purchase_from_bank_payment import create_purchase_from_bank_payment


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _make_subsidy(db_session, org_id=None, agreement_number=None):
    s = Subsidy(
        name=f"ФАДМ-{_uid()}", year=2026, require_planned_dates=False,
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
        payee_inn=None, payee_name=None, payment_number=None, expense_code=None, payment_date=None):
    import datetime
    return BankPayment(
        payment_number=payment_number or f"ПП-{_uid()}",
        payee_inn=payee_inn,
        payee_name=payee_name,
        amount=Decimal(amount),
        status=status,
        purpose_text=f"Оплата по Соглашению № {agreement} от 28.01.2026 за товар",
        subsidy_id=subsidy_id,
        expense_code=expense_code,
        payment_date=payment_date or datetime.date(2026, 5, 1),
    )


# ---------------------------------------------------------------------------
# 1. Исполненные vs отменённые
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancelled_payment_goes_to_not_executed(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-1")
    bp_ok = _bp(agreement="АГР-1", amount="500.00", status="ИСПОЛНЕН")
    bp_bad = _bp(agreement="АГР-1", amount="300.00", status="АННУЛИРОВАН")
    db_session.add_all([bp_ok, bp_bad])
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    assert result["totals"]["executed_count"] == 1
    assert result["totals"]["executed_total"] == 500.0
    assert result["totals"]["not_executed_count"] == 1
    assert len(result["not_executed"]) == 1
    assert result["not_executed"][0]["status"] == "АННУЛИРОВАН"


# ---------------------------------------------------------------------------
# 2. Неотмеченная статья → not_reconciled, не registry_only; сумма учтена
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unselected_code_is_not_reconciled_not_registry_only(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-2")
    bp = _bp(agreement="АГР-2", amount="1000.00", expense_code="0810004")
    db_session.add(bp)
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    row = next(r for r in result["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row["status"] == "not_reconciled"
    assert result["counts"]["registry_only"] == 0
    assert result["totals"]["not_reconciled_total"] == 1000.0
    assert result["totals"]["executed_total"] == 1000.0


# ---------------------------------------------------------------------------
# 3. Неизвестный код → ищет закупку + unknown_code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_code_flagged_and_searches_purchase(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-3")
    bp = _bp(agreement="АГР-3", amount="700.00", expense_code="9999999")
    db_session.add(bp)
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    row = next(r for r in result["rows"] if r["bank_payment_ids"] == [bp.id])
    assert row["unknown_code"] is True
    assert row["status"] == "registry_only"  # искали закупку, не нашли
    assert result["totals"]["unknown_code_total"] == 700.0


# ---------------------------------------------------------------------------
# 4. Дубль (а) — два исполненных платежа ИНН+сумма+дата
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_same_inn_amount_date(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-4")
    inn = "7700000099"
    bp1 = _bp(agreement="АГР-4", amount="2500.00", payee_inn=inn)
    bp2 = _bp(agreement="АГР-4", amount="2500.00", payee_inn=inn)
    bp1.payment_date = bp2.payment_date
    db_session.add_all([bp1, bp2])
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    statuses = {r["status"] for r in result["rows"] if r["bank_payment_ids"][0] in (bp1.id, bp2.id)}
    assert statuses == {"duplicate"}
    assert result["counts"]["duplicate"] == 2


# ---------------------------------------------------------------------------
# 5. Строка видна двум субсидиям по соглашению
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_row_visible_to_two_subsidies_by_agreement(db_session, test_org):
    sub1 = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-5")
    sub2 = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-5")
    bp = _bp(agreement="АГР-5", amount="4000.00")
    db_session.add(bp)
    await db_session.commit()

    r1 = await build_payment_control(db_session, sub1)
    r2 = await build_payment_control(db_session, sub2)
    assert r1["totals"]["executed_count"] == 1
    assert r2["totals"]["executed_count"] == 1


# ---------------------------------------------------------------------------
# 6. Итоги = Σ строк (Σ статей == executed_total)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_articles_sum_equals_executed_total(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-6")
    bp1 = _bp(agreement="АГР-6", amount="100.00", expense_code="0200032")
    bp2 = _bp(agreement="АГР-6", amount="200.00", expense_code="0810004")
    bp3 = _bp(agreement="АГР-6", amount="300.00", expense_code=None)
    db_session.add_all([bp1, bp2, bp3])
    await db_session.commit()

    result = await build_payment_control(db_session, sub)
    total_articles = sum(a["statement_total"] for a in result["articles"])
    assert abs(total_articles - result["totals"]["executed_total"]) < 0.01
    assert abs(result["totals"]["executed_total"] - 600.0) < 0.01


# ---------------------------------------------------------------------------
# 7. codes GET/PUT и default
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_codes_default_then_explicit(db_session, test_org):
    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-7")

    codes, is_default = await get_search_codes(db_session, sub.id)
    assert is_default is True
    assert "0200032" in codes  # is_procurement=true по умолчанию
    assert "0810004" not in codes

    await set_search_codes(db_session, sub.id, ["0810004"])
    await db_session.commit()

    codes2, is_default2 = await get_search_codes(db_session, sub.id)
    assert is_default2 is False
    assert codes2 == {"0810004"}


# ---------------------------------------------------------------------------
# 8. create-purchase — закупка «Не определена», Payment привязан
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_purchase_from_bank_payment(db_session, test_org):
    from app.models.user import User

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-8")
    bp = _bp(agreement="АГР-8", amount="1500.00", payee_inn="7700000123",
             payee_name="ООО Ромашка", expense_code="0200032")
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    admin = (await db_session.execute(
        select(User).where(User.org_id == test_org.id).limit(1)
    )).scalars().first()
    if admin is None:
        admin = User(username=f"u_{_uid()}", password_hash="x", role="admin", org_id=test_org.id)
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

    result = await create_purchase_from_bank_payment(db_session, admin, sub, bp)
    await db_session.commit()

    p = await db_session.get(Purchase, result.purchase.id)
    assert p.created_from_bank_payment_id == bp.id
    assert p.subsidy_id == sub.id
    assert p.status == "contracted"

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert len(items) == 1

    from app.models.feo_category import FeoCategory
    cat = await db_session.get(FeoCategory, p.feo_category_id)
    assert cat is not None
    assert cat.name == "Не определена"

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == p.id, Payment.bank_payment_id == bp.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].confirmed_by_statement is True


# ---------------------------------------------------------------------------
# 9. Наименование позиции — приёмка 05.10.2026: код известен → название статьи
#    расходов из справочника + «по договору № ... от ...»
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_purchase_item_name_from_known_expense_code(db_session, test_org):
    import datetime
    from app.models.user import User

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-9")
    bp = _bp(agreement="АГР-9", amount="90000.00", payee_inn="7700000777",
             payee_name="ООО Аренда", expense_code="0200012")
    bp.purpose_text = (
        "(711К0232001;0200012) Соглашение № 091-10-2026-008 от 28.01.2026 "
        "Договор № 15 от 10.02.2026 аренда помещения"
    )
    bp.parsed_contract_number = "15"
    bp.parsed_contract_date = datetime.date(2026, 2, 10)
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    admin = (await db_session.execute(
        select(User).where(User.org_id == test_org.id).limit(1)
    )).scalars().first()
    if admin is None:
        admin = User(username=f"u_{_uid()}", password_hash="x", role="admin", org_id=test_org.id)
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

    result = await create_purchase_from_bank_payment(db_session, admin, sub, bp)
    await db_session.commit()

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == result.purchase.id)
    )).scalars().all()
    assert len(items) == 1
    name = items[0].item_name
    assert name.startswith("Арендная плата за объекты основных средств")
    assert "по договору № 15 от 10.02.2026" in name
    # Сырой префикс/соглашение не должны просочиться в наименование.
    assert "(711К0232001" not in name
    assert "Соглашение" not in name


# ---------------------------------------------------------------------------
# 10. Код НЕ в справочнике → очищенный предмет из назначения (без префикса
#     и без «Соглашение ... от ...»), тоже «по договору № ... от ...»
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_purchase_item_name_from_unknown_code_cleans_purpose(db_session, test_org):
    import datetime
    from app.models.user import User

    sub = await _make_subsidy(db_session, test_org.id, agreement_number="АГР-10")
    bp = _bp(agreement="АГР-10", amount="5000.00", payee_inn="7700000888",
             payee_name="ООО Прочее", expense_code="9999999")
    bp.purpose_text = (
        "(711К0232001;9999999) Соглашение № 091-10-2026-008 от 28.01.2026 "
        "Договор № 21 от 01.03.2026 канцелярские товары"
    )
    bp.parsed_contract_number = "21"
    bp.parsed_contract_date = datetime.date(2026, 3, 1)
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    admin = (await db_session.execute(
        select(User).where(User.org_id == test_org.id).limit(1)
    )).scalars().first()
    if admin is None:
        admin = User(username=f"u_{_uid()}", password_hash="x", role="admin", org_id=test_org.id)
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

    result = await create_purchase_from_bank_payment(db_session, admin, sub, bp)
    await db_session.commit()

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == result.purchase.id)
    )).scalars().all()
    assert len(items) == 1
    name = items[0].item_name
    assert "(711К0232001" not in name
    assert "Соглашение" not in name
    assert "канцелярские товары" in name
    assert "по договору № 21 от 01.03.2026" in name
