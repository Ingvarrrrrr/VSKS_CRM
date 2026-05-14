"""Phase 27.1 D-15: contract_savings post-processing calc-column."""
import pytest
from app.services.calc_columns import apply_contract_savings, apply_calc_columns


def test_contract_savings_formula():
    rows = [{'planned_total_price': 1000, 'contracted_total': 800}]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] == 200.0


def test_contract_savings_negative():
    rows = [{'planned_total_price': 500, 'contracted_total': 600}]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] == -100.0


def test_contract_savings_handles_none_planned():
    rows = [{'planned_total_price': None, 'contracted_total': 500}]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] is None


def test_contract_savings_handles_none_contracted():
    rows = [{'planned_total_price': 1000, 'contracted_total': None}]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] is None


def test_contract_savings_handles_string_input():
    # Numbers могут приходить как Decimal или string из SQL
    rows = [{'planned_total_price': '1000.50', 'contracted_total': '800.25'}]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] == pytest.approx(200.25)


def test_contract_savings_custom_keys():
    rows = [{'plan_amt': 900, 'contract_amt': 750}]
    result = apply_contract_savings(
        rows,
        planned_key='plan_amt',
        contracted_key='contract_amt',
        output_key='savings',
    )
    assert result[0]['savings'] == 150.0


def test_apply_calc_columns_contract_savings_dispatch():
    """Проверяет dispatch через apply_calc_columns."""
    rows = [{'planned_total_price': 500, 'contracted_total': 400}]
    apply_calc_columns(rows, [{'type': 'contract_savings'}])
    assert rows[0]['contract_savings'] == 100.0


def test_contract_savings_multiple_rows():
    rows = [
        {'planned_total_price': 1000, 'contracted_total': 900},
        {'planned_total_price': 2000, 'contracted_total': 1800},
        {'planned_total_price': None, 'contracted_total': 500},
    ]
    result = apply_contract_savings(rows)
    assert result[0]['contract_savings'] == 100.0
    assert result[1]['contract_savings'] == 200.0
    assert result[2]['contract_savings'] is None
