"""Разбор страницы товара отдельных магазинов — один файл на магазин
(ПРАВИЛО №5). Перенесено из tools/harvest/stores/<магазин>.py (ПРАВИЛО №6 —
tools/harvest импортирует ровно эти функции обратно через
tools/harvest/stores/_backend_bridge.py, а не хранит вторую копию).

Используется ДВУМЯ сторонами:
  - tools/harvest/stores/<магазин>.py — офлайн-сборщик каталога;
  - app/services/store_search/take.py — довизит на страницу товара сразу
    после «Взять» предложение живого поиска (этап 2).

Магазины, для которых перенос НЕ сделан (см. отчёт сессии):
  - chipdip/avtoall/emex — tools/harvest/stores/<магазин>.py изменены
    ПАРАЛЛЕЛЬНОЙ сессией и не трогаются; для них используется ОБЩИЙ
    JSON-LD-разбор app/services/store_search/price_from_product_page.py
    (extract_product_details), а не store_pages-модуль;
  - sima_land/inari — parse_product_page исходного харвест-модуля — пустая
    заглушка (товар никогда не посещается), переносить нечего.

Каждый модуль несёт ровно `parse_product_page(html: str, url: str) -> dict`
(ice_age/baucenter — тело страницы само JSON, не HTML, но тот же
сигнатурный контракт)."""
from __future__ import annotations

from typing import Callable, Optional

from app.services.store_pages import (
    baucenter,
    ice_age,
    k_spasatel,
    kns,
    kuvalda,
    magazin01,
    medtehno,
    promalper,
    regard,
    safe,
)

# store_key (тот же, что ADAPTERS в app/services/store_search/registry.py) ->
# parse_product_page(html, url) -> dict с полями, специфичными для магазина
# (см. докстринг каждого модуля) — take.py решает, какие поля из результата
# переносить в Product.
PARSERS: dict[str, Callable[[str, str], dict]] = {
    "kuvalda": kuvalda.parse_product_page,
    "safe": safe.parse_product_page,
    "magazin01": magazin01.parse_product_page,
    "promalper": promalper.parse_product_page,
    "regard": regard.parse_product_page,
    "medtehno": medtehno.parse_product_page,
    "ice_age": ice_age.parse_product_page,
    "kns": kns.parse_product_page,
    "baucenter": baucenter.parse_product_page,
    "k_spasatel": k_spasatel.parse_product_page,
}


def get_parser(store_key: str) -> Optional[Callable[[str, str], dict]]:
    return PARSERS.get(store_key)


# Магазины, у которых разбираемый контент лежит НЕ по человекочитаемому
# URL товара (тот, что видит покупатель и хранит StoreOffer.url), а по
# отдельному адресу — ice_age.ru (JSON API InSales, см. docstring
# ice_age.product_page_fetch_url). Отсутствие ключа — URL для скачивания
# совпадает с URL товара (большинство магазинов).
_FETCH_URL_TRANSFORMS: dict[str, Callable[[str], str]] = {
    "ice_age": ice_age.product_page_fetch_url,
}


def product_page_fetch_url(store_key: str, url: str) -> str:
    """URL, который нужно СКАЧАТЬ для разбора parse_product_page(store_key)
    — обычно тот же `url`, кроме магазинов из _FETCH_URL_TRANSFORMS."""
    transform = _FETCH_URL_TRANSFORMS.get(store_key)
    return transform(url) if transform else url
