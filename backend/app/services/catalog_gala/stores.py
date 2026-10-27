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
from typing import Iterable, Optional

# ОГРН у юрлиц, ОГРНИП у ИП — модель Contractor (app/models/contractor.py)
# хранит оба в одном поле `ogrn`, поэтому здесь это единое поле без различения
# по названию (как и в остальной БД).
#
# article_is_manufacturer (владелец, 27.10.2026, задача product_similar п.4):
# True — значение в колонке "Артикул" этого магазина — артикул ПРОИЗВОДИТЕЛЯ
# (значит одинаковое у разных магазинов для одного и того же товара, можно
# использовать как ключ сопоставления); False — это СВОЙ номер магазина
# (у Сима-ленда «Артикул Сима-ленд», у Бауцентра «Артикул» — внутренний
# номенклатурный номер, по проду 27.10.2026 у одного и того же товара
# отличается между магазинами). Проверено на проде: True — electro-mpo.ru
# (МПО Электромонтаж, пример 14054DEK), k-spasatel.ru (Высокая опора, пример
# M34A TLN). False — sima-land.ru (1431671), baucenter.ru (643000047).
#
# Обновлено 27.10.2026 (повторная проверка на проде): ice-age.ru и
# medtehno.ru переведены в True — в их «артикуле» в основном артикул
# производителя (ice-age: D020AA00 у Petzl I'D S, 037801-BU, SN75UKO009;
# Промедик: KZ 0307, DE 0504, «1002213 [VR6118L]»), а не внутренний номер
# магазина.
# Остальные — False (пока не проверено на реальных файлах — безопасный
# дефолт "не считать артикулом производителя").
STORES: dict[str, dict] = {
    "sima-land.ru": {
        "name": "ООО ТД «Сима-ленд»", "inn": "6679104850",
        "ogrn": "1176658004929", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "baucenter.ru": {
        "name": "ООО «Бауцентр Рус»", "inn": "7702596813",
        "ogrn": "1067746357524", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "electro-mpo.ru": {
        "name": "ЗАО «МПО Электромонтаж»", "inn": "7719079370",
        "ogrn": "1037700089052", "org_type": "Юр.лицо",
        "article_is_manufacturer": True,
    },
    "vkusvill.ru": {
        "name": "АО «Вкусвилл»", "inn": "7734443270",
        "ogrn": "1217700253671", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "k-spasatel.ru": {
        "name": "ООО «Высокая опора»", "inn": "9718172669",
        "ogrn": "1217700197219", "org_type": "Юр.лицо",
        "article_is_manufacturer": True,
    },
    "magazin01.ru": {
        "name": "ООО «Торговая сеть «Магазин 01»»", "inn": "7718595621",
        "ogrn": "1067746872490", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "medtehno.ru": {
        "name": "ООО «Промедик»", "inn": "7725810446",
        "ogrn": "5137746124698", "org_type": "Юр.лицо",
        "article_is_manufacturer": True,
    },
    "ice-age.ru": {
        "name": "ИП Оганов Артём Айкович", "inn": "772823702838",
        "ogrn": "305770000298252", "org_type": "ИП",
        "article_is_manufacturer": True,
    },
    # Реквизиты с сайта магазина, сверены 27.10.2026 (владелец: seller_inn в
    # новых выгрузках kns/regard/kuvalda/safe/promalper — НЕВЕРНЫЕ, не
    # проходят контрольную цифру ИНН и не принадлежат магазину; ниже —
    # настоящие реквизиты). article_is_manufacturer=False — эти магазины
    # дают manufacturer_article/store_article отдельными полями явно,
    # устаревший флаг article_is_manufacturer (трактовка item.article) их не
    # касается.
    "kns.ru": {
        "name": "ООО «КОМПЬЮЛАН»", "inn": "9723033526",
        "ogrn": "1177746877220", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "regard.ru": {
        "name": "ООО «Регард МСК»", "inn": "7730234438",
        "ogrn": "1177746406584", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "kuvalda.ru": {
        "name": "ООО «Энтузиаст-С»", "inn": "6319060894",
        "ogrn": "1026301703010", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "safe.ru": {
        "name": "ООО «НПО Промет»", "inn": "7751009218",
        "ogrn": "1155003003121", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    "promalper.com": {
        "name": "ООО «Технологии Промышленной Безопасности»", "inn": "7806293316",
        "ogrn": "1177847338074", "org_type": "Юр.лицо",
        "article_is_manufacturer": False,
    },
    # inari.pro — реквизиты НЕ подтверждены (ИНН из файла 1832034960 не
    # проходит контрольную цифру, владелец 27.10.2026) — в справочник
    # сознательно НЕ добавлен; seller_inn_for_* для него вернёт None, пока
    # владелец не найдёт настоящий ИНН.
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


def article_is_manufacturer_for_inn(inn: Optional[str]) -> bool:
    """True, если у магазина с этим ИНН колонка "Артикул" несёт артикул
    ПРОИЗВОДИТЕЛЯ (см. комментарий у STORES выше) — используется
    app.services.product_similar для ключа сопоставления по артикулу.
    Неизвестный ИНН/магазин → False (безопасный дефолт — не считать
    незнакомое значение артикулом производителя)."""
    info = store_for_inn(inn)
    return bool(info and info.get("article_is_manufacturer"))


def split_legacy_article(article: Optional[str], inn: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """ЕДИНСТВЕННОЕ место трактовки устаревшего поля item.article (ПРАВИЛО
    №6, владелец 27.10.2026, см. докстринг item в format.py) — раскладывает
    его на (manufacturer_article, store_article) по article_is_manufacturer_
    for_inn(inn): True → (article, None), False/неизвестный ИНН → (None,
    article). Пустой/None article → (None, None). Вызывают конвертеры
    (from_*.py, когда у них ещё нет отдельных manufacturer_article/
    store_article полей источника) и products_import_apply.py (трактовка
    article старых файлов GALA без новых колонок)."""
    if not article:
        return None, None
    if article_is_manufacturer_for_inn(inn):
        return article, None
    return None, article


def seller_inn_for_url(url: Optional[str]) -> Optional[str]:
    info = store_for_url(url)
    return info["inn"] if info else None


def seller_inn_for_source_store(text: Optional[str]) -> Optional[str]:
    info = store_for_source_store(text)
    return info["inn"] if info else None


def inn_checksum_valid(inn: Optional[str]) -> bool:
    """Контрольная цифра ИНН РФ (владелец, 27.10.2026, повод — seller_inn
    новых выгрузок kns/regard/kuvalda/safe/promalper/inari: 5 из 6 оказались
    НЕВЕРНЫМИ, ни один не принадлежал магазину). 10 знаков — юрлицо (девятая
    цифра контрольная), 12 — ИП (11-я и 12-я контрольные). Не 10/12 цифр или
    не только цифры → False. Единственный валидатор контрольной цифры ИНН в
    проекте (grep по 'checksum'/'контрольн' на момент написания не нашёл ни
    одного — не плодить второй, ПРАВИЛО №6)."""
    if not inn or not inn.isdigit():
        return False
    if len(inn) == 10:
        w = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        check = sum(int(d) * wi for d, wi in zip(inn[:9], w)) % 11 % 10
        return check == int(inn[9])
    if len(inn) == 12:
        w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        d11 = sum(int(d) * wi for d, wi in zip(inn[:10], w11)) % 11 % 10
        d12 = sum(int(d) * wi for d, wi in zip(inn[:11], w12)) % 11 % 10
        return d11 == int(inn[10]) and d12 == int(inn[11])
    return False


def resolve_seller_inn(
    file_inn: Optional[str], url_candidates: Iterable[Optional[str]],
) -> tuple[Optional[str], Optional[str]]:
    """РЕШЕНИЕ ВЛАДЕЛЬЦА (27.10.2026) — ЕДИНСТВЕННОЕ место, определяющее
    seller_inn строки импорта каталога (вызывает load_gala_catalog.
    item_to_row): seller_inn файла (item["seller_inn"]) оказался НЕВЕРНЫМ у
    5 из 6 новых магазинов (не проходил контрольную цифру и/или не
    принадлежал магазину по его реквизитам с сайта).

    Правило:
      1. Если домен хоть одной из `url_candidates` (товарные ссылки строки —
         links[0].url/source_url конвертера, в порядке приоритета) известен
         в STORES → seller_inn ВСЕГДА берётся из STORES, значение файла
         игнорируется. file_inn, отличающийся от табличного — не ошибка
         вызывающего, просто другой ИНН в источнике; возвращается
         reason="ИНН из файла заменён по сайту магазина" (для счётчика
         загрузки), если file_inn был непустым и отличался.
      2. Домен не известен STORES → используется file_inn, но ТОЛЬКО если
         он проходит контрольную цифру (inn_checksum_valid, 10/12 знаков) —
         иначе seller_inn=None, reason="ИНН невалиден, магазин не определён".

    Возвращает (seller_inn, reason); reason=None — ничего менять не
    потребовалось (домен неизвестен, file_inn пуст либо прошёл проверку без
    конфликта с известным магазином)."""
    for url in url_candidates:
        info = store_for_url(url)
        if info is not None:
            reason = None
            if file_inn and file_inn.strip() and file_inn.strip() != info["inn"]:
                reason = "ИНН из файла заменён по сайту магазина"
            return info["inn"], reason

    inn_norm = (file_inn or "").strip()
    if not inn_norm:
        return None, None
    if inn_checksum_valid(inn_norm):
        return inn_norm, None
    return None, "ИНН невалиден, магазин не определён"
