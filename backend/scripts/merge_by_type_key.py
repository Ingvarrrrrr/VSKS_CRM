"""CLI: слияние карточек УЖЕ ЗАГРУЖЕННОГО каталога по общему ключу вида
товара (пожарная безопасность: огнетушитель/знак/рукав/шкаф, решение
владельца 27.10.2026, app.services.product_type_keys).

Импорт (scripts/load_gala_catalog.py → services/products_import_apply.py)
уже сводит НОВЫЕ строки по ключу вида товара через критерий (0.75)
(services/products_import_match.py) — этот скрипт закрывает ПРОШЛОЕ: товары,
загруженные ДО появления этого критерия, у которых разные карточки разных
магазинов имеют один и тот же полный ключ вида товара, но не были сведены
при загрузке.

Своей логики сравнения ключей НЕ пишет (ПРАВИЛО №6) — вызывает ТОЛЬКО
app.services.product_type_keys.type_key() для разбора, и
app.services.product_merge.merge_products для самого слияния (та же
единственная функция, что и POST /api/products/merge и scripts/merge_by_
barcode.py).

Группа карточек (один (kind, полный key)) мержится ТОЛЬКО если:
  - у них ≥2 РАЗНЫХ магазина (Product.price_source_contractor_id ИЛИ
    contractor_id строк истории product_price_history) — карточки одного-
    единственного магазина сами по себе всегда разные товары, сливать их
    нечего (тот же принцип, что у merge_by_barcode.py/product_similar.py::
    _distinct_stores);
  - «один магазин не продаёт товар дважды» (владелец, 27.10.2026): если
    КАКОЙ-ТО магазин группы имеет историю (contractor_id, store_article) с
    РАЗНЫМИ store_article у РАЗНЫХ карточек этой же группы — группа
    КОНСЕРВАТИВНО пропускается целиком и считается в счётчике "conflict"
    пробного прогона (сигнал плохих данных, не однозначный дубль, та же
    проверка, что в merge_by_barcode.py — ПРАВИЛО №6);
  - ОДНОЗНАЧНОСТЬ (владелец, 27.10.2026, QA-дефект того же дня: «три ОУ-3
    Спасателя + одна М01» — группировка по точному key сама по себе НЕ
    различает «1-к-1» от «3 карточки одного магазина под тем же ключом»,
    сливать такое нельзя) — ПРОВЕРЯЕТСЯ ТОЛЬКО через
    app.services.product_type_keys.keys_match_unique (ЕДИНСТВЕННАЯ
    реализация правила 1-к-1, ПРАВИЛО №6 — здесь своего счётчика повторов
    не пишем). Для КАЖДОЙ пары карточек группы (из РАЗНЫХ магазинов)
    keys_match_unique(a, b, peers_a, peers_b) должен вернуть "уверенно"
    (peers_* — TypeKeyResult всех распознанных карточек ТОГО ЖЕ kind у
    магазина(ов) этой карточки); если хоть одна пара даёт "проверить" —
    ВСЯ группа консервативно пропускается как "неоднозначно" (попадает в
    conflict, человек решает глазами через «Похожие товары»,
    app/services/product_similar.py — та же функция там уже используется).

winner группы — карточка с БОЛЬШИМ числом строк истории цены, затем с
МЕНЬШИМ id (тот же простой приём, что в merge_by_barcode.py — не
app.services.product_similar.py::_pick_winner, у которой есть доп. критерии
фото/описания, не нужные здесь).

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.merge_by_type_key --user-email <email>            # пробный прогон
    python -m scripts.merge_by_type_key --user-email <email> --apply    # слияние, порциями по 200 групп
"""
import argparse
import asyncio
import sys
from collections import defaultdict

from sqlalchemy import or_, select

from app.database import async_session
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.services.product_merge import merge_products
from app.services.product_type_keys import keys_match_unique, type_key

BATCH_SIZE = 200

# Та же загрузка кандидатов (ILIKE первого слова), что и
# services/products_import_match_type_key.py (ПРАВИЛО №6 — не второй список
# шаблонов видов товара).
_KIND_NAME_PATTERNS = ("огнетуш%", "знак%", "рукав%", "шкаф%")


async def _get_user(email: str):
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user


async def _load_type_key_groups(db) -> tuple:
    """{(kind, key): set(product_id, ...)} — ТОЛЬКО группы с ≥2 РАЗНЫМИ
    product_id (товары распознанных видов, у которых type_key() вернул
    полный ключ), products_by_id и results_by_id (TypeKeyResult каждого —
    нужен дальше для keys_match_unique, ПРАВИЛО №6 — разбор ОДИН раз, не
    второй вызов type_key() на ту же карточку). Один запрос на весь каталог
    (ILIKE первого слова названия, та же выборка, что у
    load_type_key_candidates)."""
    conditions = [Product.name.ilike(p) for p in _KIND_NAME_PATTERNS]
    rows = (await db.execute(select(Product).where(or_(*conditions)))).scalars().all()
    groups: dict = defaultdict(set)
    products_by_id: dict = {}
    results_by_id: dict = {}
    for p in rows:
        r = type_key(p.name, p.characteristics, p.manufacturer, None)
        if r is None or r.key is None:
            continue
        groups[(r.kind, r.key)].add(p.id)
        products_by_id[p.id] = p
        results_by_id[p.id] = r
    groups = {k: ids for k, ids in groups.items() if len(ids) >= 2}
    return groups, products_by_id, results_by_id


async def _load_history(db, product_ids: set) -> tuple:
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
    return history_count_by_id, history_pairs_by_id


def _product_stores(product, history_pairs_by_id: dict) -> set:
    stores = set()
    if product.price_source_contractor_id is not None:
        stores.add(product.price_source_contractor_id)
    for cid, _sa in history_pairs_by_id.get(product.id, ()):
        if cid is not None:
            stores.add(cid)
    return stores


def _has_store_conflict(product_ids: list, history_pairs_by_id: dict) -> bool:
    """«Один магазин не продаёт товар дважды» (владелец, 27.10.2026) — тот
    же приём, что merge_by_barcode.py::_has_store_conflict (карта
    "контрагент → set(store_article)" по всей группе, конфликт — когда у
    контрагента больше одного значения)."""
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


def _is_group_unique(ids: list, kind: str, results_by_id: dict, stores_by_id: dict, peers_by_store_kind: dict) -> bool:
    """ЕДИНСТВЕННАЯ проверка правила 1-к-1 (владелец, 27.10.2026, QA-дефект
    «три ОУ-3 Спасателя + одна М01») — зовёт ТОЛЬКО
    product_type_keys.keys_match_unique для КАЖДОЙ пары карточек группы (не
    свой счётчик повторов, ПРАВИЛО №6). `peers_by_store_kind[(kind, store)]`
    — TypeKeyResult ВСЕХ распознанных кандидатов этого kind у данного
    магазина (считается один раз для всего каталога вызывающим `_plan`, не
    на каждую пару). Карточка без магазина (store=None) получает peers-
    список по ключу (kind, None) — свой «магазин» из одной карточки, что и
    должно давать "уверенно" только если напарник по этому ключу у NULL-
    магазина тоже единственный."""
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            a_result, b_result = results_by_id[a_id], results_by_id[b_id]
            peers_a = []
            for store in (stores_by_id[a_id] or {None}):
                peers_a.extend(peers_by_store_kind.get((kind, store), []))
            peers_b = []
            for store in (stores_by_id[b_id] or {None}):
                peers_b.extend(peers_by_store_kind.get((kind, store), []))
            if keys_match_unique(a_result, b_result, peers_a, peers_b) != "уверенно":
                return False
    return True


async def _plan(db) -> list:
    """Возвращает список {"kind", "key", "winner_id", "loser_ids"} — группы,
    готовые к слиянию (без конфликтов, ≥2 разных магазина, 1-к-1 по
    keys_match_unique). Не меняет БД."""
    groups, products_by_id, results_by_id = await _load_type_key_groups(db)
    if not groups:
        return []

    all_product_ids = set()
    for ids in groups.values():
        all_product_ids.update(ids)
    history_count_by_id, history_pairs_by_id = await _load_history(db, all_product_ids)

    stores_by_id = {
        pid: _product_stores(products_by_id[pid], history_pairs_by_id)
        for pid in all_product_ids
    }

    # peers_by_store_kind[(kind, store)] — TypeKeyResult ВСЕХ распознанных
    # карточек (ЛЮБОГО ключа, того же kind) этого магазина — нужен
    # keys_match_unique, чтобы посчитать «сколько карточек у ЭТОГО магазина
    # под ЭТИМ ключом» (владелец, 27.10.2026). Карточка без магазина
    # (пустой stores) считается «магазином None».
    peers_by_store_kind: dict = defaultdict(list)
    for pid, r in results_by_id.items():
        for store in (stores_by_id.get(pid) or {None}):
            peers_by_store_kind[(r.kind, store)].append(r)

    plan = []
    for (kind, key), ids in groups.items():
        ids = [pid for pid in ids if pid in products_by_id]
        if len(ids) < 2:
            continue
        distinct_stores = set()
        for pid in ids:
            distinct_stores.update(stores_by_id[pid])
        if len(distinct_stores) < 2:
            continue  # все карточки одного и того же (или никакого) магазина
        if _has_store_conflict(ids, history_pairs_by_id):
            plan.append({"kind": kind, "key": key, "conflict": True, "reason": "store_article", "product_ids": ids})
            continue
        if not _is_group_unique(ids, kind, results_by_id, stores_by_id, peers_by_store_kind):
            # Неоднозначно (владелец, 27.10.2026) — например, несколько
            # карточек ОДНОГО магазина под этим же ключом (любая из пар
            # группы не прошла keys_match_unique). Автоматически НЕ сводим —
            # это ровно повод для человека посмотреть в «Похожие товары»
            # (app/services/product_similar.py, тот же keys_match_unique
            # уже решает её группы «уверенно»/«проверить»).
            plan.append({"kind": kind, "key": key, "conflict": True, "reason": "неоднозначно", "product_ids": ids})
            continue
        winner_id = _pick_winner_simple(ids, history_count_by_id)
        loser_ids = [pid for pid in ids if pid != winner_id]
        plan.append({
            "kind": kind, "key": key, "conflict": False,
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

    by_kind: dict = defaultdict(int)
    for g in mergeable:
        by_kind[g["kind"]] += 1

    ambiguous = [g for g in conflicts if g.get("reason") == "неоднозначно"]
    store_conflicts = [g for g in conflicts if g.get("reason") == "store_article"]

    print(f"Групп с общим ключом вида товара (≥2 магазина): {len(mergeable) + len(conflicts)}")
    print(f"  готовых к слиянию (1-к-1, keys_match_unique): {len(mergeable)} (карточек будет удалено: {cards_to_remove})")
    print(f"  неоднозначно (несколько карточек у какого-то магазина под этим ключом — см. «Похожие товары»): {len(ambiguous)}")
    print(f"  пропущено из-за конфликта «один магазин — две позиции»: {len(store_conflicts)}")
    print("  по видам:")
    for kind, count in sorted(by_kind.items()):
        print(f"    {kind}: {count}")

    print("\nПримеры (до 10):")
    for g in mergeable[:10]:
        loser_names = ", ".join(f"№{lid} «{g['names'][lid]}»" for lid in g["loser_ids"])
        print(f"  {g['kind']}: winner №{g['winner_id']} «{g['names'][g['winner_id']]}» ← {loser_names}")

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
                    print(f"  пропущено (ошибка слияния) {g['kind']}: {e}", file=sys.stderr)
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
