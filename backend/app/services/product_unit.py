"""Единица измерения товара — единая точка правды (владелец, 2026-09-01):

«Как блядь нет единицы измерения — добавить! И при следующем импорте данных
из экселя, там где нет этих данных, добавить в каждую карточку товара.
Должно браться из БД по товарам. Если две разные единицы измерения записаны
для какого-то товара, то ничего не надо указывать — никакой единицы
измерения».

Правило переиспользуется:
  - миграцией-бэкфиллом (alembic/versions/f25e7fa19cbc_products_unit.py —
    та же логика, но одним SQL-запросом по всей таблице сразу);
  - импортом товаров/позиций (app/routers/products.py::import_products_from_excel,
    app/routers/purchase_items_import.py::_upsert_product_to_catalog и
    «matched»-ветки импортов позиций закупки);
  - GET /api/feo-planned-items/product-hint (приоритет: Product.unit, если
    заполнена, иначе — фолбэк на unit_from_purchase_history).
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_item import PurchaseItem


async def unit_from_purchase_history(db: AsyncSession, product_id: int) -> Optional[str]:
    """Единственная ЕИ, с которой товар фигурировал в позициях закупок.

    None, если товар ни разу не покупался с явно указанной ЕИ, либо
    встречался с двумя и более различными (после обрезки пробелов)."""
    rows = (await db.execute(
        select(PurchaseItem.unit)
        .where(
            PurchaseItem.product_id == product_id,
            PurchaseItem.unit.isnot(None),
            PurchaseItem.unit != "",
        )
        .distinct()
    )).scalars().all()
    normalized = {u.strip() for u in rows if u and u.strip()}
    if len(normalized) == 1:
        return next(iter(normalized))
    return None


async def backfill_product_unit(
    db: AsyncSession,
    product,
    import_unit: Optional[str] = None,
) -> None:
    """Дозаполнить product.unit, НЕ перетирая уже заполненное значение.

    Приоритет: собственная ЕИ товара (если уже задана — не трогаем) →
    ЕИ, которую явно принёс сам импорт этой строки → единственная ЕИ из
    истории закупок этого товара (иначе молчим, ничего не указываем)."""
    if getattr(product, "unit", None):
        return
    val = (import_unit or "").strip() if import_unit else ""
    if val:
        product.unit = val
        return
    product_id = getattr(product, "id", None)
    if product_id:
        hist = await unit_from_purchase_history(db, product_id)
        if hist:
            product.unit = hist
