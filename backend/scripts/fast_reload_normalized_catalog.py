"""Быстрая безблокировочная и потоковая (<50 МБ RAM) перезагрузка каталога на прод.

Гарантии:
1. Товары, привязанные к закупкам, договорам, заявкам и КП
   (таблица bk_20261118_protected_products), НИКОГДА не удаляются и не изменяются.
2. Чистые уже скачанные WebP-фото сохраняются во временную UNLOGGED таблицу по
   photo_link (исключая dirty_photo_ids) и сразу привязываются к новым карточкам.
3. Удаление непривязанных товаров и вставка новых идут потоково из .jsonl.gz
   батчами по 1000 карточек без загрузки всего каталога в оперативную память.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import gzip
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Iterator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import insert, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import DEFAULT_PRODUCT_CATEGORY, Product  # noqa: E402
from app.models.product_barcode import ProductBarcode  # noqa: E402
from app.models.product_price_history import ProductPriceHistory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.catalog_gala.stores import store_for_inn  # noqa: E402
from app.services.contractor_resolve import find_or_create_contractor  # noqa: E402
from app.services.product_protection import is_bad_photo_url  # noqa: E402


def _parse_date(s: str | None) -> dt.date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return dt.date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def _scan_inns_and_count(catalog_path: Path) -> tuple[set[str], int]:
    """Проход 1: потоковый сбор уникальных seller_inn и подсчёт строк (<2 МБ RAM)."""
    inns: set[str] = set()
    total = 0
    with gzip.open(catalog_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            it = json.loads(s)
            total += 1
            if it.get("seller_inn"):
                inns.add(it["seller_inn"])
            for pt in it.get("price_points") or ():
                if pt.get("seller_inn"):
                    inns.add(pt["seller_inn"])
    return inns, total


def _iter_jsonl_batches(catalog_path: Path, batch_size: int = 1000) -> Iterator[list[dict]]:
    """Проход 2: потоковый генератор батчей из .jsonl.gz."""
    batch: list[dict] = []
    with gzip.open(catalog_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            batch.append(json.loads(s))
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


async def _resolve_contractors(db, inns: set[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for inn in sorted(inns):
        info = store_for_inn(inn)
        cid = await find_or_create_contractor(
            db,
            info["name"] if info else inn,
            inn=inn,
            ogrn=info["ogrn"] if info else None,
            org_type=info["org_type"] if info else None,
        )
        mapping[inn] = cid
    await db.commit()
    return mapping


async def run_reload(catalog_path: Path, dirty_ids_path: Path, user_email: str) -> None:
    dirty_ids = set(json.loads(dirty_ids_path.read_text(encoding="utf-8"))) if dirty_ids_path.exists() else set()
    print(f"Грязных фото к исключению из кэша: {len(dirty_ids)}", flush=True)

    inns, total_items = _scan_inns_and_count(catalog_path)
    print(f"Карточек к потоковой загрузке: {total_items}, уникальных ИНН: {len(inns)}", flush=True)

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none()
        if not user:
            raise RuntimeError(f"Пользователь {user_email!r} не найден")
        user_id = user.id
        user_name = user.full_name or user.username or user_email

        cnt_prot = (await db.execute(text("SELECT count(*) FROM bk_20261118_protected_products"))).scalar_one()
        if cnt_prot == 0:
            raise RuntimeError("Таблица bk_20261118_protected_products пуста — остановка во избежание потери данных!")
        print(f"Защищённых товаров в бэкап-таблице: {cnt_prot}", flush=True)

        inn_to_cid = await _resolve_contractors(db, inns)
        print(f"Разрезолвлено магазинов по ИНН: {len(inn_to_cid)}", flush=True)

        # 1. Сохраняем чистые фото по photo_link
        print("1. Сохранение кэша чистых фото во временную таблицу...", flush=True)
        await db.execute(text("DROP TABLE IF EXISTS tmp_clean_photo_by_url;"))
        await db.execute(text("""
            CREATE UNLOGGED TABLE tmp_clean_photo_by_url (
                photo_link TEXT PRIMARY KEY,
                data BYTEA NOT NULL,
                mime VARCHAR(50),
                size INTEGER NOT NULL
            );
        """))
        await db.commit()

        max_id = (await db.execute(text("SELECT coalesce(max(id), 0) FROM products"))).scalar_one()
        dirty_list = sorted(dirty_ids)
        for lo in range(0, max_id + 1, 25_000):
            hi = lo + 25_000
            await db.execute(text("""
                INSERT INTO tmp_clean_photo_by_url (photo_link, data, mime, size)
                SELECT DISTINCT ON (p.photo_link) p.photo_link, pp.data, pp.mime, pp.size
                FROM products p
                JOIN product_photos pp ON pp.product_id = p.id
                WHERE p.id > :lo AND p.id <= :hi
                  AND p.photo_link IS NOT NULL AND trim(p.photo_link) <> ''
                  AND p.photo_link NOT ILIKE '%avatars.mds.yandex.net%'
                  AND p.photo_link NOT ILIKE '%logo.svg%'
                  AND p.photo_link NOT ILIKE '%nophoto%'
                  AND p.photo_link NOT ILIKE '%shansk-spasatel%'
                  AND NOT (p.id = ANY(:dirty_ids))
                ORDER BY p.photo_link, p.id
                ON CONFLICT (photo_link) DO NOTHING;
            """), {"lo": lo, "hi": hi, "dirty_ids": dirty_list})
            await db.commit()
        cached_cnt = (await db.execute(text("SELECT count(*) FROM tmp_clean_photo_by_url"))).scalar_one()
        print(f"   Сохранено уникальных чистых фото в кэш: {cached_cnt}", flush=True)

        # 2. Пакетный снос непривязанных товаров
        print("2. Пакетное удаление непривязанных товаров...", flush=True)
        deleted_total = 0
        for lo in range(0, max_id + 1, 10_000):
            hi = lo + 10_000
            res = await db.execute(text("""
                DELETE FROM products
                WHERE id > :lo AND id <= :hi
                  AND id NOT IN (SELECT id FROM bk_20261118_protected_products);
            """), {"lo": lo, "hi": hi})
            deleted_total += res.rowcount or 0
            await db.commit()
        rem_cnt = (await db.execute(text("SELECT count(*) FROM products"))).scalar_one()
        print(f"   Удалено непривязанных: {deleted_total}, осталось в products (только защищённые): {rem_cnt}", flush=True)

        # 3. Потоковая пакетная вставка нормализованного каталога (батч 1000)
        print("3. Потоковая вставка нормализованных карточек...", flush=True)
        now_dt = dt.datetime.utcnow()
        today_d = dt.date.today()
        import_note = f"Нормализация каталога (скрипт), {user_name}, {now_dt.strftime('%d.%m.%Y %H:%M')}"
        inserted_total = 0
        photos_linked = 0

        for batch_no, chunk in enumerate(_iter_jsonl_batches(catalog_path, 1000), 1):
            prod_rows = []
            for it in chunk:
                plink = it.get("photo_link")
                if plink and is_bad_photo_url(plink):
                    plink = None
                p_date = _parse_date(it.get("price_date"))
                price_val = Decimal(str(round(float(it["price"]), 2))) if it.get("price") else None
                cid = inn_to_cid.get(it.get("seller_inn") or "")
                prod_rows.append({
                    "name": it["name"],
                    "description": it.get("description"),
                    "category": (it.get("category") or DEFAULT_PRODUCT_CATEGORY)[:200],
                    "product_type": (it.get("product_type") or "")[:200] or None,
                    "unit": (it.get("unit") or "")[:50] or None,
                    "item_kind": (it.get("item_kind") or "товар")[:20],
                    "is_reusable": True,
                    "is_active": True,
                    "photo_link": plink[:1000] if plink else None,
                    "clarification_link": (it.get("clarification_link") or "")[:1000] or None,
                    "manufacturer": (it.get("manufacturer") or "")[:300] or None,
                    "article": (it.get("article") or "")[:200] or None,
                    "country_origin": (it.get("country_origin") or "")[:100] or None,
                    "characteristics": it.get("characteristics") or [],
                    "price": price_val,
                    "price_links": it.get("price_links") or [],
                    "price_source": "import" if price_val else None,
                    "price_source_ref": (it.get("price_source_ref") or "")[:1000] or None,
                    "price_source_contractor_id": cid,
                    "price_updated_at": dt.datetime.combine(p_date or today_d, dt.time.min) if price_val else None,
                    "import_note": import_note,
                    "updated_at": now_dt,
                    "updated_by": user_name[:200],
                })

            ret = (await db.execute(
                insert(Product).returning(Product.id, Product.photo_link),
                prod_rows,
            )).all()
            inserted_total += len(ret)

            hist_rows = []
            bc_rows = []
            new_pids = []
            for (new_id, _plink), it in zip(ret, chunk):
                new_pids.append(new_id)
                for pt in it.get("price_points") or []:
                    hist_rows.append({
                        "product_id": new_id,
                        "price": Decimal(str(round(float(pt["price"]), 2))),
                        "source": "import",
                        "source_ref": (pt.get("url") or "")[:1000] or None,
                        "contractor_id": inn_to_cid.get(pt.get("seller_inn") or ""),
                        "collected_at": _parse_date(pt.get("collected_at")) or today_d,
                        "created_by": user_id,
                        "store_article": (pt.get("store_article") or "")[:200] or None,
                    })
                for bc in it.get("barcodes") or []:
                    bc_rows.append({
                        "product_id": new_id,
                        "barcode": bc[:14],
                        "contractor_id": inn_to_cid.get(it.get("seller_inn") or ""),
                    })

            if hist_rows:
                await db.execute(insert(ProductPriceHistory), hist_rows)
            if bc_rows:
                await db.execute(
                    pg_insert(ProductBarcode).on_conflict_do_nothing(
                        constraint="uq_product_barcodes_product_barcode"
                    ),
                    bc_rows,
                )

            linked_res = await db.execute(text("""
                INSERT INTO product_photos (product_id, data, mime, size, updated_at)
                SELECT p.id, c.data, c.mime, c.size, :now_dt
                FROM products p
                JOIN tmp_clean_photo_by_url c ON c.photo_link = p.photo_link
                WHERE p.id = ANY(:pids)
                ON CONFLICT (product_id) DO NOTHING;
            """), {"pids": new_pids, "now_dt": now_dt})
            photos_linked += linked_res.rowcount or 0
            await db.execute(text("""
                UPDATE products p
                SET photo_mime = pp.mime, photo_size = pp.size
                FROM product_photos pp
                WHERE pp.product_id = p.id AND p.id = ANY(:pids);
            """), {"pids": new_pids})
            await db.commit()
            if batch_no % 10 == 0 or inserted_total == total_items:
                print(f"   загружено {inserted_total}/{total_items}, привязано кэш-фото: {photos_linked}", flush=True)

        await db.execute(text("DROP TABLE IF EXISTS tmp_clean_photo_by_url;"))
        await db.execute(text("SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT coalesce(max(id), 1) FROM products));"))
        await db.commit()

    print(f"Готово: вставлено={inserted_total}, привязано из кэша фото={photos_linked}.", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--dirty-ids", required=True)
    ap.add_argument("--user-email", required=True)
    args = ap.parse_args()
    asyncio.run(run_reload(Path(args.catalog), Path(args.dirty_ids), args.user_email))


if __name__ == "__main__":
    main()
