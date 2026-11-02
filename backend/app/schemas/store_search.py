"""Схемы GET /api/products/store-search — этап 1 «живой поиск товара в
магазинах» (владелец, 28.10.2026). Отдельный файл (ПРАВИЛО №5) — не
дописывается в products.py/schemas.py."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.products import ProductOut


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


class StoreTakeOut(ProductOut):
    """Ответ POST /api/products/store-take — ProductOut + один флаг `created`
    (владелец, 29.10.2026: тост на странице «Товары» должен различать
    «добавлен в каталог» от «обновлена цена»). Наследование от ProductOut
    (ПРАВИЛО №6) — ProductPickerDialog.vue/useItemsCatalog.ts подставляют
    ответ ТУДА ЖЕ, куда обычный выбор товара из каталога (emit('pick', ...)),
    и просто игнорируют поле `created`, которого там не ждут — второй
    формы ответа для одного и того же товара не заводим."""
    created: bool = True


class StoreTakeIn(BaseModel):
    """Тело POST /api/products/store-take (этап 2, «Взять», владелец
    29.10.2026, app/services/store_search/take.py). ПРАВИЛО №8 п.4 — НЕ несёт
    ни цены, ни названия, ни фото: только то, что нужно, чтобы сервер сам
    нашёл предложение в своём кэше/магазине заново (store_key+url — ключ
    предложения, query — та же фраза, что ушла в поиск, нужна для
    clean_query() при повторном походе, если кэш уже протух)."""
    store_key: str
    url: str
    query: str = ""
