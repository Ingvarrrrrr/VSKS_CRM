"""Автодокачка фото товара по внешней ссылке — ОДНА функция
(schedule_photo_fetch), вызываемая из ВСЕХ мест, где у товара появляется/
меняется photo_url/photo_link, а сохранённого фото ещё нет (владелец,
29.10.2026, решение «хранить, 200 px»: раз ссылка известна — не ждать,
пока кто-то руками нажмёт «Скачать фото»/зайдёт на download-photos).

ПРАВИЛО №6 — не второй механизм отложенного запуска: переиспользует
queue_after_commit (app/services/notify_after_commit.py) — тот же приём
«выполнить ПОСЛЕ реального commit текущей транзакции», которым уже
пользуются уведомления; откат транзакции (ROLLBACK/SAVEPOINT) отменяет и
скачивание, как и уведомление. Переиспользует download_and_save_photo/
pick_external_url (product_photo_download.py) и has_photo
(product_photo_store.py) — вторых копий этой логики не пишем.

Каждый товар скачивается в СВОЕЙ сессии БД (app.database.async_session) —
не держит сессию исходного HTTP-запроса (та уже закоммичена и может быть
закрыта к моменту, когда фоновая задача реально выполнится). Параллелизм
ограничен asyncio.Semaphore(4) — не заливать внешние магазины/CDN
одновременными запросами при массовом импорте. Ошибка по одному товару
логируется и не прерывает остальные (как и весь проект — фоновая задача не
должна ронять ничего, кроме себя)."""
import asyncio
import logging
from typing import Iterable

from app.database import async_session
from app.models.product import Product
from app.services.notify_after_commit import queue_after_commit
from app.services.product_photo_download import download_and_save_photo, pick_external_url
from app.services.product_photo_store import has_photo

logger = logging.getLogger(__name__)

MAX_CONCURRENT_DOWNLOADS = 4


def schedule_photo_fetch(db, product_ids: Iterable[int]) -> None:
    """Поставить скачивание фото для `product_ids` в очередь — выполнится
    ПОСЛЕ того, как `db` реально закоммитит текущую транзакцию (см.
    docstring модуля). Безвредно звать «на всякий случай» для товара без
    ссылки или уже с фото — проверка (pick_external_url/has_photo) делается
    внутри фоновой задачи, по СВЕЖИМ данным из новой сессии (не по
    значениям текущего объекта в памяти вызывающего — та сессия закоммитит
    только ПОСЛЕ этого вызова, и значения в текущей транзакции уже верны к
    моменту запуска очереди).

    Вызывающая сторона НЕ обязана сама проверять photo_url/has_photo перед
    вызовом — дёшево позвать для любого набора id после commit (создание/
    правка товара, импорт, взять из живого поиска)."""
    ids = [pid for pid in dict.fromkeys(product_ids) if pid]
    if not ids:
        return
    queue_after_commit(db, lambda: _fetch_many(ids))


async def _fetch_many(product_ids: list) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async def _guarded(product_id: int) -> None:
        async with semaphore:
            try:
                await _fetch_one(product_id)
            except Exception:
                logger.warning(
                    "product_photo_autofetch: ошибка для product_id=%s", product_id, exc_info=True,
                )

    await asyncio.gather(*(_guarded(pid) for pid in product_ids))


async def _fetch_one(product_id: int) -> None:
    async with async_session() as db:
        product = await db.get(Product, product_id)
        if product is None or has_photo(product):
            return
        url = pick_external_url(product)
        if not url:
            return
        ok, reason, message = await download_and_save_photo(product_id, url, db)
        if not ok:
            logger.info(
                "product_photo_autofetch: product_id=%s не скачано (%s): %s",
                product_id, reason, message,
            )
