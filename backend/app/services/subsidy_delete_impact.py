"""Единственный источник подсчёта зависимостей субсидии перед удалением
(Правило №6) — используется и GET /subsidies/{id}/delete-impact (предупреждение
в UI ДО отправки запроса), и DELETE /subsidies/{id} (сам гейт на 409). Вынесено
из app/routers/subsidies.py (Правило №5, 2026-09-17).

Раньше подсчёт закупок отдавал одно число «11 закупок» без разбивки — но
реестр закупок (app/routers/purchases.py, scope='purchases') безусловно
скрывает status='wishes' (заявки, ещё не переданные в работу) и status='split'
(родительские записи разделённых закупок): ни то, ни другое никаким фильтром
на /orders не найти. Владелец удалил 2 видимые закупки субсидии
«ЦентрПоиск_2026» (id=46), счётчик блокера не изменился — оставшиеся 11 были
status='wishes', реестр их не показывает вовсе. Разбивка по группам ниже даёт
и число, и конкретные объекты по каждой группе, чтобы UI мог сослаться на
правильный фильтр реестра (?status=wishes / ?status=split) и показать список
без второго запроса.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase

# Ограничение на число объектов, возвращаемых в списке каждой группы — общий
# счётчик "count" при этом всегда точный, UI дописывает "и ещё N".
MAX_LISTED_ITEMS = 50

# Человеческие подписи групп — единственный источник текста для 409 и для
# диалога удаления (SubsidyDeleteDialog.vue строит текст из этих же данных,
# не хардкодит собственную копию, Правило №6).
GROUP_LABELS: dict[str, str] = {
    "purchases": "закупок",
    "wishes": "заявок, не переданных в работу",
    "split": "разделённых закупок (родительских записей)",
    "contracts": "договоров",
}


def _purchase_group_key(status: Optional[str]) -> str:
    if status == "wishes":
        return "wishes"
    if status == "split":
        return "split"
    return "purchases"


async def get_subsidy_delete_impact(db: AsyncSession, subsidy_id: int) -> dict:
    """Возвращает счётчики ФЭО/плановых позиций + закупки, разбитые на группы
    purchases/wishes/split (по видимости в реестре закупок) + договоры.
    Каждая группа — {"count": int, "items": [{id, number, name, status}, ...]}
    (items ограничен MAX_LISTED_ITEMS, count — точный)."""
    feo_count = await db.scalar(
        select(func.count()).select_from(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    planned_count = await db.scalar(
        select(func.count()).select_from(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )
    purchase_rows = (await db.execute(
        select(
            Purchase.id, Purchase.purchase_number, Purchase.order_number,
            Purchase.item_name, Purchase.subject, Purchase.status,
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .order_by(Purchase.id.desc())
    )).all()
    contract_rows = (await db.execute(
        select(Contract.id, Contract.number, Contract.subject, Contract.status)
        .where(Contract.subsidy_id == subsidy_id)
        .order_by(Contract.id.desc())
    )).all()

    buckets: dict[str, list[dict]] = {"purchases": [], "wishes": [], "split": [], "contracts": []}
    for p in purchase_rows:
        buckets[_purchase_group_key(p.status)].append({
            "id": p.id,
            "number": p.purchase_number if p.purchase_number is not None else p.order_number,
            "name": p.item_name or p.subject,
            "status": p.status,
        })
    for c in contract_rows:
        buckets["contracts"].append({
            "id": c.id,
            "number": c.number,
            "name": c.subject,
            "status": c.status,
        })

    result: dict = {
        "feo_categories": feo_count or 0,
        "planned_items": planned_count or 0,
    }
    for key, rows in buckets.items():
        result[key] = {"count": len(rows), "items": rows[:MAX_LISTED_ITEMS]}
    return result


def has_blocking_dependents(impact: dict) -> bool:
    return any(impact[key]["count"] > 0 for key in ("purchases", "wishes", "split", "contracts"))


def format_delete_block_message(subsidy_name: str, impact: dict) -> Optional[str]:
    """Единственный источник текста 409 при удалении субсидии — тот же текст,
    из которого SubsidyDeleteDialog.vue строит сообщение в UI (не дублирует
    формулировку, Правило №6)."""
    parts = [
        f"{impact[key]['count']} {label}"
        for key, label in GROUP_LABELS.items()
        if impact[key]["count"] > 0
    ]
    if not parts:
        return None
    return (
        f"Нельзя удалить субсидию «{subsidy_name}»: связано {', '.join(parts)}. "
        f"Заявки «не в работе» и разделённые закупки не показываются в реестре "
        f"закупок обычными фильтрами. Сначала удалите или перепривяжите их."
    )
