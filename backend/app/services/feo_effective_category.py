"""Правило «эффективной категории ФЭО позиции» (Правило №6, 20.10.2026) —
ОДИН источник истины для него, не разбросанные копии инлайна.

Прод-баг (закупка РЕЕ-2026-04252, заявка №206): согласующий сменил категорию
ФЭО шапки заявки (feo_per_item=False — «одна категория на всю заявку»), но
14 WishItem.feo_category_id остались со старой («протухшей») категорией.
При конвертации заявки в закупку auto_assign_planned_items(
app/services/plan_autoassign.py) заводил НОВЫЕ плановые позиции в протухшей
категории товара, а не в категории шапки — хотя режим «одна категория на
всю заявку» требует обратного. Правило «эффективной категории» уже было
реализовано (но инлайн, без переиспользования) в
app/services/purchase_feo_checks.py::_item_feo_mismatch (строки 157-161,
до этой правки) — здесь оно вынесено в функцию и используется также в
app/services/plan_autoassign.py::auto_assign_planned_items, чтобы не считать
одно и то же правило в двух местах по-разному (именно это и разошлось в
проде).

Правило одно и для WishItem+Wish, и для PurchaseItem+Purchase — оба имеют
колонку `feo_per_item` (Boolean, default False) на шапке и `feo_category_id`
на позиции (см. app/models/wish.py, app/models/purchase.py).
"""
from typing import Optional


def effective_item_feo_category_id(
    per_item: bool,
    header_cat_id: Optional[int],
    item_cat_id: Optional[int],
) -> Optional[int]:
    """Категория ФЭО, которой РЕАЛЬНО принадлежит позиция (заявки или закупки).

    - `per_item=False` («одна категория на всю заявку/закупку») — эффективная
      категория ВСЕГДА категория шапки, собственная категория позиции (даже
      если она технически заполнена — протухший остаток от смены режима/
      смены категории шапки без синхронизации позиций) не учитывается.
    - `per_item=True` («разные категории для каждого товара») — собственная
      категория позиции, если задана, иначе фолбэк на категорию шапки (старые
      позиции до включения режима могли остаться без своей категории).
    """
    if not per_item:
        return header_cat_id
    return item_cat_id or header_cat_id


async def sync_items_to_header_category(
    items: list,
    old_header_cat_id: Optional[int],
    new_header_cat_id: Optional[int],
    per_item_mode: bool,
    db,
    *,
    is_advance_report: bool = False,
) -> list[str]:
    """«Позиции следуют за шапкой» (владелец, прод-баг заявки №206, 20.10.2026):
    при ВЫКЛЮЧЕННОМ per_item (`per_item_mode=False`) смена категории ФЭО шапки
    заявки/закупки обязана переносить ВСЕ позиции в новую категорию — иначе
    позиция остаётся со старой («протухшей») feo_category_id, которая потом
    копируется дальше (например, при конвертации заявки в закупку) и рождает
    расхождение категорий там, где пользователь был уверен, что категория
    одна на весь документ.

    Единая функция для обоих вызывающих путей (Правило №6, не копия):
    - app/routers/wish_transitions.py::patch_wish_execution (согласующий меняет
      feo_category_id шапки заявки через PATCH /execution);
    - app/routers/wishes.py::update_wish (полная правка заявки, PUT).

    Для каждой позиции с ДРУГОЙ категорией: feo_category_id переставляется на
    новую категорию шапки; если у позиции есть feo_planned_item_id — вызывается
    move_or_detach_planned_item (та же логика «план следует за позицией»,
    что и при точечной смене категории ОДНОЙ позиции). Предупреждения («план
    общий с другими закупками/заявками, привязка снята») собираются и
    возвращаются вызывающему — тот обязан вернуть их в ответе API, не
    проглатывать молча (тот же контракт, что и у move_or_detach_planned_item).

    Не делает ничего (пустой список), если:
    - per_item_mode=True — у каждой позиции своя категория, шапка не диктует;
    - категория шапки не менялась (old == new);
    - новой категории нет (новая категория неизвестна/снята — для этого случая
      массовый перенос ВСЕХ позиций в «без категории» слишком разрушителен,
      оставляем вызывающему явно обработать по месту, как раньше).

    Позиции с feo_planned_item_id (загружены из Плана закупок или явно
    привязаны к плановой позиции) — владелец (22.10.2026, заявка №209):
    «категория позиции по плану не меняется, даже когда меняется категория
    шапки» — пропускаются целиком: ни feo_category_id, ни привязка к плану не
    трогаются. Прод-баг был ровно в обратном: такая позиция переезжала в
    категорию шапки, move_or_detach_planned_item снимал привязку к плану, а
    «освобождённая» позиция без feo_planned_item_id дальше ложно считалась
    дублем чужой закупки той же (новой) категории (см.
    app/services/plan_duplicate_warning.py, app/services/
    wish_item_category_guard.py — единственное место правила, ПРАВИЛО №6).

    Commit не делает — это на вызывающем.
    """
    if per_item_mode or old_header_cat_id == new_header_cat_id or new_header_cat_id is None:
        return []

    from app.models.feo_planned_item import FeoPlannedItem
    from app.services.wish_item_category_guard import is_wish_item_plan_locked

    warnings: list[str] = []
    for it in items:
        if not hasattr(it, "feo_category_id"):
            continue
        if not is_advance_report and is_wish_item_plan_locked(it):
            _allow_auto = False
            if (
                not getattr(it, "from_plan", False)
                and getattr(it, "feo_planned_item_id", None) is not None
                and db is not None
            ):
                _fpi = await db.get(FeoPlannedItem, it.feo_planned_item_id)
                if _fpi is not None and _fpi.auto_created:
                    _allow_auto = True
            if not _allow_auto:
                continue
        if it.feo_category_id == new_header_cat_id:
            continue
        it.feo_category_id = new_header_cat_id
    return warnings


async def replace_wish_auto_planned_items_on_category_change(
    db,
    wish,
    old_wi_snapshot: dict[int, tuple[Optional[int], Optional[int]]],
) -> None:
    """При смене категории ФЭО в заявке отменяет (деактивирует) старые
    автосозданные плановые позиции (auto_created=True, from_plan=False) и
    создаёт/подбирает новые в новой категории ФЭО, синхронизируя незамороженные
    закупки и их позиции."""
    from sqlalchemy import select
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.services.plan_autoassign import auto_assign_planned_items, deactivate_if_orphaned
    from app.routers.purchases import TZ_FROZEN_STATUSES

    per_item_mode = bool(getattr(wish, "feo_per_item", False))
    wish_items = list(getattr(wish, "items", None) or [])
    if not wish_items:
        return

    old_fpis_to_deactivate: dict[int, FeoPlannedItem] = {}
    moved_wish_items: list = []

    linked_purchases = (await db.execute(
        select(Purchase).where(Purchase.wish_id == wish.id)
    )).scalars().all()
    unfrozen_purchase_ids = {
        p.id for p in linked_purchases if p.status not in TZ_FROZEN_STATUSES
    }

    for wi in wish_items:
        eff_cat_id = effective_item_feo_category_id(
            per_item_mode, getattr(wish, "feo_category_id", None), getattr(wi, "feo_category_id", None),
        )
        _old_cat_id, old_fpi_id = old_wi_snapshot.get(
            getattr(wi, "id", None),
            (getattr(wi, "feo_category_id", None), getattr(wi, "feo_planned_item_id", None)),
        )
        fpi_id_to_check = old_fpi_id or getattr(wi, "feo_planned_item_id", None)
        if fpi_id_to_check is None:
            continue
        old_fpi = await db.get(FeoPlannedItem, fpi_id_to_check)
        if (
            old_fpi is not None
            and old_fpi.feo_category_id != eff_cat_id
            and old_fpi.auto_created
            and not getattr(wi, "from_plan", False)
        ):
            wi.feo_planned_item_id = None
            wi.planned_item = None
            wi.over_plan = False
            wi.feo_category_id = eff_cat_id
            if getattr(wi, "id", None) is not None and unfrozen_purchase_ids:
                linked_pis = (await db.execute(
                    select(PurchaseItem).where(
                        PurchaseItem.wish_item_id == wi.id,
                        PurchaseItem.purchase_id.in_(unfrozen_purchase_ids),
                    )
                )).scalars().all()
                for pi in linked_pis:
                    pi.feo_planned_item_id = None
                    pi.over_plan = False
                    pi.feo_category_id = eff_cat_id
            old_fpis_to_deactivate[old_fpi.id] = old_fpi
            moved_wish_items.append(wi)

    if moved_wish_items:
        await db.flush()
        for old_fpi in old_fpis_to_deactivate.values():
            await deactivate_if_orphaned(db, old_fpi)
        items_for_auto = [
            wi for wi in moved_wish_items
            if effective_item_feo_category_id(
                per_item_mode, getattr(wish, "feo_category_id", None), getattr(wi, "feo_category_id", None),
            ) is not None
        ]
        if items_for_auto:
            await auto_assign_planned_items(
                items_for_auto,
                getattr(wish, "feo_category_id", None),
                db,
                note=f"сменой категории ФЭО в заявке №{wish.id}",
                per_item_mode=per_item_mode,
            )
            for _mwi in items_for_auto:
                if getattr(_mwi, "feo_planned_item_id", None) is not None:
                    _mwi.planned_item = await db.get(FeoPlannedItem, _mwi.feo_planned_item_id)

    if unfrozen_purchase_ids:
        for p in linked_purchases:
            if p.id in unfrozen_purchase_ids and getattr(p, "purchase_method", None) != "advance":
                p.feo_category_id = getattr(wish, "feo_category_id", None)
                p.feo_per_item = per_item_mode
        wi_by_id = {wi.id: wi for wi in wish_items if getattr(wi, "id", None) is not None}
        if wi_by_id:
            all_linked_pis = (await db.execute(
                select(PurchaseItem).where(
                    PurchaseItem.wish_item_id.in_(set(wi_by_id.keys())),
                    PurchaseItem.purchase_id.in_(unfrozen_purchase_ids),
                )
            )).scalars().all()
            for pi in all_linked_pis:
                wi = wi_by_id.get(pi.wish_item_id)
                if wi is not None:
                    pi.feo_category_id = wi.feo_category_id
                    pi.feo_planned_item_id = wi.feo_planned_item_id
