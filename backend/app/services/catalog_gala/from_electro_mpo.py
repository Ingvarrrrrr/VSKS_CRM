"""Конвертер выгрузки electro-mpo.ru → формат GALA (см. format.py).

Вход (raw) — список объектов вида:
  {name, category, section, subsection, price, unit, url, photo,
   specifications: {"<Имя> в <ед>": "<значение>", "Производитель": "...", ...}}

Правила:
  - name/category/unit как есть; price==0 → null (цены нет).
  - category_path = [category]. section/subsection — технические slug-коды
    раздела прайса поставщика (например "rozetki_vyklyuchateli_..."), НЕ
    категория в смысле читателя каталога, поэтому в category_path не идут;
    самостоятельного смысла для GALA у них нет (ни читаемое имя, ни
    source_id) — сознательно отбрасываются.
  - specifications разбираются по ключу:
      * ключ вида "<Имя> в <ед>" (повторные пробелы в ключе схлопываются перед
        разбором, встречается "Объём  в м3") → характеристика
        {"name": "<Имя>", "unit": "<ед>", "value": <значение>}.
      * ключ вида "<Имя> (<ед>)" (выгрузка кабелей, electro_mpo_cables_all.json,
        26.10: "Сечение жилы кабеля (мм2)", "Диаметр жилы (мм)") →
        характеристика {"name": "<Имя>", "unit": "<ед>", "value": <значение>},
        тем же путём нормализации единицы, что и у формата "в <ед>"
        (_normalize_unit — ОДНА функция на оба формата, ПРАВИЛО №6).
        "Марка изделия" скобок не содержит и этим правилом не затрагивается
        — остаётся обычной характеристикой без unit.
      * "Производитель" → manufacturer (не дублируется в characteristics).
      * ключ, содержащий одновременно "номер" и "поставщик" (например
        "Номера поставщика") → article (не дублируется).
      * "Тип изделия" → product_type (не дублируется).
      * все остальные ключи (Номер по прайс-листу, Серия, Цвет, IP, упаковка,
        хрупкость и т.п.) → characteristics как есть, в порядке словаря.
  - url → source_url и links=[{"url":url,"price":price}] (если url есть).
  - photo → photos=[photo] если непусто, иначе [].
  - is_reusable/is_active не определены в исходнике → null.
  - item_kind = "товар" (только товары в этой выгрузке).
  - name, значения характеристик и manufacturer/article/product_type
    (приходят из тех же specifications-значений) чистятся через
    catalog_gala.clean.clean_text (ПРАВИЛО №6, HTML-сущности/<br>/теги).
  - in_description=False (владелец, 2026-10-26, Задача 2; ПЕРЕСМОТРЕНО
    26.10.2026, Задача 1б) — у характеристик упаковки/логистики поставщика,
    которые не несут смысла для читателя техописания: "Номер по прайс-листу",
    "Торговая единица", "Количество товара в упаковке", "Высота", "Ширина",
    "Глубина" (габариты упаковки). "Хрупкость" и "Объём" ИСКЛЮЧЕНЫ из этого
    набора 26.10.2026 (Задача 1б) — это технические параметры самого товара
    (хрупкость — свойство груза при перевозке, но характеризует сам товар;
    объём — в большинстве выгрузок объём товара, не только тары), владелец
    решил показывать их в описании. "Вес" НЕ входит в список — остаётся в
    описании. Флаг читает services/product_tech_description.py::build_tech_description.
  - Значение "0" у размерных характеристик "Высота"/"Ширина"/"Глубина"/
    "Объём"/"Вес" (владелец, 2026-10-26, выгрузка electro_mpo_breakers_all.json
    — у автоматов эти поля часто "0", т.е. не измерялись) трактуется как
    «нет значения» — характеристика целиком НЕ попадает в characteristics
    (не "0", не пустая строка — просто отсутствует).
  - Код поставщика в начале названия ("00113. . Провод...", "04610.
    Автоматический выключатель...", владелец 2026-10-26, Задача 3) срезается
    через clean.strip_leading_code — ДО clean_text (код всегда ASCII-цифры,
    порядок с html-очисткой не важен, но strip_leading_code работает на
    "сырой" строке до обрезки пробелов, чтобы не плодить вторую функцию
    очистки). check_cable_consistency получает уже очищенное от кода имя.
  - Категория "Кабельно-проводниковая продукция" (кабели, владелец 2026-10-26,
    Задача 4): характеристики "Способ прокладки"/"Назначение" — почти всегда
    подставлены сборщиком выгрузки по умолчанию, не несут смысла для
    читателя техописания → in_description=False (как и у упаковочных
    характеристик Задачи 2), характеристика всё равно хранится в карточке.
"""
import re
from typing import Optional

from app.services.catalog_gala.clean import clean_text, strip_leading_code
from app.services.catalog_gala.electro_consistency import check_cable_consistency
from app.services.catalog_gala.spec_parse import clean_key as _clean_key, split_key_unit
from app.services.catalog_gala.stores import seller_inn_for_url

# Задача 2 — характеристики, которые есть в карточке (characteristics
# хранятся полностью), но НЕ попадают в собранное техописание.
# ПЕРЕСМОТРЕНО 26.10.2026 (Задача 1б): "хрупкость" и "объём" убраны отсюда —
# это технические параметры товара, не служебные поля упаковки/логистики
# поставщика (см. докстринг модуля).
_NOT_IN_DESCRIPTION = {
    "номер по прайс-листу", "торговая единица", "количество товара в упаковке",
    "высота", "ширина", "глубина",
}

# Задача 4 (26.10) — у кабелей эти характеристики почти всегда дефолтные
# (подставлены сборщиком выгрузки), не несут смысла для техописания.
_CABLE_CATEGORY = "Кабельно-проводниковая продукция"
_CABLE_NOT_IN_DESCRIPTION = {"способ прокладки", "назначение"}

# Размерные характеристики, у которых "0" значит «не измерялось» — владелец,
# 2026-10-26, electro_mpo_breakers_all.json (автоматы).
_ZERO_IS_EMPTY_NAMES = {"высота", "ширина", "глубина", "объём", "вес"}


def _is_zero(value) -> bool:
    if value is None:
        return False
    try:
        return float(str(value).strip().replace(",", ".")) == 0
    except (TypeError, ValueError):
        return False


def _char(name: str, value, unit, is_cable: bool) -> Optional[dict]:
    """Собирает элемент characteristics, добавляя in_description=False для
    характеристик упаковки поставщика из _NOT_IN_DESCRIPTION (Задача 2) и,
    у кабелей (is_cable), из _CABLE_NOT_IN_DESCRIPTION (Задача 4).
    Возвращает None (характеристику не писать вовсе), если имя — размерное
    из _ZERO_IS_EMPTY_NAMES и значение — ноль (automaты electro_mpo_breakers_all.json,
    см. докстринг модуля)."""
    name_lower = name.lower()
    if name_lower in _ZERO_IS_EMPTY_NAMES and _is_zero(value):
        return None
    item = {"name": name, "value": value, "unit": unit}
    if name_lower in _NOT_IN_DESCRIPTION or (is_cable and name_lower in _CABLE_NOT_IN_DESCRIPTION):
        item["in_description"] = False
    return item


def _parse_specifications(specs: dict, is_cable: bool) -> tuple:
    """Возвращает (characteristics, manufacturer, article, product_type)."""
    characteristics = []
    manufacturer = None
    article = None
    product_type = None

    for raw_key, raw_value in (specs or {}).items():
        key = _clean_key(raw_key)
        key_lower = key.lower()
        value = clean_text(raw_value)

        if key_lower == "производитель":
            manufacturer = value
            continue
        if "номер" in key_lower and "поставщик" in key_lower:
            article = value
            continue
        if key_lower == "тип изделия":
            product_type = value
            continue

        name, unit = split_key_unit(key)
        c = _char(name, value, unit, is_cable)
        if c is not None:
            characteristics.append(c)

    return characteristics, manufacturer, article, product_type


def convert(raw: list, source_file: str) -> dict:
    items = []
    excluded = []
    for row in raw or []:
        price = row.get("price") or None
        if price == 0:
            price = None

        category = row.get("category") or None
        is_cable = (category or "").strip() == _CABLE_CATEGORY

        characteristics, manufacturer, article, product_type = _parse_specifications(
            row.get("specifications") or {}, is_cable
        )

        name = clean_text(strip_leading_code(row.get("name")))

        # Владелец, 2026-10-26: кабели, где «N×S» в названии противоречит
        # «Сечение жилы кабеля»/«Количество жил кабеля» — не загружаем вовсе
        # (см. docstring модуля electro_consistency.py).
        ok, reason = check_cable_consistency(name, characteristics)
        if not ok:
            excluded.append({"name": name, "reason": reason})
            continue

        url = row.get("url") or None
        links = [{"url": url, "price": price}] if url else []

        photo = row.get("photo") or None
        photos = [photo] if photo else []

        items.append({
            "name": name,
            "category": category,
            "category_path": [category] if category else [],
            "product_type": product_type,
            "item_kind": "товар",
            "unit": row.get("unit") or None,
            "pack_quantity": None,
            "pack_unit": None,
            "price": price,
            "price_date": None,
            "currency": None,
            "manufacturer": manufacturer,
            "article": article,
            "description": None,
            "characteristics": characteristics,
            "photos": photos,
            "links": links,
            "source_url": url,
            "source_id": None,
            "is_reusable": None,
            "is_active": None,
            "seller_inn": seller_inn_for_url(url),
        })

    return {"source": "electro_mpo", "items": items, "excluded": excluded}
