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
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract_item import ContractItem


def build_purchase_search_clause(search: str) -> ColumnElement:
    """Условие WHERE для поиска закупок по строке `search`.

    Совпадение по любому полю шапки закупки ИЛИ по наименованию хотя бы одной
    её позиции — как в purchase_items (ТЗ), так и в contract_items (то, что
    фактически заказано по договору, Phase 27.1 — своё поле `name`, не
    item_name). Копирование в другую субсидию (app/services/purchase_transfer/)
    — поиск по номеру оригинала находит и его копию, и наоборот (связь
    Purchase.copied_from_purchase_id), через EXISTS, без N+1.
    """
    like = f"%{search}%"
    # Настоящий self-join через aliased() — без него inner/outer "Purchase"
    # ссылались бы на одну и ту же сущность, и EXISTS молча не находил пару
    # (баг найден тестом test_search_finds_copy_by_original_registry_number).
    _PurchaseAlias = aliased(Purchase)
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
        # Найти копию по номеру оригинала.
        select(_PurchaseAlias.id).where(
            _PurchaseAlias.id == Purchase.copied_from_purchase_id,
            _PurchaseAlias.registry_number.ilike(like),
        ).exists(),
        # Найти оригинал по номеру его копии.
        select(_PurchaseAlias.id).where(
            _PurchaseAlias.copied_from_purchase_id == Purchase.id,
            _PurchaseAlias.registry_number.ilike(like),
        ).exists(),
    ]
    if search.strip().isdigit():
        search_filters.append(Purchase.purchase_number == int(search.strip()))
    return or_(*search_filters)
