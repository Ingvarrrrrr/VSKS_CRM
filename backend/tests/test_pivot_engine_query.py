"""Регрессия на баг «конструктор сводных висит >60с и даёт неверные суммы» (23.10.2026).

Причина была в pivot_engine._execute_pivot: select(*select_cols).select_from(base.subquery())
собирал колонки из ИСХОДНЫХ таблиц, а не из подзапроса — Postgres добавлял все join'нутые
таблицы ЕЩЁ РАЗ через запятую в FROM (декартово произведение без фильтров) => REQUEST_TIMEOUT
и неверные суммы. Плюс: LEFT JOIN contract_items размножал строки (1 закупка → N позиций
договора), поэтому SUM(planned_quantity) без полей contract_items в конфиге задваивался.

Тест (а) не требует БД — компилирует SQL и проверяет, что в FROM нет декартова произведения.
Тест (б) поднимает БД (через db_session фикстуру из conftest.py, откатывается после теста) и
проверяет реальную сумму/фильтр на минимальном наборе данных.
"""
import pytest


def _compiled_sql(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_pivot_sql_has_no_cartesian_product():
    """(а) Скомпилированный pivot-SQL не задваивает таблицы в FROM через запятую."""
    from sqlalchemy import and_
    from app.services.pivot_engine import (
        _base_query, _config_needs_contract_items, _resolve_column, _apply_agg,
        _build_filters,
    )
    from app.services.field_registry import get_field

    config = {
        'rows': ['feo_category_id'],
        'cols': ['subsidy_id', 'contract_item_name'],
        'measures': [{'field': 'planned_quantity', 'agg': 'sum'}],
        'filters': {'subsidy_id': [1, 2, 3], 'status': ['work_in_progress']},
    }
    measure_fields = [m['field'] for m in config['measures']]
    needs_ci = _config_needs_contract_items(
        config['rows'], config['cols'], [], [], measure_fields, list(config['filters'].keys()),
    )
    assert needs_ci is True  # contract_item_name в cols требует JOIN

    base, feo_l1, feo_l2, feo_l3 = _base_query(include_contract_items=needs_ci)
    where = _build_filters(config['filters'], feo_l1, feo_l2, feo_l3)
    base = base.where(and_(*where))

    all_dims = config['rows'] + config['cols']
    select_cols = []
    for key in all_dims:
        f = get_field(key)
        select_cols.append(_resolve_column(f, feo_l1, feo_l2, feo_l3).label(key))
    for m in config['measures']:
        f = get_field(m['field'])
        col = _resolve_column(f, feo_l1, feo_l2, feo_l3)
        select_cols.append(_apply_agg(col, m['agg']).label(f"sum_{m['field']}"))

    pivot_q = base.with_only_columns(*select_cols)
    group_exprs = [_resolve_column(get_field(k), feo_l1, feo_l2, feo_l3) for k in all_dims]
    pivot_q = pivot_q.group_by(*group_exprs).limit(5000)

    sql = _compiled_sql(pivot_q)

    # Декартово произведение выглядит как ", table_name" внутри FROM — тех таблиц,
    # которые уже есть в JOIN-цепочке базового запроса. Берём ТОЛЬКО сам FROM-клоз
    # (до WHERE/GROUP BY/LIMIT) — иначе ", subsidies.id" из GROUP BY ложно совпадает
    # с паттерном ", subsidies".
    from_clause = sql.split('FROM', 1)[1]
    for stopper in (' WHERE ', ' GROUP BY ', ' LIMIT '):
        from_clause = from_clause.split(stopper, 1)[0]
    assert ' AS anon_1' not in from_clause, "pivot-запрос всё ещё обёрнут в лишний подзапрос"
    for table in ('purchases', 'subsidies', 'feo_categories', 'contract_items'):
        assert f', {table}' not in from_clause, (
            f"таблица {table} задвоена в FROM через запятую — декартово произведение вернулось"
        )
    assert 'WHERE' in sql and 'GROUP BY' in sql


def test_pivot_sql_skips_contract_items_join_when_not_needed():
    """Без полей contract_item в конфиге JOIN contract_items не должен попадать в FROM —
    иначе SUM(planned_quantity) задваивается на число позиций договора."""
    from app.services.pivot_engine import _base_query, _config_needs_contract_items

    needs_ci = _config_needs_contract_items(
        ['feo_category_id'], ['subsidy_id'], [], [], ['planned_quantity'], ['subsidy_id', 'status'],
    )
    assert needs_ci is False

    base, *_ = _base_query(include_contract_items=needs_ci)
    sql = _compiled_sql(base)
    assert 'contract_items' not in sql


@pytest.mark.asyncio
async def test_pivot_sum_not_multiplied_by_contract_items(db_session, test_org):
    """(б) На реальной БД: субсидия с одной закупкой planned_quantity=5 и ДВУМЯ позициями
    договора — pivot по subsidy_id без полей contract_items должен дать 5, не 10. Фильтр
    по чужой subsidy_id должен отсечь закупку другой субсидии."""
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase
    from app.models.contract_item import ContractItem
    from app.models.user import User
    from app.auth.jwt import hash_password
    from app.services.pivot_engine import execute_query
    import uuid

    subsidy = Subsidy(name=f"Test subsidy {uuid.uuid4().hex[:6]}", org_id=test_org.id, year=2026)
    other_subsidy = Subsidy(name=f"Other subsidy {uuid.uuid4().hex[:6]}", org_id=test_org.id, year=2026)
    db_session.add_all([subsidy, other_subsidy])
    await db_session.flush()

    purchase = Purchase(
        status="work_in_progress",
        item_type="goods",
        item_name="Test purchase",
        subsidy_id=subsidy.id,
        planned_quantity=5,
    )
    other_purchase = Purchase(
        status="work_in_progress",
        item_type="goods",
        item_name="Other org purchase",
        subsidy_id=other_subsidy.id,
        planned_quantity=99,
    )
    db_session.add_all([purchase, other_purchase])
    await db_session.flush()

    db_session.add_all([
        ContractItem(purchase_id=purchase.id, name="Позиция 1", quantity=1, total=1),
        ContractItem(purchase_id=purchase.id, name="Позиция 2", quantity=1, total=1),
    ])
    await db_session.commit()

    user = User(
        username=f"pivot_test_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("testpass123"),
        role="superadmin",
        org_id=test_org.id,
        full_name="Pivot Test User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    config = {
        'kind': 'pivot',
        'rows': ['subsidy_id'],
        'cols': [],
        'measures': [{'field': 'planned_quantity', 'agg': 'sum'}],
        'filters': {'subsidy_id': [subsidy.id]},
    }
    result = await execute_query(config, user, db_session)

    assert result['rows_count'] == 1
    row = result['rows'][0]
    assert row['subsidy_id'] == subsidy.id
    # Баг: было 10 (5 × 2 позиции договора) из-за JOIN contract_items без
    # контроля размножения строк.
    assert float(row['sum_planned_quantity']) == 5.0

    # Фильтр по чужой subsidy_id отсекает закупку другой субсидии.
    other_config = dict(config, filters={'subsidy_id': [other_subsidy.id]})
    other_result = await execute_query(other_config, user, db_session)
    assert other_result['rows_count'] == 1
    assert float(other_result['rows'][0]['sum_planned_quantity']) == 99.0
    assert other_result['rows'][0]['subsidy_id'] == other_subsidy.id
