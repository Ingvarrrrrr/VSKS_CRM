"""CLI: слияние карточек УЖЕ ЗАГРУЖЕННОГО каталога по общему правилу «тот же
товар» (название + бренд + цифро-буквенные токены, app.services.product_name_signature).

Товары, задействованные в договорах, закупках и заявках (load_protected_product_ids),
исключаются из любых слияний. Вспомогательные функции вынесены в
`scripts/merge_by_name_model_helpers.py` (Правило №5).

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.merge_by_name_model --user-email <email>            # пробный прогон
    python -m scripts.merge_by_name_model --user-email <email> --apply    # слияние, порциями по 200 групп
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database import async_session
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.services.product_merge import merge_products
from app.services.product_name_signature import build_signature, normalize_name_for_dedup
from app.services.product_protection import load_protected_product_ids
from app.services.product_query_parse import get_manufacturer_brand_dictionary
from scripts.merge_by_name_model_helpers import (
    PHASE2_CHUNK_IDS,
    _apply_history_contractors,
    _effective_source_id,
    _has_duplicate_store_cards,
    _has_store_conflict,
    _is_group_unique,
    _load_candidate_groups,
    _pick_winner_simple,
    _split_unrelated_subgroups,
    _store_key,
)

BATCH_SIZE = 200


async def _get_user(email: str):
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user


async def _plan_batch(
    db, batch_groups: list, brand_dictionary=None, protected_ids: set[int] | None = None,
) -> list:
    """Фаза 2 для ОДНОЙ порции (суммарно <= PHASE2_CHUNK_IDS id)."""
    protected = protected_ids or set()
    batch_ids = sorted({pid for _key, ids in batch_groups for pid in ids if pid not in protected})
    if not batch_ids:
        return []

    rows = (await db.execute(
        select(
            Product.id, Product.name, Product.manufacturer,
            Product.country_origin, Product.characteristics,
            Product.product_type, Product.category,
            Product.price_source_contractor_id,
            Product.price_source_ref,
            Product.description,
        ).where(Product.id.in_(batch_ids))
    )).all()
    products_by_id = {}
    price_source_by_id = {}
    for pid, name, manufacturer, _country, characteristics, product_type, category, price_source_contractor_id, price_source_ref, description in rows:
        products_by_id[pid] = {
            "name": name, "manufacturer": manufacturer, "characteristics": characteristics or [],
            "product_type": product_type, "category": category, "description": description,
        }
        price_source_by_id[pid] = _effective_source_id(price_source_contractor_id, price_source_ref)

    hist_rows = (await db.execute(
        select(
            ProductPriceHistory.product_id,
            ProductPriceHistory.contractor_id,
            ProductPriceHistory.store_article,
        ).where(ProductPriceHistory.product_id.in_(batch_ids))
    )).all()
    history_count_by_id: dict = {}
    history_pairs_by_id: dict = {}
    for pid, cid, sa in hist_rows:
        history_count_by_id[pid] = history_count_by_id.get(pid, 0) + 1
        history_pairs_by_id.setdefault(pid, []).append((cid, sa))

    result = []
    for key, ids in batch_groups:
        ids = [pid for pid in ids if pid in products_by_id and pid not in protected]
        if len(ids) < 2:
            continue
        signatures_by_id = {
            pid: build_signature(products_by_id[pid], brand_dictionary=brand_dictionary)
            for pid in ids
        }
        group_ptype, group_mc = key if (isinstance(key, tuple) and len(key) == 2) else (None, frozenset())
        norm_to_brand: dict[str, list] = {}
        for pid in ids:
            sig = signatures_by_id[pid]
            if sig.brand_fold:
                norm_n = normalize_name_for_dedup(products_by_id[pid].get("name"))
                norm_to_brand.setdefault(norm_n, []).append((sig.brand, sig.brand_fold, sig.brand_phonetic_keys))

        for pid in ids:
            sig = signatures_by_id[pid]
            if not sig.model_code_tokens and group_mc:
                sig.model_code_tokens = group_mc
                sig.digit_tokens = sig.digit_tokens | group_mc
                if not sig.brand_fold:
                    norm_n = normalize_name_for_dedup(products_by_id[pid].get("name"))
                    brand_entries = norm_to_brand.get(norm_n, [])
                    distinct_bf = {b[1] for b in brand_entries}
                    if len(distinct_bf) == 1:
                        b_cand, bf_cand, bpk_cand = brand_entries[0]
                        sig.brand = b_cand
                        sig.brand_fold = bf_cand
                        sig.brand_phonetic_keys = bpk_cand

        for sub_ids in _split_unrelated_subgroups(
            ids, signatures_by_id, price_source_by_id, history_pairs_by_id
        ):
            distinct_store_keys = {
                _store_key(pid, price_source_by_id.get(pid), tuple(history_pairs_by_id.get(pid, ())))
                for pid in sub_ids
            }
            if len(distinct_store_keys) < 2:
                continue
            non_empty_brands = {signatures_by_id[pid].brand_fold for pid in sub_ids if signatures_by_id[pid].brand_fold}
            same_confirmed_brand = len(non_empty_brands) == 1 and len(distinct_store_keys) >= 2
            if not _is_group_unique(sub_ids, signatures_by_id):
                result.append({"key": key, "conflict": True, "reason": "неоднозначно", "product_ids": sub_ids})
                continue
            if _has_store_conflict(sub_ids, history_pairs_by_id) and not same_confirmed_brand:
                result.append({"key": key, "conflict": True, "reason": "store_article", "product_ids": sub_ids})
                continue
            if _has_duplicate_store_cards(sub_ids, price_source_by_id, history_pairs_by_id) and not same_confirmed_brand:
                result.append({"key": key, "conflict": True, "reason": "один магазин — несколько карточек", "product_ids": sub_ids})
                continue
            winner_id = _pick_winner_simple(sub_ids, history_count_by_id)
            loser_ids = [pid for pid in sub_ids if pid != winner_id]
            result.append({
                "key": key, "conflict": False,
                "winner_id": winner_id, "loser_ids": loser_ids,
                "names": {pid: products_by_id[pid]["name"] for pid in sub_ids},
            })
    return result


async def _plan(db) -> list:
    protected_ids = await load_protected_product_ids(db)
    print(f"  защищено товаров (договоры/закупки/заявки): {len(protected_ids)}", file=sys.stderr)
    brand_dictionary = await get_manufacturer_brand_dictionary(db)
    groups = await _load_candidate_groups(db, brand_dictionary=brand_dictionary, protected_ids=protected_ids)
    print(f"  фаза 1: групп-кандидатов (общий цифровой ключ, ≥2 карточки): {len(groups)}", file=sys.stderr)
    if not groups:
        return []

    groups = await _apply_history_contractors(db, groups)
    print(f"  после проверки «≥2 разных магазина»: {len(groups)} групп", file=sys.stderr)
    if not groups:
        return []
    plan: list = []
    group_items = list(groups.items())
    total_groups = len(group_items)
    processed_groups = 0
    batch_no = 0
    batch_groups: list = []
    batch_id_count = 0

    for key, ids in group_items:
        batch_groups.append((key, ids))
        batch_id_count += len(ids)
        if batch_id_count >= PHASE2_CHUNK_IDS:
            batch_no += 1
            plan.extend(await _plan_batch(db, batch_groups, brand_dictionary=brand_dictionary, protected_ids=protected_ids))
            processed_groups += len(batch_groups)
            print(f"  фаза 2: порция {batch_no}, групп обработано {processed_groups}/{total_groups}", file=sys.stderr)
            batch_groups = []
            batch_id_count = 0
    if batch_groups:
        batch_no += 1
        plan.extend(await _plan_batch(db, batch_groups, brand_dictionary=brand_dictionary, protected_ids=protected_ids))
        processed_groups += len(batch_groups)
        print(f"  фаза 2: порция {batch_no}, групп обработано {processed_groups}/{total_groups}", file=sys.stderr)

    return plan


async def main_async(user_email: str, apply: bool) -> None:
    user = await _get_user(user_email)

    async with async_session() as db:
        plan = await _plan(db)

    mergeable = [g for g in plan if not g["conflict"]]
    conflicts = [g for g in plan if g["conflict"]]
    cards_to_remove = sum(len(g["loser_ids"]) for g in mergeable)

    ambiguous = [g for g in conflicts if g.get("reason") == "неоднозначно"]
    duplicate_store_cards = [g for g in conflicts if g.get("reason") == "один магазин — несколько карточек"]
    store_conflicts = [g for g in conflicts if g.get("reason") == "store_article"]

    print(f"Групп с общей сигнатурой названия (≥2 магазина): {len(mergeable) + len(conflicts)}")
    print(f"  готовых к слиянию (1-к-1, product_name_signature.match): {len(mergeable)} (карточек будет удалено: {cards_to_remove})")
    print(f"  неоднозначно (несколько карточек у какого-то магазина под этим ключом — см. «Похожие товары»): {len(ambiguous)}")
    print(f"  пропущено — у какого-то магазина больше одной карточки в группе (ОУ-50/P04, не 1-к-1): {len(duplicate_store_cards)}")
    print(f"  пропущено из-за конфликта «один магазин — две позиции» (разные store_article): {len(store_conflicts)}")

    print("\nПримеры (до 20):")
    for g in mergeable[:20]:
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


def _print_peak_memory() -> None:
    try:
        import resource
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"\nПиковая память процесса: {peak_kb / 1024:.1f} МБ (ru_maxrss)", file=sys.stderr)
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-email", required=True, help="email пользователя, от имени которого идёт слияние")
    parser.add_argument("--apply", action="store_true", help="выполнить слияние (без флага — только пробный прогон)")
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.user_email, args.apply))
    finally:
        _print_peak_memory()


if __name__ == "__main__":
    main()
