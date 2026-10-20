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

    Commit не делает — это на вызывающем.
    """
    if per_item_mode or old_header_cat_id == new_header_cat_id or new_header_cat_id is None:
        return []
    from app.services.plan_autoassign import move_or_detach_planned_item

    warnings: list[str] = []
    for it in items:
        if not hasattr(it, "feo_category_id"):
            continue
        if it.feo_category_id == new_header_cat_id:
            continue
        it.feo_category_id = new_header_cat_id
        if getattr(it, "feo_planned_item_id", None) is not None:
            w = await move_or_detach_planned_item(db, it, new_header_cat_id)
            if w:
                warnings.append(w)
    return warnings
