#!/usr/bin/env python3
"""Запускается на сервере/в контейнере: берёт папку <id>.webp (скачанную и
сжатую локально scripts/fetch_photos_local.py) и сохраняет их через
app.services.product_photo_store.save_product_photo — ЕДИНСТВЕННУЮ точку
записи (ПРАВИЛО №6). save_product_photo сам сжимает повторно, но
compress_product_photo идемпотентна для уже-WebP-≤400px входа (не портит
то, что уже готово).

Пропускает:
  - файлы, чьё имя не <число>.<ext>;
  - id, которых нет среди products;
  - товары, у которых фото уже есть (не перезатираем существующее без спроса —
    тот же принцип, что у download-photos: заполняем пустое, не трогаем занятое).

Запуск (внутри контейнера backend; папку предварительно docker cp):
    docker cp photos/ vsks_crm-backend_a-1:/tmp/photos/
    docker exec vsks_crm-backend_a-1 python -m scripts.import_photos_dir /tmp/photos
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.product_photo_store import has_photo, save_product_photo  # noqa: E402


def _iter_files(directory: str):
    for fname in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in (".webp", ".jpg", ".jpeg", ".png"):
            continue
        if not stem.isdigit():
            continue
        yield int(stem), os.path.join(directory, fname)


async def run(directory: str, overwrite: bool) -> int:
    imported, skipped_no_product, skipped_has_photo, errors = 0, 0, 0, 0
    async with async_session() as db:
        for product_id, path in _iter_files(directory):
            product = await db.get(Product, product_id)
            if product is None:
                skipped_no_product += 1
                continue
            if has_photo(product) and not overwrite:
                skipped_has_photo += 1
                continue
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                await save_product_photo(db, product, raw)
                await db.commit()
                imported += 1
            except Exception as e:
                await db.rollback()
                print(f"  [!] id={product_id}: {e}")
                errors += 1

    print(f"Импортировано: {imported}")
    print(f"Пропущено (товар не найден): {skipped_no_product}")
    print(f"Пропущено (фото уже есть): {skipped_has_photo}")
    print(f"Ошибок: {errors}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="папка с файлами <id>.webp")
    parser.add_argument("--overwrite", action="store_true", help="перезаписать уже существующие фото")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.directory, args.overwrite)))


if __name__ == "__main__":
    main()
