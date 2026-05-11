from datetime import date
from decimal import Decimal


def test_render_composite_basic():
    from app.services.composite_columns import render_composite
    template = '{contract_number} от {contract_date|dmy}'
    row = {'contract_number': 'РЕЕ-12', 'contract_date': date(2026, 3, 15)}
    assert render_composite(template, row) == 'РЕЕ-12 от 15.03.2026'


def test_render_composite_fallback_when_all_empty():
    from app.services.composite_columns import render_composite
    template = '{payment_doc_number} от {payment_doc_date}'
    row = {'payment_doc_number': None, 'payment_doc_date': None}
    assert render_composite(template, row, fallback='Платёж не проходил') == 'Платёж не проходил'


def test_render_composite_partial_empty():
    from app.services.composite_columns import render_composite
    row = {'contract_number': 'РЕЕ-12', 'contract_date': None}
    result = render_composite('{contract_number} от {contract_date}', row, fallback='Нет данных')
    # Хотя бы одно поле не пустое — fallback НЕ применяется
    assert 'РЕЕ-12' in result
    assert result != 'Нет данных'


def test_render_composite_whitelist_protection():
    from app.services.composite_columns import render_composite
    # Поле не в whitelist'е — silently strip
    template = '{password} безопасно'
    row = {'password': 'secret'}
    assert 'secret' not in render_composite(template, row)


def test_format_thousands():
    from app.services.composite_columns import _format_value
    assert _format_value(Decimal('1500000'), 'thousands') == '1 500.00'


def test_apply_composite_columns():
    from app.services.composite_columns import apply_composite_columns
    rows = [
        {'contract_number': 'A-1', 'contract_date': date(2026, 1, 1)},
        {'contract_number': None, 'contract_date': None},
    ]
    specs = [
        {'key': 'req', 'type': 'composite', 'template': '{contract_number} от {contract_date|dmy}', 'fallback': 'Нет'},
        {'key': 'country', 'type': 'constant', 'value': 'Россия'},
    ]
    apply_composite_columns(rows, specs)
    assert rows[0]['req'] == 'A-1 от 01.01.2026'
    assert rows[0]['country'] == 'Россия'
    assert rows[1]['req'] == 'Нет'


def test_group_rows_with_subtotals():
    from app.services.composite_columns import group_rows
    rows = [
        {'event_name': 'Слёт', 'amount': 100},
        {'event_name': 'Слёт', 'amount': 200},
        {'event_name': 'Форум', 'amount': 500},
    ]
    result = group_rows(rows, group_by=['event_name'], measures=['amount'])
    types = [r.get('_row_type') for r in result]
    # group_header, data, data, subtotal, group_header, data, subtotal, grand_total
    assert types == ['group_header', 'data', 'data', 'subtotal', 'group_header', 'data', 'subtotal', 'grand_total']
    # Subtotal первой группы = 300
    subtotal_first = [r for r in result if r.get('_row_type') == 'subtotal'][0]
    assert subtotal_first['amount'] == 300
    # Grand total = 800
    gt = [r for r in result if r.get('_row_type') == 'grand_total'][0]
    assert gt['amount'] == 800
