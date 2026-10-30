# -*- coding: utf-8 -*-
"""Автодокачка фото товара по внешней ссылке (владелец, 29.10.2026, см.
app/services/product_photo_autofetch.py, Правило №6).

download_and_save_photo/async_session замоканы: товар со ссылкой и без
сохранённого фото ДОЛЖЕН вызвать скачивание, товар с уже сохранённым фото —
НЕТ (has_photo() по photo_size — тот же признак, что и везде в проекте, см.
product_photo_store.py).

queue_after_commit (notify_after_commit.py) замокан на «выполнить фабрику
сразу же» — это уже отдельный, независимо проверяемый механизм (его
использует и app/services/purchase_payments.py); здесь проверяем только
ЛОГИКУ product_photo_autofetch.py (кого скачивать/кого пропускать), не
повторно сам приём отложенного запуска после commit."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.models.product import Product
import app.services.product_photo_autofetch as autofetch_module
from app.services.product_photo_autofetch import schedule_photo_fetch


def _mk(db_session, **kwargs):
    p = Product(name=kwargs.pop("name"), category=kwargs.pop("category", "Прочее"), **kwargs)
    db_session.add(p)
    return p


def _patch_session_and_queue(monkeypatch, db_session):
    """schedule_photo_fetch() сам открывает НОВУЮ app.database.async_session()
    (не сессию теста, см. docstring модуля — фоновая задача не должна
    зависеть от сессии исходного HTTP-запроса). В тесте подменяем её на ТУ ЖЕ
    транзакционную db_session фикстуры (иначе не увидит незакоммиченные
    тестовые строки — тест не коммитит в реальную БД, см. conftest.py)."""
    @asynccontextmanager
    async def _fake_async_session():
        yield db_session

    monkeypatch.setattr(autofetch_module, "async_session", _fake_async_session)
    # queue_after_commit — выполнить фабрику НЕМЕДЛЕННО (без ожидания
    # реального after_commit события) — проверяем логику _fetch_many/
    # _fetch_one, не сам отложенный механизм (у него свой вызывающий,
    # purchase_payments.py, уже использует его в продакшене).
    monkeypatch.setattr(
        autofetch_module, "queue_after_commit",
        lambda db, coro_factory: db_session._pending_autofetch_coros.append(coro_factory),  # type: ignore[attr-defined]
    )


@pytest.mark.asyncio
async def test_schedule_downloads_product_with_link_and_no_photo(db_session, monkeypatch):
    product = _mk(db_session, name="Товар со ссылкой без фото", photo_url="https://example.com/a.jpg")
    await db_session.commit()

    _patch_session_and_queue(monkeypatch, db_session)
    db_session._pending_autofetch_coros = []

    mock_download = AsyncMock(return_value=(True, None, None))
    monkeypatch.setattr(autofetch_module, "download_and_save_photo", mock_download)

    schedule_photo_fetch(db_session, [product.id])
    assert len(db_session._pending_autofetch_coros) == 1
    await db_session._pending_autofetch_coros[0]()

    mock_download.assert_awaited_once()
    called_product_id = mock_download.await_args.args[0]
    called_url = mock_download.await_args.args[1]
    assert called_product_id == product.id
    assert called_url == "https://example.com/a.jpg"


@pytest.mark.asyncio
async def test_schedule_skips_product_with_photo_already(db_session, monkeypatch):
    product = _mk(
        db_session,
        name="Товар со ссылкой и фото",
        photo_url="https://example.com/b.jpg",
        photo_mime="image/webp",
        photo_size=123,
    )
    await db_session.commit()

    _patch_session_and_queue(monkeypatch, db_session)
    db_session._pending_autofetch_coros = []

    mock_download = AsyncMock(return_value=(True, None, None))
    monkeypatch.setattr(autofetch_module, "download_and_save_photo", mock_download)

    schedule_photo_fetch(db_session, [product.id])
    assert len(db_session._pending_autofetch_coros) == 1
    await db_session._pending_autofetch_coros[0]()

    mock_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_skips_product_without_link(db_session, monkeypatch):
    product = _mk(db_session, name="Товар без ссылки вовсе")
    await db_session.commit()

    _patch_session_and_queue(monkeypatch, db_session)
    db_session._pending_autofetch_coros = []

    mock_download = AsyncMock(return_value=(True, None, None))
    monkeypatch.setattr(autofetch_module, "download_and_save_photo", mock_download)

    schedule_photo_fetch(db_session, [product.id])
    await db_session._pending_autofetch_coros[0]()

    mock_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_with_no_ids_does_not_queue(db_session, monkeypatch):
    _patch_session_and_queue(monkeypatch, db_session)
    db_session._pending_autofetch_coros = []

    schedule_photo_fetch(db_session, [])
    assert db_session._pending_autofetch_coros == []
