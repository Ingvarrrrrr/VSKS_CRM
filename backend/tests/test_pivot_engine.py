"""Smoke tests для pivot_engine — только чистые функции, без БД."""


def test_allowed_keys_contains_region():
    from app.services.field_registry import ALLOWED_KEYS
    assert 'region' in ALLOWED_KEYS
    assert 'purchase_id' in ALLOWED_KEYS


def test_allowed_aggs_complete():
    from app.services.field_registry import ALLOWED_AGGS
    for a in ['sum', 'avg', 'count', 'count_distinct', 'min', 'max']:
        assert a in ALLOWED_AGGS


def test_calc_columns_share():
    from app.services.calc_columns import apply_share_of_total
    rows = [{'sum_x': 100}, {'sum_x': 300}]
    apply_share_of_total(rows, 'sum_x')
    assert rows[0]['share_sum_x'] == 0.25
    assert rows[1]['share_sum_x'] == 0.75


def test_calc_columns_cumulative():
    from app.services.calc_columns import apply_cumulative_sum
    rows = [{'x': 10}, {'x': 20}, {'x': 30}]
    apply_cumulative_sum(rows, 'x')
    assert rows[0]['cumulative_x'] == 10
    assert rows[1]['cumulative_x'] == 30
    assert rows[2]['cumulative_x'] == 60


def test_calc_columns_delta():
    from app.services.calc_columns import apply_delta_to_plan
    rows = [{'actual': 80, 'plan': 100}, {'actual': 50, 'plan': 100}]
    apply_delta_to_plan(rows, 'actual', 'plan')
    assert rows[0]['delta_actual_vs_plan'] == 20
    assert rows[0]['pct_actual_vs_plan'] == 0.2
    assert rows[1]['delta_actual_vs_plan'] == 50


def test_build_filters_skips_unknown_keys():
    """Неизвестные ключи должны молча игнорироваться — защита от инъекций."""
    from app.services.field_registry import ALLOWED_KEYS
    unknown = 'DROP TABLE purchases; --'
    assert unknown not in ALLOWED_KEYS


def test_apply_calc_columns_dispatch():
    from app.services.calc_columns import apply_calc_columns
    rows = [{'sum_amount': 200}, {'sum_amount': 800}]
    apply_calc_columns(rows, [{'type': 'share', 'measure': 'sum_amount'}])
    assert rows[0]['share_sum_amount'] == 0.2
    assert rows[1]['share_sum_amount'] == 0.8
