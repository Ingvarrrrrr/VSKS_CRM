"""Повторное согласование заявки, распределённой канбаном НА НЕСКОЛЬКО закупок
(split=True, approve-distribution/канбан «Распределить») — задача A (владелец,
лист 2 №2, 2026-09-20).

Контекст: `app.services.wish_distribution._sync_purchase_from_wish` (ветка
len(purchases)==1) синхронизирует единственную закупку заявки при повторном
согласовании ("вернули в черновик → поправили → согласовали заново"). Раньше
при len(purchases) > 1 функция молча возвращала None — «без сохранённого
сопоставления группа → закупка синхронизация неоднозначна» (см. старый
докстринг). Сопоставление на самом деле СОХРАНЕНО — на каждой строке закупки,
пришедшей из заявки, есть PurchaseItem.wish_item_id (жёсткая связь), поэтому
однозначное обновление возможно и здесь.

Вынесено в отдельный файл, а не дописано в wish_distribution.py (Правило №5 —
тот модуль уже ~900 строк, это отдельная, самодостаточная ветка со своей
логикой маршрутизации новых позиций по закупкам).

ПРАВИЛО №6 (не заводить вторую формулу): переиспользует
  - `sync_purchase_item_fields_from_wish_item` (app.services.
    wish_purchase_item_field_sync) — тот же набор полей и алгоритм
    «ручная правка vs заявка», что и в одиночной ветке;
  - `resolve_wish_item_group_key`/`backfill_wish_items_product_ids`
    (app.services.wish_distribution) — тот же ключ группировки «заявка →
    колонка», что и при первом создании закупок в _distribute_wish_to_purchases;
  - `recalc_purchase_money` (app.services.purchase_money_writer) — единственный
    писатель денежных колонок закупки.

Алгоритм:
  1. Закупки заявки со статусом в TZ_FROZEN_STATUSES пропускаются целиком —
    blocked_reason с номером/предметом/стадией (тот же текст, что в
    одиночной ветке), их позиции не трогаются вообще.
  2. У ОСТАЛЬНЫХ ("незамороженных") закупок заявки собираются все
    PurchaseItem вместе — сопоставление с текущими WishItem идёт по ОБЩЕМУ
    пулу (двухступенчато: wish_item_id → normalize(item_name), как в
    одиночной ветке), а не по каждой закупке отдельно — иначе позиция,
    переставленная между группами правкой в черновике, не нашла бы пару и
    считалась бы заново созданной. Совпавшая пара обновляется НА МЕСТЕ, в
    ТОЙ закупке, где реально лежит строка — сама по себе синхронизация
    никогда не переносит позицию между закупками (это отдельная ручная
    операция, см. app/routers/purchase_items_move.py, задача C).
  3. Новая позиция заявки без пары — попадает в закупку, чей «ключ группы»
    (по большинству resolve_wish_item_group_key её уже лежащих позиций)
    совпадает с ключом группы самой позиции; если такой закупки нет —
    в первую незамороженную закупку (по возрастанию id).
  4. Позиции закупки, чей wish_item_id указывает на позицию ЭТОЙ заявки, но
     сам WishItem исчез (перестал быть значимым/удалён) — удаляются, как в
     одиночной ветке. Ручные строки (wish_item_id пуст или указывает не
     сюда) не трогаются — items_kept_manual.
  5. recalc_purchase_money — для каждой НЕзамороженной закупки заявки
     (дёшево и безусловно, тот же принцип, что в одиночной ветке).

Возвращает контракт `purchase_sync`, СОВМЕСТИМЫЙ по форме с одиночной веткой
(плоские списки items_added/items_removed/items_changed/items_conflicted/
items_kept_manual — фронт их уже понимает, см. grep purchase_sync во
frontend/src), но собранный по ВСЕМ закупкам заявки, плюс новое поле
`purchases` — разбивка по каждой закупке (для будущего UI, не ломает текущий
потребитель, который per-purchase поле не читает). purchase_id/registry_number/
subject_before/subject_after верхнего уровня — от ПЕРВОЙ (по id) закупки
заявки. Если ВСЕ закупки заявки заморожены — верхний blocked_reason
перечисляет их все (тот же принцип, что у одиночной ветки: фронт при
непустом blocked_reason показывает ТОЛЬКО его и не показывает списки, см.
useWishesContext.ts::showPurchaseSync — поэтому blocked_reason верхнего
уровня заполняется ТОЛЬКО когда обновлять целиком нечего).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish_item import WishItem
from app.models.purchase_item import PurchaseItem
from app.services.item_contractor import set_item_contractor


async def sync_multi_purchase_from_wish(wish, purchases: list, db: AsyncSession) -> dict:
    from app.routers.purchases import TZ_FROZEN_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS
    # Ленивый импорт (во избежание цикла роутер↔сервис — тот же приём, что и в
    # wish_distribution.py, _sync_purchase_from_wish, ветка len(purchases)==1).
    from app.routers.wishes import (
        _is_meaningful_item,
        _ensure_feo_categories_assigned,
        _ensure_needed_dates,
        _eff_date,
    )
    from app.services.plan_autoassign import (
        auto_assign_planned_items as _auto_assign_planned_items,
        backfill_item_type_from_plan as _backfill_item_type_from_plan,
    )
    from app.services.tz_excess_approval import collect_tz_over_plan_violations
    from app.services.text_match import normalize as _normalize_name
    from app.services.wish_purchase_item_field_sync import sync_purchase_item_fields_from_wish_item
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.wish_distribution import (
        backfill_wish_items_product_ids,
        resolve_wish_item_group_key,
    )

    purchases_sorted = sorted(purchases, key=lambda p: p.id)

    items_res = await db.execute(
        select(WishItem).where(WishItem.wish_id == wish.id).order_by(WishItem.id)
    )
    _all_wish_items = items_res.scalars().all()
    wish_items = [it for it in _all_wish_items if _is_meaningful_item(it)]
    _all_wish_item_ids = {it.id for it in _all_wish_items}
    _wish_item_by_id = {it.id: it for it in _all_wish_items}

    await _ensure_feo_categories_assigned(wish, wish_items, db)
    await _ensure_needed_dates(wish, db, wish_items)
    await _auto_assign_planned_items(
        wish_items, wish.feo_category_id, db, note=f"повторным согласованием заявки №{wish.id}",
    )
    # Собранное здесь читает вызывающий код (_distribute_wish_to_purchases) ПОСЛЕ
    # возврата — та же точка расширения, что и у одиночной ветки.
    wish._tz_excess_violations_sync = await collect_tz_over_plan_violations(
        db, wish_items, fallback_category_id=wish.feo_category_id,
    )

    # Тот же бэкфилл product_id + ключ группировки, что при первом
    # распределении заявки на закупки — единственный источник (Правило №6).
    name_to_product = await backfill_wish_items_product_ids(wish_items, db)

    frozen_purchases = [p for p in purchases_sorted if p.status in TZ_FROZEN_STATUSES]
    active_purchases = [p for p in purchases_sorted if p.status not in TZ_FROZEN_STATUSES]

    def _blocked_reason(p) -> str:
        label = _STATUS_LABELS.get(p.status, p.status)
        return (
            f"Закупка №{p.purchase_number or p.id} «{p.subject or p.item_name or ''}» "
            f"уже на стадии «{label}» — обновить предмет и состав из заявки нельзя. "
            "Дальнейшие изменения вносите прямо в закупке."
        )

    purchase_reports: dict[int, dict] = {}
    for p in frozen_purchases:
        purchase_reports[p.id] = {
            "purchase_id": p.id, "registry_number": p.registry_number,
            "items_added": [], "items_removed": [], "items_changed": [],
            "items_conflicted": [], "items_kept_manual": [],
            "blocked_reason": _blocked_reason(p),
        }

    if active_purchases:
        active_ids = [p.id for p in active_purchases]
        pitems_res = await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id.in_(active_ids)).order_by(PurchaseItem.id)
        )
        existing_items = pitems_res.scalars().all()

        # Двухступенчатое сопоставление (см. докстринг модуля, п.2) — ОБЩИЙ пул
        # на все незамороженные закупки заявки, не per-purchase.
        _existing_by_wid: dict[int, PurchaseItem] = {}
        _unmatched_existing: list[PurchaseItem] = []
        for pi in existing_items:
            if pi.wish_item_id is not None and pi.wish_item_id in _all_wish_item_ids:
                _existing_by_wid[pi.wish_item_id] = pi
            else:
                _unmatched_existing.append(pi)

        _existing_pool: dict[str, list[PurchaseItem]] = {}
        for pi in _unmatched_existing:
            key = _normalize_name(pi.item_name or "")
            _existing_pool.setdefault(key, []).append(pi)

        # Ключ группы КАЖДОЙ незамороженной закупки — большинство ключей группы
        # (resolve_wish_item_group_key) её уже лежащих позиций, связанных с
        # WishItem (см. докстринг модуля, п.3).
        def _purchase_group_key(p) -> str | None:
            counts: dict[str, int] = {}
            for pi in existing_items:
                if pi.purchase_id != p.id or pi.wish_item_id is None:
                    continue
                wi = _wish_item_by_id.get(pi.wish_item_id)
                if wi is None:
                    continue
                k = resolve_wish_item_group_key(wi, name_to_product)
                counts[k] = counts.get(k, 0) + 1
            if not counts:
                return None
            return max(counts.items(), key=lambda kv: kv[1])[0]

        purchase_group_key = {p.id: _purchase_group_key(p) for p in active_purchases}
        default_purchase = active_purchases[0]  # первая незамороженная по id

        _wish_contractor_obj = None
        if getattr(wish, 'contractor_id', None):
            from app.models.contractor import Contractor as _Contractor
            _wish_contractor_obj = await db.get(_Contractor, wish.contractor_id)

        items_added: dict[int, list[dict]] = {p.id: [] for p in active_purchases}
        items_removed: dict[int, list[dict]] = {p.id: [] for p in active_purchases}
        items_changed: dict[int, list[dict]] = {p.id: [] for p in active_purchases}
        items_conflicted: dict[int, list[dict]] = {p.id: [] for p in active_purchases}
        items_kept_manual: dict[int, list[dict]] = {p.id: [] for p in active_purchases}
        synced_items: list[PurchaseItem] = []

        for wi in wish_items:
            pi = _existing_by_wid.pop(wi.id, None)
            if pi is None:
                _key = _normalize_name(wi.item_name or "")
                _bucket = _existing_pool.get(_key)
                pi = _bucket.pop(0) if _bucket else None

            if pi is None:
                # Новая позиция заявки — определяем закупку по ключу группы
                # (п.3 докстринга); нет совпадения — первая незамороженная.
                wi_key = resolve_wish_item_group_key(wi, name_to_product)
                target = next(
                    (p for p in active_purchases if purchase_group_key.get(p.id) == wi_key),
                    None,
                ) or default_purchase
                new_pi = PurchaseItem(
                    purchase_id=target.id,
                    product_id=wi.product_id,
                    item_name=wi.item_name,
                    item_type=wi.item_type,
                    quantity=wi.quantity,
                    unit=wi.unit,
                    unit_price=wi.unit_price,
                    total_price=wi.total_price,
                    extra_attrs=getattr(wi, 'extra_attrs', None) or {},
                    planned_quantity=wi.quantity,
                    planned_unit_price=wi.unit_price,
                    planned_total=wi.total_price,
                    country_origin=wi.country_origin,
                    feo_category_id=wi.feo_category_id,
                    feo_planned_item_id=wi.feo_planned_item_id,
                    over_plan=getattr(wi, 'over_plan', False),
                    needed_date=_eff_date(wish, wi),
                    wish_item_id=wi.id,
                    vat_rate=getattr(wi, 'vat_rate', None),
                )
                set_item_contractor(new_pi, contractor=_wish_contractor_obj, name=getattr(wish, 'contractor_name', None))
                db.add(new_pi)
                synced_items.append(new_pi)
                items_added[target.id].append({
                    "name": wi.item_name, "quantity": float(wi.quantity or 0), "amount": float(wi.total_price or 0),
                })
                continue

            # Совпала существующая позиция — обновляем НА МЕСТЕ, в закупке,
            # где она реально лежит (см. п.2 докстринга — никогда не переносим).
            _result = sync_purchase_item_fields_from_wish_item(pi, wi, wish)
            if _result["changed_entry"]:
                items_changed[pi.purchase_id].append(_result["changed_entry"])
            if _result["conflicts"]:
                items_conflicted[pi.purchase_id].extend(_result["conflicts"])
            synced_items.append(pi)

        # Непарные позиции — удаляем те, что реально пришли из заявки (п.4).
        _leftover_buckets = list(_existing_pool.values()) + [[pi] for pi in _existing_by_wid.values()]
        for _bucket in _leftover_buckets:
            for pi in _bucket:
                if pi.wish_item_id is not None and pi.wish_item_id in _all_wish_item_ids:
                    items_removed[pi.purchase_id].append({
                        "name": pi.item_name, "quantity": float(pi.quantity or 0), "amount": float(pi.total_price or 0),
                    })
                    await db.delete(pi)
                else:
                    items_kept_manual[pi.purchase_id].append({
                        "name": pi.item_name, "quantity": float(pi.quantity or 0), "amount": float(pi.total_price or 0),
                    })

        if synced_items:
            await _backfill_item_type_from_plan(synced_items, db)

        await db.flush()
        for p in active_purchases:
            await recalc_purchase_money(db, p)
        await db.flush()

        for p in active_purchases:
            purchase_reports[p.id] = {
                "purchase_id": p.id,
                "registry_number": p.registry_number,
                "items_added": items_added[p.id],
                "items_removed": items_removed[p.id],
                "items_changed": items_changed[p.id],
                "items_conflicted": items_conflicted[p.id],
                "items_kept_manual": items_kept_manual[p.id],
                "blocked_reason": None,
            }

    ordered_reports = [purchase_reports[p.id] for p in purchases_sorted]
    first = purchases_sorted[0]

    if not active_purchases:
        # Обновлять целиком нечего — верхний blocked_reason перечисляет ВСЕ
        # закупки заявки (фронт при непустом blocked_reason показывает только
        # его, см. докстринг модуля).
        top_blocked_reason = " ".join(r["blocked_reason"] for r in ordered_reports if r.get("blocked_reason"))
    else:
        top_blocked_reason = None

    def _flatten(key: str) -> list[dict]:
        out: list[dict] = []
        for r in ordered_reports:
            out.extend(r.get(key) or [])
        return out

    return {
        "purchase_id": first.id,
        "registry_number": first.registry_number,
        "subject_before": first.subject,
        "subject_after": first.subject,
        "items_added": _flatten("items_added"),
        "items_removed": _flatten("items_removed"),
        "items_changed": _flatten("items_changed"),
        "items_conflicted": _flatten("items_conflicted"),
        "items_kept_manual": _flatten("items_kept_manual"),
        "blocked_reason": top_blocked_reason,
        "purchases": ordered_reports,
    }
