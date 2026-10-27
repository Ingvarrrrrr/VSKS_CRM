"""Разбор ЧИСЛОВОГО ЗНАЧЕНИЯ характеристики — направление (не менее/не
более/точное/диапазон) и допуск ±10% — часть ЕДИНСТВЕННОГО генератора ТЗ
44-ФЗ (app/services/product_tz_44fz.py, ПРАВИЛО №6). Вынесено отдельным
модулем по ПРАВИЛУ №5 (разрезание product_tz_44fz.py, 809 строк, QA-ревью
26.10.2026, п.3).

Правила (см. докстринг product_tz_44fz.py для полной истории ревью):
  - Допуск ±10% применяется ТОЛЬКО к "чистому" числовому значению (число/
    диапазон + необязательная короткая единица + необязательная короткая
    скобка). "Грязное" значение (слова, "x", несколько чисел во фразе)
    возвращается БЕЗ ИЗМЕНЕНИЙ, независимо от направления по имени.
  - Явные направления в САМОМ значении ("от X", "до X", "A-B") всегда
    побеждают направление по словарю имени — литеральный перенос чисел,
    без округления/допуска.
  - "Время непрерывной/автономной работы" — форсированно "не менее",
    побеждает даже явное "до X" в значении.
"""
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.services.product_tz_44fz_rules import (
    BOILERPLATE_VALUE_MARKERS,
    EXACT_CHARACTERISTIC_NAME_KEYWORDS,
    EXCLUDED_CHARACTERISTIC_NAME_KEYWORDS,
    MANUFACTURER_KEYWORD_FALSE_POSITIVE_RE,
    NOT_LESS_CHARACTERISTIC_NAME_KEYWORDS,
    NOT_MORE_CHARACTERISTIC_NAME_KEYWORDS,
)

_NUM = r"\d+(?:[.,]\d+)?"

# "Чистый хвост" после числа: необязательная короткая единица (без цифр,
# "x"/"х"/"×", "/", "-"/"–" — иначе это уже не единица, а лишний текст) и
# необязательная короткая скобка.
_TRAIL_UNIT = r"[^\d\sx×х/\\\-–]{1,12}"
_TRAIL_PAREN = r"\([^()]{1,24}\)"
_TRAIL = rf"(?:\s*({_TRAIL_UNIT}))?(?:\s*({_TRAIL_PAREN}))?\s*$"

_RANGE_PHRASE_RE = re.compile(rf"^от\s+({_NUM})\s+до\s+({_NUM}){_TRAIL}", re.IGNORECASE)
_DASH_RANGE_RE = re.compile(rf"^({_NUM})\s*-\s*({_NUM}){_TRAIL}")
_DO_RE = re.compile(rf"^до\s+({_NUM}){_TRAIL}", re.IGNORECASE)
_OT_RE = re.compile(rf"^от\s+({_NUM}){_TRAIL}", re.IGNORECASE)
_SINGLE_RE = re.compile(rf"^({_NUM}){_TRAIL}")
# Габариты "A х B (х C) <ед>" — только числа и разделитель х/x/× целиком,
# единица/скобка — ОДНА на всё значение (исключение общего правила).
_COMPOSITE_RE = re.compile(
    rf"^({_NUM})\s*[xх×]\s*({_NUM})(?:\s*[xх×]\s*({_NUM}))?{_TRAIL}", re.IGNORECASE
)

# "Время непрерывной/автономной работы" — ВСЕГДА "не менее", проверяется
# РАНЬШЕ остальных направлений (и побеждает даже явное "до X" в значении —
# автономность/время работы для закупки формулируется только как минимум).
_FORCE_NOT_LESS_NAME_RE = re.compile(r"время.*работ|автономн|время непрерывн", re.IGNORECASE)

# Прод-ревью 26.10.2026 (четвёртый заход, п.A3/A7): "Количество"/"Кол-во"/
# "Число" В НАЧАЛЕ имени характеристики — точное значение ВСЕГДА (а не
# только конкретные словосочетания из EXACT_CHARACTERISTIC_NAME_KEYWORDS
# выше — "Количество жил кабеля" туда не попадало и уходило в range).
_QUANTITY_PREFIX_RE = re.compile(r"^(количество|кол-во|число)\b", re.IGNORECASE)
# "Температура" — точное значение (срабатывания/эксплуатации/рабочая
# и т.п.), КРОМЕ явного указания диапазона эксплуатации/рабочих условий —
# те остаются "range"/NOT_LESS по общим правилам ниже.
_TEMPERATURE_EXCLUDE_RE = re.compile(r"рабочих|эксплуатац|диапазон", re.IGNORECASE)

# "Условный проход"/"Ду"/"DN" (номинальный диаметр трубопроводной арматуры,
# id 6762, 27.10.2026) — паспортное ТОЧНОЕ значение, не диапазон. "Ду"/"DN" —
# короткие буквосочетания, матчим ТОЛЬКО по границе слова (а не подстрокой,
# иначе "ду" поймало бы середину слова "проДУкт").
_NOMINAL_DIAMETER_RE = re.compile(r"условн\w*\s*проход|\bdn\b|\bду\b", re.IGNORECASE)

# Квалификатор "не более"/"не менее" и/или короткая единица ВНУТРИ самого
# имени характеристики, через запятую (порядок любой — реальные описания
# прода дают оба варианта, 27.10.2026):
#   id 4481: "Масса, не более, кг."            (квалификатор, потом единица)
#   id 6762: "Масса, кг, не более"              (единица, потом квалификатор)
#   id 4481: "Рассчитан на вес человека не более, кг." (квалификатор слит с
#             именем без запятой, единица — через запятую)
#   id 6762: "Условный проход, мм"              (единица БЕЗ квалификатора)
# Без извлечения итоговая строка дублирует квалификатор/единицу и пачкает
# значение хвостовой точкой: "Масса, не более, кг.: не более 0.85." вместо
# "Масса: не более 0,85 кг".
_QUALIFIER_WORDS = ("не более", "не менее")
# Квалификатор, слитый с именем БЕЗ запятой ("...человека не более") —
# отделяется пробелом, не запятой.
_QUALIFIER_SUFFIX_RE = re.compile(r"\s+(не\s+более|не\s+менее)\s*$", re.IGNORECASE)

# Короткая единица измерения через запятую в ИМЕНИ ("Условный проход, мм",
# id 6762) — СПИСОК известных сокращений, а не "любое короткое слово без
# пробела": QA-регрессия 27.10.2026, тест test_omron_full_card — у "Уровень
# шума, децибел" второй сегмент "децибел" тоже короткий/без пробела/без
# цифр, но это ПОЛНОЕ слово-продолжение имени характеристики (owner даёт
# такое имя дословно), а не единица, которую нужно вынести в значение; без
# белого списка оно ложно распозналось бы как единица и обрезало имя.
_LABEL_UNIT_WORDS = frozenset({
    "кг", "г", "мг", "т",
    "мм", "см", "м", "км",
    "л", "мл",
    "шт", "шт.",
    "в", "квт", "вт", "а", "гц",
    "мпа", "кпа", "бар", "н", "дб",
    "c", "с", "мин", "час", "ч",
    "%",
})


def _split_label_qualifier(name: str):
    """Выносит из имени характеристики квалификатор "не более"/"не менее"
    и/или короткую единицу измерения, если они приклеены к имени через
    запятую (в любом порядке) — см. примеры выше. Возвращает (очищенное_имя,
    направление "not_more"/"not_less"/None, единица_или_""). Квалификатор из
    метки ПОБЕЖДАЕТ словарь направлений _direction_for_name (вызывающий
    обязан использовать forced-направление, а не пересчитывать его по
    очищенному имени) — направление возвращается, только если найдено;
    единица возвращается и без направления (просто "Метка, ед." без
    квалификатора). Если ничего не найдено — (исходное имя, None, "")."""
    s = (name or "").strip()
    if not s:
        return name, None, ""

    if "," not in s:
        # Нет запятой вовсе — квалификатор, если есть, может быть только
        # слит с именем без запятой ("...человека не более").
        m = _QUALIFIER_SUFFIX_RE.search(s)
        if not m:
            return name, None, ""
        direction = "not_more" if "более" in m.group(1).lower() else "not_less"
        base = s[: m.start()].rstrip().rstrip(",").strip()
        return (base, direction, "") if base else (name, None, "")

    segments = [seg.strip() for seg in s.split(",")]
    base = segments[0]
    direction = None
    unit = ""
    leftover = False
    for seg in segments[1:]:
        seg_clean = seg.rstrip(".").strip()
        low = seg_clean.lower()
        if direction is None and low in _QUALIFIER_WORDS:
            direction = "not_more" if low == "не более" else "not_less"
            continue
        if not unit and low in _LABEL_UNIT_WORDS:
            unit = seg_clean
            continue
        leftover = True

    if direction is None:
        m = _QUALIFIER_SUFFIX_RE.search(base)
        if m:
            direction = "not_more" if "более" in m.group(1).lower() else "not_less"
            base = base[: m.start()].rstrip().rstrip(",").strip()

    if leftover or (direction is None and not unit):
        # Ни квалификатор, ни распознанная единица не нашлись (или остался
        # непонятный "хвост" через запятую) — безопасный отказ, имя как есть.
        return name, None, ""
    base = base.strip()
    return (base, direction, unit) if base else (name, None, "")


# ---------------------------------------------------------------- числа ----

def _c(numstr: str) -> str:
    """Форматирует число как есть, только меняя точку на запятую (без
    пересчёта границ — для направлений 'не менее'/'не более'/точное значение
    и для явных диапазонов, где само число переносится из исходного
    значения без изменений)."""
    return numstr.replace(".", ",")


def _decimals_of(numstr: str) -> int:
    s = numstr.replace(",", ".")
    return len(s.split(".", 1)[1]) if "." in s else 0


_MAX_RANGE_DECIMALS = 3


def _range_bounds(numstr: str):
    """Границы допуска ±10% (значение×0,9 / значение×1,1), прод-ревью
    26.10.2026 (п.1, ПЯТЫЙ заход): знаки после запятой — НЕ по исходному
    числу (старая логика давала "13" -> floor/ceil -> "от 11 до 15", это
    ±15%, а не ±10%), а по ВЕЛИЧИНЕ: < 100 — один знак, >= 100 — целое,
    округление ВСЕГДА ROUND_HALF_UP на обеих границах. Если на этой
    точности границы совпали ИЛИ нижняя ушла в 0 — добавляем ещё знак
    (максимум _MAX_RANGE_DECIMALS=3). Если границы совпадают даже на
    максимальной точности — возвращаем None: вызывающий обязан вывести
    ТОЧНОЕ значение без диапазона (см. _format_numeric_value/_try_composite)."""
    value = Decimal(numstr.replace(",", "."))
    decimals = 0 if value >= 100 else 1
    low = high = None
    while True:
        quant = Decimal("1").scaleb(-decimals)
        low = (value * Decimal("0.9")).quantize(quant, rounding=ROUND_HALF_UP)
        high = (value * Decimal("1.1")).quantize(quant, rounding=ROUND_HALF_UP)
        if (low == high or low == 0) and decimals < _MAX_RANGE_DECIMALS:
            decimals += 1
            continue
        break
    if low == high:
        return None
    return low, high, decimals


def _fmt_decimal(d: Decimal, decimals: int) -> str:
    """Прод-ревью 26.10.2026 (п.1): граница без лишних ",0" — "9,0" из
    _range_bounds (decimals=1, но округление дало целое) выводится как
    "9", а не "9,0" ("от 9 до 11" допустимо, если ровно)."""
    text = str(int(d)) if decimals == 0 else f"{d:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _suffix(dict_unit: str, captured_unit: Optional[str], captured_paren: Optional[str]) -> str:
    unit = (dict_unit or captured_unit or "").strip()
    parts = [p for p in (unit, (captured_paren or "").strip()) if p]
    return " ".join(parts)


def _with_unit(text: str, suffix: str) -> str:
    suffix = (suffix or "").strip()
    return f"{text} {suffix}" if suffix else text


# ------------------------------------------------------- направление ----

def _direction_for_name(name: str) -> str:
    lname = (name or "").lower()
    if _FORCE_NOT_LESS_NAME_RE.search(lname):
        return "force_not_less"
    if _QUANTITY_PREFIX_RE.match(lname):
        return "exact"
    if "температур" in lname and not _TEMPERATURE_EXCLUDE_RE.search(lname):
        return "exact"
    if _NOMINAL_DIAMETER_RE.search(lname):
        return "exact"
    for kw in EXACT_CHARACTERISTIC_NAME_KEYWORDS:
        if kw in lname:
            return "exact"
    for kw in NOT_MORE_CHARACTERISTIC_NAME_KEYWORDS:
        if kw in lname:
            return "not_more"
    for kw in NOT_LESS_CHARACTERISTIC_NAME_KEYWORDS:
        if kw in lname:
            return "not_less"
    return "range"


# "производител" ложно совпадает ПОДСТРОКОЙ с "производительност..." (КПД/
# коэффициент производительности — число товара, не бренд) — прод-ревью
# 26.10.2026 (п.A7): этот ключ проверяется ЕДИНСТВЕННЫМ общим regex'ом
# MANUFACTURER_KEYWORD_FALSE_POSITIVE_RE (product_tz_44fz_rules.py,
# ПРАВИЛО №6), остальные ключи — как раньше, простой подстрокой.
_NON_OVERLAPPING_EXCLUDED_KEYWORDS = tuple(
    kw for kw in EXCLUDED_CHARACTERISTIC_NAME_KEYWORDS if kw != "производител"
)


def _is_excluded_characteristic(name: str) -> bool:
    lname = (name or "").lower()
    if MANUFACTURER_KEYWORD_FALSE_POSITIVE_RE.search(lname):
        return True
    return any(kw in lname for kw in _NON_OVERLAPPING_EXCLUDED_KEYWORDS)


def _is_boilerplate_value(value: str) -> bool:
    lvalue = (value or "").lower()
    return any(marker in lvalue for marker in BOILERPLATE_VALUE_MARKERS)


# --------------------------------------------------- разбор значения ----

def _try_composite(value: str, unit: str) -> Optional[str]:
    """Габариты "A х B (х C) <ед>" — ЕДИНСТВЕННОЕ исключение общего правила:
    допуск ±10% применяется к каждому числу, единица/скобка — одна на всё
    значение. Если в значении есть что-то кроме чисел, разделителя х/x/×
    и ОДНОЙ короткой единицы/скобки в конце — это не габариты, возвращаем
    None ("оставить как есть")."""
    m = _COMPOSITE_RE.match(value)
    if not m:
        return None
    nums = [g for g in (m.group(1), m.group(2), m.group(3)) if g]
    captured_unit, captured_paren = m.group(4), m.group(5)
    suffix = _suffix(unit, captured_unit, captured_paren)
    parts = []
    for num in nums:
        bounds = _range_bounds(num)
        if bounds is None:
            parts.append(_c(num))
        else:
            low, high, decimals = bounds
            parts.append(f"от {_fmt_decimal(low, decimals)} до {_fmt_decimal(high, decimals)}")
    text = " х ".join(parts)
    return _with_unit(text, suffix)


def _format_numeric_value(value: str, unit: str, direction: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None

    # Прод-ревью 26.10.2026 (п.A2): "чистый" ноль ("0 кг", "0") —
    # бессмысленная строка ТЗ ("Вес брутто: 0 кг"), строку не выводим
    # вовсе. Проверяем ТОЛЬКО "чистое" одиночное число (_SINGLE_RE) —
    # "грязные" значения ("0 из 10 баллов") здесь не трогаем.
    m_zero = _SINGLE_RE.match(value)
    if m_zero:
        try:
            if Decimal(m_zero.group(1).replace(",", ".")) == 0:
                return None
        except Exception:
            pass

    m = _RANGE_PHRASE_RE.match(value)
    if m:
        a, b = m.group(1), m.group(2)
        suffix = _suffix(unit, m.group(3), m.group(4))
        return _with_unit(f"от {_c(a)} до {_c(b)}", suffix)

    m = _DASH_RANGE_RE.match(value)
    if m:
        a, b = m.group(1), m.group(2)
        suffix = _suffix(unit, m.group(3), m.group(4))
        return _with_unit(f"от {_c(a)} до {_c(b)}", suffix)

    m = _DO_RE.match(value)
    if m:
        a = m.group(1)
        suffix = _suffix(unit, m.group(2), m.group(3))
        # force_not_less — "время работы до X" тоже "не менее X": побеждает
        # даже явное "до" в значении.
        word = "не менее" if direction == "force_not_less" else "не более"
        return _with_unit(f"{word} {_c(a)}", suffix)

    m = _OT_RE.match(value)
    if m:
        a = m.group(1)
        suffix = _suffix(unit, m.group(2), m.group(3))
        return _with_unit(f"не менее {_c(a)}", suffix)

    # Габариты (A х B х C) — допуск применяется ТОЛЬКО если имя не задаёт
    # точное/счётное направление (иначе "Разрешение: 3840 x 2160" получило
    # бы фиктивный допуск, хотя разрешение — EXACT).
    if direction == "range":
        composite = _try_composite(value, unit)
        if composite:
            return composite

    m = _SINGLE_RE.match(value)
    if m:
        num = m.group(1)
        suffix = _suffix(unit, m.group(2), m.group(3))
        if direction == "exact":
            return _with_unit(_c(num), suffix)
        if direction == "not_more":
            return _with_unit(f"не более {_c(num)}", suffix)
        if direction in ("not_less", "force_not_less"):
            return _with_unit(f"не менее {_c(num)}", suffix)
        bounds = _range_bounds(num)
        if bounds is None:
            return _with_unit(_c(num), suffix)
        low, high, decimals = bounds
        return _with_unit(f"от {_fmt_decimal(low, decimals)} до {_fmt_decimal(high, decimals)}", suffix)

    # "Грязное" значение (слова, несколько чисел во фразе, "x"/"-pin" и
    # т.п.) — переносим КАК ЕСТЬ, без допуска/направления.
    return value
