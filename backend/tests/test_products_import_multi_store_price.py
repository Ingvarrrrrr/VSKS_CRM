"""Задача 2 (owner, 27.10.2026, product_merge): два магазина с одинаковой/
старой ценой/датой — КАЖДЫЙ оставляет свою строку в product_price_history,
даже если его цена не стала "текущей" ценой товара (_price_is_more_actual
решает только Product.price, не писать ли точку истории вовсе). Повтор той
же самой строки (тот же product+contractor_id+price+collected_at) не должен
дублировать историю — services/price_actualization.py::record_price_point."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестМультиМагазин"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_two_stores_same_price_both_get_history_row(db_session, test_user):
    name = _uniq_name("Товар")
    col_idx = {"name": 0, "price": 1, "link_url_1": 2, "seller_inn": 3}
    # Два магазина (разные ИНН — _resolve_seller_contractor создаст два
    # контрагента), одна и та же цена — вторая строка не "более актуальна"
    # (цена не изменилась), но должна оставить свою строку истории.
    data_rows = [
        (name, "100", "https://store1.ru/item/1", "6679104850"),
        (name, "100", "https://store2.ru/item/2", "7701234567"),
    ]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="multi_store.gala.json", current_user=test_user,
    )
    assert result["created"] == 1
    assert result["updated"] == 1

    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()
    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 2, [h.source_ref for h in hist]
    contractor_ids = {h.contractor_id for h in hist}
    assert len(contractor_ids) == 2
    assert all(cid is not None for cid in contractor_ids)


@pytest.mark.asyncio
async def test_repeated_exact_row_does_not_duplicate_history(db_session, test_user):
    name = _uniq_name("Товар2")
    col_idx = {"name": 0, "price": 1, "link_url_1": 2, "seller_inn": 3, "price_date": 4}
    row = (name, "100", "https://store1.ru/item/1", "6679104850", "2026-10-01")
    # Первая строка файла создаёт товар + точку истории; затем второй файл
    # (тот же товар, тот же магазин, та же цена, та же дата) повторяет её —
    # точка не должна продублироваться.
    result1 = await apply_products_import(
        db_session, [row], col_idx,
        filename="multi_store_a.gala.json", current_user=test_user,
    )
    assert result1["created"] == 1
    product = (await db_session.execute(select(Product).where(Product.name == name))).scalar_one()

    result2 = await apply_products_import(
        db_session, [row], col_idx,
        filename="multi_store_b.gala.json", current_user=test_user,
    )
    assert result2["created"] == 0

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 1, [(h.source_ref, h.price, h.collected_at) for h in hist]
