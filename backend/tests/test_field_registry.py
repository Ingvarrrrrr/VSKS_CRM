def test_registry_has_minimum_fields():
    from app.services.field_registry import FIELDS, ALLOWED_KEYS, ALLOWED_AGGS
    assert len(FIELDS) >= 60
    assert 'purchase_id' in FIELDS
    assert 'region' in FIELDS  # Plan 25-01
    assert 'ordered_money' in FIELDS
    assert 'sum' in ALLOWED_AGGS


_VALID_SOURCES = (
    'purchase', 'purchase_item', 'contract_item', 'contractor', 'subsidy',
    'feo_category', 'payment', 'bank_payment', 'event', 'computed',
)


def test_all_fields_have_required_attrs():
    from app.services.field_registry import FIELDS
    for key, f in FIELDS.items():
        assert f.key == key
        assert f.label
        assert f.type in ('string', 'number', 'currency', 'date', 'datetime', 'boolean', 'enum')
        assert f.source in _VALID_SOURCES, f'Field {key} has unknown source: {f.source}'
        assert f.group
        if f.is_measure:
            assert f.agg_default, f'Measure {key} must have agg_default'


# === Phase 27.1 D-12: contract_item source tests ===

def test_contract_items_source_registered():
    from typing import get_args
    from app.services.field_registry import FieldSource
    sources = get_args(FieldSource)
    assert 'contract_item' in sources


def test_contract_fields_in_registry():
    from app.services.field_registry import FIELDS
    expected_keys = {
        'contracted_qty', 'contracted_total', 'contract_item_unit_price',
        'contract_item_name', 'contract_item_unit',
    }
    actual = set(FIELDS.keys())
    missing = expected_keys - actual
    assert not missing, f"Missing fields in registry: {missing}"


def test_contracted_total_is_measure():
    from app.services.field_registry import FIELDS
    f = FIELDS['contracted_total']
    assert f.is_measure is True
    assert f.agg_default == 'sum'
    assert f.source == 'contract_item'
    assert f.sql_expr == 'contract_items.total'


def test_contract_item_name_is_dimension():
    from app.services.field_registry import FIELDS
    f = FIELDS['contract_item_name']
    assert f.is_dimension is True
    assert f.source == 'contract_item'


def test_pivot_table_prefix_map_contains_contract_items():
    from app.services.pivot_engine import _TABLE_PREFIX_MAP
    from app.models.contract_item import ContractItem
    assert 'contract_items' in _TABLE_PREFIX_MAP
    assert _TABLE_PREFIX_MAP['contract_items'] is ContractItem
