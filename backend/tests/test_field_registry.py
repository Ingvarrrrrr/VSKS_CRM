def test_registry_has_minimum_fields():
    from app.services.field_registry import FIELDS, ALLOWED_KEYS, ALLOWED_AGGS
    assert len(FIELDS) >= 60
    assert 'purchase_id' in FIELDS
    assert 'region' in FIELDS  # Plan 25-01
    assert 'ordered_money' in FIELDS
    assert 'sum' in ALLOWED_AGGS


def test_all_fields_have_required_attrs():
    from app.services.field_registry import FIELDS
    for key, f in FIELDS.items():
        assert f.key == key
        assert f.label
        assert f.type in ('string', 'number', 'currency', 'date', 'datetime', 'boolean', 'enum')
        assert f.source in ('purchase', 'purchase_item', 'contractor', 'subsidy', 'feo_category', 'payment', 'bank_payment', 'event', 'computed')
        assert f.group
        if f.is_measure:
            assert f.agg_default, f'Measure {key} must have agg_default'
