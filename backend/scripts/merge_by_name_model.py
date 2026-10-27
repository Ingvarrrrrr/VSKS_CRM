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

ПАМЯТЬ (дефект прода 27.10.2026 — пробный прогон убит OOM, anon-rss 1,77 ГБ
на 4-гигабайтном сервере, где кроме этого скрипта живут БД и 4 контейнера):
причина — ORM-select всего каталога (`select(Product)...scalars().all()`)
грузил ВСЕ колонки (включая characteristics JSONB) ВСЕХ ~230 тыс. товаров
сразу, плюс любые lazy='selectin'-связи Product срабатывают САМИ при ORM-
загрузке, даже если к ним не обращаться. Поэтому ниже — ДВЕ фазы:
  - фаза 1 (_load_candidate_groups) — Core select (кортежи, не ORM Product,
    selectin не срабатывает) ТОЛЬКО 4 узких колонки, порциями по id
    (keyset-пагинация, не OFFSET), сразу сворачивает в
    frozenset(digit_tokens) → [(id, price_source_contractor_id), ...] и
    отбрасывает всё, что не кандидат (нет цифровых токенов или в группе
    осталась только одна карточка) — полные объекты Product в памяти не
    живут вообще;
  - между фазами — _apply_history_contractors: один DISTINCT-запрос
    (product_id, contractor_id) из product_price_history, порциями по id
    кандидатов, чтобы отбросить группы без ≥2 разных магазинов ДО того, как
    фаза 2 полезет за тяжёлыми полями;
  - фаза 2 (_plan) — дозагружает name/manufacturer/characteristics и
    (contractor_id, store_article) истории ТОЛЬКО для id кандидатских групп,
    порциями ≤2000 id, вызывает build_signature()/match() и сразу отдаёт
    порцию сборщику мусора (локальные dict порции выходят из scope).
Итог — в памяти одновременно никогда не находится больше одной порции
полных карточек; широкий Core select фазы 1 держит только 4 узких поля.

Группа карточек (один frozenset(digit_tokens)) мержится ТОЛЬКО если:
  - у них ≥2 РАЗНЫХ магазина (Product.price_source_contractor_id ИЛИ
    contractor_id строк истории product_price_history) — карточки одного-
    единственного магазина сами по себе всегда разные товары (тот же принцип,
    что у merge_by_barcode.py/product_similar.py::_distinct_stores);
  - НЕ БОЛЬШЕ ОДНОЙ карточки НА КАЖДЫЙ магазин (владелец, доп. дефект
    пробного прогона 27.10.2026, "один магазин не продаёт товар дважды" +
    "автоматически — только однозначные пары 1-к-1"): магазин карточки —
    Product.price_source_contractor_id, если не NULL, иначе ЕДИНСТВЕННЫЙ
    contractor_id из её истории цен; карточка без определённого магазина
    (ни price_source, ни единственного contractor_id в истории) — "свой
    источник", но ДВЕ такие карточки без магазина в одной группе — тоже
    неоднозначно (см. _store_key/_has_duplicate_store_cards). Найден на
    «Огнетушитель ... ОУ-50 ВСЕ ...» — 3 карточки магазина Спасатель +
    1 карточка другого магазина были слиты в одну (разные варианты
    магазина Спасатель, не один и тот же товар); нарушение — группа
    КОНСЕРВАТИВНО пропускается целиком (попадает в счётчик "conflict");
  - «один магазин не продаёт товар дважды» (владелец, 27.10.2026): если
    какой-то магазин группы имеет историю (contractor_id, store_article) с
    РАЗНЫМИ store_article у РАЗНЫХ карточек этой же группы — группа
    КОНСЕРВАТИВНО пропускается целиком (попадает в счётчик "conflict"
    пробного прогона, та же проверка, что в merge_by_barcode.py/merge_by_
    type_key.py — ПРАВИЛО №6);
  - ОДНОЗНАЧНОСТЬ — для КАЖДОЙ пары карточек группы (из РАЗНЫХ магазинов,
    гарантировано проверкой "не больше одной на магазин" выше)
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
from app.services.product_name_signature import build_signature, grouping_key, match

BATCH_SIZE = 200  # порция слияния (--apply)

# Порог памяти ~300 МБ (дефект прода 27.10.2026) — обе константы ниже держат
# в памяти одновременно не больше одной порции: фаза 1 — узких кортежей,
# фаза 2 — полных полей кандидатов.
PHASE1_CHUNK = 5000   # строк каталога на один Core-select (keyset по id)
PHASE2_CHUNK_IDS = 2000  # id кандидатов на одну дозагрузку полных полей


async def _get_user(email: str):
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user


async def _load_candidate_groups(db) -> dict:
    """Фаза 1 — потоково, Core select (НЕ ORM Product — иначе срабатывают
    lazy='selectin'-связи и грузится весь каталог в объекты, см. докстринг
    модуля). Берёт ТОЛЬКО узкие колонки, порциями по id (keyset-
    пагинация — ORDER BY id LIMIT, без OFFSET, чтобы порция не дорожала с
    глубиной). build_signature() здесь без characteristics — функция и так
    принимает их опционально (item.get("characteristics") or []), а
    digit_tokens/вид (всё, что нужно на этой фазе) считаются только по
    name/product_type/category — второй сигнатуры/функции под
    «облегчённый» режим не заводим (ПРАВИЛО №6).

    Группирует по grouping_key() = (вид товара, код модели) — владелец,
    28.10.2026, п.1: ЕДИНАЯ функция product_name_signature.grouping_key, не
    второй механизм здесь (ПРАВИЛО №6). Раньше группировка шла по ЛЮБОМУ
    общему цифровому токену (включая голые числа без единой буквы — "43",
    "6005") по ВСЕМУ каталогу разом — отсюда и мусорные группы ("Тапочки
    размер 43"+"Коврик 43×28"+"KEDI Teste 43"). grouping_key() возвращает
    None для сигнатур без буквенно-цифрового кода — такие вообще не
    попадают в группы-кандидаты (не ключ поиска, см. докстринг
    product_name_signature.grouping_key).

    Возвращает {grouping_key: [(product_id, price_source_contractor_id),
    ...]} — ТОЛЬКО группы, где после фазы 1 уже ≥2 РАЗНЫХ product_id."""
    groups: dict = defaultdict(list)
    last_id = 0
    total_rows = 0
    while True:
        rows = (await db.execute(
            select(
                Product.id, Product.name, Product.manufacturer,
                Product.product_type, Product.category,
                Product.price_source_contractor_id,
            )
            .where(Product.is_active == True, Product.id > last_id)  # noqa: E712
            .order_by(Product.id)
            .limit(PHASE1_CHUNK)
        )).all()
        if not rows:
            break
        for pid, name, manufacturer, product_type, category, contractor_id in rows:
            sig = build_signature({
                "name": name, "manufacturer": manufacturer,
                "product_type": product_type, "category": category,
            })
            key = grouping_key(sig)
            if key is not None:
                groups[key].append((pid, contractor_id))
        total_rows += len(rows)
        last_id = rows[-1][0]
        print(f"  фаза 1: обработано строк каталога: {total_rows}", file=sys.stderr)
        if len(rows) < PHASE1_CHUNK:
            break
    groups = {key: ids for key, ids in groups.items() if len(ids) >= 2}
    return groups


async def _apply_history_contractors(db, groups: dict) -> dict:
    """Между фазами — добирает contractor_id из product_price_history ТОЛЬКО
    для id кандидатов (один DISTINCT-запрос на порцию ≤PHASE2_CHUNK_IDS id,
    без store_article — он нужен только фазе 2 для _has_store_conflict) и
    отбрасывает группы, где после этого < 2 РАЗНЫХ магазина. Возвращает
    {key: [product_id, ...]} — тройка (id, contractor) из фазы 1 больше не
    нужна дальше, оставляем только id."""
    all_ids = sorted({pid for ids in groups.values() for pid, _contractor in ids})
    history_contractors: dict = defaultdict(set)
    for i in range(0, len(all_ids), PHASE2_CHUNK_IDS):
        chunk = all_ids[i:i + PHASE2_CHUNK_IDS]
        rows = (await db.execute(
            select(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id)
            .where(ProductPriceHistory.product_id.in_(chunk))
            .distinct()
        )).all()
        for pid, cid in rows:
            if cid is not None:
                history_contractors[pid].add(cid)

    filtered: dict = {}
    for key, ids in groups.items():
        stores = set()
        for pid, contractor_id in ids:
            if contractor_id is not None:
                stores.add(contractor_id)
            stores.update(history_contractors.get(pid, ()))
        if len(stores) >= 2:
            filtered[key] = [pid for pid, _contractor in ids]
    return filtered


def _store_key(pid: int, price_source_contractor_id, history_pairs: tuple) -> tuple:
    """Магазин ОДНОЙ карточки (владелец, 27.10.2026, доп. дефект пробного
    прогона — см. докстринг модуля): price_source_contractor_id, если
    известен; иначе — ЕДИНСТВЕННЫЙ contractor_id из её истории цен; если
    история пуста или называет НЕСКОЛЬКО разных магазинов — у карточки
    нет определённого магазина, и она считается "своим источником"
    (ключ ("none",) — ОДИН И ТОТ ЖЕ для всех таких карточек НАРОЧНО: см.
    _has_duplicate_store_cards, где повтор этого ключа тоже конфликт)."""
    if price_source_contractor_id is not None:
        return ("csrc", price_source_contractor_id)
    cids = {cid for cid, _sa in history_pairs if cid is not None}
    if len(cids) == 1:
        return ("hist", next(iter(cids)))
    return ("none",)


def _has_duplicate_store_cards(product_ids: list, price_source_by_id: dict, history_pairs_by_id: dict) -> bool:
    """«Один магазин не продаёт товар дважды» (владелец, 27.10.2026, доп.
    дефект пробного прогона — найден на «Огнетушитель ... ОУ-50 ВСЕ ...»:
    3 карточки магазина Спасатель + 1 другого магазина были слиты в одну,
    хотя 3 карточки одного магазина под общим индексом названия — РАЗНЫЕ
    варианты товара, не один и тот же). True, если в группе хотя бы у
    одного магазина (см. _store_key, включая "своего источника" без
    определённого магазина) больше ОДНОЙ карточки — группа ТОГДА
    консервативно пропускается целиком, даже если каждая пара карточек
    формально прошла бы product_name_signature.match() как "auto"."""
    counts: dict = {}
    for pid in product_ids:
        key = _store_key(pid, price_source_by_id.get(pid), tuple(history_pairs_by_id.get(pid, ())))
        counts[key] = counts.get(key, 0) + 1
    return any(c > 1 for c in counts.values())


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


async def _plan_batch(db, batch_groups: list) -> list:
    """Фаза 2 для ОДНОЙ порции (суммарно ≤PHASE2_CHUNK_IDS id) — дозагружает
    полные поля (name/manufacturer/characteristics; country_origin тоже
    читаем — дешёвая скалярная колонка в том же Core select, вдруг
    понадобится вызывающему коду отчёта) ТОЛЬКО для id этой порции, плюс
    (contractor_id, store_article) истории ТОЛЬКО для них же. Всё, что
    загружено здесь (products_by_id/signatures_by_id/history_*), — локальные
    имена этой корутины: при возврате из функции порция уходит из scope и
    освобождается, следующая порция её не держит."""
    batch_ids = sorted({pid for _key, ids in batch_groups for pid in ids})
    if not batch_ids:
        return []

    rows = (await db.execute(
        select(
            Product.id, Product.name, Product.manufacturer,
            Product.country_origin, Product.characteristics,
            Product.product_type, Product.category,
            Product.price_source_contractor_id,
        ).where(Product.id.in_(batch_ids))
    )).all()
    products_by_id = {}
    price_source_by_id = {}
    for pid, name, manufacturer, _country, characteristics, product_type, category, price_source_contractor_id in rows:
        products_by_id[pid] = {
            "name": name, "manufacturer": manufacturer, "characteristics": characteristics or [],
            "product_type": product_type, "category": category,
        }
        price_source_by_id[pid] = price_source_contractor_id

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
        ids = [pid for pid in ids if pid in products_by_id]
        if len(ids) < 2:
            continue
        if _has_duplicate_store_cards(ids, price_source_by_id, history_pairs_by_id):
            # «Один магазин не продаёт товар дважды» (владелец, доп. дефект
            # пробного прогона, см. докстринг модуля) — ПЕРЕД проверкой
            # store_article и ПЕРЕД попарным match(): несколько карточек
            # одного магазина под общим индексом названия всегда
            # неоднозначны, даже если каждая пара прошла бы match() как
            # "auto" (пример ОУ-50 — 3 варианта магазина Спасатель).
            result.append({"key": key, "conflict": True, "reason": "один магазин — несколько карточек", "product_ids": ids})
            continue
        if _has_store_conflict(ids, history_pairs_by_id):
            result.append({"key": key, "conflict": True, "reason": "store_article", "product_ids": ids})
            continue
        signatures_by_id = {pid: build_signature(products_by_id[pid]) for pid in ids}
        if not _is_group_unique(ids, signatures_by_id):
            # Неоднозначно (владелец, 27.10.2026) — автоматически НЕ сводим,
            # это повод для человека посмотреть в «Похожие товары»
            # (app/services/product_similar.py, тот же match() уже решает
            # её группы «уверенно»/«проверить»).
            result.append({"key": key, "conflict": True, "reason": "неоднозначно", "product_ids": ids})
            continue
        winner_id = _pick_winner_simple(ids, history_count_by_id)
        loser_ids = [pid for pid in ids if pid != winner_id]
        result.append({
            "key": key, "conflict": False,
            "winner_id": winner_id, "loser_ids": loser_ids,
            "names": {pid: products_by_id[pid]["name"] for pid in ids},
        })
    return result


async def _plan(db) -> list:
    """Возвращает список {"key", "conflict", ...} — группы, готовые к
    слиянию (без конфликтов, ≥2 разных магазина, 1-к-1 по match()). Не меняет
    БД. Фаза 1 → отбор по магазинам → фаза 2 порциями (см. докстринги
    _load_candidate_groups/_apply_history_contractors/_plan_batch)."""
    groups = await _load_candidate_groups(db)
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
            plan.extend(await _plan_batch(db, batch_groups))
            processed_groups += len(batch_groups)
            print(f"  фаза 2: порция {batch_no}, групп обработано {processed_groups}/{total_groups}", file=sys.stderr)
            batch_groups = []
            batch_id_count = 0
    if batch_groups:
        batch_no += 1
        plan.extend(await _plan_batch(db, batch_groups))
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
    """Пиковая память процесса (resource.ru_maxrss — КБ на Linux, где и
    крутится backend_a/прод; на платформах без resource — пропускаем, не
    падаем)."""
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
