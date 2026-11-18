"""Вспомогательные функции планировщика слияния `merge_by_name_model.py` (Правило №5).

Включает двухфазный отбор кандидатов без загрузки каталога в ORM-память и
исключение защищённых товаров из договоров/закупок/заявок.
"""
import sys
from collections import defaultdict

from sqlalchemy import func, select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.catalog_gala.stores import domain_from_url
from app.services.product_name_signature import (
    _brands_match, build_signature, grouping_key, match,
    normalize_name_for_dedup,
)

PHASE1_CHUNK = 5000
PHASE2_CHUNK_IDS = 2000


def _effective_source_id(contractor_id, price_source_ref: str | None = None):
    """Идентификатор источника карточки: contractor_id (если задан), иначе
    домен/строка price_source_ref, иначе None."""
    if contractor_id is not None:
        return contractor_id
    if price_source_ref and price_source_ref.strip():
        dom = domain_from_url(price_source_ref)
        return f"ref:{dom or price_source_ref.strip().lower()}"
    return None


async def _load_candidate_groups(
    db, brand_dictionary=None, protected_ids: set[int] | None = None,
) -> dict:
    """Фаза 1 — потоково, Core select без ORM Product, исключая protected_ids."""
    groups: dict = defaultdict(list)
    no_code_by_norm_name: dict = defaultdict(list)
    norm_name_to_keys: dict = defaultdict(set)
    last_id = 0
    total_rows = 0
    protected = protected_ids or set()
    while True:
        rows = (await db.execute(
            select(
                Product.id, Product.name, Product.manufacturer,
                Product.product_type, Product.category,
                Product.price_source_contractor_id,
                Product.price_source_ref,
                func.left(Product.description, 300),
            )
            .where(Product.is_active == True, Product.id > last_id)  # noqa: E712
            .order_by(Product.id)
            .limit(PHASE1_CHUNK)
        )).all()
        if not rows:
            break
        for pid, name, manufacturer, product_type, category, contractor_id, price_source_ref, desc_head in rows:
            if pid in protected:
                continue
            sig = build_signature({
                "name": name, "manufacturer": manufacturer,
                "product_type": product_type, "category": category,
                "description": desc_head,
            }, brand_dictionary=brand_dictionary)
            key = grouping_key(sig)
            norm_name = normalize_name_for_dedup(name)
            eff_source = _effective_source_id(contractor_id, price_source_ref)
            if key is not None:
                groups[key].append((pid, eff_source))
                norm_name_to_keys[norm_name].add(key)
            else:
                no_code_by_norm_name[norm_name].append((pid, eff_source))
        total_rows += len(rows)
        last_id = rows[-1][0]
        print(f"  фаза 1: обработано строк каталога: {total_rows}", file=sys.stderr)
        if len(rows) < PHASE1_CHUNK:
            break

    for norm_name, waiting_rows in no_code_by_norm_name.items():
        keys = norm_name_to_keys.get(norm_name, ())
        if len(keys) == 1:
            target_key = next(iter(keys))
            groups[target_key].extend(waiting_rows)

    return {key: ids for key, ids in groups.items() if len(ids) >= 2}


async def _apply_history_contractors(db, groups: dict) -> dict:
    """Между фазами — добирает contractor_id из product_price_history
    и отбрасывает группы с < 2 РАЗНЫХ магазинов."""
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
            h_cids = history_contractors.get(pid, ())
            if contractor_id is not None:
                stores.add(contractor_id)
            if h_cids:
                stores.update(h_cids)
            if contractor_id is None and not h_cids:
                stores.add("__no_store__")
        if len(stores) >= 2:
            filtered[key] = [pid for pid, _contractor in ids]
    return filtered


def _store_key(pid: int, price_source_contractor_id, history_pairs: tuple) -> tuple:
    if price_source_contractor_id is not None:
        return ("csrc", price_source_contractor_id)
    cids = {cid for cid, _sa in history_pairs if cid is not None}
    if len(cids) == 1:
        return ("hist", next(iter(cids)))
    return ("none",)


def _has_duplicate_store_cards(product_ids: list, price_source_by_id: dict, history_pairs_by_id: dict) -> bool:
    counts: dict = {}
    for pid in product_ids:
        key = _store_key(pid, price_source_by_id.get(pid), tuple(history_pairs_by_id.get(pid, ())))
        counts[key] = counts.get(key, 0) + 1
    return any(c > 1 for c in counts.values())


def _has_store_conflict(product_ids: list, history_pairs_by_id: dict) -> bool:
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
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            other_peers = tuple(
                signatures_by_id[pid] for pid in ids if pid not in (a_id, b_id)
            )
            res = match(
                signatures_by_id[a_id], signatures_by_id[b_id],
                peers_a=other_peers, peers_b=other_peers,
            )
            if res["decision"] != "auto":
                return False
    return True


def _split_unrelated_subgroups(
    ids: list,
    signatures_by_id: dict,
    price_source_by_id=None,
    history_pairs_by_id=None,
) -> list[list[int]]:
    if len(ids) <= 2 or len(ids) > 80:
        return [ids]
    branded_pids = [pid for pid in ids if signatures_by_id[pid].brand_fold]
    multi_brand_bucket = any(
        not _brands_match(signatures_by_id[p1], signatures_by_id[p2])
        for idx, p1 in enumerate(branded_pids)
        for p2 in branded_pids[idx + 1:]
    )
    store_key_by_id = {}
    if price_source_by_id is not None and history_pairs_by_id is not None:
        for pid in ids:
            store_key_by_id[pid] = _store_key(
                pid, price_source_by_id.get(pid), tuple(history_pairs_by_id.get(pid, ()))
            )
    adj: dict[int, set[int]] = {pid: set() for pid in ids}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            sig_a, sig_b = signatures_by_id[a_id], signatures_by_id[b_id]
            if multi_brand_bucket:
                if sig_a.brand_fold and sig_b.brand_fold and not _brands_match(sig_a, sig_b):
                    continue
                if bool(sig_a.brand_fold) != bool(sig_b.brand_fold):
                    continue
            peers_a = tuple(
                signatures_by_id[pid] for pid in ids
                if pid != a_id and (not multi_brand_bucket or (sig_a.brand_fold and _brands_match(signatures_by_id[pid], sig_a)))
            )
            peers_b = tuple(
                signatures_by_id[pid] for pid in ids
                if pid != b_id and (not multi_brand_bucket or (sig_b.brand_fold and _brands_match(signatures_by_id[pid], sig_b)))
            )
            res = match(sig_a, sig_b, peers_a=peers_a, peers_b=peers_b)
            same_store = (
                bool(store_key_by_id)
                and store_key_by_id.get(a_id) == store_key_by_id.get(b_id)
            )
            if res["decision"] == "auto" or (same_store and res["decision"] != "no"):
                adj[a_id].add(b_id)
                adj[b_id].add(a_id)
    visited: set[int] = set()
    components: list[list[int]] = []
    for pid in ids:
        if pid in visited:
            continue
        comp = []
        queue = [pid]
        visited.add(pid)
        while queue:
            cur = queue.pop()
            comp.append(cur)
            for nxt in adj[cur]:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        if len(comp) >= 2:
            components.append(sorted(comp))
    return components
