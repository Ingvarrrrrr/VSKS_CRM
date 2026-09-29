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
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish_item import WishItem
from app.services.feo_plan_fact import planned_item_consumption, category_plan_links


async def collect_plan_duplicate_warnings(
    db: AsyncSession,
    wish_items: list[WishItem],
    exclude_wish_id: Optional[int],
) -> list[dict]:
    """Список {"type": "duplicate", "item_name", "message"} — по одному на
    позицию заявки, чья плановая позиция уже занята хотя бы одной чужой закупкой
    (exclude_wish_id — сама эта заявка, её собственные закупки/позиции дублем не
    считаются, см. apply_wish_item_exclusion внутри planned_item_consumption/
    category_plan_links). Пустой список — совпадений нет.

    Вызывать ДО создания новой закупки (в отличие от _collect_excess_warnings,
    которая намеренно считает ПОСЛЕ, чтобы увидеть уже подросший план) — иначе
    свежесозданная закупка этой же заявки попала бы в свой же список «дублей».
    """
    if not wish_items:
        return []

    fpi_ids = sorted({wi.feo_planned_item_id for wi in wish_items if wi.feo_planned_item_id is not None})
    cat_ids = sorted({
        wi.feo_category_id for wi in wish_items
        if wi.feo_planned_item_id is None and wi.feo_category_id is not None
    })

    fpi_links = await planned_item_consumption(db, fpi_ids, exclude_wish_id=exclude_wish_id) if fpi_ids else {}
    cat_links = await category_plan_links(db, cat_ids, exclude_wish_id=exclude_wish_id) if cat_ids else {}

    warnings: list[dict] = []
    for wi in wish_items:
        linked: list[dict] = []
        if wi.feo_planned_item_id is not None:
            linked = fpi_links.get(wi.feo_planned_item_id, {}).get("linked_purchases", [])
        elif wi.feo_category_id is not None:
            linked = cat_links.get(wi.feo_category_id, {}).get("linked_purchases", [])
        if not linked:
            continue
        _refs = []
        for p in linked:
            _label = p.get("registry_number") or f"закупка #{p.get('id')}"
            _wish_part = f" (заявка №{p['wish_id']})" if p.get("wish_id") else ""
            _status_part = f" — {p['status_label']}" if p.get("status_label") else ""
            _refs.append(f"{_label}{_status_part}{_wish_part}")
        warnings.append({
            "type": "duplicate",
            "item_name": wi.item_name,
            "message": (
                f"Позиция «{wi.item_name}» уже закуплена в {', '.join(_refs)} — похоже на дубль. "
                f"Проверьте, прежде чем согласовывать."
            ),
        })
    return warnings
