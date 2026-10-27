#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разъезд уже загруженного Product.article на store_article истории цены —
владелец, 27.10.2026 (задача manufacturer_article/store_article).

ПОВОД. До этой задачи item.article смешивал два понятия: артикул
ПРОИЗВОДИТЕЛЯ (одинаковый во всех магазинах) и номер товара в КОНКРЕТНОМ
магазине (свой у каждого магазина). Исторически загруженные товары, у
которых price_source_contractor_id указывает на магазин с
article_is_manufacturer=False (Сима-ленд, Бауцентр и остальные — см.
app/services/catalog_gala/stores.py), на самом деле несут в Product.article
номер магазина, а не производителя — это поле нужно разъехать на
store_article строк истории цены (ProductPriceHistory), откуда его теперь
читает products_import_match.py (критерий (0) сопоставления).

ОТБОР. Product.article непустой И price_source_contractor_id указывает на
контрагента с известным ИНН, у которого article_is_manufacturer_for_inn(inn)
== False (включая НЕИЗВЕСТНЫЙ ИНН/контрагента — безопасный дефолт "не
производитель", тот же, что у stores.article_is_manufacturer_for_inn).
Товары, где магазин — article_is_manufacturer=True (МПО Электромонтаж,
k-spasatel.ru), этот скрипт НЕ трогает вовсе.

ЧТО ДЕЛАЕТ (--apply). Для каждого отобранного товара:
  1. Переносит значение article в store_article строк product_price_history
     ЭТОГО товара с тем же contractor_id (= price_source_contractor_id) и
     source='import', у которых store_article сейчас пуст.
  2. Только если у товара есть хотя бы одна такая строка истории (иначе
     перенос был бы безвозвратной потерей значения — article НЕ очищается,
     товар считается отдельно и не трогается).
  3. Product.article становится NULL.

БЕЗ --apply (дефолт) — ТОЛЬКО пробный прогон, ничего не пишет в БД: печатает
сколько товаров затронется по каждому магазину, 5 примеров, сколько строк
истории получат store_article, и сколько товаров НЕ тронется (нет строки
истории этого магазина с source='import').

--apply пишет порциями по 5000 товаров (BATCH_SIZE), коммит на каждую
порцию, печатает прогресс по порциям. Перенос делается одним UPDATE...FROM
на порцию (не по одному товару) — для ускорения на боевом объёме.

Запуск (backend-код смонтирован, перезапуск контейнера не нужен):
  docker compose -p vsks_crm exec -T backend_a python scripts/split_store_articles.py
  docker compose -p vsks_crm exec -T backend_a python scripts/split_store_articles.py --apply
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import bindparam, select, text, tuple_  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.contractor import Contractor  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_price_history import ProductPriceHistory  # noqa: E402
from app.services.catalog_gala.stores import article_is_manufacturer_for_inn  # noqa: E402
from app.utils.chunking import chunked  # noqa: E402

BATCH_SIZE = 5000


async def _collect_candidates(db):
    """Возвращает список (product_id, product_name, article, contractor_id,
    inn) — товары с непустым article, чей price_source_contractor_id
    указывает на магазин НЕ-производителя (см. докстринг модуля)."""
    rows = (await db.execute(
        select(
            Product.id, Product.name, Product.article,
            Product.price_source_contractor_id, Contractor.inn,
        )
        .join(Contractor, Contractor.id == Product.price_source_contractor_id)
        .where(Product.article.isnot(None), Product.article != "")
    )).all()
    return [
        (pid, name, article, contractor_id, inn)
        for pid, name, article, contractor_id, inn in rows
        if not article_is_manufacturer_for_inn(inn)
    ]


async def _history_row_counts(db, pairs) -> dict:
    """Для набора (product_id, contractor_id) — число строк
    product_price_history с source='import' и пустым store_article (те, что
    получат store_article при --apply). Пара без строк не попадает в
    результат (а не 0) — удобно отличать has_history от no_history ниже."""
    valid_pairs = [(pid, cid) for pid, cid in pairs if pid is not None and cid is not None]
    if not valid_pairs:
        return {}
    counts: dict = {}
    for chunk in chunked(valid_pairs):
        rows = (await db.execute(
            select(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id)
            .where(
                tuple_(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id).in_(chunk),
                ProductPriceHistory.source == "import",
                ProductPriceHistory.store_article.is_(None),
            )
        )).all()
        for product_id, contractor_id in rows:
            key = (product_id, contractor_id)
            counts[key] = counts.get(key, 0) + 1
    return counts


async def dry_run(db) -> None:
    candidates = await _collect_candidates(db)
    if not candidates:
        print("Нет товаров-кандидатов (article пуст либо магазин — производитель).")
        return

    counts = await _history_row_counts(db, [(pid, cid) for pid, _, _, cid, _ in candidates])

    by_store_affected: dict = {}
    by_store_no_history: dict = {}
    total_history_rows = 0
    examples = []
    no_history_total = 0

    for pid, name, article, cid, inn in candidates:
        key = (pid, cid)
        n = counts.get(key, 0)
        store_label = inn or "неизвестный магазин"
        if n > 0:
            by_store_affected[store_label] = by_store_affected.get(store_label, 0) + 1
            total_history_rows += n
            if len(examples) < 5:
                examples.append((name, article))
        else:
            by_store_no_history[store_label] = by_store_no_history.get(store_label, 0) + 1
            no_history_total += 1

    print("=== Пробный прогон split_store_articles.py (ничего не записано) ===")
    print("\nТоваров затронется (есть строка истории этого магазина, article → store_article):")
    for store, n in sorted(by_store_affected.items(), key=lambda kv: -kv[1]):
        print(f"  {store}: {n}")
    print(f"  ИТОГО товаров затронется: {sum(by_store_affected.values())}")

    print("\nПримеры (товар — article — станет store_article):")
    for name, article in examples:
        print(f"  {name} — {article} — {article}")

    print(f"\nСтрок истории получат store_article: {total_history_rows}")

    print("\nТоваров НЕ тронется (нет строки истории source='import' этого магазина — article останется как есть):")
    for store, n in sorted(by_store_no_history.items(), key=lambda kv: -kv[1]):
        print(f"  {store}: {n}")
    print(f"  ИТОГО без истории: {no_history_total}")


async def apply(db) -> None:
    candidates = await _collect_candidates(db)
    counts = await _history_row_counts(db, [(pid, cid) for pid, _, _, cid, _ in candidates])
    affected_ids = [pid for pid, _, _, cid, _ in candidates if counts.get((pid, cid), 0) > 0]

    if not affected_ids:
        print("Нет товаров для переноса — ничего не сделано.")
        return

    update_history_stmt = text(
        """
        UPDATE product_price_history pph
        SET store_article = p.article
        FROM products p
        WHERE pph.product_id = p.id
          AND pph.contractor_id = p.price_source_contractor_id
          AND pph.source = 'import'
          AND pph.store_article IS NULL
          AND p.id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    clear_article_stmt = text(
        "UPDATE products SET article = NULL WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))

    batches = list(chunked(affected_ids, BATCH_SIZE))
    for i, batch in enumerate(batches, start=1):
        await db.execute(update_history_stmt, {"ids": batch})
        await db.execute(clear_article_stmt, {"ids": batch})
        await db.commit()
        print(f"Порция {i}/{len(batches)}: {len(batch)} товаров обработано.")

    print(f"\nГотово: {len(affected_ids)} товаров перенесены (article -> store_article), article очищен.")


async def main_async(do_apply: bool) -> None:
    async with async_session() as db:
        if do_apply:
            await apply(db)
        else:
            await dry_run(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="реально писать в БД (порциями, см. докстринг)")
    args = parser.parse_args()
    asyncio.run(main_async(args.apply))


if __name__ == "__main__":
    main()
