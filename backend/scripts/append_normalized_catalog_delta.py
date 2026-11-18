"""Потоковая доливка и склейка дельты каталога (electro-mpo, vkusvill и др.)
на прод без сноса действующей базы и без изменения защищённых товаров.

Логика для каждой записи:
1. Если совпадает (norm_key имени или бренд+артикул) с защищённым товаром
   (load_protected_product_ids ∪ bk_20261118_protected_products) — пропуск.
2. Если совпадает с существующей непривязанной карточкой — склейка в одну:
   merge_price_links, merge_characteristics, дозаполнение пустых полей и
   добавление строки цены в product_price_history.
3. Иначе — вставка новой карточки в products, product_price_history и barcodes.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import gzip
import json
import os
import re
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
from app.services.brand_code_fold import fold_brand_or_code  # noqa: E402
from app.services.catalog_gala.stores import store_for_inn  # noqa: E402
from app.services.contractor_resolve import find_or_create_contractor  # noqa: E402
from app.services.product_name_signature import merge_characteristics, merge_price_links  # noqa: E402
from app.services.product_protection import is_bad_photo_url, load_protected_product_ids  # noqa: E402
from app.services.product_tech_description import build_tech_description  # noqa: E402

_WS_RE = re.compile(r"\s+")


def _norm_key(name: str | None) -> str:
    return _WS_RE.sub(" ", (name or "").strip().lower()).strip()


def _parse_date(s: str | None) -> dt.date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return dt.date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def _scan_inns(path: Path) -> set[str]:
    inns: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            it = json.loads(s)
            if it.get("seller_inn"):
                inns.add(it["seller_inn"])
            for pt in it.get("price_points") or ():
                if pt.get("seller_inn"):
                    inns.add(pt["seller_inn"])
    return inns


def _iter_batches(path: Path, size: int = 500) -> Iterator[list[dict]]:
    batch: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            batch.append(json.loads(s))
            if len(batch) >= size:
                yield batch
                batch = []
    if batch:
        yield batch


async def _resolve_contractors(db, inns: set[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for inn in sorted(inns):
        info = store_for_inn(inn)
        mapping[inn] = await find_or_create_contractor(
            db,
            info["name"] if info else inn,
            inn=inn,
            ogrn=info["ogrn"] if info else None,
            org_type=info["org_type"] if info else None,
        )
    await db.commit()
    return mapping


async def _load_existing_index(db, protected_ids: set[int]) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    by_nk: dict[str, int] = {}
    by_ma: dict[tuple[str, str], int] = {}
    max_id = (await db.execute(text("SELECT coalesce(max(id), 0) FROM products"))).scalar_one()
    for lo in range(0, max_id + 1, 25_000):
        hi = lo + 25_000
        rows = (await db.execute(text("""
            SELECT id, name, manufacturer, article
            FROM products
            WHERE id > :lo AND id <= :hi AND is_active IS TRUE
        """), {"lo": lo, "hi": hi})).all()
        for pid, name, mfr, art in rows:
            nk = _norm_key(name)
            if nk and (nk not in by_nk or (by_nk[nk] in protected_ids and pid not in protected_ids)):
                by_nk[nk] = pid
            mf = fold_brand_or_code(mfr)
            af = fold_brand_or_code(art)
            if mf and af:
                key = (mf, af)
                if key not in by_ma or (by_ma[key] in protected_ids and pid not in protected_ids):
                    by_ma[key] = pid
    return by_nk, by_ma


def _hist_rows_for(pid: int, it: dict, inn_to_cid: dict[str, int], today_d: dt.date, user_id: int) -> list[dict]:
    rows = []
    for pt in it.get("price_points") or ():
        if not pt.get("price"):
            continue
        rows.append({
            "product_id": pid,
            "price": Decimal(str(round(float(pt["price"]), 2))),
            "source": "import",
            "source_ref": (pt.get("url") or "")[:1000] or None,
            "contractor_id": inn_to_cid.get(pt.get("seller_inn") or ""),
            "collected_at": _parse_date(pt.get("collected_at")) or today_d,
            "created_by": user_id,
            "store_article": (pt.get("store_article") or "")[:200] or None,
        })
    return rows


async def run_append(catalog_path: Path, user_email: str) -> None:
    inns = _scan_inns(catalog_path)
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none()
        if not user:
            raise RuntimeError(f"Пользователь {user_email!r} не найден")
        user_id = user.id
        user_name = user.full_name or user.username or user_email

        bk_rows = (await db.execute(text("SELECT id FROM bk_20261118_protected_products"))).scalars().all()
        protected_ids = (await load_protected_product_ids(db)) | {int(x) for x in bk_rows}
        print(f"Защищённых товаров (активные + бэкап): {len(protected_ids)}", flush=True)

        inn_to_cid = await _resolve_contractors(db, inns)
        by_nk, by_ma = await _load_existing_index(db, protected_ids)
        print(f"Индекс существующих товаров: names={len(by_nk)}, brand+art={len(by_ma)}", flush=True)

        now_dt = dt.datetime.utcnow()
        today_d = dt.date.today()
        import_note = f"Доливка МПО+ВкусВилл, {user_name}, {now_dt.strftime('%d.%m.%Y %H:%M')}"

        inserted = merged_existing = skipped_prot = hist_added = 0

        for chunk in _iter_batches(catalog_path, 500):
            to_insert: list[dict] = []
            to_merge: list[tuple[int, dict]] = []

            for it in chunk:
                nk = _norm_key(it.get("name"))
                mf = fold_brand_or_code(it.get("manufacturer"))
                af = fold_brand_or_code(it.get("article"))
                target_id = by_nk.get(nk) or (by_ma.get((mf, af)) if mf and af else None)

                if target_id is not None:
                    if target_id in protected_ids:
                        skipped_prot += 1
                    else:
                        to_merge.append((target_id, it))
                else:
                    to_insert.append(it)

            if to_merge:
                merge_ids = list({pid for pid, _ in to_merge})
                cur_rows = (await db.execute(select(Product).where(Product.id.in_(merge_ids)))).scalars().all()
                by_id = {p.id: p for p in cur_rows}
                existing_hist = {
                    (r[0], r[1], r[2])
                    for r in (await db.execute(
                        select(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id, ProductPriceHistory.source_ref)
                        .where(ProductPriceHistory.product_id.in_(merge_ids))
                    )).all()
                }
                hist_rows = []
                for pid, it in to_merge:
                    p = by_id.get(pid)
                    if not p or pid in protected_ids:
                        continue
                    merged_links = merge_price_links(p.price_links or [], it.get("price_links") or [])
                    if merged_links != (p.price_links or []):
                        p.price_links = merged_links
                    new_chars = merge_characteristics(p.characteristics or [], it.get("characteristics") or [])
                    if new_chars != (p.characteristics or []):
                        p.characteristics = new_chars
                        if not (p.description or "").strip():
                            p.description = build_tech_description(new_chars)
                    elif not (p.description or "").strip() and it.get("description"):
                        p.description = it["description"]

                    field_limits = {"manufacturer": 300, "article": 200, "product_type": 200, "clarification_link": 1000}
                    for field, max_len in field_limits.items():
                        if not getattr(p, field) and it.get(field):
                            setattr(p, field, str(it[field])[:max_len])
                    if (not p.category or p.category == DEFAULT_PRODUCT_CATEGORY) and it.get("category"):
                        p.category = str(it["category"])[:200]
                    if not p.photo_link and it.get("photo_link") and not is_bad_photo_url(it["photo_link"]):
                        p.photo_link = it["photo_link"][:1000]
                    if (p.price is None or p.price <= 0) and it.get("price"):
                        p.price = Decimal(str(round(float(it["price"]), 2)))
                        p.price_source = "import"
                        p.price_source_ref = (it.get("price_source_ref") or "")[:1000] or None
                        p.price_source_contractor_id = inn_to_cid.get(it.get("seller_inn") or "")
                        p.price_updated_at = now_dt

                    for hr in _hist_rows_for(pid, it, inn_to_cid, today_d, user_id):
                        sig = (hr["product_id"], hr["contractor_id"], hr["source_ref"])
                        if sig not in existing_hist:
                            existing_hist.add(sig)
                            hist_rows.append(hr)
                    merged_existing += 1
                if hist_rows:
                    await db.execute(insert(ProductPriceHistory), hist_rows)
                    hist_added += len(hist_rows)

            if to_insert:
                prod_rows = []
                for it in to_insert:
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
                ret = (await db.execute(insert(Product).returning(Product.id), prod_rows)).scalars().all()
                inserted += len(ret)
                hist_rows = []
                bc_rows = []
                for new_id, it in zip(ret, to_insert):
                    nk = _norm_key(it.get("name"))
                    if nk:
                        by_nk[nk] = new_id
                    mf = fold_brand_or_code(it.get("manufacturer"))
                    af = fold_brand_or_code(it.get("article"))
                    if mf and af:
                        by_ma[(mf, af)] = new_id
                    hist_rows.extend(_hist_rows_for(new_id, it, inn_to_cid, today_d, user_id))
                    for bc in it.get("barcodes") or ():
                        bc_rows.append({"product_id": new_id, "barcode": bc[:14], "contractor_id": inn_to_cid.get(it.get("seller_inn") or "")})
                if hist_rows:
                    await db.execute(insert(ProductPriceHistory), hist_rows)
                    hist_added += len(hist_rows)
                if bc_rows:
                    await db.execute(
                        pg_insert(ProductBarcode).on_conflict_do_nothing(constraint="uq_product_barcodes_product_barcode"),
                        bc_rows,
                    )

            await db.commit()

        await db.execute(text("SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT coalesce(max(id), 1) FROM products));"))
        await db.commit()
    print(f"Готово: вставлено новых={inserted}, дообогащено существующих={merged_existing}, пропущено защищённых={skipped_prot}, строк истории цен={hist_added}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--user-email", required=True)
    args = ap.parse_args()
    asyncio.run(run_append(Path(args.catalog), args.user_email))


if __name__ == "__main__":
    main()
