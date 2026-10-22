"""plan_duplicate_warning.py — «дубль занял план молча», продолжение на этапе
согласования заявки (владелец, 2026-09-29): карточка заявки №82 показывала
«Брендвол — план 29 514,00 ₽ · превышение на 29 514,00 ₽», но НИГДЕ не было
написано, что та же плановая позиция уже занята закупкой РЕЕ-2026-00959,
рождённой заявкой №83 («про то, что это дубликат, ничего не написано; я это уже
просил»).

collect_plan_duplicate_warnings ниже — предупреждение (НЕ блок, тот же принцип,
что и _collect_excess_warnings в app.services.wish_distribution) для
согласующего: если у позиции заявки плановая позиция уже занята ЧУЖОЙ закупкой,
согласующий должен увидеть это ДО подтверждения, а не после, когда закупка-дубль
уже создана.

ПРАВИЛО №6: источник данных о занятости плана — ТЕ ЖЕ функции, что уже считают
linked_purchases для GET /feo-categories/plan-positions (единственный источник
«кто занял план», не второй расчёт): app.services.feo_plan_fact.
planned_item_consumption (kind='planned_item') и .category_plan_links
(kind='plan_position'/'feo_article', план введён прямо на листе). Здесь только
читаем их результат и превращаем в текст предупреждения, ничего не считаем заново.

Прод-баг (заявка №209, 22.10.2026): позиция без feo_planned_item_id (привязка
была снята сменой категории шапки — см. app/services/feo_effective_category.py
и app/services/wish_item_category_guard.py, этот класс бага устранён там же)
попадала в category_plan_links(10827) — категории, у которой на самом деле
ЕСТЬ активные FeoPlannedItem (т.е. план этой категории ведётся детализацией
Ур.5, kind='planned_item', а НЕ напрямую на листе). Категорийный фолбэк
category_plan_links предназначен ТОЛЬКО для категорий kind='plan_position'/
'feo_article' (план введён прямо на листе, без отдельных FeoPlannedItem) — у
категории С плановыми позициями матчинг «по категории целиком» слишком грубый:
он объединяет совершенно разные плановые позиции одной категории и даёт
ложный «дубль» (ровно это случилось с заявкой №209 — чужая закупка держала
СОВЕРШЕННО ДРУГУЮ плановую позицию 43508 той же категории).

Критерий «план введён прямо на листе» = категория НЕ имеет ни одной активной
FeoPlannedItem — тот же набор условий (FeoPlannedItem.feo_category_id IN (...),
is_active == True), который использует GET /feo-categories/plan-positions
(app/routers/feo_plan_reads_tree.py::get_plan_positions) для различения строк
kind='planned_item' (детализация внутри категории) от kind='plan_position'/
'feo_article' (план самого листа) — здесь просто проверяем ОТСУТСТВИЕ таких
строк для категории, не второй критерий.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish_item import WishItem
from app.services.feo_plan_fact import planned_item_consumption, category_plan_links


async def _categories_without_active_planned_items(db: AsyncSession, cat_ids: list[int]) -> set[int]:
    """Подмножество cat_ids, у которых НЕТ ни одной активной FeoPlannedItem —
    «план введён прямо на листе» (kind='plan_position'/'feo_article', см.
    get_plan_positions). Те же условия фильтра (feo_category_id IN (...),
    is_active == True), что и там — переиспользуются, не копия критерия."""
    if not cat_ids:
        return set()
    from app.models.feo_planned_item import FeoPlannedItem

    cats_with_fpi = set((await db.execute(
        select(FeoPlannedItem.feo_category_id).where(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active == True,
        ).distinct()
    )).scalars().all())
    return set(cat_ids) - cats_with_fpi


async def collect_plan_duplicate_warnings(
    db: AsyncSession,
    wish_items: list[WishItem],
    exclude_wish_id: Optional[int],
) -> list[dict]:
    """Список {"type", "item_name", "message", "purchases"} — по одному на
    позицию заявки, чья плановая позиция уже занята хотя бы одной чужой закупкой
    (exclude_wish_id — сама эта заявка, её собственные закупки/позиции дублем не
    считаются, см. apply_wish_item_exclusion внутри planned_item_consumption/
    category_plan_links). Пустой список — совпадений нет.

    `purchases` — структурированный список [{id, registry_number, status_label,
    wish_id}] ТЕХ ЖЕ закупок, что уже упомянуты текстом в `message` (фронт
    строит ссылки на карточки закупок из этого списка, не парсит текст).

    Категорийный фолбэк (позиция без feo_planned_item_id, matching по
    feo_category_id) применяется ТОЛЬКО к категориям без активных
    FeoPlannedItem (см. _categories_without_active_planned_items выше) — иначе
    позиция ложно считается дублем совершенно другой плановой позиции той же
    категории (прод-баг заявки №209).

    Вызывать ДО создания новой закупки (в отличие от _collect_excess_warnings,
    которая намеренно считает ПОСЛЕ, чтобы увидеть уже подросший план) — иначе
    свежесозданная закупка этой же заявки попала бы в свой же список «дублей».
    """
    if not wish_items:
        return []

    fpi_ids = sorted({wi.feo_planned_item_id for wi in wish_items if wi.feo_planned_item_id is not None})
    _cat_ids_candidate = sorted({
        wi.feo_category_id for wi in wish_items
        if wi.feo_planned_item_id is None and wi.feo_category_id is not None
    })
    _cat_ids_eligible = await _categories_without_active_planned_items(db, _cat_ids_candidate)

    fpi_links = await planned_item_consumption(db, fpi_ids, exclude_wish_id=exclude_wish_id) if fpi_ids else {}
    cat_links = (
        await category_plan_links(db, sorted(_cat_ids_eligible), exclude_wish_id=exclude_wish_id)
        if _cat_ids_eligible else {}
    )

    warnings: list[dict] = []
    for wi in wish_items:
        linked: list[dict] = []
        if wi.feo_planned_item_id is not None:
            linked = fpi_links.get(wi.feo_planned_item_id, {}).get("linked_purchases", [])
        elif wi.feo_category_id is not None and wi.feo_category_id in _cat_ids_eligible:
            linked = cat_links.get(wi.feo_category_id, {}).get("linked_purchases", [])
        if not linked:
            continue
        _refs = []
        _purchases: list[dict] = []
        for p in linked:
            _label = p.get("registry_number") or f"закупка #{p.get('id')}"
            _wish_part = f" (заявка №{p['wish_id']})" if p.get("wish_id") else ""
            _status_part = f" — {p['status_label']}" if p.get("status_label") else ""
            _refs.append(f"{_label}{_status_part}{_wish_part}")
            _purchases.append({
                "id": p.get("id"),
                "registry_number": p.get("registry_number"),
                "status_label": p.get("status_label"),
                "wish_id": p.get("wish_id"),
            })
        warnings.append({
            "type": "duplicate",
            "item_name": wi.item_name,
            "message": (
                f"Позиция «{wi.item_name}» уже закуплена в {', '.join(_refs)} — похоже на дубль. "
                f"Проверьте, прежде чем согласовывать."
            ),
            "purchases": _purchases,
        })
    return warnings
