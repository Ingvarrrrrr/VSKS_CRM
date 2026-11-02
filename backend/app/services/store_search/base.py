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
from html import unescape as _html_unescape
from typing import Optional, Protocol

from app.services.catalog_gala.stores import store_for_domain


@dataclass
class StoreOffer:
    """ДЕФЕКТ приёмки 29.10.2026: название товара несло HTML-сущности
    («КАМАЗ-6520 с бардачком &quot;Мустанг&quot;» вместо нормальных кавычек) —
    chipdip.py декодировал через html.unescape ТОЛЬКО цену, но не name
    (каждый адаптер разбирает HTML своего магазина, и то же самое может
    случиться у любого другого). Чтобы не чистить name/manufacturer в КАЖДОМ
    адаптере по отдельности (ПРАВИЛО №6 — второй механизм не заводим),
    __post_init__ ниже декодирует их ОДИН раз здесь, для всех адаптеров
    сразу — это единственное место, создающее StoreOffer."""

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

    def __post_init__(self) -> None:
        if self.name:
            self.name = _html_unescape(self.name)
        if self.manufacturer:
            self.manufacturer = _html_unescape(self.manufacturer)


def store_display_name(domain: str, fallback: str) -> str:
    """Название магазина для StoreOffer.store_name и строки статусов поиска
    (ПРАВИЛО №6 — единственное место, формирующее человекочитаемое имя
    магазина для живого поиска).

    ДЕФЕКТ с прода 29.10.2026: раньше здесь бралось `name` из справочника
    stores.py (store_for_domain) — но то поле хранит ЮРЛИЦО/ИП магазина для
    контрагента при загрузке каталога (см. докстринг STORES там), не имя
    сайта. Владелец видел в строке статусов «ООО «Энтузиаст-С» — 0» вместо
    «Кувалда.ру — 0» и не мог узнать магазин. Юрлицо для ЧЕЛОВЕКА, читающего
    статус поиска, не нужно — только `fallback`, человекочитаемое название
    сайта, которое передаёт сам адаптер (STORE_NAME_FALLBACK).

    ВТОРОЙ ДЕФЕКТ с приёмки 29.10.2026: строка статусов магазинов показывала
    ключи («kuvalda», «chipdip», «sima_land») вместо имён — service.py
    строил _STORE_DISPLAY_NAMES, подставляя сюда `fallback=key` (ключ
    магазина), а не человекочитаемое имя адаптера, потому что у service.py
    не было доступа к STORE_NAME_FALLBACK каждого адаптера — только к
    экземплярам в ADAPTERS. Починено — каждый адаптер несёт своё имя как
    атрибут `display_name = STORE_NAME_FALLBACK` (см. StoreAdapter.
    display_name выше), и service.py/StoreOffer.store_name читают ОДНО и то
    же значение оттуда (ПРАВИЛО №6 — один источник имени на магазин)."""
    return fallback


def seller_inn_for_domain(domain: str) -> Optional[str]:
    info = store_for_domain(domain)
    return info.get("inn") if info else None


class StoreAdapter(Protocol):
    key: str
    domain: str
    display_name: str

    async def search(self, client, query: str, limit: int) -> list[StoreOffer]:
        ...


class StoreBlocked(Exception):
    """Адаптер поднимает это исключение, когда ответ магазина похож на
    антибот-блокировку/капчу, а не на честные «0 найдено» (ПРАВИЛО №8 п.6 —
    статус не должен молча стать 'ok' с 0 предложений; дефект с прода
    29.10.2026, kuvalda.ru). Разбор ответа магазина — дело адаптера, этот
    класс — только общий сигнал для оркестратора.

    service.py::_search_one_store СЕЙЧАС ловит только `asyncio.TimeoutError`
    и общий `Exception` → статус 'timeout'/'error'; чтобы владелец увидел
    «магазин недоступен», а не ошибку, туда нужно добавить ОДНУ строку ПЕРЕД
    общим `except Exception:` (этот файл не трогаем — правит исполнитель
    service.py/registry.py):

        except StoreBlocked:
            offers = []
            status = "blocked"
    """
