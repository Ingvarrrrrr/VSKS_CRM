"""Тип плановой позиции («товар/услуга/работа») при импорте ФЭО vs каталог
товаров — решение владельца, 22.09.

Колонка «Тип» файла (`c_item_type`, см. app/routers/feo_import.py::find_col и
app/services/feo_import_params.py::_COL_INT_FIELDS) уже нормализуется на
месте построчного чтения (feo_import_apply.py, через
`app.routers.feo_planned_items.normalize_item_type` — реэкспорт
app.services.item_types.normalize_item_type). Этот модуль — единственное
место, решающее, ЧТО в итоге запишется в FeoPlannedItem.item_type, когда рядом
есть товар каталога с ТОЧНО таким же (после нормализации) именем:

  1. Колонка пуста, товар с таким именем в каталоге ОДИН (при нескольких
     совпадениях — не брать, см. `_catalog_product_for_name`) → item_type
     берётся из Product.item_kind, warning `item_type_from_catalog`.
  2. Колонка заполнена и совпадает с товаром каталога → без вопросов, тип из
     файла (он же тип каталога).
  3. Колонка заполнена и ОТЛИЧАЕТСЯ от товара каталога → конфликт: строка
     кладётся в `state.item_type_conflicts` (предпросмотр, dry_run и боевой
     вызов возвращают его одинаково — фронт показывает выбор по строкам).
     Решение человека — `state.item_type_decisions[str(row_num)]`
     ('file'|'catalog'), тем же способом, каким уже принимаются решения по
     конфликтам бюджета (см. app/services/feo_import_budget_conflicts.py,
     app/services/feo_import_core.py::_do_feo_import — разбор JSON-параметра
     ДО основного цикла, до FeoImportState). Отдельный JSON-канал
     `item_type_decisions`, а НЕ общий `duplicate_resolutions` (Правило №6 —
     не смешивать пространства имён: тот канал ключуется ТЕКСТОВЫМ ключом
     группы категории/дублей, этот — номером строки файла, они не совпадают
     по природе и не должны делить один словарь):
       - 'file'    → item_type из файла, apply_item_type_to_product пишет его
                     в Product.item_kind (единственная точка записи —
                     app/services/item_types.py, Правило №6, не дублируем).
       - 'catalog' → item_type из каталога, товар не трогаем.
       - решения нет: на боевом импорте (не dry_run) — применяется тип из
         файла БЕЗ изменения каталога (не блокируем импорт, но и не портим
         чужой товар вслепую) + warning `item_type_conflict_unresolved`;
         на предпросмотре (dry_run) — конфликт просто показывается в
         `item_type_conflicts`, без этого предупреждения (ничего ещё не
         "применено" — dry_run в любом случае откатывает транзакцию).
  4. Товара с таким именем в каталоге нет (или их несколько — неоднозначность,
     см. п.1) → тип из колонки как есть, каталог не трогаем, конфликта нет.

Поиск товара по имени — ТА ЖЕ точка нормализации, что и everywhere в проекте
(`app.services.product_catalog_match.normalize_product_name`/
`_sql_normalized_name_expr`, Правило №6 — не второй нормализатор). НЕ
переиспользует `app.services.item_types.resolve_product_for_planned_item`
напрямую: та функция расчитана на ОДИН вызов с уже существующим
FeoPlannedItem (после того, как позиция создана) и не отдаёт Product.item_kind
— здесь резолвинг идёт МАССОВО, по каждой строке файла ДО того, как
FeoPlannedItem вообще существует, и нужен сам Product (для item_kind и имени в
`item_type_conflicts`), поэтому запрос сделан напрямую с тем же критерием
неоднозначности («2+ совпадений → не брать»), результат кешируется в
`state.item_type_product_cache` (по нормализованному имени) — один и тот же
товар/то же имя в файле не запрашивается у БД повторно.

Публичный API:
    ITEM_TYPE_DECISION_VALUES              — допустимые значения item_type_decisions
    resolve_item_type_for_row(state, row_num, item_name, file_item_type)
        — единственная точка решения, вызывается из feo_import_apply.py в
          каждом месте, где строка файла кладёт item_type в
          pending_lvl5_items/collected_plan (регистрация через
          feo_import_duplicates.register_pending_item и прямую запись
          collected_plan[cat.id] в feo_import_apply.py). `file_item_type` —
          уже нормализованное значение колонки файла (или None) — сама
          нормализация и warning `item_type_unknown` остаются на месте
          (Правило №6 — не дублировать normalize_item_type).
"""
from typing import Optional

from sqlalchemy import select

from app.models.product import Product
from app.services.item_types import ITEM_TYPES, apply_item_type_to_product
from app.services.product_catalog_match import _sql_normalized_name_expr, normalize_product_name

# Единственный источник допустимых значений item_type_decisions — 'file'
# (побеждает тип из файла, каталог переписывается) | 'catalog' (побеждает тип
# каталога, товар не трогаем). Валидируется в feo_import_core.py при разборе
# JSON-параметра, тем же приёмом, что и budget_group_key/category_sum_
# conflict_key значения в feo_import_budget_conflicts.py.
ITEM_TYPE_DECISION_VALUES = ("file", "catalog")


async def _catalog_product_for_name(state, item_name: Optional[str]) -> Optional[Product]:
    """Товар каталога по ТОЧНОМУ (после нормализации) имени — None, если
    товара нет или совпадений 2+ (неоднозначность, владелец 22.09: «при
    нескольких совпадениях — не брать»). Кеш `state.item_type_product_cache`
    (нормализованное имя -> Product|None) — в пределах одного импорта то же
    имя строки файла запрашивается у БД не больше одного раза."""
    norm = normalize_product_name(item_name)
    if not norm:
        return None
    cache = state.item_type_product_cache
    if norm in cache:
        return cache[norm]
    candidates = (
        await state.db.execute(select(Product).where(_sql_normalized_name_expr() == norm))
    ).scalars().all()
    product = candidates[0] if len(candidates) == 1 else None
    cache[norm] = product
    return product


async def resolve_item_type_for_row(
    state, row_num: int, item_name: Optional[str], file_item_type: Optional[str],
) -> Optional[str]:
    """Возвращает item_type, который должен лечь в FeoPlannedItem для этой
    строки/позиции — см. докстринг модуля, пункты 1–4. Побочные эффекты:
    warnings (`item_type_from_catalog`/`item_type_conflict_unresolved`),
    `state.item_type_conflicts` (конфликт — пункт 3), запись Product.item_kind
    через `apply_item_type_to_product` (решение 'file')."""
    product = await _catalog_product_for_name(state, item_name)
    if product is None:
        # Пункт 4: товара нет или неоднозначность — колонка файла как есть.
        return file_item_type

    catalog_type = product.item_kind if product.item_kind in ITEM_TYPES else None

    if file_item_type is None:
        if catalog_type is None:
            return None
        # Пункт 1: колонка пуста, каталог знает тип — берём его, без записи
        # обратно в товар (тип и так пришёл ИЗ товара, писать нечего).
        state.warnings.append({
            "kind": "item_type_from_catalog",
            "row": row_num,
            "name": item_name,
            "message": f"Для «{item_name}» товар/услуга взяты из каталога: {catalog_type} (товар «{product.name}»)",
        })
        return catalog_type

    if catalog_type is None or file_item_type == catalog_type:
        # Пункт 2 (совпадают) — либо у товара каталога тип не определён
        # (item_kind вне ITEM_TYPES, легаси-данные) — сравнивать не с чем,
        # ведёт себя как «конфликта нет», тип из файла.
        return file_item_type

    # Пункт 3: конфликт — файл и каталог называют РАЗНЫЙ тип для одного и
    # того же товара.
    decision = state.item_type_decisions.get(str(row_num))
    state.item_type_conflicts.append({
        "row": row_num,
        "item_name": item_name,
        "file_type": file_item_type,
        "catalog_type": catalog_type,
        "product_id": product.id,
        "product_name": product.name,
        "decision": decision,
    })

    if decision == "file":
        await apply_item_type_to_product(state.db, product.id, file_item_type)
        return file_item_type
    if decision == "catalog":
        return catalog_type

    # Решения нет: боевой импорт применяет тип из файла и НЕ трогает каталог
    # (владелец: «импорт не блокируем, но каталог не портим»); на dry_run —
    # конфликт только показан (item_type_conflicts выше), предупреждения нет,
    # т.к. dry_run ничего не применяет по-настоящему (транзакция откатится).
    if not state.dry_run:
        state.warnings.append({
            "kind": "item_type_conflict_unresolved",
            "row": row_num,
            "name": item_name,
            "message": (
                f"«{item_name}»: в файле «{file_item_type}», в каталоге (товар «{product.name}») "
                f"«{catalog_type}» — решение не получено, применено значение из файла, каталог не изменён"
            ),
        })
    return file_item_type
