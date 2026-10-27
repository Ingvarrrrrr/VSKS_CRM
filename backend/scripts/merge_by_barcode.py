"""CLI: слияние карточек УЖЕ ЗАГРУЖЕННОГО каталога по общему штрихкоду
(решение владельца, 27.10.2026 — штрихкод главный ключ сведения карточки).

Импорт (scripts/load_gala_catalog.py → services/products_import_apply.py)
уже сводит НОВЫЕ строки по штрихкоду через критерий (0.25)
(services/products_import_match.py) — этот скрипт закрывает ПРОШЛОЕ: товары,
загруженные ДО появления штрихкода как критерия, у которых разные карточки
разных магазинов имеют один и тот же штрихкод, но не были сведены при
загрузке.

Своей логики слияния НЕ пишет (ПРАВИЛО №6) — вызывает
app.services.product_merge.merge_products, ту же единственную функцию, что и
POST /api/products/merge.

Группа карточек мержится ТОЛЬКО если:
  - у них общий штрихкод (product_barcodes.barcode);
  - среди них ≥2 РАЗНЫХ магазина (Product.price_source_contractor_id ИЛИ
    contractor_id строк истории product_price_history) — карточки одного-
    единственного магазина сами по себе всегда разные товары (магазин не
    продаёт одно и то же дважды), сливать их нечего (тот же принцип, что у
    app/services/product_similar.py::_distinct_stores);
  - «один магазин не продаёт товар дважды» (владелец, 27.10.2026): если
    КАКОЙ-ТО магазин группы имеет историю (contractor_id, store_article) с
    РАЗНЫМИ store_article у РАЗНЫХ карточек этой же группы — группа
    КОНСЕРВАТИВНО пропускается целиком (а не частично сливается) и считается
    в счётчике "conflict" пробного прогона — это сигнал плохих данных
    (магазин продаёт две разные позиции под одним штрихкодом), а не
    однозначный дубль.

winner группы — карточка с БОЛЬШИМ числом строк истории цены, затем с
МЕНЬШИМ id (как и просит владелец — простое правило, не
app/services/product_similar.py::_pick_winner, у которой есть доп. критерии
фото/описания, не нужные здесь).

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.merge_by_barcode --user-email <email>            # пробный прогон
    python -m scripts.merge_by_barcode --user-email <email> --apply    # слияние, порциями по 200 групп
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database import async_session
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.services.product_merge import merge_products

BATCH_SIZE = 200


async def _get_user(email: str):
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user


async def _load_barcode_groups(db) -> dict:
    """{barcode: [product_id, ...]} — ТОЛЬКО штрихкоды, за которыми записано
    ≥2 РАЗНЫХ product_id (один и тот же товар сам с собой сливать нечего)."""
    rows = (await db.execute(
        select(ProductBarcode.barcode, ProductBarcode.product_id)
    )).all()
    groups: dict[str, set] = {}
    for barcode, product_id in rows:
        groups.setdefault(barcode, set()).add(product_id)
    return {b: ids for b, ids in groups.items() if len(ids) >= 2}


async def _load_products_and_history(db, product_ids: set) -> tuple:
    products_by_id: dict = {}
    rows = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
    for p in rows:
        products_by_id[p.id] = p

    history_count_by_id: dict = {}
    history_pairs_by_id: dict = {}
    hist_rows = (await db.execute(
        select(
            ProductPriceHistory.product_id,
            ProductPriceHistory.contractor_id,
            ProductPriceHistory.store_article,
        ).where(ProductPriceHistory.product_id.in_(product_ids))
    )).all()
    for product_id, contractor_id, store_article in hist_rows:
        history_count_by_id[product_id] = history_count_by_id.get(product_id, 0) + 1
        history_pairs_by_id.setdefault(product_id, []).append((contractor_id, store_article))

    return products_by_id, history_count_by_id, history_pairs_by_id


def _product_stores(product, history_pairs_by_id: dict) -> set:
    stores = set()
    if product.price_source_contractor_id is not None:
        stores.add(product.price_source_contractor_id)
    for cid, _sa in history_pairs_by_id.get(product.id, ()):
        if cid is not None:
            stores.add(cid)
    return stores


def _has_store_conflict(product_ids: list, history_pairs_by_id: dict) -> bool:
    """«Один магазин не продаёт товар дважды» (владелец, 27.10.2026) —
    pairwise-вариант того же правила, что conflicts_with_row_store в
    app/services/products_import_match.py (там — строка файла против ОДНОГО
    кандидата, здесь — карточка группы против КАЖДОЙ другой карточки той же
    группы, поэтому не вызываем саму функцию напрямую, а строим общую карту
    "контрагент → set(store_article)" по ВСЕЙ группе и ищем контрагента с
    более чем одним значением — тот же смысл правила, не вторая формула
    сравнения двух пар)."""
    store_articles_by_contractor: dict = {}
    for pid in product_ids:
        for cid, sa in history_pairs_by_id.get(pid, ()):
            if cid is None or not sa:
                continue
            store_articles_by_contractor.setdefault(cid, set()).add(sa)
    return any(len(sas) > 1 for sas in store_articles_by_contractor.values())


def _pick_winner_simple(product_ids: list, history_count_by_id: dict) -> int:
    return sorted(
        product_ids,
        key=lambda pid: (-history_count_by_id.get(pid, 0), pid),
    )[0]


async def _plan(db) -> list:
    """Возвращает список {"barcode", "winner_id", "loser_ids"} — группы,
    готовые к слиянию (без конфликтов, ≥2 разных магазина). Не меняет БД."""
    barcode_groups = await _load_barcode_groups(db)
    if not barcode_groups:
        return []

    all_product_ids = set()
    for ids in barcode_groups.values():
        all_product_ids.update(ids)
    products_by_id, history_count_by_id, history_pairs_by_id = await _load_products_and_history(
        db, all_product_ids,
    )

    plan = []
    for barcode, ids in barcode_groups.items():
        ids = [pid for pid in ids if pid in products_by_id]
        if len(ids) < 2:
            continue
        distinct_stores = set()
        for pid in ids:
            distinct_stores.update(_product_stores(products_by_id[pid], history_pairs_by_id))
        if len(distinct_stores) < 2:
            continue  # все карточки одного и того же (или никакого) магазина
        if _has_store_conflict(ids, history_pairs_by_id):
            plan.append({"barcode": barcode, "conflict": True, "product_ids": ids})
            continue
        winner_id = _pick_winner_simple(ids, history_count_by_id)
        loser_ids = [pid for pid in ids if pid != winner_id]
        plan.append({
            "barcode": barcode, "conflict": False,
            "winner_id": winner_id, "loser_ids": loser_ids,
            "names": {pid: products_by_id[pid].name for pid in ids},
        })
    return plan


async def main_async(user_email: str, apply: bool) -> None:
    user = await _get_user(user_email)

    async with async_session() as db:
        plan = await _plan(db)

    mergeable = [g for g in plan if not g["conflict"]]
    conflicts = [g for g in plan if g["conflict"]]
    cards_to_remove = sum(len(g["loser_ids"]) for g in mergeable)

    print(f"Групп с общим штрихкодом (≥2 магазина): {len(mergeable) + len(conflicts)}")
    print(f"  готовых к слиянию: {len(mergeable)} (карточек будет удалено: {cards_to_remove})")
    print(f"  пропущено из-за конфликта «один магазин — две позиции»: {len(conflicts)}")

    print("\nПримеры (до 10):")
    for g in mergeable[:10]:
        loser_names = ", ".join(f"№{lid} «{g['names'][lid]}»" for lid in g["loser_ids"])
        print(f"  штрихкод {g['barcode']}: winner №{g['winner_id']} «{g['names'][g['winner_id']]}» ← {loser_names}")

    if not apply:
        print("\nПробный прогон — ничего не записано. Повторите с --apply для слияния.")
        return

    merged_groups = 0
    merged_cards = 0
    for i in range(0, len(mergeable), BATCH_SIZE):
        batch = mergeable[i:i + BATCH_SIZE]
        async with async_session() as db:
            for g in batch:
                try:
                    await merge_products(db, g["winner_id"], g["loser_ids"], user)
                except ValueError as e:
                    print(f"  пропущено (ошибка слияния) штрихкод {g['barcode']}: {e}", file=sys.stderr)
                    continue
                merged_groups += 1
                merged_cards += len(g["loser_ids"])
            await db.commit()
        print(f"  порция {i // BATCH_SIZE + 1}: слито {len(batch)} групп, всего {merged_groups}/{len(mergeable)}")

    print(f"\nГотово: слито групп {merged_groups}, удалено карточек {merged_cards}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-email", required=True, help="email пользователя, от имени которого идёт слияние")
    parser.add_argument("--apply", action="store_true", help="выполнить слияние (без флага — только пробный прогон)")
    args = parser.parse_args()
    asyncio.run(main_async(args.user_email, args.apply))


if __name__ == "__main__":
    main()
