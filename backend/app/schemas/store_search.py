"""Схемы GET /api/products/store-search — этап 1 «живой поиск товара в
магазинах» (владелец, 28.10.2026). Отдельный файл (ПРАВИЛО №5) — не
дописывается в products.py/schemas.py."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StoreOfferOut(BaseModel):
    # from_attributes — service.py отдаёт StoreOffer (dataclass), не dict
    # (ПРАВИЛО №6: один датакласс-источник, см. base.py); pydantic читает
    # его поля напрямую, второй конвертер в dict не пишем.
    model_config = ConfigDict(from_attributes=True)

    store_key: str
    store_name: str
    seller_inn: Optional[str] = None
    name: str
    price: Optional[Decimal] = None
    currency: str = "RUB"
    url: str
    image_url: Optional[str] = None
    store_article: Optional[str] = None
    manufacturer: Optional[str] = None


class StoreStatusOut(BaseModel):
    key: str
    name: str
    status: str  # ok | timeout | error | blocked | rate_limited
    count: int
    ms: int


class StoreSearchOut(BaseModel):
    query_sent: str
    offers: List[StoreOfferOut]
    stores: List[StoreStatusOut]
