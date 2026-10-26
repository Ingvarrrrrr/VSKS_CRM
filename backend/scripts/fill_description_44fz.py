#!/usr/bin/env python3
"""Массовое заполнение Product.description_44fz по характеристикам каталога
(владелец, 26.10.2026). Обрабатывает ТОЛЬКО товары с пустым description_44fz
(не трогает уже заполненные/верифицированные вручную).

Единственный генератор текста — app.services.product_tz_44fz.build_tz_44fz
(ПРАВИЛО №6, второй расчёт здесь не заводится); история правки — через
app.services.product_description_history.set_product_description, тот же
писатель, что и у PATCH-роутера (source='fill_empty').

ВСЕГДА --dry-run по умолчанию — только печатает счётчики и примеры, в БД
ничего не пишет. --apply переключает на запись порциями по 1000 с commit на
порцию.

Запуск (внутри контейнера backend):
    docker compose -p vsks_crm exec backend_a python -m scripts.fill_description_44fz
    docker compose -p vsks_crm exec backend_a python -m scripts.fill_description_44fz --apply
    docker compose -p vsks_crm exec backend_a python -m scripts.fill_description_44fz --limit 500
    docker compose -p vsks_crm exec backend_a python -m scripts.fill_description_44fz --ids 1,2,3 --apply
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import or_, select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.product_description_history import set_product_description  # noqa: E402
from app.services.product_tz_44fz import build_tz_44fz  # noqa: E402
from app.services.product_tz_44fz_brands import collect_catalog_brands  # noqa: E402

BATCH_SIZE = 1000
AUTOGEN_SOURCE = "fill_empty"  # app.services.product_description_history.Source


def _empty_description_44fz_filter():
    # Пустое поле — NULL или строка из одних пробелов (та же трактовка
    # "пусто", что у set_product_description.normalized_old/new).
    return or_(Product.description_44fz.is_(None), Product.description_44fz == "")


async def _fetch_batch(db, after_id, batch_size, ids):
    stmt = select(Product).where(_empty_description_44fz_filter()).order_by(Product.id)
    if ids is not None:
        stmt = stmt.where(Product.id.in_(ids))
    if after_id is not None:
        stmt = stmt.where(Product.id > after_id)
    stmt = stmt.limit(batch_size)
    return (await db.execute(stmt)).scalars().all()


async def run(dry_run: bool, limit, ids, batch_size: int) -> int:
    # Каталожный набор брендов (ревью 26.10.2026, п.1) — собирается ОДИН раз
    # на весь прогон скрипта (один полный скан products), а не на каждый
    # товар (ПРАВИЛО №6: единственный загрузчик — product_tz_44fz_brands.py).
    async with async_session() as db:
        brands = await collect_catalog_brands(db)
    print(f"Каталожных брендов (manufacturer + характеристики Бренд/Производитель/Торговая марка): {len(brands)}")

    filled = 0
    skipped_no_data = 0
    needs_review_count = 0
    examples = []
    after_id = None
    processed = 0

    while True:
        remaining = None if limit is None else max(0, limit - processed)
        if remaining == 0:
            break
        this_batch = batch_size if remaining is None else min(batch_size, remaining)

        async with async_session() as db:
            rows = await _fetch_batch(db, after_id, this_batch, ids)
            if not rows:
                break
            for product in rows:
                processed += 1
                after_id = product.id
                text, needs_review = build_tz_44fz(
                    name=product.name,
                    characteristics=product.characteristics,
                    description=product.description,
                    manufacturer=product.manufacturer,
                    article=product.article,
                    brands=brands,
                    product_type=product.product_type,
                )
                if not text:
                    skipped_no_data += 1
                    continue
                filled += 1
                if needs_review:
                    needs_review_count += 1
                if len(examples) < 5:
                    examples.append((product.id, product.name, text, needs_review))
                if not dry_run:
                    await set_product_description(
                        db, product, "description_44fz", text, user=None,
                        source=AUTOGEN_SOURCE,
                    )
            if not dry_run:
                await db.commit()
        if len(rows) < this_batch:
            break

    print(f"Обработано товаров с пустым description_44fz: {processed}")
    print(f"Заполнится: {filled}")
    print(f"  из них требуют проверки наименования (needs_review): {needs_review_count}")
    print(f"Пропущено (нет данных для ТЗ — ни характеристик, ни fallback из description): {skipped_no_data}")
    print("\nПримеры:")
    for pid, name, text, needs_review in examples:
        flag = " [needs_review]" if needs_review else ""
        print(f"\n--- product_id={pid} — {name}{flag} ---")
        print(text)

    if dry_run:
        print("\n[DRY-RUN] Изменения НЕ записаны. Повторите с --apply для реальной записи.")
    else:
        print(f"\nЗаписано в БД: {filled}")
    return 0


def _parse_ids(raw):
    if not raw:
        return None
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="реально записать (по умолчанию — dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="обработать не более N товаров")
    parser.add_argument("--ids", type=str, default=None, help="CSV id товаров, напр. 1,2,3")
    args = parser.parse_args()
    ids = _parse_ids(args.ids)
    sys.exit(asyncio.run(run(dry_run=not args.apply, limit=args.limit, ids=ids, batch_size=BATCH_SIZE)))


if __name__ == "__main__":
    main()
