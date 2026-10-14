"""Средняя цена по региону и партии (план clever-bouncing-lantern.md, Часть 2,
14.10.2026) — compute_price_stats с target_region/quantity, поиск субъекта в
адресе (region_from_text), идемпотентность писателя по позициям закупки
(actualize_contract_item_prices)."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pytest

from app.services.product_price_stats import compute_price_stats, batch_label
from app.services.region_from_text import find_region_in_text
from app.services.ru_regions import canonical_region_name


@dataclass
class _Row:
    price: Optional[Decimal]
    collected_at: Optional[date]
    region: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    source_ref: Optional[str] = None


TODAY = date(2026, 10, 14)


def _d(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_batch_label_ranges():
    assert batch_label(5) == "1-9"
    assert batch_label(50) == "10-99"
    assert batch_label(500) == "100-999"
    assert batch_label(5000) == "1000+"
    assert batch_label(0) is None
    assert batch_label(None) is None


def test_region_batch_level_moscow_1000_cheaper():
    """Москва, партия 1000+ — своя (дешёвая) цена; обычное правило (all) её бы
    смешало с дорогими точками других регионов/партий."""
    rows = [
        _Row(Decimal("100"), _d(10), region="Москва", quantity=Decimal("1200"), unit="шт", source_ref="C1"),
        _Row(Decimal("110"), _d(20), region="Москва", quantity=Decimal("1500"), unit="шт", source_ref="C2"),
        _Row(Decimal("900"), _d(5), region="Чукотский автономный округ", quantity=Decimal("10"), unit="шт", source_ref="C3"),
    ]
    stats = compute_price_stats(rows, today=TODAY, target_region="Москва", quantity=1200, product_unit="шт")
    assert stats.level == "region_batch"
    assert stats.region_used == "Москва"
    assert stats.batch == "1000+"
    assert stats.avg_price == Decimal("105.00")
    assert stats.basis_count == 2


def test_chukotka_small_batch_more_expensive_and_separate_from_moscow():
    rows = [
        _Row(Decimal("100"), _d(10), region="Москва", quantity=Decimal("1200"), unit="шт", source_ref="C1"),
        _Row(Decimal("900"), _d(5), region="Чукотский автономный округ", quantity=Decimal("10"), unit="шт", source_ref="C2"),
        _Row(Decimal("950"), _d(6), region="Чукотский автономный округ", quantity=Decimal("12"), unit="шт", source_ref="C3"),
    ]
    stats = compute_price_stats(rows, today=TODAY, target_region="Чукотский автономный округ", quantity=10, product_unit="шт")
    assert stats.level == "region_batch"
    assert stats.region_used == "Чукотский автономный округ"
    assert stats.avg_price == Decimal("925.00")


def test_dnr_no_data_falls_back_to_nearest_region_with_data():
    """ДНР без своих точек — лестница должна уйти на ближайший регион, у
    которого данных хватает (не сразу на 'all')."""
    rows = [
        _Row(Decimal("200"), _d(5), region="Ростовская область", quantity=Decimal("50"), unit="шт", source_ref="C1"),
        _Row(Decimal("220"), _d(8), region="Ростовская область", quantity=Decimal("60"), unit="шт", source_ref="C2"),
        _Row(Decimal("5000"), _d(3), region="Чукотский автономный округ", quantity=Decimal("50"), unit="шт", source_ref="C3"),
        _Row(Decimal("5100"), _d(4), region="Чукотский автономный округ", quantity=Decimal("55"), unit="шт", source_ref="C4"),
    ]
    stats = compute_price_stats(
        rows, today=TODAY, target_region="Донецкая Народная Республика", quantity=55, product_unit="шт",
    )
    assert stats.level in ("nearest_batch", "nearest")
    assert stats.region_used == "Ростовская область"
    assert stats.avg_price == Decimal("210.00")


def test_nothing_matches_falls_back_to_all_old_rule_unchanged():
    """Нет ни региона, ни партии с достаточными данными — уходим на старое
    правило (60 дней/фолбэк 3), оно не менялось."""
    rows = [_Row(Decimal("100"), _d(10), region=None, quantity=None, unit="шт", source_ref="C1")]
    stats = compute_price_stats(rows, today=TODAY, target_region="Москва", quantity=5, product_unit="шт")
    assert stats.level == "all"
    assert stats.region_used is None
    assert stats.batch is None
    assert stats.avg_price == Decimal("100.00")
    assert stats.window_days == 60


def test_unit_mismatch_excludes_point_from_filtered_levels():
    """Позиция в других единицах (кг вместо шт) не должна попасть в
    отфильтрованный уровень — даже если регион/партия совпали."""
    rows = [
        _Row(Decimal("100"), _d(5), region="Москва", quantity=Decimal("5"), unit="кг", source_ref="C1"),
        _Row(Decimal("110"), _d(6), region="Москва", quantity=Decimal("6"), unit="кг", source_ref="C2"),
    ]
    stats = compute_price_stats(rows, today=TODAY, target_region="Москва", quantity=5, product_unit="шт")
    # единица товара "шт", у обеих точек "кг" — фильтрованные уровни не находят
    # данных вообще (ни с партией, ни без, ни у соседей) → падаем на "all",
    # где единица не проверяется (старое правило).
    assert stats.level == "all"


def test_no_history_still_reports_basis_zero():
    stats = compute_price_stats([], today=TODAY, target_region="Москва", quantity=5)
    assert stats.avg_price is None
    assert stats.basis_count == 0
    assert stats.level == "all"


def test_old_call_signature_without_filters_unchanged():
    """Без target_region/quantity — поведение буквально как раньше (level
    добавился как новое поле, но значения авg_price/basis_count/stale те же)."""
    rows = [_Row(Decimal("100"), _d(10)), _Row(Decimal("200"), _d(5))]
    stats = compute_price_stats(rows, today=TODAY)
    assert stats.avg_price == Decimal("150.00")
    assert stats.basis_count == 2
    assert stats.stale is False
    assert stats.level == "all"


# --- region_from_text / canonical_region_name ------------------------------

def test_find_region_in_text_moscow_postal_address():
    assert find_region_in_text("119454, Г.МОСКВА, ул. Лобачевского, д. 1") == "Москва"


def test_find_region_in_text_lnr_full_name():
    assert find_region_in_text("Луганская Народная Республика, г. Луганск, ул. Советская 1") == \
        "Луганская Народная Республика"


def test_find_region_in_text_no_match_returns_none():
    assert find_region_in_text("ул. Пушкина, д. 10") is None
    assert find_region_in_text(None) is None
    assert find_region_in_text("") is None


def test_canonical_region_name_normalizes_delivery_region_text():
    assert canonical_region_name("ХМАО") == "Ханты-Мансийский автономный округ — Югра"
    assert canonical_region_name("г. москва") == "Москва"
    assert canonical_region_name("Не определён") is None
    assert canonical_region_name(None) is None


# --- actualize_contract_item_prices идемпотентность -------------------------

@pytest.mark.asyncio
async def test_actualize_contract_item_prices_idempotent(db_session):
    from sqlalchemy import select
    from app.models.product import Product
    from app.models.product_price_history import ProductPriceHistory
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.services.price_actualization import actualize_contract_item_prices

    product = Product(name="Товар для регионального досчёта", category="Прочее")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    purchase = Purchase(
        status="contracted", item_type="goods", item_name="Test",
        contract_number="CN-REG-1", contract_date=date(2026, 10, 1),
        delivery_region="г. Москва",
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Item", quantity=Decimal("50"), unit="шт",
        unit_price=Decimal("120"), total_price=Decimal("6000"), product_id=product.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(purchase)

    await actualize_contract_item_prices(db_session, purchase, [item])
    await db_session.commit()
    await actualize_contract_item_prices(db_session, purchase, [item])
    await db_session.commit()

    rows = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.purchase_item_id == item.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].region == "Москва"
    assert rows[0].quantity == Decimal("50.0000")
    assert rows[0].unit == "шт"
