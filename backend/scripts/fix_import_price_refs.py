"""CLI: исправление source_ref/contractor_id у уже загруженных строк цены
каталога GALA (владелец, 26.10.2026).

До этой задачи backend/scripts/load_gala_catalog.py писал
source_ref=<имя файла JSON> (например "electro_mpo_cables_all.json") и
contractor_id=NULL — правильно должно быть source_ref=<ссылка на страницу
товара у магазина> и contractor_id=<контрагент магазина по ИНН> (см.
services/catalog_gala/stores.py, apply_products_import). Этот скрипт
чинит уже записанные ТАКИМ образом строки:
  - ProductPriceHistory (source='import', source_ref заканчивается на
    ".json") — source_ref := Product.clarification_link, иначе первая
    непустая url из Product.price_links;
  - Product (price_source='import', price_source_ref заканчивается на
    ".json") — та же замена для price_source_ref/price_source_contractor_id.

Контрагент — тот же резолвер, что и у apply_products_import (ПРАВИЛО №6):
app.services.contractor_resolve.find_or_create_contractor по ИНН магазина,
определённому services/catalog_gala/stores.py::store_for_url(ссылка), с
кэшем по ИНН на весь прогон. Строка без ссылки (ни clarification_link, ни
price_links) или со ссылкой на неизвестный домен — source_ref/contractor_id
НЕ трогается (остаётся старое значение), считается отдельно в отчёте.

Идемпотентен: после замены source_ref больше не заканчивается на ".json" —
повторный запуск находит 0 строк для исправления.

Логика вынесена в `fix_import_price_refs(db, ...)`, принимающую готовую
AsyncSession (а не открывающую свою) — так тесты
(tests/test_fix_import_price_refs.py) могут вызвать её на той же
транзакционной сессии, что и фикстура db_session (см. её докстринг в
tests/conftest.py: отдельное соединение/async_session() пула не увидело бы
несохранённые SAVEPOINT-данные теста). `_run`/`main` — обычный CLI-вызов,
открывает настоящую app.database.async_session().

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.fix_import_price_refs [--apply] [--batch 5000]
По умолчанию --dry-run (ничего не пишет, только печатает отчёт).
"""
import argparse
import asyncio
from collections import Counter

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.catalog_gala.stores import store_for_url
from app.services.contractor_resolve import find_or_create_contractor

_JSON_SUFFIX = ".json"


def _first_price_link_url(price_links) -> str | None:
    for link in (price_links or []):
        url = (link or {}).get("url") if isinstance(link, dict) else None
        if url and url.strip():
            return url.strip()
    return None


def _resolve_link(product: Product) -> str | None:
    direct = (product.clarification_link or "").strip()
    if direct:
        return direct
    return _first_price_link_url(product.price_links)


async def fix_import_price_refs(db: AsyncSession, *, apply: bool, batch: int) -> dict:
    """Основная логика (без открытия/закрытия сессии — см. докстринг модуля).
    Возвращает {stats: {...}, by_store: Counter}."""
    contractor_cache: dict = {}
    stats = {
        "history_fixed": 0,
        "history_no_link": 0,
        "history_unknown_store": 0,
        "product_fixed": 0,
        "product_no_link": 0,
        "product_unknown_store": 0,
    }
    by_store: Counter = Counter()

    async def resolve_contractor(url: str):
        info = store_for_url(url)
        if not info:
            return None
        inn = info["inn"]
        if inn in contractor_cache:
            return contractor_cache[inn]
        cid = await find_or_create_contractor(
            db, info["name"], inn, match_by_name=False,
            ogrn=info.get("ogrn"), org_type=info.get("org_type"),
        )
        contractor_cache[inn] = cid
        return cid

    # --- ProductPriceHistory ---
    last_id = 0
    while True:
        rows = (await db.execute(
            select(ProductPriceHistory, Product)
            .join(Product, Product.id == ProductPriceHistory.product_id)
            .where(and_(
                ProductPriceHistory.id > last_id,
                ProductPriceHistory.source == "import",
                ProductPriceHistory.source_ref.ilike(f"%{_JSON_SUFFIX}"),
            ))
            .order_by(ProductPriceHistory.id)
            .limit(batch)
        )).all()
        if not rows:
            break
        for hist, product in rows:
            last_id = hist.id
            link = _resolve_link(product)
            if not link:
                stats["history_no_link"] += 1
                continue
            info = store_for_url(link)
            if not info:
                stats["history_unknown_store"] += 1
            if apply:
                hist.source_ref = link
                cid = await resolve_contractor(link)
                if cid is not None:
                    hist.contractor_id = cid
            if info:
                by_store[info["name"]] += 1
            stats["history_fixed"] += 1
        if apply:
            await db.commit()
        if len(rows) < batch:
            break

    # --- Product.price_source_ref ---
    last_id = 0
    while True:
        rows = (await db.execute(
            select(Product)
            .where(and_(
                Product.id > last_id,
                Product.price_source == "import",
                Product.price_source_ref.ilike(f"%{_JSON_SUFFIX}"),
            ))
            .order_by(Product.id)
            .limit(batch)
        )).scalars().all()
        if not rows:
            break
        for product in rows:
            last_id = product.id
            link = _resolve_link(product)
            if not link:
                stats["product_no_link"] += 1
                continue
            info = store_for_url(link)
            if not info:
                stats["product_unknown_store"] += 1
            if apply:
                product.price_source_ref = link
                cid = await resolve_contractor(link)
                if cid is not None:
                    product.price_source_contractor_id = cid
            stats["product_fixed"] += 1
        if apply:
            await db.commit()
        if len(rows) < batch:
            break

    if not apply:
        await db.rollback()

    return {"stats": stats, "by_store": by_store}


def _print_report(apply: bool, result: dict) -> None:
    stats = result["stats"]
    by_store = result["by_store"]
    print(f"=== fix_import_price_refs ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"product_price_history: исправлено {stats['history_fixed']}, "
          f"без ссылки {stats['history_no_link']}, домен не в справочнике {stats['history_unknown_store']}")
    print(f"products (price_source_ref): исправлено {stats['product_fixed']}, "
          f"без ссылки {stats['product_no_link']}, домен не в справочнике {stats['product_unknown_store']}")
    print("по магазинам (строк истории с опознанным доменом):")
    for name, n in by_store.most_common():
        print(f"  {name}: {n}")


async def _run(apply: bool, batch: int) -> None:
    async with async_session() as db:
        result = await fix_import_price_refs(db, apply=apply, batch=batch)
    _print_report(apply, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="записать изменения (по умолчанию dry-run)")
    parser.add_argument("--batch", type=int, default=5000, help="размер порции (по умолчанию 5000)")
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply, batch=args.batch))


if __name__ == "__main__":
    main()
