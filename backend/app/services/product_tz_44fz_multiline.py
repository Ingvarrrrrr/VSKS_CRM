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

from app.services.product_characteristics_parse import _split_line as _shared_split_line
from app.services.product_tz_44fz_name import _strip_brand_mentions
from app.services.product_tz_44fz_values import (
    _direction_for_name,
    _format_numeric_value,
    _is_boilerplate_value,
    _is_excluded_characteristic,
    _split_label_qualifier,
)

# Лейбл начинается на границе слова (начало строки или после пробела/
# запятой/точки/тире) — без этого на длинном тексте regex мог начать матч
# СЕРЕДИНОЙ слова (например "методом" → "одом"), если только так укладывал
# расстояние до двоеточия в лимит 40 символов.
_FALLBACK_INLINE_RE = re.compile(r"(?:^|(?<=[\s,;.\-—]))([A-Za-zА-Яа-яЁё][^:\n.;]{1,40}):\s*([^\n.;]{2,80})")

# Метка не должна заканчиваться на цифры-значение, прилипшие к концу
# строки ("Размер (мм)        1200" — это два слепленных поля, не метка).
_TRAILING_DIGITS_RE = re.compile(r"\d\s*$")

# Владелец, 27.10.2026 (товар 3002): двоеточие ВНУТРИ обычного предложения
# ("Изделие подходит для оснащения различных объектов и помещений:
# административных зданий...") ловилось построчным/inline-разбором как
# пара характеристики. Коррекция владельца (та же дата, товар 32655):
# жёсткий порог 5 слов/40 символов зарезал легитимную метку "Максимальный
# диаметр перекусываемого стального прутка" (5 слов, 52 симв.) — порог
# смягчён до >10 слов/>80 симв., основной сигнал — глагол-маркер
# предложения в начале слова. Этот фильтр — ТОЛЬКО для разбора description
# (построчного и inline); на характеристики товара (JSON) он не действует —
# там имя задаёт сам каталог/поставщик, а не произвольный текст description.
_SENTENCE_VERB_MARKERS = (
    "подходит", "предназначен", "используется", "применяется",
    "позволяет", "обеспечивает", "имеет", "является",
)
_SENTENCE_LABEL_MAX_CHARS = 80
_SENTENCE_LABEL_MAX_WORDS = 10


def _looks_like_sentence_label(label: str) -> bool:
    """True — метка похожа на обычное предложение (описание товара), а не
    на имя характеристики: длиннее 80 символов, больше 10 слов, или одно из
    слов начинается с глагола-маркера предложения (_SENTENCE_VERB_MARKERS,
    регистронезависимо, "по началу слова" — совпадение префикса, чтобы
    ловить и "подходит"/"подходят", и "предназначен"/"предназначена")."""
    s = (label or "").strip()
    if not s or len(s) > _SENTENCE_LABEL_MAX_CHARS:
        return True
    words = s.split()
    if len(words) > _SENTENCE_LABEL_MAX_WORDS:
        return True
    return any(
        w.lower().startswith(marker)
        for w in words
        for marker in _SENTENCE_VERB_MARKERS
    )


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

    # Квалификатор "не более"/"не менее" (+ единица) ВНУТРИ имени — выносим
    # наружу ДО всех проверок (27.10.2026, товар 4481 с прода): очищенное
    # имя идёт и в проверку исключённых характеристик, и в дубль-проверку
    # названия товара; хвостовая точка значения убирается, раз квалификатор
    # уже явно задан меткой (значение "0.85." → "0.85").
    name, forced_direction, forced_unit = _split_label_qualifier(name)
    if forced_direction:
        raw_value = raw_value.rstrip(".").strip()
        if not raw_value:
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

    # Квалификатор из метки ПОБЕЖДАЕТ словарь направлений по имени (п.3,
    # 27.10.2026) — на случай, если очищенное имя словарём читается иначе.
    direction = forced_direction or _direction_for_name(name)
    effective_unit = unit or forced_unit
    formatted = _format_numeric_value(value, effective_unit or "", direction)
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
      1. Построчно, ЕДИНЫМ построчным разборщиком _split_line из
         app/services/product_characteristics_parse.py (ПРАВИЛО №6 — тот же
         разбор "Метка: значение"/"Метка\\tзначение"/"Метка - значение"/
         "Метка ..... значение", что и у вставки характеристик с сайта;
         второго такого построчного разбора здесь не пишем). Юнит из
         значения (если есть) НЕ отделяется здесь нарочно — им уже умеет
         пользоваться _format_numeric_value (TRAIL-группа), второй раз
         этим не занимаемся.
      2. То же самое, но внутри фразы (не с начала строки) — своё регулярное
         выражение _FALLBACK_INLINE_RE: paste-разборщик работает на весь
         текст целиком и не умеет искать "label: value" В СЕРЕДИНЕ абзаца —
         эта способность нужна только description (пользователь вставляет
         связный текст, а не таблицу характеристик), второго места для неё
         в проекте нет.
      3. Чередующиеся строки "Название"/"значение" со СТРУКТУРНОЙ проверкой
         group-заголовков (_parse_pairs/_is_valid_label, backtracking) —
         paste-разборщик для "рваного" текста делает только наивное
         деление пополам БЕЗ пропуска заголовков групп (там это оправдано:
         пользователь вставляет таблицу без вложенных секций); реальные
         описания каталога (id 582631/582099, 27.10.2026 — id 3002/4481)
         содержат заголовки групп ("Общая информация", "Технические
         характеристики") между парами — наивное деление даёт сдвиг пар,
         поэтому backtracking-версия остаётся ТОЛЬКО здесь, под description."""
    if not description:
        return []
    result = []
    seen = set()
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pair = _shared_split_line(line)
        if pair:
            name, value = pair
            if not name or not value or (name, value) in seen:
                continue
            # Проверяем ОЧИЩЕННУЮ (без квалификатора "не более"/"не менее" в
            # метке, см. _split_label_qualifier) версию имени — иначе
            # легитимные метки вида "Рассчитан на вес человека не более,
            # кг." (4 слова после очистки) ложно отбраковывались бы по
            # числу слов квалификатора+единицы.
            base_name = _split_label_qualifier(name)[0]
            if _looks_like_sentence_label(base_name):
                continue
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
            if not name or not value or (name, value) in seen:
                continue
            if _looks_like_sentence_label(_split_label_qualifier(name)[0]):
                continue
            seen.add((name, value))
            result.append({"name": name, "value": value, "unit": None})
        if result:
            return result

    lines = [l.strip() for l in description.splitlines() if l.strip()]
    pairs = _parse_pairs(lines) if len(lines) >= 2 else None
    if not pairs:
        return []
    return [{"name": label, "value": value, "unit": None} for label, value in pairs]
