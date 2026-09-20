"""purchase_search.py — единая сборка условия текстового поиска по закупкам.

Владелец (2026-09-20): строка «Поиск» находила закупку только по полям её
шапки (registry_number/subject/item_name/…) — «Рукав пожарный», лежащий
ПОЗИЦИЕЙ внутри другой закупки, не находился ни разу. GET /purchases/?search=
используется не только реестром закупок (OrdersView.vue грузит список БЕЗ
search и фильтрует на клиенте — см. frontend/src/composables/orders/
ordersSearch.ts, там отдельный клиентский источник истины), а ещё и
GlobalSearch.vue (шапка), TaskEditDialog.vue (привязка задачи к закупке) и
VehicleRepairsTab.vue — для НИХ это единственная точка поиска, и раньше они
тоже не находили закупку по составу.

Правило №6: один показатель — одна функция сборки условия. Не дублировать
этот or_/exists в другом роутере — импортировать build_purchase_search_clause.
"""
from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract_item import ContractItem


def build_purchase_search_clause(search: str) -> ColumnElement:
    """Условие WHERE для поиска закупок по строке `search`.

    Совпадение по любому полю шапки закупки ИЛИ по наименованию хотя бы одной
    её позиции — как в purchase_items (ТЗ), так и в contract_items (то, что
    фактически заказано по договору, Phase 27.1 — своё поле `name`, не
    item_name).
    """
    like = f"%{search}%"
    search_filters = [
        Purchase.item_name.ilike(like),
        Purchase.subject.ilike(like),
        Purchase.registry_number.ilike(like),
        Purchase.contract_number.ilike(like),
        Purchase.order_number.ilike(like),
        select(PurchaseItem.id).where(
            PurchaseItem.purchase_id == Purchase.id,
            PurchaseItem.item_name.ilike(like),
        ).exists(),
        select(ContractItem.id).where(
            ContractItem.purchase_id == Purchase.id,
            ContractItem.name.ilike(like),
        ).exists(),
    ]
    if search.strip().isdigit():
        search_filters.append(Purchase.purchase_number == int(search.strip()))
    return or_(*search_filters)
