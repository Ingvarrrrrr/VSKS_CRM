"""Composite + constant columns для list-режима отчётов (Phase 25-05).

Composite-колонки = template-строки с подстановкой {field_key} из row dict.
Constant-колонки = фиксированное значение (например "Россия").
Поддержка fallback'ов при пустых полях.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.services.field_registry import ALLOWED_KEYS


# Регулярка для подстановки: {field_key} или {field_key|format}
_PLACEHOLDER_RE = re.compile(r'\{([a-z_][a-z0-9_]*)(?:\|([a-z0-9_]+))?\}')

# Запрещённые ключи в шаблонах (защита) — кроме whitelist'а
_TEMPLATE_WHITELIST = ALLOWED_KEYS  # только зарегистрированные поля


def _format_value(value: Any, fmt: Optional[str] = None) -> str:
    """Форматирование значения по типу."""
    if value is None or value == '':
        return ''

    if isinstance(value, (date, datetime)):
        if fmt == 'dmy' or fmt is None:
            return value.strftime('%d.%m.%Y')
        if fmt == 'iso':
            return value.isoformat()
        if fmt == 'month':
            return value.strftime('%m.%Y')

    if isinstance(value, (Decimal, float)):
        if fmt == 'rub':
            return f'{float(value):,.2f} ₽'.replace(',', ' ')
        if fmt == 'thousands':
            return f'{float(value)/1000:,.2f}'.replace(',', ' ')
        if fmt == 'millions':
            return f'{float(value)/1_000_000:,.2f}'.replace(',', ' ')
        return f'{float(value):,.2f}'.replace(',', ' ')

    return str(value)


def render_composite(template: str, row: Dict[str, Any], fallback: str = '') -> str:
    """Подставляет {field_key} из row.

    template: "{contract_number} от {contract_date|dmy}"
    row: {'contract_number': 'РЕЕ-2026-00012', 'contract_date': date(2026, 3, 15)}
    fallback: применяется ЕСЛИ все плейсхолдеры пустые

    Returns: "РЕЕ-2026-00012 от 15.03.2026"
    """
    all_empty = True

    def _replace(match):
        nonlocal all_empty
        key = match.group(1)
        fmt = match.group(2)
        if key not in _TEMPLATE_WHITELIST:
            return ''  # silently strip unknown
        val = row.get(key)
        if val is not None and val != '':
            all_empty = False
        return _format_value(val, fmt)

    rendered = _PLACEHOLDER_RE.sub(_replace, template)

    if all_empty and fallback:
        return fallback
    return rendered.strip()


def apply_composite_columns(
    rows: List[Dict[str, Any]],
    column_specs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Применяет список колонок-шаблонов и констант к каждой строке.

    column_specs: [
        {key: 'contract_req', type: 'composite', template: '{contract_number} от {contract_date|dmy}', fallback: 'Нет данных'},
        {key: 'country', type: 'constant', value: 'Россия'},
        {key: 'planned_total_thousands', type: 'format', source: 'planned_total_price', format: 'thousands'},
    ]

    Кладёт результат в row[spec.key] на каждой строке.
    """
    for row in rows:
        for spec in column_specs:
            ckey = spec.get('key')
            ctype = spec.get('type')
            if not ckey:
                continue
            if ctype == 'composite':
                template = spec.get('template', '')
                fallback = spec.get('fallback', '')
                row[ckey] = render_composite(template, row, fallback)
            elif ctype == 'constant':
                row[ckey] = spec.get('value', '')
            elif ctype == 'format':
                # форматирование существующего поля
                src_key = spec.get('source')
                fmt = spec.get('format')
                if src_key and src_key in row:
                    row[ckey] = _format_value(row[src_key], fmt)
    return rows


def group_rows(
    rows: List[Dict[str, Any]],
    group_by: List[str],
    measures: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Группирует строки по group_by ключам, вставляя subtotal-строки и group-headers.

    Returns строки в порядке:
      [group_header, row1, row2, ..., subtotal, group_header2, ..., grand_total]

    Спец-строки помечены _row_type = 'group_header' | 'data' | 'subtotal' | 'grand_total'
    """
    if not group_by:
        for r in rows:
            r['_row_type'] = 'data'
        return rows

    measures = measures or []

    # Сортируем по group_by ключам
    def _sort_key(r):
        return tuple(str(r.get(k, '')) for k in group_by)

    sorted_rows = sorted(rows, key=_sort_key)

    result = []
    current_group_key = None
    group_buffer: List[Dict[str, Any]] = []

    def _flush_group():
        if not group_buffer:
            return
        # group_header
        header_row: Dict[str, Any] = {'_row_type': 'group_header'}
        for k in group_by:
            header_row[k] = group_buffer[0].get(k)
        result.append(header_row)
        # data
        for r in group_buffer:
            r['_row_type'] = 'data'
            result.append(r)
        # subtotal
        subtotal: Dict[str, Any] = {'_row_type': 'subtotal'}
        for k in group_by:
            subtotal[k] = group_buffer[0].get(k)
        for m in measures:
            try:
                subtotal[m] = sum(float(r.get(m) or 0) for r in group_buffer)
            except (TypeError, ValueError):
                subtotal[m] = 0
        result.append(subtotal)

    for r in sorted_rows:
        gk = _sort_key(r)
        if gk != current_group_key:
            _flush_group()
            group_buffer = [r]
            current_group_key = gk
        else:
            group_buffer.append(r)
    _flush_group()

    # grand_total
    if measures:
        gt: Dict[str, Any] = {'_row_type': 'grand_total'}
        for m in measures:
            try:
                gt[m] = sum(float(r.get(m) or 0) for r in rows)
            except (TypeError, ValueError):
                gt[m] = 0
        result.append(gt)

    return result
