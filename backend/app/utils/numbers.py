"""Числовые парсеры, общие для нескольких роутеров (Правило №6).

Единственное место, где строка из Excel/PDF/HTML превращается в Decimal —
раньше почти в каждом импортёре (`purchase_items_import*.py`,
`items_import_parsing.py`, ...) жила своя копия-регулярка вида
`s.replace(',', '.')`, которая заменяла запятую на точку ДО разбора и тем
самым портила числа с точкой-разделителем тысяч: "499.950,00" превращалось в
"499.950.00", откуда бралось только "499.950" → Decimal("499.95") вместо
верных 499950 (боевой дефект, позиция закупки id=3166, 2026-09-14).
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

_LEADING_NUMBER_RE = re.compile(r'^-?[0-9]+(?:\.[0-9]+)?')
_EMPTY_TOKENS = {'-', '—', '–', 'none', 'null', 'nan', ''}


def to_decimal_ambiguous(v) -> tuple[Optional[Decimal], bool]:
    """Разобрать число из ячейки импорта, определяя формат по ВЗАИМНОМУ
    расположению точки и запятой, а не заменяя запятую на точку "в лоб".

    Правило распознавания (Правило №6 — один источник для всех импортёров):
      - точка И запятая одновременно → десятичный разделитель — тот из них,
        что стоит ПРАВЕЕ по строке; второй символ — разделитель разрядов
        (групп), убирается целиком. "499.950,00" → запятая правее → точка
        это тысячи → 499950.00. "1.234.567,89" → 1234567.89.
      - один и тот же символ встречается НЕСКОЛЬКО раз (без второго
        символа) → он не может быть десятичным разделителем (дробная часть
        ровно одна) → это разделители разрядов, убираются целиком.
      - только запятая (один раз) → десятичный разделитель (русская
        запись: "499,95" → 499.95).
      - только точка (один раз):
          - ровно 3 цифры после точки — НЕОДНОЗНАЧНО: "1.500" может быть и
            1500 (разделитель тысяч), и полтора (1.5 с лишним нулём). В
            русских выгрузках это почти всегда разделитель тысяч (в рублях
            копейки — это 2 знака, не 3), поэтому разбираем как тысячи, но
            возвращаем ambiguous=True — вызывающий код (предпросмотр
            импорта) обязан показать это пользователю, а не молча
            довериться эвристике на дорогой ошибке.
          - иначе (1-2 или 4+ цифр после точки) — обычный десятичный
            разделитель, не неоднозначно.

    Возвращает (значение, ambiguous). ambiguous=True только для описанного
    выше случая «единственная точка + ровно 3 цифры после неё».
    """
    if v is None:
        return None, False
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v)), False
        except (InvalidOperation, ValueError):
            return None, False

    s = str(v).strip().replace(' ', '').replace('\xa0', '')
    if s.lower() in _EMPTY_TOKENS:
        return None, False

    dot_count = s.count('.')
    comma_count = s.count(',')
    ambiguous = False

    if dot_count and comma_count:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif comma_count:
        s = s.replace(',', '') if comma_count > 1 else s.replace(',', '.')
    elif dot_count:
        if dot_count > 1:
            s = s.replace('.', '')
        elif len(s.split('.')[-1]) == 3:
            ambiguous = True
            s = s.replace('.', '')
        # иначе точка остаётся десятичным разделителем как есть

    try:
        return Decimal(s), ambiguous
    except (InvalidOperation, ValueError):
        m = _LEADING_NUMBER_RE.match(s)
        if not m:
            return None, ambiguous
        try:
            return Decimal(m.group(0)), ambiguous
        except (InvalidOperation, ValueError):
            return None, ambiguous


def to_decimal(v) -> Optional[Decimal]:
    value, _ambiguous = to_decimal_ambiguous(v)
    return value
