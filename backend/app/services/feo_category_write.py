"""Запись дерева категорий ФЭО — create/update/delete. ЕДИНАЯ точка записи
(Правило №6), вынесена из app/routers/feo_categories.py (Правило №5,
модульность) без изменения поведения.

Зачем: позже правки исполнителя будут копиться в «корректировке» субсидии и
применяться ПОСЛЕ утверждения — применение обязано пройти ТЕ ЖЕ проверки и
ту же запись, что и прямая правка. Если логика записи размазана по роутеру,
применение корректировки неизбежно плодит вторую, слегка другую копию
(ровно то, от чего предостерегает Правило №6). Здесь — то единственное место,
которое вызывает и сам роутер (прямая правка), и (следующим шагом, отдельной
задачей) применение корректировки.

Контракт каждой функции:
- принимает `db`, `user`, данные + уже ЗАГРУЖЕННЫЙ ORM-объект там, где он
  нужен (update/delete получают `cat`, загруженную ВЫЗЫВАЮЩИМ роутером — так
  право по субсидии проверяется по объекту из БД, а не по телу запроса, см.
  docstring _require_feo_category_write в routers/feo_categories.py);
- НЕ коммитит — коммит остаётся за вызывающим роутером (db.add()/db.flush()
  здесь допустимы, db.commit() — нет);
- НЕ проверяет права — гейты (_require_feo_category_write,
  assert_direct_edit) остаются в роутере;
- принимает `source`/`source_ref` (идут как есть в feo_history.record_*) и
  `create_version` (гейтит вызов _create_plan_graph_version) — дефолт
  ('manual', None, True) это прямая правка человеком через HTTP; применение
  корректировки позже передаст свои значения (source='revision',
  source_ref=<id корректировки>, create_version=False — одна версия плана на
  весь пакет правок корректировки, а не по версии на поле).
"""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryCreate
from app.services import feo_history

# Поля категории, которые реально правятся через create/update (кроме
# parent_id/subsidy_id — им управляют отдельно: create получает их явно,
# move — отдельная ручка, субсидию категория не меняет никогда).
TRACKED_FIELDS = (
    "name", "code", "appendix", "is_active", "description", "budget",
    "feo_quantity", "feo_unit", "feo_amount", "planned_quantity",
    "planned_amount", "unit", "plan_source", "manual_plan_amount",
    # ФОТ и иные выплаты персоналу (решение владельца 07.10.2026, план
    # .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2) — ручной
    # переключатель, через тот же PUT, без отдельной ручки.
    "is_payroll",
)


def validate_plan_pair(planned_quantity: Optional[float], planned_amount: Optional[float]) -> None:
    """Правило владельца (2026-08-09): плановое количество и плановая цена за
    единицу — ПАРА. См. полный докстринг в прежнем месте
    (routers/feo_categories.py, история до разрезания) — поведение и текст
    сообщений не менялись, перенесено как есть.
    «Заполнено» = число > 0 (не просто not None) — совпадает с порогом
    app.services.feo_plan.compute_feo_plan_tree._visit (qty > 0 and amt > 0).
    """
    qty_filled = planned_quantity is not None and float(planned_quantity) > 0
    amt_filled = planned_amount is not None and float(planned_amount) > 0
    if qty_filled == amt_filled:
        return
    if qty_filled:
        detail = (
            "Задано плановое количество, но не задана плановая стоимость за единицу. "
            "Заполните оба поля («Плановое количество» и «Плановая стоимость за ед.») — "
            "тогда сумма посчитается автоматически, — либо очистите количество и задайте "
            "план общей суммой отдельной плановой позицией (кнопка «Добавить плановую» "
            "в панели) без указания количества."
        )
    else:
        detail = (
            "Задана плановая стоимость за единицу, но не задано плановое количество. "
            "Заполните оба поля («Плановое количество» и «Плановая стоимость за ед.») — "
            "тогда сумма посчитается автоматически, — либо очистите цену и задайте план "
            "общей суммой отдельной плановой позицией (кнопка «Добавить плановую» в "
            "панели) без указания количества."
        )
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def plan_pair_unchanged(
    old_quantity: Optional[float], old_amount: Optional[float],
    new_quantity: Optional[float], new_amount: Optional[float],
) -> bool:
    """Дефект 2026-08-31: пара обязана биться ТОЛЬКО когда пользователь реально
    ЗАДАЁТ/МЕНЯЕТ одно из двух полей — см. прежний докстринг в
    routers/feo_categories.py (история до разрезания)."""
    def norm(v):
        return None if v is None else float(v)
    return norm(old_quantity) == norm(new_quantity) and norm(old_amount) == norm(new_amount)


async def create_category(
    db: AsyncSession, user, category_data: FeoCategoryCreate,
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
) -> FeoCategory:
    """Тело POST /feo-categories/ (без гейта прав и без коммита — см. контракт
    модуля)."""
    validate_plan_pair(category_data.planned_quantity, category_data.planned_amount)

    if category_data.parent_id:
        parent = (await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена")
        level = parent.level + 1
    else:
        level = 1

    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active,
        description=category_data.description,
        budget=category_data.budget,
        feo_quantity=category_data.feo_quantity,
        feo_unit=category_data.feo_unit,
        feo_amount=category_data.feo_amount,
        planned_quantity=category_data.planned_quantity,
        planned_amount=category_data.planned_amount,
        unit=category_data.unit,
        plan_source=category_data.plan_source or "planned_items",
        manual_plan_amount=category_data.manual_plan_amount,
        is_payroll=bool(category_data.is_payroll),
    )
    db.add(new_category)
    await db.flush()
    await feo_history.record_created(
        db, feo_history.ENTITY_FEO_CATEGORY, new_category.id, user,
        source=source, source_ref=source_ref, commit=False,
    )
    return new_category


async def update_category(
    db: AsyncSession, user, cat: FeoCategory, category_data: FeoCategoryCreate,
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
    create_version: bool = True,
) -> dict:
    """Тело PUT /feo-categories/{cat_id} (без гейта прав и без коммита).

    Дефект 2026-10-02 (прод): инлайн-правка одного поля с фронта шлёт PUT БЕЗ
    остальных полей FeoCategoryCreate — раньше код присваивал ВСЕ поля схемы
    безусловно, молча стирая описание/ФЭО-количество/сумму/ручной план и
    сбрасывая plan_source в дефолт. Фикс: правятся ТОЛЬКО поля, реально
    присланные в запросе (`category_data.model_fields_set`, пустая строка →
    None нормализуется до этого в FeoCategoryCreate.empty_numeric_strings_to_none
    и не мешает exclude_unset — валидатор трогает только УЖЕ присутствующие в
    теле ключи, не добавляет новых). Диалог FeoCategoryDialog.vue шлёт ВСЕ
    поля явно (buildCategoryFullPayload) — для него exclude_unset не меняет
    ничего, очистка поля через null по-прежнему применяется.

    planned_quantity/planned_amount для проверки «пара обязана биться»
    считаются ПОСЛЕ слияния частичной правки с текущими значениями категории
    (merged_qty/merged_amount) — не сырыми полями запроса, которые при
    частичной правке были бы ошибочно None, даже если пара в БД не менялась.

    Возвращает {"category": cat, "warning": Optional[str]}.
    """
    update_fields = category_data.model_dump(exclude_unset=True)

    merged_qty = update_fields.get("planned_quantity", cat.planned_quantity)
    merged_amount = update_fields.get("planned_amount", cat.planned_amount)
    if not plan_pair_unchanged(cat.planned_quantity, cat.planned_amount, merged_qty, merged_amount):
        validate_plan_pair(merged_qty, merged_amount)

    _old_values = {f: getattr(cat, f) for f in TRACKED_FIELDS}
    _old_plan = (
        cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount,
        cat.plan_source, cat.manual_plan_amount,
    )

    for field in TRACKED_FIELDS:
        if field not in update_fields:
            continue
        value = update_fields[field]
        if field == "plan_source":
            value = value or "planned_items"
        setattr(cat, field, value)

    # Задача владельца «план ≠ факт» (шаг D, сессия 2026-08-06): защита от
    # повторения К1 (боевые 16 760 000 — сумма записана в поле «цена за
    # единицу»). НЕ блокируем, только предупреждаем, если planned_quantity ×
    # planned_amount более чем вдвое больше финансирования ФЭО.
    warning: Optional[str] = None
    if (
        cat.planned_quantity is not None and float(cat.planned_quantity) > 1
        and cat.planned_amount is not None
        and cat.budget is not None and float(cat.budget) > 0
    ):
        _qty = float(cat.planned_quantity)
        _amt = float(cat.planned_amount)
        _budget = float(cat.budget)
        _total = _qty * _amt
        if _total > _budget * 2:
            warning = (
                f"Похоже, в поле «Цена за единицу» введена сумма: "
                f"{_qty:g} × {_amt:,.2f} = {_total:,.2f} ₽ при финансировании {_budget:,.2f} ₽."
            )

    # Владелец, план zany-fluttering-mountain.md (2026-08-13): предупреждение
    # о смене режима расчёта плана, если под категорией уже есть плановые
    # позиции — переключение на 'manual_sum' их не удаляет, но планом
    # становится введённая сумма, а не их Σ.
    if _old_plan[5] != cat.plan_source:
        from app.models.feo_planned_item import FeoPlannedItem as _FeoPlannedItem
        _items_cnt = (await db.execute(
            select(func.count(_FeoPlannedItem.id))
            .where(_FeoPlannedItem.feo_category_id == cat.id)
            .where(_FeoPlannedItem.is_active.is_(True))
        )).scalar_one()
        if _items_cnt:
            _mode_warning = (
                f"Смена способа расчёта плана: у категории уже есть {_items_cnt} "
                f"плановых позиций. "
                + (
                    "Планом теперь становится введённая сумма, а не их Σ — если сумма "
                    "меньше, появится превышение."
                    if cat.plan_source == "manual_sum"
                    else "Планом снова становится Σ плановых позиций."
                )
            )
            warning = f"{warning} {_mode_warning}" if warning else _mode_warning

    _new_plan = (
        cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount,
        cat.plan_source, cat.manual_plan_amount,
    )
    if create_version and _new_plan != _old_plan and cat.subsidy_id:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=cat.subsidy_id, db=db, user=user,
            note=f"Авто-версия: изменение плановых показателей ФЭО «{cat.name}»",
        )

    _new_values = {f: getattr(cat, f) for f in TRACKED_FIELDS}
    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_CATEGORY, cat.id, user,
        _old_values, _new_values,
        source=source, source_ref=source_ref, commit=False,
    )
    return {"category": cat, "warning": warning}


# Удаление блокируют только закупки, по которым работа реально идёт (стадия
# «Ведётся работа» и далее). Желания/план закупок/подтверждено — работа не
# начата, категория удаляется, привязка обнуляется (FK SET NULL).
BLOCKING_STATUSES = ("work_in_progress", "contracted", "ordered", "delivered", "paid")


async def collect_blocking_purchases(ids: list[int], db: AsyncSession) -> list:
    """Закупки в блокирующих статусах, привязанные к переданным категориям
    напрямую (Purchase.feo_category_id) либо через позиции
    (PurchaseItem.feo_category_id). Уникальные по id, поля: id,
    purchase_number, subject, status."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    direct = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status).where(
            Purchase.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()
    via_items = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()

    seen: dict[int, object] = {}
    for row in direct:
        seen[row.id] = row
    for row in via_items:
        seen.setdefault(row.id, row)
    return list(seen.values())


# Обратная совместимость с именами, под которыми этот код жил в
# routers/feo_categories.py до разрезания (нижнее подчёркивание — туда его и
# ре-экспортирует feo_categories.py, см. его шапку).
_collect_blocking_purchases = collect_blocking_purchases


async def purge_feo_categories(
    ids: list[int], db: AsyncSession, user=None,
    source: str = feo_history.SOURCE_MANUAL, source_ref: int | None = None,
    record_history: bool = True,
):
    """Отвязать все ссылки на переданные категории и удалить их. Не коммитит —
    коммитит вызывающий.

    `source`/`source_ref` — по умолчанию 'manual' (удаление категории
    человеком через DELETE /{cat_id}), но feo_import_remap.py зовёт эту же
    функцию для удаления опустевших узлов при переезде с source='import' +
    source_ref=id прогона (Правило №6 — один механизм удаления категории).
    `record_history=False` — dry_run: очистка ссылок и DELETE всё равно
    отрабатывают (иначе dry_run не показал бы реальный итог), но откатятся
    вместе со всей транзакцией; история пишется только для боевого прогона.
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem

    # Отвязать закупки ранних стадий и их позиции от удаляемого поддерева
    await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id.in_(ids)).values(feo_category_id=None)
    )
    await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK references in products before deleting
    await db.execute(
        Product.__table__.update().where(Product.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK in purchase_items referencing planned_items of these categories
    planned_item_ids = (await db.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalars().all()
    if planned_item_ids:
        await db.execute(
            PurchaseItem.__table__.update().where(
                PurchaseItem.feo_planned_item_id.in_(planned_item_ids)
            ).values(feo_planned_item_id=None)
        )

    if record_history:
        for _pi_id in planned_item_ids:
            await feo_history.record_deleted(
                db, feo_history.ENTITY_FEO_ITEM, _pi_id, user,
                source=source, source_ref=source_ref, commit=False,
            )

    # Delete planned items explicitly (in case DB lacks CASCADE)
    await db.execute(
        FeoPlannedItem.__table__.delete().where(FeoPlannedItem.feo_category_id.in_(ids))
    )

    if record_history:
        for _cat_id in ids:
            await feo_history.record_deleted(
                db, feo_history.ENTITY_FEO_CATEGORY, _cat_id, user,
                source=source, source_ref=source_ref, commit=False,
            )

    # Delete categories in one statement — feo_categories.parent_id is
    # ON DELETE CASCADE in the DB, so order doesn't matter.
    await db.execute(
        FeoCategory.__table__.delete().where(FeoCategory.id.in_(ids))
    )


# Обратная совместимость с прежним именем (routers/feo_categories.py
# ре-экспортирует именно под этим именем — см. его докстринг и
# feo_import_remap.py::`fc._purge_feo_categories`).
_purge_feo_categories = purge_feo_categories


async def delete_category(
    db: AsyncSession, user, cat: FeoCategory,
    *, source: str = feo_history.SOURCE_MANUAL, source_ref: Optional[int] = None,
) -> dict:
    """Тело DELETE /feo-categories/{cat_id} (без гейта прав и без коммита).

    Обход поддерева — через `app.routers.feo_categories._collect_subtree_ids`,
    отложенным (внутрифункциональным) импортом: та функция уже используется
    внешним кодом (purchases.py, feo_tree_ops.py) и переносить её тоже значило
    бы задевать файлы вне разрешённого списка правки — Правило №6 здесь
    соблюдено переиспользованием единственного существующего обхода дерева,
    а не второй его копией.
    """
    from app.routers.feo_categories import _collect_subtree_ids

    all_ids = await _collect_subtree_ids(cat.id, db)

    linked_purchases = await collect_blocking_purchases(all_ids, db)
    if linked_purchases:
        purchase_ids = [p.id for p in linked_purchases]
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Нельзя удалить: {len(linked_purchases)} закупок со стадией "
                    f"«Ведётся работа» и далее привязано к этой категории. "
                    f"Закупки на ранних стадиях (желания, план закупок) удалению не мешают."
                ),
                "purchase_ids": purchase_ids,
                "feo_category_ids": all_ids,
            }
        )

    await purge_feo_categories(all_ids, db, user=user, source=source, source_ref=source_ref)
    return {"deleted_count": len(all_ids)}
