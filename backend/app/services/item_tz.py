"""Действующее ТЗ (характеристики) одной позиции заявки/закупки — ЕДИНСТВЕННЫЙ
источник этой формулы (ПРАВИЛО №6, владелец 14.10.2026, план
item-tz-description.md): у позиции может быть своё ТЗ (WishItem.tz_description /
PurchaseItem.tz_description), загруженное из файла при импорте; если его нет —
действует ТЗ товара каталога (Product.description / description_44fz).

Каталожный текст товара (description/description_44fz), если он пуст, а у
товара заполнены структурированные характеристики (Product.characteristics) —
собирается из них тем же единственным механизмом, что и везде в проекте
(ПРАВИЛО №6): app/services/product_tech_description.py::build_tech_description
(учитывает in_description=false). Второй сборщик текста из характеристик
здесь не пишется.

Вызывается ВСЕМИ местами, которые раньше читали item.product.description
напрямую для документов/выдачи:
  - app/routers/wish_documents.py (служебная записка, техническое задание)
  - app/services/documents/contexts.py (_build_items_list_from_contract_items,
    _build_items_list_from_plan_or_contract)
  - app/services/documents/kp_xlsx.py
  - app/services/purchase_serializers.py (PurchaseItemOut.product_description)
  - app/services/product_snapshot.py (WishItemOut.description, через item.tz_description)

Не копировать формулу `item.tz_description or product.description` второй раз
где-либо ещё — импортировать effective_item_tz/effective_item_tz_44fz отсюда.

Вызывающий код должен грузить product.characteristics обычным способом (без
defer) — см. product_search.py, где этот столбец ЯВНО отложен для списков
товаров (там он не нужен); все перечисленные выше вызывающие места читают
Product целиком, поэтому MissingGreenlet здесь не возникает.
"""
from typing import Optional

from app.services.product_tech_description import build_tech_description


def _catalog_fallback(product, field: str) -> Optional[str]:
    """Текст поля `field` ('description'/'description_44fz') каталожного
    товара; если он пуст — собирается из характеристик через
    build_tech_description (ПРАВИЛО №6, владелец 26.10.2026: товар может не
    иметь вольного текста, но иметь заполненные характеристики)."""
    direct = getattr(product, field, None)
    if direct and direct.strip():
        return direct
    return build_tech_description(getattr(product, "characteristics", None), None)


def effective_item_tz(item, product=None) -> Optional[str]:
    """ТЗ позиции (обычный режим) — item.tz_description, если непустое,
    иначе product.description (с фолбэком на характеристики, см.
    _catalog_fallback). `item` — WishItem/PurchaseItem/ContractItem
    ОРМ-инстанс или любой объект с атрибутом tz_description (getattr с
    default=None — безопасно для объектов без этого поля, напр. ContractItem
    до появления там своего текста). `product` — опционально явный Product,
    если у `item` нет собственной связи .product (напр. ContractItem, где
    товар резолвится отдельно вызывающим кодом) — по умолчанию берётся
    item.product."""
    own = getattr(item, "tz_description", None)
    if own and own.strip():
        return own
    _product = product if product is not None else getattr(item, "product", None)
    return _catalog_fallback(_product, "description") if _product else None


def effective_item_tz_44fz(item, product=None) -> Optional[str]:
    """То же самое, но для режима 44-ФЗ (description_mode == '44fz') — своё
    ТЗ позиции не различает режим (одно поле на обе формулировки, как и было
    решено владельцем для tz_description), каталожный текст — из
    product.description_44fz (с тем же фолбэком на характеристики)."""
    own = getattr(item, "tz_description", None)
    if own and own.strip():
        return own
    _product = product if product is not None else getattr(item, "product", None)
    return _catalog_fallback(_product, "description_44fz") if _product else None
