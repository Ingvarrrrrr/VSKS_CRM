"""Авто-план для авансовых отчётов (Purchase.purchase_method == 'advance').

Владелец (30.09.2026, решение повторное и жёсткое): «Из авансового все
позиции АВТОМАТИЧЕСКИ привязываются к плану. Не надо там искать сопоставление.
Это отдельная покупка, которую человек принёс в чеке — её не было в плане.
Не сопоставляем».

В отличие от app.services.plan_autoassign.auto_assign_planned_items — общий
путь «закупка сама становится планом» (ищет существующую FeoPlannedItem по
ТОЧНОМУ совпадению нормализованного имени в категории и только потом
создаёт) — здесь поиск/дедуп по имени НЕ выполняется НИКОГДА: каждая позиция
авансового отчёта без своей плановой позиции получает СОБСТВЕННУЮ новую (по
построению — сравнимо с allow_duplicate_name=True у ручного создания,
app/routers/feo_planned_items.py). «Доставка» из двух разных чеков не должна
схлопнуться в одну плановую строку только потому, что называется одинаково.

Само конструирование новой FeoPlannedItem — ОБЩИЙ хелпер
plan_autoassign.create_auto_planned_item (Правило №6 — тот же код, которым
пользуется auto_assign_planned_items), не вторая копия.

Единственная точка входа — sync_advance_auto_plan_items, вызывается при
КАЖДОМ сохранении авансового отчёта (создание, PUT, точечный PATCH позиции,
пересчёт из чеков) — см. её докстринг.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def sync_advance_auto_plan_items(
    items, fallback_category_id: Optional[int], db: AsyncSession, *, note: str = "авансовым отчётом",
) -> None:
    """Синхронизирует привязку к плану ФЭО для позиций авансового отчёта.

    `items` — PurchaseItem (ORM-строки ИЛИ ещё pydantic PurchaseItemCreate-
    объекты до сохранения, см. app.services.plan_autoassign.auto_assign_planned_items,
    тот же набор атрибутов: item_name/quantity/unit/unit_price/total_price/
    item_type/feo_category_id/feo_planned_item_id/over_plan/purchase_id).

    Для каждой позиции:
      - over_plan=True → пропускаем целиком (сознательно сверх плана, авто-план
        ей не положен, ни создание, ни обновление существующей привязки);
      - нет ни своей (feo_category_id), ни шапочной (fallback_category_id)
        категории ФЭО:
          * если позиция уже ссылалась на СВОЮ auto_created плановую — отвязываем
            и убираем плановую, если она осиротела (deactivate_if_orphaned) —
            категорию убрали, план по ней больше не нужен;
          * иначе — пропускаем; план появится сам при следующем сохранении,
            когда категория будет проставлена (тот же хук вызывается на каждое
            сохранение — задача, п.1: «создать плановую при появлении категории»);
      - feo_planned_item_id уже указывает на плановую позицию, заведённую
        ЧЕЛОВЕКОМ (auto_created=False) — НЕ трогаем: ручная привязка (в т.ч.
        унаследованная от периода до этой правки) не перебивается автоматикой;
      - feo_planned_item_id указывает на СВОЮ auto_created позицию — обновляем
        её название/количество/цену/сумму/категорию на месте (владелец, п.1:
        «если меняются количество/цена — авто-плановая обновляется так же»,
        иначе следующее сохранение решило бы, что ТЗ превысило старый план);
      - иначе (привязки нет, или ссылка на несуществующую строку) — создаёт
        НОВУЮ auto_created FeoPlannedItem через
        plan_autoassign.create_auto_planned_item, БЕЗ поиска существующей.

    Commit — на вызывающем (как и у auto_assign_planned_items).
    """
    from app.models.feo_planned_item import FeoPlannedItem
    from app.services.plan_autoassign import (
        create_auto_planned_item,
        backfill_item_type_from_plan,
        deactivate_if_orphaned,
    )

    items = list(items)
    if not items:
        return

    _existing_fpi_ids = {
        getattr(it, "feo_planned_item_id", None) for it in items
        if getattr(it, "feo_planned_item_id", None)
    }
    _fpi_by_id: dict[int, FeoPlannedItem] = {}
    if _existing_fpi_ids:
        _rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(_existing_fpi_ids))
        )).scalars().all()
        _fpi_by_id = {r.id: r for r in _rows}

    for it in items:
        if getattr(it, "over_plan", False):
            continue

        eff_cat_id = getattr(it, "feo_category_id", None) or fallback_category_id
        fpi_id = getattr(it, "feo_planned_item_id", None)
        fpi = _fpi_by_id.get(fpi_id) if fpi_id else None

        if eff_cat_id is None:
            # Категория снята/ещё не выбрана — авто-плановой позиции без неё
            # не бывает (см. докстринг). Своя auto_created привязка, если была,
            # отвязывается и уходит на уборку — иначе останется указывать на
            # категорию, которой у позиции больше нет.
            if fpi is not None and fpi.auto_created:
                it.feo_planned_item_id = None
                await deactivate_if_orphaned(db, fpi)
            continue

        if fpi is not None and not fpi.auto_created:
            # Плановая позиция заведена человеком — не наша забота (владелец
            # не просил перебивать ручные привязки автоматикой).
            continue

        if fpi is not None and fpi.auto_created:
            # Своя авто-плановая — синхронизируем числа/категорию на месте,
            # НЕ заводя вторую (Правило №6 — один источник чисел на позицию).
            _name = getattr(it, "item_name", None)
            if _name:
                fpi.name = _name
            fpi.quantity = getattr(it, "quantity", None)
            fpi.unit = getattr(it, "unit", None)
            fpi.unit_price = getattr(it, "unit_price", None)
            fpi.amount = getattr(it, "total_price", None)
            _item_type = getattr(it, "item_type", None)
            if _item_type:
                fpi.item_type = _item_type
            if fpi.feo_category_id != eff_cat_id:
                fpi.feo_category_id = eff_cat_id
            continue

        # Нет привязки (или ссылка на несуществующую/уже удалённую строку) —
        # новая СОБСТВЕННАЯ плановая, БЕЗ поиска существующей по имени
        # (владелец, 30.09.2026: «не сопоставляем»).
        new_fpi = await create_auto_planned_item(db, it, eff_cat_id, note)
        it.feo_planned_item_id = new_fpi.id
        if hasattr(it, "over_plan"):
            it.over_plan = False

    await backfill_item_type_from_plan(items, db)
