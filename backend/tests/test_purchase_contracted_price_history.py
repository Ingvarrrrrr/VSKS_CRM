"""Владелец, 2026-09-16, п.D: переход закупки в 'contracted' пишет цену
договора в историю товара (ProductPriceHistory, source='contract') по КАЖДОЙ
позиции с product_id — через единственный писатель
app.services.price_actualization.actualize_product_price. Идемпотентно:
повторный переход (тот же номер/дата договора) не плодит вторую строку
истории (см. дедуп-проверка в app/routers/purchase_transitions.py).

Роутер-функция вызывается НАПРЯМУЮ (как и test_purchase_contract_price_recalc.py
делает с `_recalc_contract_price_from_contract_items`) — Depends() на
db/current_user просто перекрываются явными позиционными/именованными
аргументами, HTTP-слой тут не нужен.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.contract_item import ContractItem
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.routers.purchase_transitions import transition_status


async def _make_contracted_purchase(db_session, product, *, contract_number="CN-100"):
    p = Purchase(
        status="contracted",
        item_type="goods",
        item_name="Test purchase",
        contract_number=contract_number,
        contract_date=date(2026, 9, 1),
    )
    db_session.add(p)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=p.id, item_name="Item", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("777"), total_price=Decimal("777"), product_id=product.id,
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(ContractItem(
        purchase_id=p.id, name="Item", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("777"), total=Decimal("777"), source_item_id=item.id,
        match_confirmed=True,
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_contracted_transition_writes_price_history_idempotently(db_session, test_admin_user):
    product = Product(name="Товар для истории договора", category="Прочее")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    p = await _make_contracted_purchase(db_session, product)

    await transition_status(pid=p.id, target_status="contracted", db=db_session, current_user=test_admin_user)

    rows = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "contract"
    assert rows[0].source_ref == "CN-100"
    assert rows[0].collected_at == date(2026, 9, 1)
    assert rows[0].price == Decimal("777.00")

    await db_session.refresh(product)
    assert product.price == Decimal("777.00")
    assert product.contract_price == Decimal("777.00")

    # Повторный переход (тот же договор/дата, admin может двигать статус
    # "назад"/на месте) — не плодит вторую строку истории.
    await transition_status(pid=p.id, target_status="contracted", db=db_session, current_user=test_admin_user)
    rows2 = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(rows2) == 1


@pytest.mark.asyncio
async def test_contracted_transition_different_contract_adds_new_history_row(db_session, test_admin_user):
    """Разный номер договора (или дата) — легитимно вторая строка истории, это
    не дубль, а другой контракт по тому же товару."""
    product = Product(name="Товар с двумя договорами", category="Прочее")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    p1 = await _make_contracted_purchase(db_session, product, contract_number="CN-1")
    await transition_status(pid=p1.id, target_status="contracted", db=db_session, current_user=test_admin_user)

    p2 = await _make_contracted_purchase(db_session, product, contract_number="CN-2")
    await transition_status(pid=p2.id, target_status="contracted", db=db_session, current_user=test_admin_user)

    rows = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(rows) == 2
    assert {r.source_ref for r in rows} == {"CN-1", "CN-2"}


@pytest.mark.asyncio
async def test_contracted_transition_older_contract_does_not_overwrite_fresher_price(db_session, test_admin_user):
    """План clever-bouncing-lantern.md, часть 2, п.1 (15.10): точка в историю
    пишется всегда, а Product.price/contract_price/contract_number/
    contract_date договор меняет только если его дата НЕ старше текущей
    price_updated_at товара — иначе загрузка факта со старым договором
    затёрла бы более свежую цену старой."""
    product = Product(name="Товар со свежей ценой", category="Прочее")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    # Цена товара уже "свежая" (актуализирована позже, чем будет договор ниже).
    product.price = Decimal("999.00")
    product.price_updated_at = datetime(2026, 9, 20)
    product.price_source = "manual"
    product.contract_price = Decimal("999.00")
    product.contract_number = "CN-FRESH"
    product.contract_date = date(2026, 9, 15)
    await db_session.commit()
    await db_session.refresh(product)

    # Договор СТАРШЕ (contract_date=2026-09-01 < price_updated_at=2026-09-20).
    p = await _make_contracted_purchase(product=product, db_session=db_session, contract_number="CN-OLD")

    await transition_status(pid=p.id, target_status="contracted", db=db_session, current_user=test_admin_user)

    # История — всё равно новая точка (не дубль, другой purchase_item_id).
    rows = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_ref == "CN-OLD"
    assert rows[0].collected_at == date(2026, 9, 1)
    assert rows[0].price == Decimal("777.00")

    # Но Product.price/contract_* не сдвинулись — старый договор их не затёр.
    await db_session.refresh(product)
    assert product.price == Decimal("999.00")
    assert product.price_updated_at == datetime(2026, 9, 20)
    assert product.contract_price == Decimal("999.00")
    assert product.contract_number == "CN-FRESH"
    assert product.contract_date == date(2026, 9, 15)
