"""Проверка «это настоящий производитель, а не мусор в колонке manufacturer»
(владелец, 27.10.2026, РЕШЕНИЕ про сведение товаров по бренду+артикулу
производителя — см. products_import_match.py): если manufacturer неправильный,
строка импорта не должна ни писать его в Product.manufacturer, ни участвовать
в новом критерии сопоставления «тот же бренд + тот же артикул производителя»
(ПРАВИЛО №6 — обе проверки должны сверяться с ОДНИМ результатом этой функции,
не заводить вторую эвристику).

Проверено на реальных выгрузках (C:\\Users\\1\\Downloads\\Товары и ТЗ\\,
27.10.2026):
  - kuvalda_tools_hardware_equipment.json — 12089 из 13644 строк: manufacturer
    = первое слово названия товара ("Лестница", "Насос", "Машина", "Хомут",
    "Комплект", "Тележка" и т.п.) — источник спутал тип товара с брендом.
  - regard_computers_office_equipment.json — 856 строк: manufacturer буквально
    "Производитель" (имя колонки попало в данные).
  - promalper_height_safety_equipment.json — 136 строк: manufacturer —
    название страны ("Россия", "Франция", "Италия", "Чехия") — спутано со
    страной производства.
  - kns_computers_office_equipment.json — 24 строки: тоже "Производитель".

Три независимых признака неправильного значения (любой — достаточно):
  1. Пусто (после strip).
  2. Техническая метка-заглушка источника ("производитель", "бренд", "нет",
     "без бренда", "noname" и т.п., BOGUS_LABELS ниже) — регистр и пробелы не
     важны.
  3. Название страны (catalog_gala.country_names.is_country_name — ПРАВИЛО
     №6, второй список стран здесь не заводим).
  4. Совпадает с ПЕРВЫМ словом названия товара, написано кириллицей и НЕ
     встречается в названии ещё раз — это и есть признак «источник взял тип
     товара за бренд» (у настоящего бренда, напечатанного в начале названия,
     название обычно повторяет бренд ещё раз дальше, см. докстринг
     _matches_leading_category_word). Латиница (MAKITA, ASUS, HP) этим
     правилом НЕ проверяется вовсе — реальные бренды почти всегда пишутся
     латиницей в этих выгрузках, а кириллические совпадения с первым словом
     названия систематически оказываются типом товара, не брендом."""
import re
from typing import Optional

from app.services.catalog_gala.country_names import is_country_name

# Метки-заглушки источника вместо настоящего производителя (регистр и
# пробелы по краям не важны — сравнение после .strip().lower()).
BOGUS_LABELS = {
    "производитель",
    "бренд",
    "нет",
    "нет бренда",
    "нет данных",
    "без бренда",
    "без марки",
    "не указан",
    "не указано",
    "не указана",
    "неизвестен",
    "неизвестно",
    "неизвестный",
    "noname",
    "no name",
    "no-name",
    "n/a",
    "na",
    "-",
    "—",
}

# Слово кириллицей — только кириллические буквы и дефис/пробел внутри
# (составные вида "воздушно-пенный" тоже считаются кириллическим словом).
_CYRILLIC_WORD_RE = re.compile(r"^[а-яё]+(?:[\-\s][а-яё]+)*$", re.IGNORECASE)

# Токенизация названия товара — слово как последовательность букв/цифр
# (пунктуация/скобки не входят в токен, поэтому "Лестница," и "(Россия)"
# очищаются до "лестница"/"россия").
_WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower().replace("ё", "е")


def _is_bogus_label(manufacturer_norm: str) -> bool:
    return manufacturer_norm in BOGUS_LABELS


def _is_cyrillic_word(manufacturer: str) -> bool:
    return bool(_CYRILLIC_WORD_RE.match(manufacturer.strip()))


def _name_tokens(name: str) -> list[str]:
    return [_WORD_RE.match(w).group(0).lower().replace("ё", "е") if _WORD_RE.match(w) else ""
            for w in [m.group(0) for m in _WORD_RE.finditer(name)]]


def _matches_leading_category_word(manufacturer_norm: str, manufacturer: str, name: Optional[str]) -> bool:
    """True, если manufacturer — кириллическое слово, совпадающее с ПЕРВЫМ
    словом названия, и больше в названии не встречается (ровно один раз —
    сам этот первый токен). Второе и далее совпадение (слово повторяется в
    названии) — признак, что это настоящий повторённый бренд, а не тип
    товара, случайно совпавший с началом названия; такую строку не
    отбраковываем."""
    if not manufacturer_norm or not _is_cyrillic_word(manufacturer):
        return False
    tokens = _name_tokens(name or "")
    if not tokens or tokens[0] != manufacturer_norm:
        return False
    return tokens.count(manufacturer_norm) == 1


def is_bogus_manufacturer(manufacturer: Optional[str], name: Optional[str] = None) -> bool:
    """True — manufacturer неправильный (пустой/заглушка/страна/тип товара,
    принятый за бренд источником файла) и не должен ни писаться в
    Product.manufacturer, ни участвовать в сопоставлении по бренду+артикулу
    производителя (products_import_match.py). `name` обязателен только для
    признака 4 (первое слово названия) — без него эта проверка просто не
    сработает, остальные три признака не зависят от name."""
    manufacturer_norm = _norm(manufacturer)
    if not manufacturer_norm:
        return True
    if _is_bogus_label(manufacturer_norm):
        return True
    if is_country_name(manufacturer_norm):
        return True
    if _matches_leading_category_word(manufacturer_norm, manufacturer or "", name):
        return True
    return False
