"""Применение предпросмотра загрузки обратно «Выгрузить ФЭО» (владелец,
20.10.2026) — ЕДИНСТВЕННОЕ место, которое пишет в БД для этой фичи.

ПРАВИЛО №6: создание/правка/перенос категорий и позиций — через
существующие сервисы, которыми пользуется дерево ФЭО и «Импорт ФЭО»
(app.services.feo_category_write, feo_item_write, feo_tree_write) — второй
механизм не заводится. Журнал — существующий FeoImportRun/entity_changes
(source=feo_history.SOURCE_IMPORT), как и у «Импорт ФЭО».

Один проход по `resolved` (diff.build_hierarchy) в порядке файла — файл уже
в порядке «родитель перед детьми» (так его пишет feo_export_xlsx.py), поэтому
к моменту обработки ребёнка id его родителя (новый или существующий) уже
известен — второй проход не нужен.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.schemas.schemas import FeoCategoryCreate
from app.schemas.feo import FeoPlannedItemCreate
from app.services import feo_category_write, feo_item_write, feo_tree_write
from app.services import feo_history
from app.services.feo_roundtrip_import.diff import KIND_CATEGORY, ResolvedRow, _norm_name


async def apply_rows(db, user, subsidy_id: int, resolved: list, run_id: int) -> dict:
    """Выполняет план `resolved` (без строк с .error — вызывающий роутер
    обязан отказать apply при наличии errors, см. ПРАВИЛО №8). Возвращает
    {created, updated, moved} — счётчики для ответа и FeoImportRun."""
    entity_id_by_index: dict[int, int] = {}
    cat_obj_by_index: dict[int, FeoCategory] = {}
    created = 0
    updated = 0
    moved = 0

    for i, rr in enumerate(resolved):
        if rr.error:
            continue
        parent_id = None
        parent_cat = None
        if rr.parent_index is not None:
            parent_id = entity_id_by_index.get(rr.parent_index)
            parent_cat = cat_obj_by_index.get(rr.parent_index)
            if parent_id is None:
                # родитель не был успешно обработан — пропускаем молча
                # (preview уже должен было пометить это как ошибку выше по
                # цепочке; defensive, не должно происходить).
                continue

        if rr.kind == KIND_CATEGORY:
            cat, did_create, did_update, did_move = await _apply_category_row(
                db, user, subsidy_id, rr, parent_id, run_id,
            )
            entity_id_by_index[i] = cat.id
            cat_obj_by_index[i] = cat
            created += int(did_create)
            updated += int(did_update)
            moved += int(did_move)
        else:
            item, did_create, did_update, did_move = await _apply_item_row(
                db, user, rr, parent_id, parent_cat, run_id,
            )
            entity_id_by_index[i] = item.id
            created += int(did_create)
            updated += int(did_update)
            moved += int(did_move)

    return {"created": created, "updated": updated, "moved": moved}


async def _apply_category_row(db, user, subsidy_id, rr: ResolvedRow, parent_id, run_id):
    p = rr.parsed
    if rr.is_new:
        data = FeoCategoryCreate(
            subsidy_id=subsidy_id,
            parent_id=parent_id,
            name=p.name,
            code=p.code,
            appendix=p.appendix,
            is_active=p.is_active if p.is_active is not None else True,
            budget=float(p.feo_amount) if (p.feo_amount is not None and not rr.has_children_in_file) else None,
        )
        cat = await feo_category_write.create_category(
            db, user, data, source=feo_history.SOURCE_IMPORT, source_ref=run_id,
        )
        return cat, True, False, False

    cat = await db.get(FeoCategory, rr.entity_id)
    did_move = False
    if cat.parent_id != parent_id:
        await feo_tree_write.move_category(
            db, user, cat, parent_id, source=feo_history.SOURCE_IMPORT, source_ref=run_id,
        )
        did_move = True

    update_kwargs = {"subsidy_id": subsidy_id}
    if p.name and _norm_name(p.name) != _norm_name(cat.name):
        update_kwargs["name"] = p.name
    if p.code is not None and (p.code or None) != (cat.code or None):
        update_kwargs["code"] = p.code
    if p.appendix is not None and (p.appendix or None) != (cat.appendix or None):
        update_kwargs["appendix"] = p.appendix
    if p.is_active is not None and p.is_active != cat.is_active:
        update_kwargs["is_active"] = p.is_active
    if not rr.has_children_in_file and p.feo_amount is not None:
        _old = float(cat.budget) if cat.budget is not None else None
        if _old is None or abs(_old - float(p.feo_amount)) >= 0.005:
            update_kwargs["budget"] = float(p.feo_amount)

    did_update = len(update_kwargs) > 1  # больше, чем только subsidy_id
    if did_update:
        # name — обязательное поле схемы, передаём текущее, если сам не менялся.
        update_kwargs.setdefault("name", cat.name)
        data = FeoCategoryCreate(**update_kwargs)
        await feo_category_write.update_category(
            db, user, cat, data, source=feo_history.SOURCE_IMPORT, source_ref=run_id,
            create_version=False,
        )
    return cat, False, did_update, did_move


async def _apply_item_row(db, user, rr: ResolvedRow, parent_id, parent_cat, run_id):
    """ДВА независимых комплекта чисел позиции (см. докстринг FeoPlannedItem и
    diff.py::_diff_item_fields) — «по ФЭО» (feo_quantity/feo_unit_price/
    feo_amount) и «план» (quantity/unit_price/amount), `unit` общий.
    rr.resolved_feo_amount/resolved_plan_amount — уже сведённые build_preview
    суммы (кол-во×цена, если сама сумма пуста/расходится — см.
    amount_resolve.resolve_amount), второй раз здесь не считаем (ПРАВИЛО №6)."""
    p = rr.parsed
    if rr.is_new:
        data = FeoPlannedItemCreate(
            feo_category_id=parent_id,
            name=p.name,
            quantity=p.plan_qty,
            unit=p.feo_unit,
            unit_price=p.plan_unit_price,
            amount=rr.resolved_plan_amount,
            feo_quantity=p.feo_qty,
            feo_unit_price=p.feo_unit_price,
            feo_amount=rr.resolved_feo_amount,
            is_active=p.is_active if p.is_active is not None else True,
        )
        if parent_cat is None:
            parent_cat = await db.get(FeoCategory, parent_id)
        item = await feo_item_write.create_planned_item(
            db, user, parent_cat, data,
            source=feo_history.SOURCE_IMPORT, source_ref=run_id, create_version=False,
        )
        return item, True, False, False

    item = await db.get(FeoPlannedItem, rr.entity_id)
    did_move = item.feo_category_id != parent_id

    merged_feo_quantity = p.feo_qty if p.feo_qty is not None else item.feo_quantity
    merged_unit = p.feo_unit if p.feo_unit is not None else item.unit
    merged_feo_unit_price = p.feo_unit_price if p.feo_unit_price is not None else item.feo_unit_price
    merged_feo_amount = rr.resolved_feo_amount if rr.resolved_feo_amount is not None else item.feo_amount
    merged_quantity = p.plan_qty if p.plan_qty is not None else item.quantity
    merged_unit_price = p.plan_unit_price if p.plan_unit_price is not None else item.unit_price
    merged_amount = rr.resolved_plan_amount if rr.resolved_plan_amount is not None else item.amount
    # Имя переписываем только при РЕАЛЬНОМ отличии (не пробелы) — иначе апдейт
    # по другому полю (напр. feo_amount) заодно переписал бы cat/item.name
    # вариантом пробелов из файла, не тронув смысл (ПРАВИЛО №6, та же
    # нормализация, что и в diff.py::_norm_name).
    merged_name = p.name if (p.name and _norm_name(p.name) != _norm_name(item.name)) else item.name
    merged_active = p.is_active if p.is_active is not None else item.is_active

    changed = (
        _norm_name(merged_name) != _norm_name(item.name)
        or _dec_changed(merged_feo_quantity, item.feo_quantity)
        or (merged_unit or None) != (item.unit or None)
        or _dec_changed(merged_feo_unit_price, item.feo_unit_price)
        or _dec_changed(merged_feo_amount, item.feo_amount)
        or _dec_changed(merged_quantity, item.quantity)
        or _dec_changed(merged_unit_price, item.unit_price)
        or _dec_changed(merged_amount, item.amount)
        or merged_active != item.is_active
        or did_move
    )
    if not changed:
        return item, False, False, False

    data = FeoPlannedItemCreate(
        feo_category_id=parent_id,
        name=merged_name,
        quantity=merged_quantity,
        unit=merged_unit,
        unit_price=merged_unit_price,
        amount=merged_amount,
        feo_quantity=merged_feo_quantity,
        feo_unit_price=merged_feo_unit_price,
        feo_amount=merged_feo_amount,
        is_active=merged_active,
        notes=item.notes,
        item_type=item.item_type,
        sort_order=item.sort_order,
        payment_mode=item.payment_mode or "one_time",
    )
    await feo_item_write.update_planned_item(
        db, user, item, data,
        source=feo_history.SOURCE_IMPORT, source_ref=run_id, create_version=False,
    )
    return item, False, True, did_move


def _dec_changed(a, b) -> bool:
    fa = float(a) if a is not None else None
    fb = float(b) if b is not None else None
    if fa is None and fb is None:
        return False
    if fa is None or fb is None:
        return True
    return abs(fa - fb) >= 0.005
