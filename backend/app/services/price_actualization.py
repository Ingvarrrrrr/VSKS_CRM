"""Единая точка входа для актуализации цены товара — владелец, 2026-08-29.

Владелец: «Цена может актуализироваться по запросу КП или по уже совершённым
контрактам». Все места кода, которые меняют product.price по «настоящему»
основанию (не черновой ввод), обязаны звать actualize_product_price — иначе
price_updated_at/price_source рассинхронизируются с фактической ценой и
контроль устаревания (app/services/price_freshness.py) начнёт врать.

Вызывающие точки (см. TASKS для этой сессии):
  1. app/routers/purchase_transitions.py — переход в 'contracted'
  2. app/routers/products.py — update_product/patch_product (ручной ввод / пересчёт из price_links)
  3. app/routers/products.py — импорт каталога (существующий товар)
  4. app/routers/products.py — POST /{id}/price-actualization
  5. app/routers/commercial_requests.py — POST /offers/{offer_id}/accept
"""
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory

VALID_PRICE_SOURCES = ("contract", "kp", "manual", "import", "monitoring")


async def actualize_product_price(
    db: AsyncSession,
    product: Product,
    *,
    price,
    source: str,
    source_ref: Optional[str] = None,
    contractor_id: Optional[int] = None,
    collected_at=None,
    note: Optional[str] = None,
    user=None,
    write_history: bool = True,
) -> None:
    """Проставляет цену + метаданные актуализации на product и (по умолчанию)
    пишет строку в product_price_history. Не коммитит — вызывающий код
    управляет транзакцией (как и остальные мутации в этих роутерах).
    """
    if price is not None and not isinstance(price, Decimal):
        price = Decimal(str(price))

    collected_date: Optional[_date] = None
    if isinstance(collected_at, datetime):
        collected_date = collected_at.date()
    elif isinstance(collected_at, _date):
        collected_date = collected_at
    elif isinstance(collected_at, str) and collected_at:
        try:
            collected_date = _date.fromisoformat(collected_at[:10])
        except ValueError:
            collected_date = None

    product.price = price
    product.price_updated_at = datetime.utcnow()
    product.price_source = source
    product.price_source_ref = source_ref
    product.price_source_contractor_id = contractor_id

    if write_history:
        db.add(ProductPriceHistory(
            product_id=product.id,
            price=price,
            source=source,
            source_ref=source_ref,
            contractor_id=contractor_id,
            collected_at=collected_date,
            note=note,
            created_by=getattr(user, "id", None) if user is not None else None,
        ))
