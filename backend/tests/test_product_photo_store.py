"""Тесты product_photo_compress + product_photo_store (владелец, 26.10.2026):
фото каталога — отдельная таблица product_photos, всегда хранится сжатым
(WebP, длинная сторона ≤400px). Покрывает: сжатие (большой JPEG, PNG с
прозрачностью, уже маленький WebP не портится), save/load/delete через
единственный модуль-источник, отдачу GET /api/products/{id}/photo, has_photo.
"""
import io

import pytest
from PIL import Image

from app.models.product import Product
from app.services.product_photo_compress import (
    MAX_SIDE_PX,
    compress_product_photo,
    is_already_compressed,
)
from app.services.product_photo_store import (
    delete_product_photo,
    has_photo,
    load_product_photo,
    save_product_photo,
)


def _make_jpeg(size=(1200, 800), color=(200, 50, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_png_rgba(size=(600, 600)) -> bytes:
    img = Image.new("RGBA", size, (10, 20, 30, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_small_webp(size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, (1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=75)
    return buf.getvalue()


class TestCompressProductPhoto:
    def test_large_jpeg_becomes_webp_under_max_side(self):
        raw = _make_jpeg(size=(2000, 1000))
        out, mime = compress_product_photo(raw)
        assert mime == "image/webp"
        img = Image.open(io.BytesIO(out))
        assert img.format == "WEBP"
        assert max(img.size) <= MAX_SIDE_PX

    def test_png_with_transparency_flattened_to_white(self):
        raw = _make_png_rgba(size=(500, 500))
        out, mime = compress_product_photo(raw)
        assert mime == "image/webp"
        img = Image.open(io.BytesIO(out))
        assert img.mode in ("RGB",)
        assert max(img.size) <= MAX_SIDE_PX

    def test_small_webp_does_not_grow_absurdly(self):
        raw = _make_small_webp()
        out, mime = compress_product_photo(raw)
        assert mime == "image/webp"
        img = Image.open(io.BytesIO(out))
        assert max(img.size) == 100  # already under MAX_SIDE_PX — not upscaled

    def test_is_already_compressed_true_for_small_webp(self):
        raw = _make_small_webp()
        assert is_already_compressed(raw, "image/webp") is True

    def test_is_already_compressed_false_for_jpeg(self):
        raw = _make_jpeg(size=(100, 100))
        assert is_already_compressed(raw, "image/jpeg") is False

    def test_is_already_compressed_false_for_oversized_webp(self):
        raw = _make_small_webp(size=(800, 800))
        assert is_already_compressed(raw, "image/webp") is False


@pytest.mark.asyncio
class TestProductPhotoStore:
    async def test_save_load_delete_roundtrip(self, db_session):
        product = Product(name="Тест фото товар", category="Прочее", is_active=True)
        db_session.add(product)
        await db_session.flush()

        assert has_photo(product) is False

        raw = _make_jpeg(size=(1600, 900))
        await save_product_photo(db_session, product, raw)
        await db_session.commit()

        assert has_photo(product) is True
        assert product.photo_mime == "image/webp"
        assert product.photo_size is not None and product.photo_size > 0

        loaded = await load_product_photo(db_session, product.id)
        assert loaded is not None
        data, mime = loaded
        assert mime == "image/webp"
        img = Image.open(io.BytesIO(data))
        assert max(img.size) <= MAX_SIDE_PX

        await delete_product_photo(db_session, product)
        await db_session.commit()
        assert has_photo(product) is False
        assert await load_product_photo(db_session, product.id) is None

    async def test_save_twice_upserts(self, db_session):
        product = Product(name="Тест upsert фото", category="Прочее", is_active=True)
        db_session.add(product)
        await db_session.flush()

        await save_product_photo(db_session, product, _make_jpeg(color=(10, 10, 10)))
        await db_session.commit()
        first = await load_product_photo(db_session, product.id)

        await save_product_photo(db_session, product, _make_jpeg(color=(250, 250, 250)))
        await db_session.commit()
        second = await load_product_photo(db_session, product.id)

        assert first is not None and second is not None
        assert first[0] != second[0]


@pytest.mark.asyncio
class TestServePhotoEndpoint:
    async def test_get_photo_404_when_absent(self, client, db_session):
        product = Product(name="Без фото", category="Прочее", is_active=True)
        db_session.add(product)
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(f"/api/products/{product.id}/photo")
        assert resp.status_code == 404

    async def test_get_photo_returns_bytes_after_save(self, client, db_session):
        product = Product(name="С фото", category="Прочее", is_active=True)
        db_session.add(product)
        await db_session.flush()
        await save_product_photo(db_session, product, _make_jpeg())
        await db_session.commit()

        resp = await client.get(f"/api/products/{product.id}/photo")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/webp")
        img = Image.open(io.BytesIO(resp.content))
        assert max(img.size) <= MAX_SIDE_PX
