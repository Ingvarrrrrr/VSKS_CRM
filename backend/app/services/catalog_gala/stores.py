"""Единственный справочник «магазин GALA → ИНН/название/ОГРН» (ПРАВИЛО №6,
владелец, 26.10.2026): конвертеры (from_electro_mpo.py, from_vkusvill.py,
from_baucenter.py, from_store_nomenclature.py, from_gala_sheet.py) определяют
seller_inn товара ТОЛЬКО через функции этого модуля — никакой конвертер не
хранит свою копию списка ИНН/доменов.

Контрагент для строки цены при загрузке каталога — юрлицо/ИП магазина-
источника по ИНН (владелец подтвердил 8 магазинов, см. список ниже), НЕ сам
поставщик файла. Поиск контрагента по ИНН делает
app.services.contractor_resolve.find_or_create_contractor — этот модуль
только определяет, КАКОЙ ИНН/название/ОГРН подставить, самого контрагента не
создаёт и с БД не работает.

Домен определяется из ссылки на СТРАНИЦУ ТОВАРА (source_url / links[].url) —
не из ссылок на фото (поддомены вида img.vkusvill.ru/goods-photos.static1-
sima-land.com к делу не относятся, т.к. эта функция вызывается только на
товарных ссылках). from_store_nomenclature.py — особый случай: там магазин
известен из текстового поля source_store вида «Сима-ленд (sima-land.ru)»,
домен достаётся из скобок тем же способом (store_for_source_store).

catalog_goods_1010 (from_gala_sheet.py) — в нём встречаются ссылки на разные
магазины (Яндекс Маркет, DNS и т.п.), НЕ входящие в этот справочник — для них
seller_inn_for_url просто возвращает None (ОК по докстрингу item в format.py:
поле опционально).
"""
from __future__ import annotations

import re
from typing import Optional

# ОГРН у юрлиц, ОГРНИП у ИП — модель Contractor (app/models/contractor.py)
# хранит оба в одном поле `ogrn`, поэтому здесь это единое поле без различения
# по названию (как и в остальной БД).
STORES: dict[str, dict[str, str]] = {
    "sima-land.ru": {
        "name": "ООО ТД «Сима-ленд»", "inn": "6679104850",
        "ogrn": "1176658004929", "org_type": "Юр.лицо",
    },
    "baucenter.ru": {
        "name": "ООО «Бауцентр Рус»", "inn": "7702596813",
        "ogrn": "1067746357524", "org_type": "Юр.лицо",
    },
    "electro-mpo.ru": {
        "name": "ЗАО «МПО Электромонтаж»", "inn": "7719079370",
        "ogrn": "1037700089052", "org_type": "Юр.лицо",
    },
    "vkusvill.ru": {
        "name": "АО «Вкусвилл»", "inn": "7734443270",
        "ogrn": "1217700253671", "org_type": "Юр.лицо",
    },
    "k-spasatel.ru": {
        "name": "ООО «Высокая опора»", "inn": "9718172669",
        "ogrn": "1217700197219", "org_type": "Юр.лицо",
    },
    "magazin01.ru": {
        "name": "ООО «Торговая сеть «Магазин 01»»", "inn": "7718595621",
        "ogrn": "1067746872490", "org_type": "Юр.лицо",
    },
    "medtehno.ru": {
        "name": "ООО «Промедик»", "inn": "7725810446",
        "ogrn": "5137746124698", "org_type": "Юр.лицо",
    },
    "ice-age.ru": {
        "name": "ИП Оганов Артём Айкович", "inn": "772823702838",
        "ogrn": "305770000298252", "org_type": "ИП",
    },
}

_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/?#]+)", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^()]+)\)")


def domain_from_url(url: Optional[str]) -> Optional[str]:
    """Домен страницы (без схемы/www./пути/query) в нижнем регистре.
    Не ссылка (пусто/не строка) → None."""
    if not url or not isinstance(url, str):
        return None
    m = _DOMAIN_RE.match(url.strip())
    if not m:
        return None
    return m.group(1).lower().strip() or None


def store_for_domain(domain: Optional[str]) -> Optional[dict]:
    """Запись STORES для домена (включая поддомены известного домена).
    Неизвестный/пустой домен → None — единственная точка сравнения домена со
    справочником, остальные функции этого модуля вызывают только её."""
    if not domain:
        return None
    for known_domain, info in STORES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return info
    return None


def store_for_url(url: Optional[str]) -> Optional[dict]:
    return store_for_domain(domain_from_url(url))


def store_for_source_store(text: Optional[str]) -> Optional[dict]:
    """Текст вида «Сима-ленд (sima-land.ru)» / «Бауцентр (baucenter.ru)» —
    домен достаётся из (первых) скобок и ищется тем же store_for_domain, что
    и store_for_url (ПРАВИЛО №6 — одно сравнение с справочником)."""
    if not text:
        return None
    m = _PAREN_RE.search(text)
    if not m:
        return None
    return store_for_domain(domain_from_url(m.group(1).strip()))


def store_for_inn(inn: Optional[str]) -> Optional[dict]:
    """Запись STORES по ИНН (обратный поиск — апстрим (apply_products_import)
    знает только seller_inn товара и должен подставить name/ogrn/org_type
    при создании контрагента, см. docstring модуля)."""
    if not inn:
        return None
    for info in STORES.values():
        if info["inn"] == inn:
            return info
    return None


def seller_inn_for_url(url: Optional[str]) -> Optional[str]:
    info = store_for_url(url)
    return info["inn"] if info else None


def seller_inn_for_source_store(text: Optional[str]) -> Optional[str]:
    info = store_for_source_store(text)
    return info["inn"] if info else None
