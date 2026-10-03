"""Часть А плана breezy-mixing-lovelace.md: «Похожие закупки в импорте
факта» — при совпадении будущей закупки (группа строк файла) с уже
существующей закупкой («та же закупка — ОФИСМАГ, 15 позиций в GALA, 1 строка
в файле на ту же сумму») новая закупка НЕ создаётся, а существующая
привязывается к строкам плана из файла.

Два входа:
  - `find_existing_matches_for_group()` — preview.py вызывает её на каждую
    группу файла: тот же поставщик (все id с совпадающим нормализованным
    именем — find_contractors_by_name) + ИТОГОВАЯ сумма группы (contract_
    amount группы, без пропущенных строк — см. grouping.py) против
    total_nmck/contract_price/payment_amount/сумм платежей существующей
    закупки (find_similar_purchases). kind='same_amount' — поставщик И
    сумма совпали («скорее всего та же», предвыбрано). kind='same_supplier'
    — только поставщик («возможно», без предвыбора — решение обязательно).
  - `build_existing_match_items()` — для КОНКРЕТНОЙ существующей закупки
    (после того, как её выбрали/предложили) отдаёт ВСЕ её позиции: уже
    привязанные к плану — как есть, непривязанные — с предложенной плановой
    позицией (точное совпадение имени в каталоге → иначе строка плана из
    файла) и пометкой «категория: было → станет», если привязка её меняет.
  - `apply_existing_match_decision()` — commit.py: применяет решение
    владельца (item_links) к позициям существующей закупки через
    `feo_item_linking.link_purchase_item_to_planned` (ПРАВИЛО №6, тот же
    сервис, что и ручной POST /feo-planned-items/map) с
    `enforce_category_check=False` — решение в предпросмотре заменяет отказ
    проверки категорий. Возвращает backup предыдущих значений для
    rollback.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.contractor_resolve import find_contractors_by_name
from app.services.historical_fact_import.matching import normalize_item_name
from app.services.purchase_similar import find_similar_purchases


async def find_existing_matches_for_group(
    db: AsyncSession,
    subsidy_id: int,
    supplier_name: Optional[str],
    group_amount: Optional[Decimal],
) -> list[dict]:
    """[{purchase_id, registry_number, subject, contractor, amount, status,
    kind}] — без items (см. build_existing_match_items, вызывается отдельно
    на выбранную/предложенную закупку, чтобы не тянуть позиции закупок, на
    которые владелец даже не посмотрит)."""
    contractor_ids = await find_contractors_by_name(db, supplier_name)
    if not contractor_ids:
        return []

    out: list[dict] = []
    same_amount_ids: set = set()
    if group_amount is not None and group_amount > 0:
        same_amount = await find_similar_purchases(
            db,
            subsidy_id=subsidy_id,
            contractor_ids=contractor_ids,
            amount=group_amount,
            include_payment_rows=True,
            exclude_statuses=("split",),
            exclude_stopped=True,
        )
        for m in same_amount:
            same_amount_ids.add(m["id"])
            out.append({**m, "purchase_id": m["id"], "kind": "same_amount"})

    if not out:
        same_supplier = await find_similar_purchases(
            db,
            subsidy_id=subsidy_id,
            contractor_ids=contractor_ids,
            amount=None,
            exclude_statuses=("split",),
            exclude_stopped=True,
            exclude_ids=list(same_amount_ids) or None,
        )
        for m in same_supplier:
            out.append({**m, "purchase_id": m["id"], "kind": "same_supplier"})

    return out


async def _category_name(db: AsyncSession, cat_id: Optional[int], cache: dict) -> Optional[str]:
    if cat_id is None:
        return None
    if cat_id not in cache:
        cat = await db.get(FeoCategory, cat_id)
        cache[cat_id] = cat.name if cat else None
    return cache[cat_id]


async def build_existing_match_items(
    db: AsyncSession,
    purchase_id: int,
    matching_ctx: dict,
    file_row_planned_item_id: Optional[int],
) -> list[dict]:
    """Все позиции существующей закупки `purchase_id` — уже привязанные к
    плановой позиции показываются как есть (не трогаются), непривязанным
    предлагается плановая позиция (точное совпадение имени среди СВОБОДНЫХ
    кандидатов каталога — ctx["by_name"]/ctx["already_bound"]/ctx["used_ids"],
    тот же каскад матчинга, что и у строк файла, ПРАВИЛО №6 — else строка
    плана из файла `file_row_planned_item_id`)."""
    purchase = await db.get(Purchase, purchase_id)
    items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().all()

    cat_name_cache: dict = {}
    file_row_category_id: Optional[int] = None
    if file_row_planned_item_id is not None:
        fpi = await db.get(FeoPlannedItem, file_row_planned_item_id)
        file_row_category_id = fpi.feo_category_id if fpi else None

    out: list[dict] = []
    for it in items:
        base = {
            "item_id": it.id,
            "name": it.item_name,
            "qty": float(it.quantity) if it.quantity is not None else None,
            "price": float(it.unit_price) if it.unit_price is not None else None,
            "total": float(it.total_price) if it.total_price is not None else None,
        }
        if it.feo_planned_item_id:
            planned = await db.get(FeoPlannedItem, it.feo_planned_item_id)
            out.append({
                **base,
                "feo_planned_item_id": it.feo_planned_item_id,
                "planned_item_name": planned.name if planned else None,
                "feo_category_path": await _category_name(db, it.feo_category_id, cat_name_cache),
                "suggested": None,
                "category_change": None,
            })
            continue

        cat_from_id = it.feo_category_id if it.feo_category_id is not None else (
            purchase.feo_category_id if purchase else None
        )

        key = normalize_item_name(it.item_name)
        candidates = matching_ctx["by_name"].get(key, [])
        already_bound = matching_ctx["already_bound"]
        used_ids = matching_ctx["used_ids"]
        free = [c for c in candidates if c["id"] not in already_bound and c["id"] not in used_ids]

        if free:
            chosen = sorted(free, key=lambda c: c["id"])[0]
            # Так же, как match_row (matching.py, РЕЕ-2026-08630) — отданная
            # свободная плановая позиция больше не предлагается следующей
            # позиции закупки с тем же именем В ЭТОМ ЖЕ прогоне.
            used_ids.add(chosen["id"])
            suggested = {"planned_item_id": chosen["id"], "reason": "same_name"}
            cat_to_id = chosen.get("category_id")
        else:
            suggested = {"planned_item_id": file_row_planned_item_id, "reason": "file_row"}
            cat_to_id = file_row_category_id

        category_change = None
        if cat_to_id is not None and cat_to_id != cat_from_id:
            category_change = {
                "from": await _category_name(db, cat_from_id, cat_name_cache),
                "to": await _category_name(db, cat_to_id, cat_name_cache),
            }

        out.append({
            **base,
            "feo_planned_item_id": None,
            "planned_item_name": None,
            "feo_category_path": await _category_name(db, cat_from_id, cat_name_cache),
            "suggested": suggested,
            "category_change": category_change,
        })

    return out


def resolve_group_decision(group: dict, existing_decisions: dict) -> dict:
    """Решение владельца по группе (decisions.existing_match[group_key]) +
    умолчание из preview.py (group["needs_existing_decision"]/
    existing_matches): {action: 'same'|'new'|None, match: entry|None}.

    action=None — в группе нет ни одного existing_matches (обычная новая
    закупка, ничего не меняется). 'same' без явного решения применяется
    ТОЛЬКО для kind='same_amount' (владелец: «скорее всего та же,
    предвыбрано»); для kind='same_supplier' без явного решения
    needs_existing_decision=True уже отклонил коммит раньше (см. commit.py)
    — сюда такая группа без решения не попадает."""
    matches = group.get("existing_matches") or []
    if not matches:
        return {"action": None, "match": None}

    decision = existing_decisions.get(group["key"])
    if decision:
        action = decision.get("action")
        purchase_id = decision.get("purchase_id")
        match = next((m for m in matches if m["id"] == purchase_id), matches[0])
        return {"action": action or "new", "match": match if action == "same" else None}

    same_amount = [m for m in matches if m["kind"] == "same_amount"]
    if same_amount:
        return {"action": "same", "match": same_amount[0]}
    return {"action": None, "match": None}


async def apply_existing_match_decision(
    db: AsyncSession,
    *,
    purchase_id: int,
    items_info: list[dict],
    item_links: dict,
    current_user,
) -> dict:
    """decisions.existing_match[group_key].item_links = {"<item_id>":
    {planned_item_id?, create_planned?, skip?}} — применяет к НЕпривязанным
    позициям существующей закупки `purchase_id`. `items_info` — РОВНО тот
    список, что build_preview уже посчитал для этой же закупки в этом же
    прогоне (commit.py повторно вызывает build_preview — ПРАВИЛО №6, та же
    группировка/матчинг, не второй расчёт, см. докстринг commit.py) —
    избегаем пересчёта suggested/category_change второй раз.

    Явной записи в item_links может не быть для какой-то позиции — владелец:
    «непривязанная — СРАЗУ предложена плановая позиция», т.е. применяется
    предложение по умолчанию (items_info[...]["suggested"]), пока явно не
    выбрано «не привязывать» (skip) или другая плановая/«создать плановую».

    Возвращает {item_backups: [...], created_planned_item_ids: [...]} для
    commit.py/rollback.py: item_backups — предыдущие значения
    feo_planned_item_id/feo_category_id (откат восстанавливает их, см.
    rollback.py), created_planned_item_ids — заведённые здесь плановые
    позиции («создать плановую» на непривязанной позиции)."""
    from app.services.feo_item_linking import link_purchase_item_to_planned
    from app.services.plan_autoassign import create_auto_planned_item

    item_links = item_links or {}

    item_backups: list[dict] = []
    created_planned_item_ids: list[int] = []

    for info in items_info:
        if info["feo_planned_item_id"] is not None:
            # Уже привязана (владелец: «уже стоящие привязки не трогаем»).
            continue

        link = item_links.get(str(info["item_id"])) or {}
        if link.get("skip"):
            continue

        planned_item_id = link.get("planned_item_id")
        create_planned = bool(link.get("create_planned"))
        if planned_item_id is None and not create_planned and not link:
            # Ничего явно не выбрано — предложение по умолчанию.
            sug = info.get("suggested") or {}
            planned_item_id = sug.get("planned_item_id")

        pi = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.id == info["item_id"], PurchaseItem.purchase_id == purchase_id)
        )).scalar_one_or_none()
        if not pi or pi.feo_planned_item_id is not None:
            continue

        prev_planned_id = pi.feo_planned_item_id
        prev_category_id = pi.feo_category_id

        if not planned_item_id and create_planned:
            eff_cat_id = pi.feo_category_id
            if eff_cat_id is None:
                purchase = await db.get(Purchase, purchase_id)
                eff_cat_id = purchase.feo_category_id if purchase else None
            if eff_cat_id:
                from types import SimpleNamespace
                fake_item = SimpleNamespace(
                    item_name=pi.item_name, quantity=pi.quantity, unit=pi.unit,
                    total_price=pi.total_price, item_type=pi.item_type,
                )
                new_fpi = await create_auto_planned_item(
                    db, fake_item, eff_cat_id, note="импортом факта — та же закупка (breezy-mixing-lovelace.md)",
                )
                planned_item_id = new_fpi.id
                created_planned_item_ids.append(new_fpi.id)

        if not planned_item_id:
            continue

        await link_purchase_item_to_planned(
            db, pi=pi, planned_item_id=planned_item_id, current_user=current_user,
            enforce_category_check=False,
        )
        item_backups.append({
            "purchase_item_id": pi.id,
            "prev_feo_planned_item_id": prev_planned_id,
            "prev_feo_category_id": prev_category_id,
            "set_feo_planned_item_id": pi.feo_planned_item_id,
            "set_feo_category_id": pi.feo_category_id,
        })

    return {"item_backups": item_backups, "created_planned_item_ids": created_planned_item_ids}
