#!/usr/bin/env python3
"""Пережать все фото каталога через единую функцию сжатия (владелец,
26.10.2026, порог обновлён 29.10.2026 — см. MAX_SIDE_PX в
app/services/product_photo_compress.py, НЕ дублируем число здесь): длинная
сторона ≤MAX_SIDE_PX, WebP ~75. Применяется к уже закэшированным в
product_photos байтам — фото, которые туда попали ДО введения правила
(старые JPEG/PNG оригиналы) или которые по какой-то причине больше
MAX_SIDE_PX/не WebP (в т.ч. старые фото, сжатые ПОД ПРЕЖНИЙ порог 400px, до
29.10.2026).

Идемпотентен: если результат сжатия не меньше исходного И исходное фото
уже WebP ≤MAX_SIDE_PX — строка не трогается (is_already_compressed).

НЕ запускать на проде без явного решения владельца — разовый перегон всех
фото каталога, дорогая операция.

Запуск (внутри контейнера backend):
    docker exec vsks_crm-backend_a-1 python -m scripts.recompress_product_photos --dry-run
    docker exec vsks_crm-backend_a-1 python -m scripts.recompress_product_photos --batch 200
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select, func  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product_photo import ProductPhoto  # noqa: E402
from app.services.product_photo_compress import compress_product_photo, is_already_compressed  # noqa: E402


async def _fetch_batch(db, after_id, batch_size):
    stmt = select(ProductPhoto).order_by(ProductPhoto.product_id).limit(batch_size)
    if after_id is not None:
        stmt = stmt.where(ProductPhoto.product_id > after_id)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


async def run(dry_run: bool, batch_size: int) -> int:
    async with async_session() as db:
        total = (await db.execute(select(func.count()).select_from(ProductPhoto))).scalar() or 0
    print(f"Всего фото в product_photos: {total}")

    processed = 0
    recompressed = 0
    skipped_already_ok = 0
    bytes_before = 0
    bytes_after = 0
    after_id = None

    while True:
        async with async_session() as db:
            rows = await _fetch_batch(db, after_id, batch_size)
        if not rows:
            break
        for row in rows:
            processed += 1
            after_id = row.product_id
            raw = bytes(row.data)
            if is_already_compressed(raw, row.mime):
                skipped_already_ok += 1
                continue
            try:
                new_bytes, new_mime = compress_product_photo(raw)
            except Exception as e:
                print(f"  [!] product_id={row.product_id}: ошибка сжатия — {e}")
                continue
            if len(new_bytes) >= len(raw) and (row.mime or "").lower() == "image/webp":
                # Уже не хуже — не трогаем (идемпотентность при повторных прогонах).
                skipped_already_ok += 1
                continue
            bytes_before += len(raw)
            bytes_after += len(new_bytes)
            recompressed += 1
            if not dry_run:
                async with async_session() as db:
                    obj = await db.get(ProductPhoto, row.product_id)
                    if obj is not None:
                        obj.data = new_bytes
                        obj.mime = new_mime
                        obj.size = len(new_bytes)
                        from app.models.product import Product
                        product = await db.get(Product, row.product_id)
                        if product is not None:
                            product.photo_mime = new_mime
                            product.photo_size = len(new_bytes)
                        await db.commit()
        if len(rows) < batch_size:
            break

    print(f"\nОбработано: {processed}")
    print(f"Пережато: {recompressed}")
    print(f"Уже в порядке (пропущено): {skipped_already_ok}")
    if recompressed:
        mb_before = bytes_before / (1024 * 1024)
        mb_after = bytes_after / (1024 * 1024)
        print(f"Было: {mb_before:.2f} МБ -> Стало: {mb_after:.2f} МБ (-{mb_before - mb_after:.2f} МБ)")
    if dry_run:
        print("\n[DRY-RUN] Изменения НЕ записаны. Повторите с --batch без --dry-run... "
              "(по умолчанию --dry-run выключен, см. аргументы).")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="только посчитать, не писать в БД")
    parser.add_argument("--batch", type=int, default=100, help="размер пачки (по умолчанию 100)")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.dry_run, args.batch)))


if __name__ == "__main__":
    main()
