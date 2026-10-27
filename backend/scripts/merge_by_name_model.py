"""CLI: слияние карточек УЖЕ ЗАГРУЖЕННОГО каталога по общему правилу «тот же
товар» (название + бренд + цифро-буквенные токены, решение владельца
27.10.2026, app.services.product_name_signature). ЗАМЕНЯЕТ
scripts/merge_by_type_key.py (удалён вместе с app/services/product_type_keys*
— ПРАВИЛО №6: один механизм «тот же товар» по названию, не два).

Импорт (scripts/load_gala_catalog.py → services/products_import_apply.py)
уже сводит НОВЫЕ строки по этому же правилу через критерий (0.75)
(services/products_import_match_name_model.py) — этот скрипт закрывает
ПРОШЛОЕ: товары, загруженные ДО появления критерия, у которых разные карточки
разных магазинов имеют одинаковую сигнатуру (ProductSignature), но не были
сведены при загрузке.

Своей логики сравнения НЕ пишет (ПРАВИЛО №6) — вызывает ТОЛЬКО
app.services.product_name_signature.build_signature()/match() для разбора и
решения, и app.services.product_merge.merge_products для самого слияния (та
же единственная функция, что и POST /api/products/merge и
scripts/merge_by_barcode.py).

Группа карточек (один frozenset(digit_tokens)) мержится ТОЛЬКО если:
  - у них ≥2 РАЗНЫХ магазина (Product.price_source_contractor_id ИЛИ
    contractor_id строк истории product_price_history) — карточки одного-
    единственного магазина сами по себе всегда разные товары (тот же принцип,
    что у merge_by_barcode.py/product_similar.py::_distinct_stores);
  - «один магазин не продаёт товар дважды» (владелец, 27.10.2026): если
    какой-то магазин группы имеет историю (contractor_id, store_article) с
    РАЗНЫМИ store_article у РАЗНЫХ карточек этой же группы — группа
    КОНСЕРВАТИВНО пропускается целиком (попадает в счётчик "conflict"
    пробного прогона, та же проверка, что в merge_by_barcode.py/merge_by_
    type_key.py — ПРАВИЛО №6);
  - ОДНОЗНАЧНОСТЬ — для КАЖДОЙ пары карточек группы (из РАЗНЫХ магазинов)
    product_name_signature.match(a, b, peers_a, peers_b) должен вернуть
    decision == "auto" (peers_* — ProductSignature всех ОСТАЛЬНЫХ карточек
    группы — своя же функция match() решает однозначность через свой
    _ambiguity_reason, ПРАВИЛО №6 — здесь своего счётчика повторов не
    пишем); если хоть одна пара не "auto" — ВСЯ группа консервативно
    пропускается как "неоднозначно" (попадает в conflict, человек решает
    глазами через «Похожие товары», app/services/product_similar.py — та же
    функция там уже используется).

winner группы — карточка с БОЛЬШИМ числом строк истории цены, затем с
МЕНЬШИМ id (тот же простой приём, что в merge_by_barcode.py/merge_by_type_
key.py).

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.merge_by_name_model --user-email <email>            # пробный прогон
    python -m scripts.merge_by_name_model --user-email <email> --apply    # слияние, порциями по 200 групп
"""
import argparse
import asyncio
import sys
from collections import defaultdict

from sqlalchemy import select

from app.database import async_session
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.services.product_merge import merge_products
from app.services.product_name_signature import build_signature, match

BATCH_SIZE = 200


async def _get_user(email: str):
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user


async def _load_name_model_groups(db) -> tuple:
    """{frozenset(digit_tokens): set(product_id, ...)} — ТОЛЬКО группы с ≥2
    РАЗНЫМИ product_id, у которых build_signature() дал непустой
    digit_tokens (без него ключ ничего не отличает — см. докстринг
    product_name_signature.py), products_by_id и signatures_by_id
    (ProductSignature каждого — нужен дальше для match(), ПРАВИЛО №6 —
    разбор ОДИН раз, не второй вызов build_signature на ту же карточку).
    Один запрос на весь каталог (все активные товары — в отличие от
    "ключа вида товара", здесь нет узкого ILIKE-паттерна по первому слову:
    критерий общий, не привязан к пожарной безопасности)."""
    rows = (await db.execute(select(Product).where(Product.is_active == True))).scalars().all()  # noqa: E712
    groups: dict = defaultdict(set)
    products_by_id: dict = {}
    signatures_by_id: dict = {}
    for p in rows:
        sig = build_signature({
            "name": p.name, "manufacturer": p.manufacturer,
            "characteristics": p.characteristics or [],
        })
        if not sig.digit_tokens:
            continue
        groups[sig.digit_tokens].add(p.id)
        products_by_id[p.id] = p
        signatures_by_id[p.id] = sig
    groups = {k: ids for k, ids in groups.items() if len(ids) >= 2}
    return groups, products_by_id, signatures_by_id


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
    """«Один магазин не продаёт товар дважды» (владелец, 27.10.2026) — та же
    проверка, что merge_by_barcode.py/merge_by_type_key.py::
    _has_store_conflict (карта "контрагент → set(store_article)" по всей
    группе, конфликт — когда у контрагента больше одного значения)."""
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


def _is_group_unique(ids: list, signatures_by_id: dict) -> bool:
    """ЕДИНСТВЕННАЯ проверка однозначности (ПРАВИЛО №6) — зовёт ТОЛЬКО
    product_name_signature.match() для КАЖДОЙ пары карточек группы, peers —
    все ОСТАЛЬНЫЕ карточки группы (match() сам решает многозначность через
    свой _ambiguity_reason, не второй счётчик здесь)."""
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            peers_a = tuple(signatures_by_id[pid] for pid in ids if pid != a_id)
            peers_b = tuple(signatures_by_id[pid] for pid in ids if pid != b_id)
            res = match(signatures_by_id[a_id], signatures_by_id[b_id], peers_a=peers_a, peers_b=peers_b)
            if res["decision"] != "auto":
                return False
    return True


async def _plan(db) -> list:
    """Возвращает список {"key", "conflict", ...} — группы, готовые к
    слиянию (без конфликтов, ≥2 разных магазина, 1-к-1 по match()). Не меняет
    БД."""
    groups, products_by_id, signatures_by_id = await _load_name_model_groups(db)
    if not groups:
        return []

    all_product_ids = set()
    for ids in groups.values():
        all_product_ids.update(ids)
    history_count_by_id, history_pairs_by_id = await _load_history(db, all_product_ids)

    plan = []
    for key, ids in groups.items():
        ids = [pid for pid in ids if pid in products_by_id]
        if len(ids) < 2:
            continue
        distinct_stores = set()
        for pid in ids:
            distinct_stores.update(_product_stores(products_by_id[pid], history_pairs_by_id))
        if len(distinct_stores) < 2:
            continue  # все карточки одного и того же (или никакого) магазина
        if _has_store_conflict(ids, history_pairs_by_id):
            plan.append({"key": key, "conflict": True, "reason": "store_article", "product_ids": ids})
            continue
        if not _is_group_unique(ids, signatures_by_id):
            # Неоднозначно (владелец, 27.10.2026) — автоматически НЕ сводим,
            # это повод для человека посмотреть в «Похожие товары»
            # (app/services/product_similar.py, тот же match() уже решает
            # её группы «уверенно»/«проверить»).
            plan.append({"key": key, "conflict": True, "reason": "неоднозначно", "product_ids": ids})
            continue
        winner_id = _pick_winner_simple(ids, history_count_by_id)
        loser_ids = [pid for pid in ids if pid != winner_id]
        plan.append({
            "key": key, "conflict": False,
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

    ambiguous = [g for g in conflicts if g.get("reason") == "неоднозначно"]
    store_conflicts = [g for g in conflicts if g.get("reason") == "store_article"]

    print(f"Групп с общей сигнатурой названия (≥2 магазина): {len(mergeable) + len(conflicts)}")
    print(f"  готовых к слиянию (1-к-1, product_name_signature.match): {len(mergeable)} (карточек будет удалено: {cards_to_remove})")
    print(f"  неоднозначно (несколько карточек у какого-то магазина под этим ключом — см. «Похожие товары»): {len(ambiguous)}")
    print(f"  пропущено из-за конфликта «один магазин — две позиции»: {len(store_conflicts)}")

    print("\nПримеры (до 10):")
    for g in mergeable[:10]:
        loser_names = ", ".join(f"№{lid} «{g['names'][lid]}»" for lid in g["loser_ids"])
        print(f"  winner №{g['winner_id']} «{g['names'][g['winner_id']]}» ← {loser_names}")

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
                    print(f"  пропущено (ошибка слияния): {e}", file=sys.stderr)
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
