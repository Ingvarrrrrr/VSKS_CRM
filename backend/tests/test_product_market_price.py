"""Целевой тест расчёта актуальной рыночной цены (розница + за похожий объём)
и сохранения защиты договорных товаров в product_market_price.py."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.product_market_price import (
    _persist_live_points,
    resolve_volume_pricing,
    summarize_retail_offers,
)
from app.services.product_price_stats import PriceStats


def test_summarize_retail_offers_median_and_bounds():
    offers = [
        {"store_name": "Магазин А", "price": 1200.0},
        {"store_name": "Магазин Б", "price": 1500.0},
        {"store_name": "Магазин В", "price": 1350.0},
    ]
    res = summarize_retail_offers(offers)
    assert res["retail_price"] == 1350.0
    assert res["retail_min"] == 1200.0
    assert res["retail_max"] == 1500.0
    assert res["retail_count"] == 3


def test_summarize_retail_offers_fallback_and_empty():
    assert summarize_retail_offers([], fallback_price=890.5) == {
        "retail_price": 890.5,
        "retail_min": 890.5,
        "retail_max": 890.5,
        "retail_count": 1,
    }
    assert summarize_retail_offers([], fallback_price=None) == {
        "retail_price": None,
        "retail_min": None,
        "retail_max": None,
        "retail_count": 0,
    }


def test_resolve_volume_pricing_contracts_priority():
    retail = {"retail_price": 1500.0, "retail_min": 1400.0, "retail_max": 1650.0, "retail_count": 3}
    res = resolve_volume_pricing(
        contract_prices=[1250.0, 1310.0],
        stats=None,
        quantity=25,
        unit="шт.",
        retail_summary=retail,
    )
    assert res["volume_price"] == 1280.0
    assert res["volume_batch"] == "10-99"
    assert res["volume_source"] == "contracts"
    assert res["volume_basis_count"] == 2
    assert "10-99" in res["volume_note"]


def test_resolve_volume_pricing_history_batch_and_honest_fallbacks():
    retail = {"retail_price": 1500.0, "retail_min": 1380.0, "retail_max": 1650.0, "retail_count": 3}
    stats = PriceStats(
        avg_price=Decimal("1320.50"),
        basis_count=4,
        window_days=None,
        stale=False,
        from_date=None,
        to_date=datetime.utcnow().date(),
        level="batch",
        batch="10-99",
    )
    res_hist = resolve_volume_pricing(
        contract_prices=[],
        stats=stats,
        quantity=40,
        unit="шт.",
        retail_summary=retail,
    )
    assert res_hist["volume_price"] == 1320.5
    assert res_hist["volume_source"] == "history_batch"
    assert res_hist["volume_basis_count"] == 4

    # Если сделок за объём нет, берём мин. по магазинам без выдуманной скидки
    res_min = resolve_volume_pricing(
        contract_prices=[],
        stats=None,
        quantity=150,
        unit="шт.",
        retail_summary=retail,
    )
    assert res_min["volume_price"] == 1380.0
    assert res_min["volume_batch"] == "100-999"
    assert res_min["volume_source"] == "min_retail"

    # Один магазин -> розничный ориентир
    single = {"retail_price": 500.0, "retail_min": 500.0, "retail_max": 500.0, "retail_count": 1}
    res_fb = resolve_volume_pricing(
        contract_prices=[],
        stats=None,
        quantity=2000,
        unit="шт.",
        retail_summary=single,
    )
    assert res_fb["volume_price"] == 500.0
    assert res_fb["volume_batch"] == "1000+"
    assert res_fb["volume_source"] == "retail_fallback"


def test_persist_live_points_respects_protected_products():
    async def _run():
        db = AsyncMock()
        product = SimpleNamespace(
            id=777,
            price=Decimal("1000.00"),
            price_updated_at=datetime.utcnow() - timedelta(days=20),
        )
        user = SimpleNamespace(id=5)
        live = [{"url": "https://kuvalda.ru/item/1", "price": 1250.0, "store_article": "A1"}]

        with (
            patch("app.services.product_market_price.store_for_domain", return_value=None),
            patch("app.services.product_market_price.record_price_point", new=AsyncMock(return_value=True)) as rec_mock,
            patch("app.services.product_market_price.load_protected_product_ids", new=AsyncMock(return_value={777})),
            patch("app.services.product_market_price.actualize_product_price", new=AsyncMock()) as act_mock,
        ):
            await _persist_live_points(db, product, live, user)
            rec_mock.assert_awaited_once()
            # Для защищённого товара Product.price менять НЕЛЬЗЯ
            act_mock.assert_not_awaited()
            db.commit.assert_awaited_once()

    asyncio.run(_run())


def test_persist_live_points_updates_unprotected_product():
    async def _run():
        db = AsyncMock()
        product = SimpleNamespace(
            id=888,
            price=Decimal("1000.00"),
            price_updated_at=datetime.utcnow() - timedelta(days=20),
        )
        user = SimpleNamespace(id=5)
        live = [
            {"url": "https://kuvalda.ru/item/1", "price": 1200.0, "store_article": "A1"},
            {"url": "https://regard.ru/item/2", "price": 1400.0, "store_article": "R2"},
        ]

        with (
            patch("app.services.product_market_price.store_for_domain", return_value=None),
            patch("app.services.product_market_price.record_price_point", new=AsyncMock(return_value=True)),
            patch("app.services.product_market_price.load_protected_product_ids", new=AsyncMock(return_value={777})),
            patch("app.services.product_market_price.actualize_product_price", new=AsyncMock()) as act_mock,
        ):
            await _persist_live_points(db, product, live, user)
            act_mock.assert_awaited_once()
            assert act_mock.call_args.kwargs["price"] == Decimal("1300.0")
            assert act_mock.call_args.kwargs["write_history"] is False
            db.commit.assert_awaited_once()

    asyncio.run(_run())


def test_get_product_market_price_queries_execute_safely():
    """Проверяет, что check_market_price формирует SQL-запросы к БД без AttributeError (Purchase.org_id -> Subsidy.org_id)."""
    from app.services.product_market_price import check_market_price

    async def _run():
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        product = SimpleNamespace(
            id=123,
            name="Бинт марлевый медицинский",
            price=Decimal("45.00"),
            unit="шт.",
            price_updated_at=datetime.utcnow(),
            price_shared=False,
            price_links=[],
            manufacturer=None,
        )
        user = SimpleNamespace(id=1, org_id=1, role="user")

        with (
            patch("app.services.product_market_price._resolve_product", new=AsyncMock(return_value=product)),
            patch("app.services.product_market_price._allowed_org_ids", new=AsyncMock(return_value={1})),
        ):
            res = await check_market_price(
                db=db,
                product_id=123,
                quantity=10,
                unit="шт.",
                current_user=user,
            )
            assert res is not None
            assert res["product_id"] == 123
            # Проверяем, что db.execute вызывался и сформированные запросы не упали
            assert db.execute.await_count >= 3

    asyncio.run(_run())
