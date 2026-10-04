"""Запись плановых позиций ФЭО (feo_planned_items) — ЕДИНСТВЕННОЕ место, где
create/update/delete реально пишут в БД и в журнал feo_history (Правило №6).

Вынесено из app/routers/feo_planned_items.py (волна «Корректировка утверждённой
субсидии через проверку», 02.10.2026, план breezy-mixing-lovelace.md): позже
применение накопленных правок корректировки обязано пройти ТЕ ЖЕ проверки и
записи, что и прямая правка через API — раньше вся логика жила в теле роутера
и её нельзя было вызвать повторно из другого места, не продублировав.

НЕ проверяет права доступа (это остаётся в роутере —
_check_planned_item_write_access/require_tab/assert_direct_edit) и НЕ коммитит
транзакцию — вызывающий код (роутер сейчас, применятель корректировки позже)
сам решает, когда commit/rollback.

_apply_payment_fields/_check_planned_item_write_access/_can_edit_feo_origin
ОСТАЮТСЯ в app/routers/feo_planned_items.py — их по конкретному пути модуля
импортируют app/routers/feo_comments.py и
backend/tests/test_planned_item_monthly_period.py, переносить нельзя без
правки чужих файлов (вне разрешённого периметра этой задачи). Здесь они
импортируются ЛЕНИВО (внутри функций), чтобы не ловить циклический импорт
роутер↔сервис (роутер импортирует этот модуль на уровне файла).

source/source_ref — передаются в feo_history.record_* как есть. По умолчанию
source=SOURCE_MANUAL (поведение «человек нажал кнопку через API» не меняется).
create_version — пропускает авто-версию дерева плана закупок
(_create_plan_graph_version). sync_catalog — отключает sync_product_kind-вызов
apply_item_type_to_product. Оба параметра сейчас всегда остаются True
(поведение прямой правки не меняется) — они существуют для будущего
применения корректировки пачкой (одна версия/одна синхронизация на весь
пакет правок, а не на каждую позицию черновика).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.schemas import FeoPlannedItemCreate, FeoPlannedItemBulkCreate
from app.services import feo_history
from app.services.feo_planned_item_amount import backfill_unit_price_on_quantity_change
from app.services.item_types import (
    normalize_item_type, apply_item_type_to_product, resolve_product_for_planned_item,
)
from app.services.plan_need_level import normalize_need_level
from app.services.text_match import normalize as _norm_text


async def validate_wish_or_purchase_context(
    db: AsyncSession,
    subsidy_id: Optional[int],
    wish_id: Optional[int],
    purchase_id: Optional[int],
) -> None:
    """Контекст заявки/закупки у create/bulk (см. докстринги wish_id/purchase_id
    в app/routers/feo_planned_items.py) — создание недостающей плановой позиции
    ИЗ формы заявки/закупки НЕ считается корректировкой субсидии (гейт
    assert_direct_edit не вызывается), но обязано реально относиться к ТОЙ ЖЕ
    субсидии, что и категория создаваемой позиции — иначе подмена contex'а
    стала бы обходом гейта. 422 (не 404/403) — это ошибка несовпадения данных
    запроса, не про доступ и не про отсутствие ресурса вообще."""
    if wish_id is not None:
        row = (await db.execute(
            select(Wish.id, Wish.subsidy_id).where(Wish.id == wish_id)
        )).first()
        if row is None:
            raise HTTPException(422, f"Заявка №{wish_id} не найдена")
        if row.subsidy_id != subsidy_id:
            raise HTTPException(
                422,
                f"Заявка №{wish_id} относится к другой субсидии — создание плановой "
                "позиции из неё в эту категорию невозможно",
            )
    if purchase_id is not None:
        row = (await db.execute(
            select(Purchase.id, Purchase.subsidy_id).where(Purchase.id == purchase_id)
        )).first()
        if row is None:
            raise HTTPException(422, f"Закупка №{purchase_id} не найдена")
        if row.subsidy_id != subsidy_id:
            raise HTTPException(
                422,
                f"Закупка №{purchase_id} относится к другой субсидии — создание "
                "плановой позиции из неё в эту категорию невозможно",
            )


async def create_planned_item(
    db: AsyncSession,
    user,
    cat: FeoCategory,
    data: FeoPlannedItemCreate,
    *,
    sync_catalog: bool = True,
    source: str = feo_history.SOURCE_MANUAL,
    source_ref: Optional[int] = None,
    create_version: bool = True,
) -> FeoPlannedItem:
    """Тело POST /feo-planned-items/ (без прав доступа/гейта и без commit —
    см. докстринг модуля). `cat` — уже загруженная категория-владелец
    (роутер её грузит раньше для проверки доступа, второй раз не читаем)."""
    from app.routers.feo_planned_items import _apply_payment_fields, _can_edit_feo_origin

    _norm_name = _norm_text(data.name or "")
    if _norm_name:
        _candidates = (await db.execute(
            select(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id == data.feo_category_id,
                FeoPlannedItem.is_active == True,
            )
        )).scalars().all()
        existing_item = next((it for it in _candidates if _norm_text(it.name or "") == _norm_name), None)
        if existing_item is not None and not data.allow_duplicate_name:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"Плановая позиция «{existing_item.name}» уже есть в этой категории. "
                        f"Привязать к существующей или создать отдельную?"
                    ),
                    "error_code": "planned_item_duplicate_name",
                    "existing_item_id": existing_item.id,
                    "existing_item_name": existing_item.name,
                    "existing_item_quantity": str(existing_item.quantity) if existing_item.quantity is not None else None,
                    "existing_item_unit": existing_item.unit,
                    "existing_item_amount": str(existing_item.amount) if existing_item.amount is not None else None,
                    "new_quantity": str(data.quantity) if data.quantity is not None else None,
                    "new_unit": data.unit,
                    "new_amount": str(data.amount) if data.amount is not None else None,
                },
            )
        # existing_item is not None здесь означает allow_duplicate_name=True —
        # дедуп осознанно пропущен, ниже создаётся вторая позиция с тем же именем.

    _origin_kwargs = {}
    if await _can_edit_feo_origin(user, db):
        _origin_kwargs = {
            "is_feo_breakdown": data.is_feo_breakdown,
            "is_internal_plan": data.is_internal_plan,
        }

    item = FeoPlannedItem(
        feo_category_id=data.feo_category_id,
        name=data.name,
        quantity=data.quantity,
        unit=data.unit,
        unit_price=data.unit_price,
        feo_quantity=data.feo_quantity,
        feo_unit_price=data.feo_unit_price,
        feo_amount=data.feo_amount,
        notes=data.notes,
        is_active=data.is_active,
        sort_order=data.sort_order,
        item_type=normalize_item_type(data.item_type),
        is_composite=data.is_composite,
        need_level=normalize_need_level(data.need_level),
        **_origin_kwargs,
    )
    _apply_payment_fields(item, data)
    db.add(item)
    if sync_catalog and data.sync_product_kind:
        await apply_item_type_to_product(db, data.product_id, item.item_type)
    await db.flush()
    await feo_history.record_created(
        db, feo_history.ENTITY_FEO_ITEM, item.id, user,
        source=source, source_ref=source_ref, commit=False,
    )
    if create_version and cat.subsidy_id is not None:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=cat.subsidy_id, db=db, user=user,
            note="Авто-версия: изменение плановых позиций",
        )
    return item


async def create_planned_items_bulk(
    db: AsyncSession,
    user,
    body: FeoPlannedItemBulkCreate,
    *,
    sync_catalog: bool = True,
    source: str = feo_history.SOURCE_MANUAL,
    source_ref: Optional[int] = None,
    create_version: bool = True,
) -> list[FeoPlannedItem]:
    """Тело POST /feo-planned-items/bulk (без прав доступа/гейта и без commit —
    см. докстринг модуля)."""
    from app.routers.feo_planned_items import _apply_payment_fields

    if not body.items:
        raise HTTPException(400, "Список позиций пуст")
    if len(body.items) > 500:
        raise HTTPException(400, "Слишком много позиций за один раз (максимум 500)")

    if body.require_item_type:
        missing_names = [
            (it.name or "").strip() or f"позиция #{i + 1}"
            for i, it in enumerate(body.items)
            if normalize_item_type(it.item_type) is None
        ]
        if missing_names:
            shown = missing_names[:5]
            more = len(missing_names) - len(shown)
            names_text = ", ".join(shown) + (f" и ещё {more}" if more > 0 else "")
            raise HTTPException(
                400,
                detail={
                    "message": (
                        f"Не указан тип (товар/услуга/работа) у {len(missing_names)} "
                        f"{'позиции' if len(missing_names) == 1 else 'позиций'}: {names_text}"
                    ),
                    "error_code": "planned_item_bulk_missing_type",
                    "names": missing_names,
                },
            )

    cat_ids = {it.feo_category_id for it in body.items}
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.id.in_(cat_ids))
    )).scalars().all()
    cat_by_id = {c.id: c for c in cats}
    missing = cat_ids - set(cat_by_id)
    if missing:
        raise HTTPException(404, f"Категория ФЭО не найдена: {', '.join(str(m) for m in sorted(missing))}")

    existing_by_cat: dict[int, list[FeoPlannedItem]] = {}
    if cat_ids:
        existing_rows = (await db.execute(
            select(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id.in_(cat_ids),
                FeoPlannedItem.is_active == True,
            )
        )).scalars().all()
        for r in existing_rows:
            existing_by_cat.setdefault(r.feo_category_id, []).append(r)

    max_sort_by_cat: dict[int, int] = {}
    for cid, rows in existing_by_cat.items():
        vals = [r.sort_order for r in rows if r.sort_order is not None]
        max_sort_by_cat[cid] = max(vals) if vals else 0

    created: list[FeoPlannedItem] = []
    new_items: list[FeoPlannedItem] = []
    dedup_seen: dict[tuple[int, str], FeoPlannedItem] = {}
    touched_subsidies: set[int] = set()

    for data in body.items:
        cat = cat_by_id[data.feo_category_id]
        norm_name = _norm_text(data.name or "")
        dedup_key = (data.feo_category_id, norm_name)
        existing_item = None
        if norm_name:
            if dedup_key in dedup_seen:
                existing_item = dedup_seen[dedup_key]
            else:
                existing_item = next(
                    (it for it in existing_by_cat.get(data.feo_category_id, [])
                     if _norm_text(it.name or "") == norm_name),
                    None,
                )
        if existing_item is not None and not data.allow_duplicate_name:
            created.append(existing_item)
            dedup_seen[dedup_key] = existing_item
            continue

        sort_order = data.sort_order
        if sort_order is None:
            max_sort_by_cat[data.feo_category_id] = max_sort_by_cat.get(data.feo_category_id, 0) + 1
            sort_order = max_sort_by_cat[data.feo_category_id]

        item = FeoPlannedItem(
            feo_category_id=data.feo_category_id,
            name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            feo_quantity=data.feo_quantity,
            feo_unit_price=data.feo_unit_price,
            feo_amount=data.feo_amount,
            notes=data.notes,
            is_active=data.is_active,
            sort_order=sort_order,
            item_type=normalize_item_type(data.item_type),
            is_feo_breakdown=data.is_feo_breakdown,
            is_internal_plan=data.is_internal_plan,
            is_composite=data.is_composite,
            need_level=normalize_need_level(data.need_level),
        )
        _apply_payment_fields(item, data)
        db.add(item)
        created.append(item)
        new_items.append(item)
        if norm_name:
            dedup_seen[dedup_key] = item
        if cat.subsidy_id is not None:
            touched_subsidies.add(cat.subsidy_id)
        if sync_catalog and data.sync_product_kind:
            await apply_item_type_to_product(db, data.product_id, item.item_type)

    await db.flush()

    for it in new_items:
        await feo_history.record_created(
            db, feo_history.ENTITY_FEO_ITEM, it.id, user,
            source=source, source_ref=source_ref, commit=False,
        )

    if create_version and touched_subsidies:
        from app.routers.purchases import _create_plan_graph_version
        for sid in touched_subsidies:
            await _create_plan_graph_version(
                subsidy_id=sid, db=db, user=user,
                note="Авто-версия: массовое создание плановых позиций",
            )

    return created


async def update_planned_item(
    db: AsyncSession,
    user,
    item: FeoPlannedItem,
    data: FeoPlannedItemCreate,
    *,
    sync_catalog: bool = True,
    source: str = feo_history.SOURCE_MANUAL,
    source_ref: Optional[int] = None,
    create_version: bool = True,
) -> FeoPlannedItem:
    """Тело PUT /feo-planned-items/{id} (без прав доступа/гейта и без commit —
    см. докстринг модуля). `item` — уже загруженная позиция."""
    from app.routers.feo_planned_items import _apply_payment_fields

    _feo_cat_id = item.feo_category_id
    _tracked_fields = (
        "name", "quantity", "unit", "unit_price", "feo_quantity",
        "feo_unit_price", "feo_amount", "notes", "is_active", "sort_order",
        "item_type", "is_feo_breakdown", "is_internal_plan", "is_composite",
        "feo_category_id", "payment_mode", "planned_date",
        "monthly_start_date", "monthly_end_date", "monthly_amount",
        "months_count", "amount", "need_level",
    )
    _old_values = {f: getattr(item, f) for f in _tracked_fields}
    item.name = data.name
    item.quantity = data.quantity
    item.unit = data.unit
    item.unit_price = data.unit_price
    item.feo_quantity = data.feo_quantity
    item.feo_unit_price = data.feo_unit_price
    item.feo_amount = data.feo_amount
    item.notes = data.notes
    item.is_active = data.is_active
    item.sort_order = data.sort_order
    if "need_level" in data.model_fields_set:
        item.need_level = normalize_need_level(data.need_level)
    if "item_type" in data.model_fields_set:
        item.item_type = normalize_item_type(data.item_type)
        _sync_product_id = data.product_id
        if data.sync_product_kind and _sync_product_id is None:
            _sync_product_id = await resolve_product_for_planned_item(db, item)
        if sync_catalog and data.sync_product_kind:
            _synced = await apply_item_type_to_product(db, _sync_product_id, item.item_type)
            if _synced:
                item.product_kind_synced = True
                _synced_product = (
                    await db.execute(select(Product.id, Product.name).where(Product.id == _sync_product_id))
                ).first()
                item.product_name = _synced_product.name if _synced_product else None
    if "is_feo_breakdown" in data.model_fields_set:
        item.is_feo_breakdown = data.is_feo_breakdown
    if "is_internal_plan" in data.model_fields_set:
        item.is_internal_plan = data.is_internal_plan
    if "is_composite" in data.model_fields_set:
        item.is_composite = data.is_composite
    if data.payment_mode != "monthly":
        data.amount, data.unit_price = backfill_unit_price_on_quantity_change(
            old_quantity=_old_values.get("quantity"), old_amount=_old_values.get("amount"),
            old_unit_price=_old_values.get("unit_price"),
            new_quantity=data.quantity, new_amount=data.amount, new_unit_price=data.unit_price,
        )
        item.unit_price = data.unit_price
    _apply_payment_fields(item, data)

    if data.feo_category_id != _feo_cat_id:
        old_cat = (
            await db.execute(select(FeoCategory).where(FeoCategory.id == _feo_cat_id))
        ).scalar_one_or_none() if _feo_cat_id is not None else None
        new_cat = (
            await db.execute(select(FeoCategory).where(FeoCategory.id == data.feo_category_id))
        ).scalar_one_or_none()
        if not new_cat:
            raise HTTPException(404, "Категория ФЭО назначения не найдена")
        if old_cat is not None and old_cat.subsidy_id != new_cat.subsidy_id:
            raise HTTPException(
                409,
                f"Категория «{old_cat.name}» относится к другой субсидии, чем «{new_cat.name}» — "
                "перенос плановой позиции между субсидиями невозможен.",
            )
        from app.services.plan_autoassign import move_planned_item_to_category
        await move_planned_item_to_category(db, item, data.feo_category_id, record_history=False)

    _new_values = {f: getattr(item, f) for f in _tracked_fields}
    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_ITEM, item.id, user,
        _old_values, _new_values,
        source=source, source_ref=source_ref, commit=False,
    )

    _sid = (await db.execute(
        select(FeoCategory.subsidy_id).where(FeoCategory.id == item.feo_category_id)
    )).scalar_one_or_none()
    if create_version and _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=_sid, db=db, user=user, note="Авто-версия: изменение плановых позиций",
        )
    return item


async def delete_planned_item(
    db: AsyncSession,
    user,
    item: FeoPlannedItem,
    cat: FeoCategory,
    *,
    purchase_id: Optional[int] = None,
    wish_id: Optional[int] = None,
    source: str = feo_history.SOURCE_MANUAL,
    source_ref: Optional[int] = None,
    create_version: bool = True,
) -> None:
    """Тело DELETE /feo-planned-items/{id} (без прав доступа/гейта и без
    commit — см. докстринг модуля). `item`/`cat` — уже загруженные объекты."""
    item_id = item.id
    _sid = cat.subsidy_id

    own_purchase_id = purchase_id
    own_wish_ids: set[int] = set()
    if purchase_id is not None:
        _wish_from_purchase = (await db.execute(
            select(Purchase.wish_id).where(Purchase.id == purchase_id)
        )).scalar_one_or_none()
        if _wish_from_purchase is not None:
            own_wish_ids.add(_wish_from_purchase)
    if wish_id is not None:
        own_wish_ids.add(wish_id)

    pi_holder_rows = (await db.execute(
        select(Purchase.id, Purchase.registry_number)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .distinct()
    )).all()
    wi_holder_rows = (await db.execute(
        select(Wish.id, Wish.title)
        .join(WishItem, WishItem.wish_id == Wish.id)
        .where(WishItem.feo_planned_item_id == item_id)
        .distinct()
    )).all()

    foreign_purchases = [(pid, reg) for pid, reg in pi_holder_rows if pid != own_purchase_id]
    foreign_wishes = [(wid, title) for wid, title in wi_holder_rows if wid not in own_wish_ids]

    if foreign_purchases or foreign_wishes:
        holders = [f"закупка {reg or ('№' + str(pid))}" for pid, reg in foreign_purchases]
        holders += [f"заявка №{wid}" for wid, _title in foreign_wishes]
        shown = holders[:3]
        more = len(holders) - len(shown)
        holders_text = ", ".join(shown) + (f" и ещё {more}" if more > 0 else "")
        raise HTTPException(
            409,
            f"Плановую позицию «{item.name}» использует не только эта закупка: "
            f"{holders_text}. Сначала снимите привязку там — из этой карточки "
            "удалять нельзя.",
        )

    await db.execute(
        sql_update(PurchaseItem)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .values(feo_planned_item_id=None)
    )
    await db.execute(
        sql_update(WishItem)
        .where(WishItem.feo_planned_item_id == item_id)
        .values(feo_planned_item_id=None)
    )
    await db.delete(item)
    await db.flush()
    await feo_history.record_deleted(
        db, feo_history.ENTITY_FEO_ITEM, item_id, user,
        source=source, source_ref=source_ref, commit=False,
    )
    if create_version and _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=_sid, db=db, user=user, note="Авто-версия: изменение плановых позиций",
        )
