"""POST /api/purchases/{pid}/split — наследование стадии/договора/платежей
частями при разбиении закупки, уже «в договоре» (задача 07.10.2026, прод,
субсидия «ЛНР» id 74, закупка РЕЕ-2026-00957). См. app/services/purchase_split.py.

(a) paid-закупка с временным договором и manual-платежом — разбиение на 4
    группы: каждая часть status='paid', свой договор, платёж = сумме своих
    позиций, Σ платежей частей == сумме исходного платежа, feo_category_id
    позиций сохранена, у исходной платежей не остаётся.
(b) planned-закупка — поведение НЕ изменилось (без договора, status='planned').
"""
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.contract import Contract
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy


async def _seed_paid_purchase_with_contract(db_session, test_org):
    """Паритет с бага-репортом: 4 позиции (171159 / 155499.38 / 34600 /
    112154.80 = 473413.18), paid, временный номер договора, ручной платёж на
    всю сумму."""
    subsidy = Subsidy(name="ЛНР-тест", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    feo_cat = FeoCategory(subsidy_id=subsidy.id, name="Статья ФЭО теста", level=1)
    db_session.add(feo_cat)
    await db_session.flush()

    p = Purchase(
        item_name="РЕЕ-2026-00957 тест",
        subsidy_id=subsidy.id,
        feo_category_id=feo_cat.id,
        status="paid",
        contract_number="ВРЕМ-957",
        contract_number_is_temporary=True,
        purchase_method="single",
        is_prepayment=False,
    )
    db_session.add(p)
    await db_session.flush()

    contract = Contract(number="ВРЕМ-957", contract_type="single", subsidy_id=subsidy.id, status="active")
    db_session.add(contract)
    await db_session.flush()
    p.contract_id = contract.id

    amounts = [Decimal("171159"), Decimal("155499.38"), Decimal("34600"), Decimal("112154.80")]
    items = []
    for i, amt in enumerate(amounts):
        it = PurchaseItem(
            purchase_id=p.id, item_name=f"Позиция {i}",
            quantity=1, unit="шт", unit_price=amt, total_price=amt,
            feo_category_id=feo_cat.id,
        )
        db_session.add(it)
        items.append(it)
    await db_session.flush()

    total = sum(amounts)
    p.planned_total_price = total
    p.total_nmck = total
    p.nmck = total
    p.contract_price = total

    pay = Payment(purchase_id=p.id, amount=total, payment_source="manual", confirmed_by_statement=False)
    db_session.add(pay)

    await db_session.commit()
    await db_session.refresh(p)
    for it in items:
        await db_session.refresh(it)
    return p, items, feo_cat


@pytest.mark.asyncio
async def test_split_paid_purchase_keeps_status_contract_and_money(client, db_session, admin_headers, test_org):
    p, items, feo_cat = await _seed_paid_purchase_with_contract(db_session, test_org)
    source_total = sum(Decimal(str(it.total_price)) for it in items)

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "A", "item_ids": [items[0].id]},
            {"column_key": "B", "item_ids": [items[1].id]},
            {"column_key": "C", "item_ids": [items[2].id]},
            {"column_key": "D", "item_ids": [items[3].id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 4

    children = (await db_session.execute(
        select(Purchase).where(Purchase.parent_purchase_id == p.id)
    )).scalars().all()
    assert len(children) == 4

    total_payments = Decimal("0")
    contract_numbers = set()
    for c in children:
        assert c.status == "paid", f"часть {c.id} должна наследовать paid, а не {c.status}"
        assert c.contract_id is not None, f"часть {c.id} без договора"
        assert c.contract_number, f"часть {c.id} без contract_number"
        contract_numbers.add(c.contract_number)

        c_items = (await db_session.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == c.id)
        )).scalars().all()
        assert len(c_items) == 1
        assert c_items[0].feo_category_id == feo_cat.id, (
            f"часть {c.id}: позиция потеряла feo_category_id при копировании"
        )

        c_payments = (await db_session.execute(
            select(Payment).where(Payment.purchase_id == c.id)
        )).scalars().all()
        assert len(c_payments) == 1, f"часть {c.id} должна получить ровно один платёж"
        pay_amount = Decimal(str(c_payments[0].amount))
        item_total = Decimal(str(c_items[0].total_price))
        assert pay_amount == item_total, (
            f"часть {c.id}: платёж {pay_amount} должен равняться сумме своей позиции {item_total}"
        )
        total_payments += pay_amount

    # Временный номер — каждая часть получает СВОЙ (не задваивая один договор
    # на несколько, т.к. исходный номер был ВРЕМ-* — временный).
    assert len(contract_numbers) == 4, f"временные номера частей должны быть разными: {contract_numbers}"

    assert total_payments == source_total, (
        f"Σ платежей частей {total_payments} должна равняться сумме исходного платежа {source_total} до копейки"
    )

    await db_session.refresh(p)
    assert p.status == "split"
    source_payments_left = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == p.id)
    )).scalars().all()
    assert source_payments_left == [], "у исходной закупки не должно остаться платежей после разбиения"
    assert p.contract_id is None, "у исходной закупки договор должен быть отвязан после разбиения"


@pytest.mark.asyncio
async def test_split_paid_purchase_real_contract_number_shared_across_parts(client, db_session, admin_headers, test_org):
    """Реальный (не временный) номер договора — части получают ТОТ ЖЕ
    contract_number/contract_date (один реальный договор, части — его разрезы),
    и ensure_contract_linked находит/привязывает ОДИН И ТОТ ЖЕ Contract всем
    частям (как уже происходит у рамочных договоров на несколько субсидий)."""
    p, items, feo_cat = await _seed_paid_purchase_with_contract(db_session, test_org)
    p.contract_number = "12345/2026"
    p.contract_number_is_temporary = False
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "A", "item_ids": [items[0].id, items[1].id]},
            {"column_key": "B", "item_ids": [items[2].id, items[3].id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    children = (await db_session.execute(
        select(Purchase).where(Purchase.parent_purchase_id == p.id)
    )).scalars().all()
    assert len(children) == 2
    contract_ids = {c.contract_id for c in children}
    contract_numbers = {c.contract_number for c in children}
    assert contract_numbers == {"12345/2026"}
    assert len(contract_ids) == 1, (
        f"части с одинаковым реальным номером договора должны делить ОДИН Contract, получили {contract_ids}"
    )


@pytest.mark.asyncio
async def test_split_refuses_payment_confirmed_by_statement(client, db_session, admin_headers, test_org):
    """Платёж, подтверждённый выпиской (confirmed_by_statement=True) — закупка
    не разбивается молча, 400 с понятным текстом (п.3 задачи)."""
    p, items, feo_cat = await _seed_paid_purchase_with_contract(db_session, test_org)
    pay = (await db_session.execute(select(Payment).where(Payment.purchase_id == p.id))).scalar_one()
    pay.confirmed_by_statement = True
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "A", "item_ids": [items[0].id]},
            {"column_key": "B", "item_ids": [items[1].id, items[2].id, items[3].id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "выпиской" in resp.json()["message"]


@pytest.mark.asyncio
async def test_split_planned_purchase_unchanged(client, db_session, admin_headers):
    """Регресс: закупка ДО договора (planned) разбивается как раньше — без
    договора/платежей, status='planned'."""
    p = Purchase(item_name="Тестовая закупка split-money planned", status="plan_schedule")
    db_session.add(p)
    await db_session.flush()
    items = []
    for i in range(2):
        it = PurchaseItem(
            purchase_id=p.id, item_name=f"Позиция {i}",
            quantity=1, unit="шт", unit_price=100, total_price=100,
        )
        db_session.add(it)
        items.append(it)
    await db_session.commit()
    for it in items:
        await db_session.refresh(it)

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "A", "item_ids": [items[0].id]},
            {"column_key": "B", "item_ids": [items[1].id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    children = (await db_session.execute(
        select(Purchase).where(Purchase.parent_purchase_id == p.id)
    )).scalars().all()
    assert len(children) == 2
    for c in children:
        assert c.status == "planned"
        assert c.contract_id is None
