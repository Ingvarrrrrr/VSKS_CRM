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

from app.services.field_registry import FIELDS


def _compiled_sql(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_pivot_sql_has_no_cartesian_product():
    """(а) Скомпилированный pivot-SQL не задваивает таблицы в FROM через запятую."""
    from sqlalchemy import and_
    from app.services.pivot_engine import (
        _base_query, _config_needs_optional_joins, _resolve_column, _apply_agg,
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
    needed_joins = _config_needs_optional_joins(
        config['rows'], config['cols'], [], [], measure_fields, list(config['filters'].keys()),
    )
    assert 'contract_item' in needed_joins  # contract_item_name в cols требует JOIN

    base, feo_l1, feo_l2, feo_l3 = _base_query(needed_joins=needed_joins)
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
    from app.services.pivot_engine import _base_query, _config_needs_optional_joins

    needed_joins = _config_needs_optional_joins(
        ['feo_category_id'], ['subsidy_id'], [], [], ['planned_quantity'], ['subsidy_id', 'status'],
    )
    assert needed_joins == frozenset()

    base, *_ = _base_query(needed_joins=needed_joins)
    sql = _compiled_sql(base)
    assert 'contract_items' not in sql
    assert 'events' not in sql
    assert 'bank_payments' not in sql


def test_pivot_sql_joins_events_and_bank_payments_only_when_needed():
    """events/bank_payments — тот же класс бага, что contract_items (23.10.2026):
    _base_query() их не джойнила вообще, поле из этих источников в конфиге давало
    декартово произведение (SAWarning 'cartesian product', см. test_field_as_pivot_
    dimension_no_exception ниже — там же оно теперь падает ошибкой, не предупреждением).
    JOIN строится по реальной связи: Purchase.event_id → Event.id (N:1),
    BankPayment.matched_purchase_id → Purchase.id (1:N, тот же риск умножения что у
    contract_items)."""
    from app.services.pivot_engine import _base_query, _config_needs_optional_joins

    needed_joins = _config_needs_optional_joins(['event_name'], ['bank_payment_number'], [], [], [], [])
    assert needed_joins == frozenset({'event', 'bank_payment'})

    base, *_ = _base_query(needed_joins=needed_joins)
    sql = _compiled_sql(base)
    assert 'LEFT OUTER JOIN events ON purchases.event_id = events.id' in sql
    assert 'LEFT OUTER JOIN bank_payments ON bank_payments.matched_purchase_id = purchases.id' in sql

    # Без полей event/bank_payment в конфиге — ни одна из таблиц не попадает в FROM.
    needed_joins_empty = _config_needs_optional_joins(['subsidy_id'], [], [], [], [], [])
    base_empty, *_ = _base_query(needed_joins=needed_joins_empty)
    sql_empty = _compiled_sql(base_empty)
    assert 'events' not in sql_empty
    assert 'bank_payments' not in sql_empty


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


# ---------------------------------------------------------------------------
# Регрессия на баг «500 NotImplementedError при мере на сложном выражении»
# (прод, 23.10.2026): _resolve_column() заворачивала CASE/EXTRACT/to_char/
# COALESCE(...)-поля в text(expr); TextClause не реализует .label(), на
# котором падал _execute_pivot (sqlalchemy/sql/roles.py:177). Фикс —
# literal_column(expr) вместо text(expr) (см. docstring _resolve_column).
#
# Тест параметризован по ВСЕМ полям field_registry.FIELDS на реальной БД:
# каждое измерение — pivot rows=[key], каждая мера — pivot measures=[{key,
# agg: agg_default}], плюс list-режим columns=[key]. Раньше падали с
# NotImplementedError ВСЕ поля с CASE/EXTRACT/to_char/COALESCE в sql_expr:
# ordered_money, delivered_money, paid_money, goods_amount, services_amount,
# wishes_unconfirmed_sum, confirmed_sum, quarter_of_obligation,
# year_of_obligation, month_of_obligation, quarter_of_payment,
# year_of_payment, month_of_payment, feo_planned_quantity, feo_planned_amount
# (COALESCE с подзапросом) — все остальные (простые "table.column") уже
# работали и в тест включены для регрессии при добавлении новых полей.
# ---------------------------------------------------------------------------

import pytest_asyncio


@pytest_asyncio.fixture
async def pivot_all_fields_seed(db_session, test_org):
    """Один связный набор данных, покрывающий все источники field_registry.FIELDS:
    purchase + contractor + subsidy + feo_category (3 уровня) + event +
    contract_item + bank_payment. Возвращает (user, purchase)."""
    import uuid
    from datetime import date
    from app.models.subsidy import Subsidy
    from app.models.contractor import Contractor
    from app.models.feo_category import FeoCategory
    from app.models.event import Event
    from app.models.purchase import Purchase
    from app.models.contract_item import ContractItem
    from app.models.bank_statement import BankPayment
    from app.models.user import User
    from app.auth.jwt import hash_password

    subsidy = Subsidy(
        name=f"Pivot fields subsidy {uuid.uuid4().hex[:6]}",
        org_id=test_org.id, year=2026,
        basis_doc_number="SOG-1", basis_doc_date=date(2026, 1, 1),
    )
    contractor = Contractor(
        name="Pivot Contractor", full_name="ООО Pivot Contractor",
        inn="7700000000", kpp="770001001", address="г. Тест",
        org_type="Юр.лицо", bank_name="Тестбанк",
        settlement_account="40702810000000000001", bik="044525225",
        correspondent_account="30101810000000000001", org_id=test_org.id,
    )
    db_session.add_all([subsidy, contractor])
    await db_session.flush()

    feo_l1 = FeoCategory(subsidy_id=subsidy.id, level=1, name="Направление 1")
    db_session.add(feo_l1)
    await db_session.flush()
    feo_l2 = FeoCategory(subsidy_id=subsidy.id, level=2, name="Тип расходов 1", parent_id=feo_l1.id)
    db_session.add(feo_l2)
    await db_session.flush()
    feo_l3 = FeoCategory(
        subsidy_id=subsidy.id, level=3, name="Направление приложения 1",
        parent_id=feo_l2.id, appendix="Прил. 1",
        planned_quantity=5, planned_amount=100,
    )
    db_session.add(feo_l3)
    await db_session.flush()

    event = Event(subsidy_id=subsidy.id, name="Pivot Event", region="Тверская область", org_id=test_org.id)
    db_session.add(event)
    await db_session.flush()

    purchase = Purchase(
        purchase_number=1, order_number="ORD-1", registry_number="REG-1",
        subject="Предмет", item_name="Товар теста", item_type="Товары",
        description_mode="exact",
        contractor_id=contractor.id, subsidy_id=subsidy.id,
        feo_category_id=feo_l3.id, event_id=event.id,
        contract_number="K-1", contract_date=date(2026, 1, 5), contract_end_date=date(2026, 12, 31),
        purchase_contract_type="single",
        planned_quantity=5, unit="шт", planned_unit_price=100, planned_total_price=500,
        final_unit_price=100, final_total_amount=500, contract_price=500, nmck=500,
        economy=0, delivery_payment_amount=500, acceptance_doc_amount=500, payment_amount=500,
        status="paid", substatus="done", confirmed=True, is_likely_needed=True, is_prepayment=False,
        approval_status="approved",
        region="Тверская область",
        execution_term=date(2026, 2, 1), delivery_date=date(2026, 2, 1),
        service_start_date=date(2026, 1, 1), service_end_date=date(2026, 1, 31),
        service_deadline_date=date(2026, 1, 31), submission_deadline=None,
        procurement_planned_date=date(2026, 1, 1), prepayment_date=date(2026, 1, 1),
        acceptance_doc_date=date(2026, 2, 1), acceptance_doc_number="ACT-1", acceptance_doc_name="Акт",
        payment_doc_number="PP-1", payment_doc_date=date(2026, 2, 5),
        delivery_location="г. Тест", delivery_address="г. Тест, ул. Тестовая, 1",
        country_origin="Россия", purchase_method="single",
        vat_applicable=True, vat_rate=20, third_party_involved=False,
        treasury_code="TR-1",
    )
    db_session.add(purchase)
    await db_session.flush()

    contract_item = ContractItem(
        purchase_id=purchase.id, name="Позиция договора 1",
        quantity=5, unit="шт", unit_price=100, total=500,
    )
    db_session.add(contract_item)

    bank_payment = BankPayment(
        payment_number="BP-1", payment_date=date(2026, 2, 5),
        purpose_text="Оплата по договору K-1",
        parsed_kbk="KBK-1",
        matched_purchase_id=purchase.id,  # JOIN bank_payments в _base_query идёт по этому полю
        matched_subsidy_id=subsidy.id, subsidy_id=subsidy.id, org_id=test_org.id,
    )
    db_session.add(bank_payment)
    await db_session.commit()

    user = User(
        username=f"pivot_fields_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("testpass123"),
        role="superadmin", org_id=test_org.id, full_name="Pivot Fields User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user, purchase


def _agg_for_measure(f):
    if f.type in ('string', 'enum', 'boolean'):
        return 'count'
    return f.agg_default or 'sum'


@pytest.mark.asyncio
# Баг 23.10.2026 (прод висел >60с от декартова произведения, тот же класс
# вернулся для events/bank_payments — см. _config_needs_optional_joins): любой
# SAWarning "cartesian product" от SQLAlchemy при выполнении этих запросов —
# ошибка теста, не тихое предупреждение в логе. Защита от регресса класса.
@pytest.mark.filterwarnings("error:.*cartesian product.*:sqlalchemy.exc.SAWarning")
@pytest.mark.parametrize("key", sorted(FIELDS.keys()))
async def test_field_as_pivot_dimension_no_exception(key, db_session, pivot_all_fields_seed):
    """Каждое is_dimension-поле — pivot rows=[key] с простой мерой выполняется без исключения."""
    from app.services.field_registry import get_field
    from app.services.pivot_engine import execute_query

    f = get_field(key)
    if not f.is_dimension:
        pytest.skip(f"{key}: не измерение")
    user, _ = pivot_all_fields_seed

    config = {
        'kind': 'pivot',
        'rows': [key],
        'cols': [],
        'measures': [{'field': 'planned_quantity', 'agg': 'sum'}],
        'filters': {},
        'limit': 100,
    }
    result = await execute_query(config, user, db_session)
    assert result['kind'] == 'pivot'


@pytest.mark.asyncio
@pytest.mark.filterwarnings("error:.*cartesian product.*:sqlalchemy.exc.SAWarning")
@pytest.mark.parametrize("key", sorted(FIELDS.keys()))
async def test_field_as_pivot_measure_no_exception(key, db_session, pivot_all_fields_seed):
    """Каждое is_measure-поле — pivot measures=[{field: key, agg}] по subsidy_id без исключения."""
    from app.services.field_registry import get_field
    from app.services.pivot_engine import execute_query

    f = get_field(key)
    if not f.is_measure:
        pytest.skip(f"{key}: не мера")
    user, _ = pivot_all_fields_seed

    config = {
        'kind': 'pivot',
        'rows': ['subsidy_id'],
        'cols': [],
        'measures': [{'field': key, 'agg': _agg_for_measure(f)}],
        'filters': {},
        'limit': 100,
    }
    result = await execute_query(config, user, db_session)
    assert result['kind'] == 'pivot'


@pytest.mark.asyncio
@pytest.mark.filterwarnings("error:.*cartesian product.*:sqlalchemy.exc.SAWarning")
@pytest.mark.parametrize("key", sorted(FIELDS.keys()))
async def test_field_as_list_column_no_exception(key, db_session, pivot_all_fields_seed):
    """Каждое поле в list-режиме columns=[key] выполняется без исключения (значение может быть None
    для полей, которые _extract_value пока не умеет доставать из ORM-объектов — см. её докстринг)."""
    from app.services.pivot_engine import execute_query

    user, _ = pivot_all_fields_seed

    config = {
        'kind': 'list',
        'columns': [key],
        'filters': {},
        'limit': 10,
    }
    result = await execute_query(config, user, db_session)
    assert result['kind'] == 'list'


@pytest.mark.asyncio
@pytest.mark.filterwarnings("error:.*cartesian product.*:sqlalchemy.exc.SAWarning")
@pytest.mark.parametrize("key", sorted(FIELDS.keys()))
async def test_field_in_list_mode_as_cols_dimension_no_exception(key, db_session, pivot_all_fields_seed):
    """List-режим columns=[key] — отдельный тест для режима 'list' на использование поля как
    dimension в cols (covers covers filter path via _build_filters indirectly through order_by)."""
    from app.services.field_registry import get_field
    from app.services.pivot_engine import execute_query

    f = get_field(key)
    if not f.is_dimension:
        pytest.skip(f"{key}: не измерение")
    user, _ = pivot_all_fields_seed

    config = {
        'kind': 'pivot',
        'rows': [],
        'cols': [key],
        'measures': [{'field': 'planned_quantity', 'agg': 'sum'}],
        'filters': {},
        'limit': 100,
    }
    result = await execute_query(config, user, db_session)
    assert result['kind'] == 'pivot'
