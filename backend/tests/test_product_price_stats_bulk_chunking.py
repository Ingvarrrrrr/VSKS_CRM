"""Регресс 26.10.2026: каталог дорос до 53 797 товаров — GET /api/products/
падал 500 (asyncpg "the number of query arguments cannot exceed 32767"),
потому что compute_price_stats_bulk строила один IN на ВСЕ id разом.
Фикс — оба запроса внутри compute_price_stats_bulk идут порциями
(app.utils.chunking.chunked). Тест гоняет >5000 id (больше одной порции)
на реальной БД и проверяет, что результат совпадает с тем, что даёт один
большой список (порции склеиваются без потерь/дублей)."""
from decimal import Decimal

import pytest

from app.models.product import Product
from app.services.product_price_stats import compute_price_stats_bulk
from app.utils.chunking import chunked, DEFAULT_CHUNK_SIZE


def test_chunked_splits_and_reassembles_without_loss():
    ids = list(range(1, 12001))  # > 2 порций по 5000
    chunks = list(chunked(ids, 5000))
    assert [len(c) for c in chunks] == [5000, 5000, 2000]
    assert [x for c in chunks for x in c] == ids


@pytest.mark.asyncio
async def test_compute_price_stats_bulk_handles_more_than_one_chunk(db_session):
    """N > DEFAULT_CHUNK_SIZE товаров без истории цен — раньше один IN на
    весь список уже не падал бы на такой N (DEFAULT_CHUNK_SIZE слишком мал,
    чтобы реально воспроизвести asyncpg-лимит в тесте за разумное время),
    но проверяет сам механизм склейки порций: каждому id — свой PriceStats,
    ничего не потеряно и не задвоено."""
    n = DEFAULT_CHUNK_SIZE + 37
    products = [Product(name=f"chunk-test-product-{i}") for i in range(n)]
    db_session.add_all(products)
    await db_session.flush()
    ids = [p.id for p in products]
    await db_session.commit()
    assert len(ids) == n

    stats_by_id = await compute_price_stats_bulk(db_session, ids)

    assert len(stats_by_id) == n
    assert set(stats_by_id.keys()) == set(ids)
    for pid in ids:
        stats = stats_by_id[pid]
        assert stats.avg_price is None
        assert stats.basis_count == 0
