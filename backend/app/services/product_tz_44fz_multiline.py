"""Разбор МНОГОСТРОЧНЫХ значений/описаний на пары (метка, значение) — часть
ЕДИНСТВЕННОГО генератора ТЗ 44-ФЗ (app/services/product_tz_44fz.py,
ПРАВИЛО №6). Вынесено отдельным модулем по ПРАВИЛУ №5 (разрезание
product_tz_44fz.py, 809 строк, QA-ревью 26.10.2026, п.3).

QA-ревью 26.10.2026 (после v3), п.1: список _SECTION_HEADER_LINES (захардко-
женные названия заголовков групп) оказался подгонкой под 6 конкретных
товаров — на 150 случайных товарах стенда давал ~10 случаев сдвига пар.
Заменён на СТРУКТУРНУЮ проверку без списка слов: строка — "метка" только
если выглядит как метка (см. _is_valid_label), а не как значение или
продолжение другой метки. Заголовок группы не хардкодится словами, а
определяется ТЕМ, что он не образует валидную пару со следующей строкой,
но ОСТАЛЬНЫЕ строки после его пропуска — валидные пары (см. _parse_pairs,
backtracking с мемоизацией по позиции).

Общее правило: разбивать на пары («Метка: значение», одной строкой ТЗ на
пару) ТОЛЬКО если вся структура (все строки целиком) проходит проверку;
иначе — НЕ разбирать, исходное значение идёт ОДНОЙ строкой ТЗ, переносы
строк заменяются на "; " (допуск/направление к такой "грязной" строке не
применяются — та же логика, что у product_tz_44fz_values._format_numeric_value
для "грязных" однострочных значений)."""
import re
from typing import Optional

from app.services.product_tz_44fz_name import _strip_brand_mentions
from app.services.product_tz_44fz_values import (
    _direction_for_name,
    _format_numeric_value,
    _is_boilerplate_value,
    _is_excluded_characteristic,
)

_FALLBACK_LINE_RE = re.compile(r"^\s*([^:\n]{2,60}):\s*(.+?)\s*$")
# Лейбл начинается на границе слова (начало строки или после пробела/
# запятой/точки/тире) — без этого на длинном тексте regex мог начать матч
# СЕРЕДИНОЙ слова (например "методом" → "одом"), если только так укладывал
# расстояние до двоеточия в лимит 40 символов.
_FALLBACK_INLINE_RE = re.compile(r"(?:^|(?<=[\s,;.\-—]))([A-Za-zА-Яа-яЁё][^:\n.;]{1,40}):\s*([^\n.;]{2,80})")

# Метка не должна заканчиваться на цифры-значение, прилипшие к концу
# строки ("Размер (мм)        1200" — это два слепленных поля, не метка).
_TRAILING_DIGITS_RE = re.compile(r"\d\s*$")


def _is_valid_label(line: str) -> bool:
    """Структурная проверка "это похоже на метку поля": короткая строка,
    начинается с заглавной буквы, не заканчивается на точку/запятую/
    точку с запятой и не кончается "прилипшим" числом-значением."""
    s = (line or "").strip()
    if not s or len(s) > 60:
        return False
    if not s[0].isupper():
        return False
    if s[-1] in ".,;":
        return False
    if _TRAILING_DIGITS_RE.search(s):
        return False
    return True


def _parse_pairs(lines: list) -> Optional[list]:
    """Backtracking-разбор списка строк на пары (метка, значение) с
    мемоизацией по позиции (O(n)): на каждом шаге сперва пробует текущую
    строку+следующую как обычную пару; если с этой парой весь ОСТАТОК
    строк дальше не удаётся разобрать — откатывается и пробует считать
    текущую строку заголовком группы (пропустить одну, без вывода).
    Одинокая строка-хвост без пары в конце — отбрасывается. Возвращает
    None, если структуру целиком разобрать не удалось (вызывающий тогда
    не разбивает вовсе — "лучше как есть, чем криво")."""
    n = len(lines)
    memo = {}

    def rec(i):
        if i in memo:
            return memo[i]
        remaining = n - i
        if remaining <= 1:
            memo[i] = []
            return []
        result = None
        label, value = lines[i], lines[i + 1]
        if _is_valid_label(label) and value.strip():
            rest = rec(i + 2)
            if rest is not None:
                result = [(label, value)] + rest
        if result is None and _is_valid_label(lines[i]):
            rest = rec(i + 1)
            if rest is not None:
                result = rest
        memo[i] = result
        return result

    return rec(0)


def _split_multiline_value(raw_value: str) -> Optional[list]:
    """Пытается разобрать многострочное ЗНАЧЕНИЕ ОДНОЙ характеристики на
    пары (случай, когда у товара JSON characteristics, но одно поле несёт
    вложенную мини-таблицу "Метка\\nЗначение\\nМетка\\n..."). Возвращает
    список пар или None, если структура не прошла проверку."""
    sub_lines = [l.strip() for l in raw_value.splitlines() if l.strip()]
    if len(sub_lines) < 2:
        return None
    pairs = _parse_pairs(sub_lines)
    if not pairs:
        return None
    return pairs


def _format_single_param(name, raw_value, unit, local_brand_words, global_brands, product_name_lower) -> Optional[str]:
    """Собирает ОДНУ строку "Имя: значение" — общая точка и для обычной
    характеристики, и для КАЖДОЙ пары многострочного значения: те же
    проверки (исключённое имя/штамп/дубль названия) и та же обработка
    направления/допуска/бренда."""
    name = (name or "").strip()
    raw_value = (raw_value or "").strip()
    if not name or not raw_value:
        return None
    if _is_excluded_characteristic(name):
        return None
    if _is_boilerplate_value(raw_value):
        return None
    if product_name_lower and raw_value.strip().lower() == product_name_lower:
        # Значение полностью повторяет название товара — не параметр.
        return None

    value, brand_removed = _strip_brand_mentions(raw_value, local_brand_words, global_brands)
    value = value.strip()
    if not value:
        return None

    direction = _direction_for_name(name)
    formatted = _format_numeric_value(value, unit or "", direction)
    if not formatted:
        return None
    line = f"{name}: {formatted}"
    if brand_removed:
        line += " или эквивалент"
    return line


def _build_param_lines(item, local_brand_words, global_brands, product_name_lower) -> list:
    """Возвращает СПИСОК строк ТЗ для одной характеристики (обычно 0 или 1,
    но для многострочного значения, прошедшего структурную проверку —
    несколько: каждая пара своей строкой, исходное имя характеристики-
    группы к первой паре не клеим). Если структура не прошла проверку —
    значение остаётся ОДНИМ целым (строки через "; ") под исходным именем
    характеристики, без допуска/направления (как любое "грязное" значение)."""
    if not isinstance(item, dict):
        return []
    # Прод-ревью 26.10.2026 (п.A1): флаг in_description у поставщика
    # относится к карточке товара/точному описанию, НЕ к ТЗ 44-ФЗ — он
    # больше не исключает характеристику из ТЗ. Исключение строк — ТОЛЬКО
    # по имени характеристики, см. _is_excluded_characteristic
    # (EXCLUDED_CHARACTERISTIC_NAME_KEYWORDS, product_tz_44fz_rules.py).
    name = (item.get("name") or "").strip()
    raw_value = (item.get("value") or "").strip()
    unit = (item.get("unit") or "").strip()
    if not name or not raw_value:
        return []

    if "\n" in raw_value:
        pairs = _split_multiline_value(raw_value)
        if pairs is not None:
            out = []
            for label, value in pairs:
                sub_line = _format_single_param(
                    label, value, "", local_brand_words, global_brands, product_name_lower,
                )
                if sub_line:
                    out.append(sub_line)
            return out
        raw_value = "; ".join(l.strip() for l in raw_value.splitlines() if l.strip())

    line = _format_single_param(name, raw_value, unit, local_brand_words, global_brands, product_name_lower)
    return [line] if line else []


# -------------------------------------------- fallback из description ----

def _parse_description_fallback(description: Optional[str]) -> list:
    """Три попытки разобрать СВОБОДНЫЙ ТЕКСТ description в характеристики,
    когда у товара нет JSON characteristics вовсе:
      1. Построчно "Название: значение".
      2. То же самое, но внутри фразы (не с начала строки).
      3. Чередующиеся строки "Название"/"значение" (см. _split_multiline_value/
         _parse_pairs) — структурная проверка, без списка слов-заголовков."""
    if not description:
        return []
    result = []
    seen = set()
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _FALLBACK_LINE_RE.match(line)
        if m:
            name, value = m.group(1).strip(), m.group(2).strip()
            if name and value and (name, value) not in seen:
                seen.add((name, value))
                result.append({"name": name, "value": value, "unit": None})
    if result:
        return result

    # QA-ревью (после v3): на длинном свободном тексте (многословное
    # описание/сертификат) finditer находит "label: value" ВНУТРИ обычных
    # предложений (двоеточие перед перечислением, не поле характеристики) —
    # "...печати, содержащая: - название изделия..." превращалось в мусорную
    # пару. Оригинальный сценарий этого прохода — короткая строка вида
    # "Диагональ: 65 см, вес: 4 кг." (один абзац, несколько полей через
    # запятую) — поэтому ограничиваем проход коротким текстом; длинный
    # свободный текст вместо этого идёт в структурный разбор ниже (который
    # на несвязном тексте просто вернёт None и даст [], а не мусор).
    if len(description) <= 200:
        for m in _FALLBACK_INLINE_RE.finditer(description):
            name, value = m.group(1).strip(), m.group(2).strip()
            if name and value and (name, value) not in seen:
                seen.add((name, value))
                result.append({"name": name, "value": value, "unit": None})
        if result:
            return result

    lines = [l.strip() for l in description.splitlines() if l.strip()]
    pairs = _parse_pairs(lines) if len(lines) >= 2 else None
    if not pairs:
        return []
    return [{"name": label, "value": value, "unit": None} for label, value in pairs]
