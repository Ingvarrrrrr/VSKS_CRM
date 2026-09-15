#!/usr/bin/env python3
"""
CLI: разовый поиск позиций закупок/заявок, которые НЕ привязаны к каталогу
товаров (product_id IS NULL), но нашли бы свой товар после того, как
normalize_product_name() стал приводить гомоглифы кириллица/латиница
(и заодно ё/пробелы/дефисы/кавычки) — см. app/services/product_catalog_match.py,
дополнение 2026-09-15.

ПРИЧИНА. Владелец: «"Топор колун для дров FISKARS X17 M 1,55 кг с чехлом
122463" — этот топор есть в БД, есть фото, но в закупке 914, в которую я
данные импортировал из Excel, не подтянулось ни ТЗ, ни фото». В каталоге
(id 2693) X/M — ЛАТИНСКИЕ, в позиции закупки (id 3028) те же X/M —
КИРИЛЛИЧЕСКИЕ. Строки визуально неразличимы, но normalize_product_name
(до фикса) сравнивал их как разные имена → product_id остался пустым.
Замер по боевой базе на момент диагноза: 93 позиции закупок без product_id,
у 44 из них в названии смешаны кириллица и латиница, 25 из 93 нашли бы свой
товар именно за счёт приведения гомоглифов.

ЭТОТ СКРИПТ НЕ ТРОГАЕТ существующие данные, пока не передан --yes: находит
кандидатов через ЕДИНУЮ точку сопоставления по имени
(app/services/product_catalog_match.py::normalize_product_name +
index_products_by_name — та же функция, что использует импорт закупок,
конверсия заявки, распределение — Правило №6, второй нормализатор здесь не
заводится) и только печатает, что нашлось. Привязка (запись product_id)
делается ТОЛЬКО с --yes, и только сам product_id — остальные поля позиции
(цена/описание/ТЗ) этим скриптом не трогаются, ими товар обычно уже
самостоятельно владеет в каталоге.

ЧТО ИЩЕТСЯ:
  - purchase_items с product_id IS NULL;
  - wish_items с product_id IS NULL.
Для каждой такой строки — normalize_product_name(item_name) ищется в индексе
каталога (index_products_by_name, тот же pick_preferred при дублях каталога:
предпочитает запись с заполненным описанием).

ФЛАГИ:
    --dry-run              показать план (умолчание, если --yes не передан).
    --yes                  реально проставить product_id найденным строкам.
    --filter-name-substr S  учитывать только позиции, чьё нормализованное имя
                           содержит S (регистр не важен) — точечный прогон.
    --limit N              ограничить число ОБРАБАТЫВАЕМЫХ найденных строк
                           (отладка/точечная проверка на стенде).
    --purchases-only       не проверять wish_items.
    --wishes-only          не проверять purchase_items.

Запуск (внутри контейнера backend, tests/scripts не примонтированы —
предварительно docker cp):
    docker exec vsks_crm-backend_a-1 python scripts/find_products_via_homoglyph_fold.py --dry-run
    docker exec vsks_crm-backend_a-1 python scripts/find_products_via_homoglyph_fold.py --yes

ВНИМАНИЕ: реальная привязка на боевой/локальной базе — только после того,
как владелец увидел список из --dry-run и подтвердил его.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.wish_item import WishItem  # noqa: E402
from app.services.product_catalog_match import (  # noqa: E402
    index_products_by_name, normalize_product_name,
)


async def load_product_index(db) -> dict:
    products = (await db.execute(select(Product))).scalars().all()
    return index_products_by_name(products)


async def find_purchase_item_matches(db, product_by_name: dict, name_substr: str | None) -> list[dict]:
    rows = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.product_id.is_(None))
    )).scalars().all()
    out = []
    for it in rows:
        name = (it.item_name or "").strip()
        if not name:
            continue
        norm = normalize_product_name(name)
        if name_substr and name_substr.lower() not in norm:
            continue
        hit = product_by_name.get(norm)
        if hit:
            out.append({
                "kind": "purchase_item", "id": it.id, "purchase_id": it.purchase_id,
                "item_name": name, "product_id": hit.id, "product_name": hit.name,
            })
    return out


async def find_wish_item_matches(db, product_by_name: dict, name_substr: str | None) -> list[dict]:
    rows = (await db.execute(
        select(WishItem).where(WishItem.product_id.is_(None))
    )).scalars().all()
    out = []
    for it in rows:
        name = (it.item_name or "").strip()
        if not name:
            continue
        norm = normalize_product_name(name)
        if name_substr and name_substr.lower() not in norm:
            continue
        hit = product_by_name.get(norm)
        if hit:
            out.append({
                "kind": "wish_item", "id": it.id, "wish_id": it.wish_id,
                "item_name": name, "product_id": hit.id, "product_name": hit.name,
            })
    return out


async def apply_matches(db, matches: list[dict]) -> None:
    """Проставляет product_id найденным строкам — ТОЛЬКО это поле, ничего
    больше (цена/описание у позиции не трогаются)."""
    purchase_ids = [m["id"] for m in matches if m["kind"] == "purchase_item"]
    wish_ids = [m["id"] for m in matches if m["kind"] == "wish_item"]
    if purchase_ids:
        rows = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.id.in_(purchase_ids))
        )).scalars().all()
        by_id = {r.id: r for r in rows}
        for m in matches:
            if m["kind"] == "purchase_item":
                by_id[m["id"]].product_id = m["product_id"]
    if wish_ids:
        rows = (await db.execute(
            select(WishItem).where(WishItem.id.in_(wish_ids))
        )).scalars().all()
        by_id = {r.id: r for r in rows}
        for m in matches:
            if m["kind"] == "wish_item":
                by_id[m["id"]].product_id = m["product_id"]
    await db.commit()


async def run(apply_changes: bool, name_substr: str | None, limit: int | None,
               purchases_only: bool, wishes_only: bool) -> int:
    async with async_session() as db:
        product_by_name = await load_product_index(db)
        print(f"Каталог: {len(product_by_name)} уникальных нормализованных имён.")

        matches: list[dict] = []
        if not wishes_only:
            matches += await find_purchase_item_matches(db, product_by_name, name_substr)
        if not purchases_only:
            matches += await find_wish_item_matches(db, product_by_name, name_substr)

        print(f"\nНайдено строк, которые нашли бы свой товар после нормализации: {len(matches)}")
        if limit:
            matches = matches[:limit]
            print(f"(ограничено --limit до {len(matches)})")

        for m in matches:
            if m["kind"] == "purchase_item":
                print(f"  [позиция закупки] id={m['id']} purchase_id={m['purchase_id']}"
                      f" name={m['item_name']!r} -> product id={m['product_id']} name={m['product_name']!r}")
            else:
                print(f"  [позиция заявки]  id={m['id']} wish_id={m['wish_id']}"
                      f" name={m['item_name']!r} -> product id={m['product_id']} name={m['product_name']!r}")

        n_purchase = sum(1 for m in matches if m["kind"] == "purchase_item")
        n_wish = sum(1 for m in matches if m["kind"] == "wish_item")
        print("\n" + "=" * 70)
        print(f"Итого: {len(matches)} (позиций закупок: {n_purchase}, позиций заявок: {n_wish})")

        if apply_changes:
            await apply_matches(db, matches)
            print(f"\nПРИМЕНЕНО: product_id проставлен {len(matches)} строкам.")
        else:
            print("\nDRY-RUN — изменения НЕ применены (передайте --yes для реальной привязки).")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="показать план, ничего не писать (поведение по умолчанию)")
    parser.add_argument("--yes", action="store_true", help="реально проставить product_id найденным строкам")
    parser.add_argument("--filter-name-substr", default=None,
                         help="учитывать только позиции, чьё нормализованное имя содержит эту подстроку")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число обрабатываемых найденных строк (отладка)")
    parser.add_argument("--purchases-only", action="store_true", help="не проверять wish_items")
    parser.add_argument("--wishes-only", action="store_true", help="не проверять purchase_items")
    args = parser.parse_args()

    apply_changes = args.yes and not args.dry_run
    return await run(apply_changes, args.filter_name_substr, args.limit,
                      args.purchases_only, args.wishes_only)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
