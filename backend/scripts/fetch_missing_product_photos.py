#!/usr/bin/env python3
"""Разовый прогон: скачать фото для ВСЕХ товаров каталога, у которых есть
внешняя ссылка (photo_url/photo_link) и ЕЩЁ НЕТ сохранённого фото (владелец,
29.10.2026, задача «фото 200 px», п. «разовый прогон»).

ПРАВИЛО №6 — не вторая копия ядра скачивания: переиспользует ТЕ ЖЕ функции,
что и POST /api/products/download-photos (app/routers/products_photos.py::
download_all_photos) и фоновую автодокачку (app/services/
product_photo_autofetch.py) — pick_external_url/download_and_save_photo
(app/services/product_photo_download.py) и has_photo
(app/services/product_photo_store.py). Разница с download_all_photos —
только: (1) параллелизм (asyncio.Semaphore, по умолчанию 4, не
последовательный проход), (2) сгруппированный отчёт по причинам ошибок в
stdout вместо JSON-ответа HTTP, (3) свободный запуск без входа в систему
(это offline-скрипт, не эндпоинт).

НЕ ЗАПУСКАТЬ НА ПРОДЕ без явного решения владельца — массовое обращение к
внешним магазинам/CDN за один прогон.

Запуск (внутри контейнера backend, на DEV-стенде):
    docker exec vsks_crm-backend_a-1 python -m scripts.fetch_missing_product_photos
    docker exec vsks_crm-backend_a-1 python -m scripts.fetch_missing_product_photos --concurrency 4 --limit 500
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.product_photo_download import download_and_save_photo, pick_external_url  # noqa: E402
from app.services.product_photo_store import has_photo  # noqa: E402

DEFAULT_CONCURRENCY = 4


async def _candidate_ids(limit: int | None) -> list[int]:
    """Товары с (возможной) внешней ссылкой и БЕЗ сохранённого фото —
    photo_size IS NULL — тот же признак has_photo(), см. docstring модуля;
    photo_url/photo_link проверяются по строке позже (pick_external_url
    решает, ЧТО из двух полей валидный http(s)-источник, Правило №6)."""
    async with async_session() as db:
        stmt = select(Product.id).where(
            Product.photo_size.is_(None),
            (Product.photo_url.is_not(None)) | (Product.photo_link.is_not(None)),
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows)


async def _process_one(product_id: int, results: dict, lock: asyncio.Lock) -> None:
    async with async_session() as db:
        product = await db.get(Product, product_id)
        if product is None or has_photo(product):
            async with lock:
                results["skipped"] += 1
            return
        url = pick_external_url(product)
        if not url:
            async with lock:
                results["skipped"] += 1
            return
        ok, reason, message = await download_and_save_photo(product_id, url, db)
        async with lock:
            results["attempted"] += 1
            if ok:
                results["downloaded"] += 1
            else:
                by_reason = results["errors_by_reason"]
                by_reason[reason] = by_reason.get(reason, 0) + 1
                if len(results["error_samples"]) < 20:
                    results["error_samples"].append(
                        {"id": product_id, "name": product.name, "reason": reason, "message": message}
                    )


async def run(concurrency: int, limit: int | None) -> int:
    ids = await _candidate_ids(limit)
    print(f"Кандидатов (есть ссылка, нет сохранённого фото): {len(ids)}")
    if not ids:
        return 0

    results = {
        "attempted": 0, "downloaded": 0, "skipped": 0,
        "errors_by_reason": {}, "error_samples": [],
    }
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def _guarded(pid: int) -> None:
        async with semaphore:
            try:
                await _process_one(pid, results, lock)
            except Exception as e:
                async with lock:
                    results["errors_by_reason"]["exception"] = results["errors_by_reason"].get("exception", 0) + 1
                    if len(results["error_samples"]) < 20:
                        results["error_samples"].append({"id": pid, "name": None, "reason": "exception", "message": str(e)})

    await asyncio.gather(*(_guarded(pid) for pid in ids))

    print(f"\nПопыток скачать: {results['attempted']}")
    print(f"Скачано: {results['downloaded']}")
    print(f"Пропущено (фото уже есть/ссылки не оказалось): {results['skipped']}")
    if results["errors_by_reason"]:
        print("Ошибки по причинам:")
        for reason, count in sorted(results["errors_by_reason"].items(), key=lambda kv: -kv[1]):
            print(f"  {reason}: {count}")
        print("Примеры (до 20):")
        for sample in results["error_samples"]:
            print(f"  id={sample['id']} {sample['name']!r} [{sample['reason']}] {sample['message']}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="параллельных скачиваний (по умолчанию 4)")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число кандидатов (по умолчанию — все)")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.concurrency, args.limit)))


if __name__ == "__main__":
    main()
