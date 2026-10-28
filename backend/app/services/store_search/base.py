"""Общий датакласс предложения магазина и интерфейс адаптера — этап 1
«живой поиск товара в магазинах» (владелец, 28.10.2026). Единственное место,
определяющее форму StoreOffer (ПРАВИЛО №6) — адаптеры (kuvalda.py, safe.py,
...) только заполняют это поле, второй такой же датакласс не заводится.

seller_inn/store_name — берутся из app.services.catalog_gala.stores
(ПРАВИЛО №6 — единственный справочник «магазин → ИНН/название», см.
докстринг там; этот модуль его не копирует)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from app.services.catalog_gala.stores import store_for_domain


@dataclass
class StoreOffer:
    store_key: str
    store_name: str
    seller_inn: Optional[str]
    name: str
    price: Optional[Decimal]
    url: str
    currency: str = "RUB"
    image_url: Optional[str] = None
    store_article: Optional[str] = None
    manufacturer: Optional[str] = None
    raw_unit: Optional[str] = None


def store_display_name(domain: str, fallback: str) -> str:
    """Название магазина для StoreOffer.store_name — ИЗ справочника stores.py
    по домену (ПРАВИЛО №6); если домен там не заведён (справочник живёт для
    другой задачи — поставщики загруженного каталога — и не обязан знать
    КАЖДЫЙ магазин, который когда-либо подключат к живому поиску), берётся
    `fallback` (человекочитаемое название, которое передаёт сам адаптер)."""
    info = store_for_domain(domain)
    if info and info.get("name"):
        return info["name"]
    return fallback


def seller_inn_for_domain(domain: str) -> Optional[str]:
    info = store_for_domain(domain)
    return info.get("inn") if info else None


class StoreAdapter(Protocol):
    key: str
    domain: str

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        ...
