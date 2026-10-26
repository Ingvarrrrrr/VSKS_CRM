"""CLI: загрузка каталога товаров поставщиков из файлов формата GALA
(backend/app/services/catalog_gala/) в products — владелец, 2026-10-26.

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.load_gala_catalog --files a.gala.json b.gala.json \
        --user-email <email пользователя> [--dry-run] [--photos] [--photos-limit N]

Своей логики создания/обновления товаров этот скрипт НЕ пишет (ПРАВИЛО №6) —
он только:
  1. читает и валидирует каждый GALA-файл (validate_gala_catalog из
     services/catalog_gala/format.py); при ошибках валидации файл
     пропускается, остальные файлы обрабатываются;
  2. превращает items файла в data_rows/col_idx, которые понимает ЕДИНЫЙ
     цикл создания/обновления товаров — apply_products_import
     (services/products_import_apply.py), с supplier_description=True
     (описание строки = build_tech_description(характеристики, описание
     поставщика), characteristics/manufacturer/article заполняются по
     правилам этого режима — см. докстринг apply_products_import);
  3. (--photos) скачивает фото новым/обновлённым товарам без photo_data —
     тем же services/product_photo_download.py, которым пользуется
     POST /api/products/download-photos (routers/products_photos.py), не
     второй копией логики скачивания.

Каждый файл — своя транзакция (apply_products_import сам коммитит/
откатывает внутри вызова; --dry-run откатывает ВСЕ файлы). Файлы
обрабатываются по очереди, ошибка валидации одного файла не прерывает
остальные.

source_url → Product.clarification_link — поле, которого НЕТ в col_idx
apply_products_import (там нет подходящего маппинга), поэтому заполняется
отдельным быстрым проходом ПОСЛЕ apply() для файла, и только если
clarification_link у товара пуст (как и остальные "докидываемые" поля) — это
не второй механизм записи каталога, а разовая докидка одного поля, которого
основной цикл не знает.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import async_session
from app.models.product import Product
from app.models.user import User
from app.services.catalog_gala.format import validate_gala_catalog
from app.services.product_catalog_guard import can_edit_catalog
from app.services.product_photo_download import download_and_save_photo, pick_external_url
from app.services.products_import_apply import apply_products_import

_MAX_LINKS = 9

FIXED_COLUMNS = [
    "name", "description", "category", "product_type", "price", "price_date",
    "unit", "pack_quantity", "pack_unit", "photo_link", "is_reusable",
    "is_active", "characteristics", "manufacturer", "article", "country_origin",
] + [f"link_url_{n}" for n in range(1, _MAX_LINKS + 1)] + [
    f"link_price_{n}" for n in range(1, _MAX_LINKS + 1)
]
COL_IDX = {name: i for i, name in enumerate(FIXED_COLUMNS)}


def _bool_to_cell(value):
    """GALA is_reusable/is_active (bool|None) → ячейка, которую понимает
    products_import_apply._to_bool ("да"/"нет"); None — колонка пуста, тогда
    _to_bool(None) вернёт True (дефолт Product.is_reusable/is_active)."""
    if value is None:
        return None
    return "да" if value else "нет"


def _num_to_cell(value):
    return str(value) if value is not None else None


def item_to_row(item: dict) -> tuple:
    row = [None] * len(FIXED_COLUMNS)
    row[COL_IDX["name"]] = item.get("name")
    row[COL_IDX["description"]] = item.get("description")
    row[COL_IDX["category"]] = item.get("category")
    row[COL_IDX["product_type"]] = item.get("product_type")
    row[COL_IDX["price"]] = _num_to_cell(item.get("price"))
    row[COL_IDX["price_date"]] = item.get("price_date")
    row[COL_IDX["unit"]] = item.get("unit")
    row[COL_IDX["pack_quantity"]] = _num_to_cell(item.get("pack_quantity"))
    row[COL_IDX["pack_unit"]] = item.get("pack_unit")
    photos = item.get("photos") or []
    row[COL_IDX["photo_link"]] = photos[0] if photos else None
    row[COL_IDX["is_reusable"]] = _bool_to_cell(item.get("is_reusable"))
    row[COL_IDX["is_active"]] = _bool_to_cell(item.get("is_active"))
    row[COL_IDX["characteristics"]] = item.get("characteristics") or []
    row[COL_IDX["manufacturer"]] = item.get("manufacturer")
    row[COL_IDX["article"]] = item.get("article")
    row[COL_IDX["country_origin"]] = item.get("country_origin")
    for i, link in enumerate((item.get("links") or [])[:_MAX_LINKS], start=1):
        row[COL_IDX[f"link_url_{i}"]] = link.get("url")
        row[COL_IDX[f"link_price_{i}"]] = _num_to_cell(link.get("price"))
    return tuple(row)


async def _get_user(email: str) -> User:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user.id


async def _fill_clarification_link(db, items: list) -> None:
    by_name_url = {i["name"]: i.get("source_url") for i in items if i.get("name") and i.get("source_url")}
    if not by_name_url:
        return
    rows = (await db.execute(select(Product).where(Product.name.in_(by_name_url.keys())))).scalars().all()
    touched = False
    for p in rows:
        url = by_name_url.get(p.name)
        if url and not p.clarification_link:
            p.clarification_link = url
            touched = True
    if touched:
        await db.commit()


async def _load_one_file(path: str, user_id: int, dry_run: bool) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        envelope = json.load(f)

    errors = validate_gala_catalog(envelope)
    if errors:
        print(f"\n=== {path}: ОШИБКА валидации, файл пропущен ===", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        return {"path": path, "skipped_file": True, "errors_count": len(errors)}

    items = envelope.get("items", [])
    data_rows = [item_to_row(item) for item in items]

    async with async_session() as db:
        user = await db.get(User, user_id)
        editor_can_edit_catalog = await can_edit_catalog(user, db)
        result = await apply_products_import(
            db, data_rows, COL_IDX,
            filename=envelope.get("source_file") or Path(path).name,
            current_user=user,
            dry_run=dry_run,
            editor_can_edit_catalog=editor_can_edit_catalog,
            replace_descriptions=True,
            supplier_description=True,
        )
        if not dry_run:
            await _fill_clarification_link(db, items)

    # Текст причины — из products_import_match.py (ЕДИНСТВЕННЫЙ источник
    # формулировки многозначности, ПРАВИЛО №6): «в БД несколько товаров с
    # этим названием (id: ...)».
    multiple_same_name = sum(
        1 for r in result["rows"] if r.get("reason") and "несколько товаров с этим названием" in r["reason"]
    )

    return {
        "path": path,
        "items": len(items),
        "created": result["created"],
        "updated": result["updated"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "multiple_same_name": multiple_same_name,
    }


async def _download_photos(limit) -> dict:
    """Скачивает фото товарам с внешней ссылкой и без photo_data — то же
    ядро, что у POST /api/products/download-photos (ПРАВИЛО №6), с
    ограниченным параллелизмом (≤4) и лимитом числа попыток (--photos-limit)."""
    async with async_session() as db:
        rows = (await db.execute(select(Product).where(Product.is_active == True))).scalars().all()

    from app.services.product_photo_store import has_photo as _has_photo
    targets = []
    for p in rows:
        if _has_photo(p):
            continue
        src = pick_external_url(p)
        if not src:
            continue
        targets.append((p.id, src))
        if limit and len(targets) >= limit:
            break

    sem = asyncio.Semaphore(4)

    async def _one(product_id, url):
        async with sem:
            async with async_session() as db:
                ok, reason, err = await download_and_save_photo(product_id, url, db)
                return ok

    results = await asyncio.gather(*(_one(pid, url) for pid, url in targets), return_exceptions=True)
    updated = sum(1 for r in results if r is True)
    errors = len(results) - updated
    return {"attempted": len(targets), "updated": updated, "errors": errors}


async def main_async(files, user_email, dry_run, photos, photos_limit):
    user_id = await _get_user(user_email)

    total = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    for path in files:
        report = await _load_one_file(path, user_id, dry_run)
        if report.get("skipped_file"):
            continue
        print(f"\n=== {path} ===")
        print(f"  позиций в файле: {report['items']}")
        print(f"  created={report['created']} updated={report['updated']} skipped={report['skipped']}")
        print(f"  несколько одноимённых: {report['multiple_same_name']}")
        errs = report["errors"]
        print(f"  ошибок: {len(errs)}")
        for e in errs[:10]:
            print(f"    строка {e.get('row')}: {e.get('name')}: {e.get('message')}")
        for k in ("created", "updated", "skipped"):
            total[k] += report[k]
        total["errors"] += len(errs)

    print(f"\n=== ИТОГО ===")
    print(f"created={total['created']} updated={total['updated']} skipped={total['skipped']} errors={total['errors']}")

    if photos and not dry_run:
        photo_report = await _download_photos(photos_limit)
        print(f"\n=== Фото ===")
        print(f"попыток: {photo_report['attempted']} скачано: {photo_report['updated']} ошибок: {photo_report['errors']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True, help="пути к *.gala.json")
    parser.add_argument("--user-email", required=True, help="email пользователя, от имени которого идёт загрузка")
    parser.add_argument("--dry-run", action="store_true", help="прогон без записи (flush без commit)")
    parser.add_argument("--photos", action="store_true", help="после загрузки скачать фото по внешним ссылкам")
    parser.add_argument("--photos-limit", type=int, default=None, help="ограничить число попыток скачивания фото")
    args = parser.parse_args()

    asyncio.run(main_async(args.files, args.user_email, args.dry_run, args.photos, args.photos_limit))


if __name__ == "__main__":
    main()
