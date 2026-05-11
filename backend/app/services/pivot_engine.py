"""Pivot/list query engine для UI-конфигуратора отчётов (Phase 25).

Принимает декларативный конфиг, генерирует безопасный SQL через SQLAlchemy core.
Whitelist полей и aggs из field_registry — защита от SQL-инъекций.
"""

from typing import Any, Optional, List, Dict
from sqlalchemy import select, func, and_, literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy import text

from app.services.field_registry import (
    FIELDS, ALLOWED_KEYS, ALLOWED_AGGS, FieldDef, get_field,
)
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.bank_statement import BankPayment
from app.models.user import User
from app.auth.jwt import get_org_filter

try:
    from app.models.event import Event as _Event
    _EVENT_MODEL = _Event
except ImportError:
    _EVENT_MODEL = None

_TABLE_PREFIX_MAP: Dict[str, Any] = {
    'purchases': Purchase,
    'contractors': Contractor,
    'subsidies': Subsidy,
    'feo_categories': FeoCategory,
    'bank_payments': BankPayment,
    'events': _EVENT_MODEL,
}


# === Базовые JOINs ===

def _base_query():
    """Базовый select из purchases + LEFT JOIN всех связанных таблиц."""
    from sqlalchemy.orm import aliased
    feo_l1 = aliased(FeoCategory, name='feo_l1')
    feo_l2 = aliased(FeoCategory, name='feo_l2')
    feo_l3 = aliased(FeoCategory, name='feo_l3')

    q = (
        select(Purchase, Contractor, Subsidy, FeoCategory, feo_l1, feo_l2, feo_l3)
        .select_from(Purchase)
        .outerjoin(Contractor, Purchase.contractor_id == Contractor.id)
        .outerjoin(Subsidy, Purchase.subsidy_id == Subsidy.id)
        .outerjoin(FeoCategory, Purchase.feo_category_id == FeoCategory.id)
        .outerjoin(feo_l3, and_(FeoCategory.level == 3, feo_l3.id == FeoCategory.id))
        .outerjoin(feo_l2, and_(feo_l3.parent_id == feo_l2.id, feo_l2.level == 2))
        .outerjoin(feo_l1, and_(feo_l2.parent_id == feo_l1.id, feo_l1.level == 1))
    )
    return q, feo_l1, feo_l2, feo_l3


# === Field accessor ===

def _resolve_column(field: FieldDef, feo_l1, feo_l2, feo_l3) -> ColumnElement:
    """Превращает FieldDef.sql_expr в SQLAlchemy column expression.

    Поддерживает 3 случая:
    1. "purchases.column_name" → Purchase.column_name
    2. "feo_l1.name" → aliased FeoCategory column
    3. CASE WHEN/EXTRACT/to_char/etc — raw text() как fallback
    """
    expr = field.sql_expr.strip()

    if '.' in expr and ' ' not in expr and 'CASE' not in expr.upper():
        parts = expr.split('.', 1)
        if len(parts) == 2:
            table_name, col_name = parts
            if table_name == 'feo_l1':
                return getattr(feo_l1, col_name)
            if table_name == 'feo_l2':
                return getattr(feo_l2, col_name)
            if table_name == 'feo_l3':
                return getattr(feo_l3, col_name)
            model = _TABLE_PREFIX_MAP.get(table_name)
            if model is not None:
                col = getattr(model, col_name, None)
                if col is not None:
                    return col

    # Сложные случаи (CASE/EXTRACT/to_char) — text()
    return text(expr)


def _apply_agg(col_expr, agg: str):
    if agg == 'sum':
        return func.sum(col_expr)
    if agg == 'avg':
        return func.avg(col_expr)
    if agg == 'count':
        return func.count(col_expr)
    if agg == 'count_distinct':
        return func.count(func.distinct(col_expr))
    if agg == 'min':
        return func.min(col_expr)
    if agg == 'max':
        return func.max(col_expr)
    if agg == 'first':
        return func.min(col_expr)  # fallback — нет PG ANY_VALUE без extension
    raise ValueError(f'Unknown agg: {agg}')


# === Org filter (multi-tenancy) ===

def _apply_org_filter(query, user: User):
    """Возвращает query с фильтром по организациям пользователя.

    Использует get_org_filter из app.auth.jwt — тот же паттерн что в dashboard.py.
    Superadmin без выбранных org_ids → без фильтра.
    """
    org_ids = get_org_filter(user)
    if org_ids is None:
        return query  # superadmin без фильтра
    if not org_ids:
        return query.where(literal(False))
    return query.where(Subsidy.org_id.in_(org_ids))


# === Filters builder ===

def _build_filters(filters: Dict[str, Any], feo_l1, feo_l2, feo_l3) -> List[ColumnElement]:
    """Принимает {field_key: value | [value]} → список WHERE clauses.

    Поддерживает:
    - простые: {'subsidy_id': 7} → eq
    - множественные: {'status': ['confirmed', 'paid']} → IN
    - диапазон даты: {'contract_date': {'from': '2026-01-01', 'to': '2026-06-30'}}
    - search: {'item_name': {'contains': 'Ростел'}}
    - boolean: {'confirmed': True}
    """
    where_clauses = []
    for key, value in filters.items():
        if key not in ALLOWED_KEYS:
            continue  # silently skip unknown — защита от инъекций
        field = get_field(key)
        if field is None:
            continue
        col = _resolve_column(field, feo_l1, feo_l2, feo_l3)
        if isinstance(value, dict):
            if 'from' in value and value['from']:
                where_clauses.append(col >= value['from'])
            if 'to' in value and value['to']:
                where_clauses.append(col <= value['to'])
            if 'contains' in value and value['contains']:
                where_clauses.append(col.ilike(f'%{value["contains"]}%'))
        elif isinstance(value, list):
            if value:
                where_clauses.append(col.in_(value))
        elif value is None:
            where_clauses.append(col.is_(None))
        else:
            where_clauses.append(col == value)
    return where_clauses


# === Public API ===

async def execute_query(
    config: Dict[str, Any],
    user: User,
    db: AsyncSession,
) -> Dict[str, Any]:
    """Главный entry-point. Возвращает {rows, totals, rows_count}.

    config:
    - kind: 'list' | 'pivot'
    - dimensions / rows: List[str] (field keys)
    - measures: List[{field, agg}] для pivot, [] для list
    - columns: List[str] (только для list — какие колонки возвращать)
    - filters: Dict
    - order_by: List[{field, dir}]
    - limit: int (default 5000)
    - offset: int (default 0)
    """
    kind = config.get('kind', 'list')

    base, feo_l1, feo_l2, feo_l3 = _base_query()
    base = _apply_org_filter(base, user)
    where = _build_filters(config.get('filters', {}), feo_l1, feo_l2, feo_l3)
    if where:
        base = base.where(and_(*where))

    if kind == 'list':
        return await _execute_list(base, config, feo_l1, feo_l2, feo_l3, db)
    elif kind == 'pivot':
        return await _execute_pivot(base, config, feo_l1, feo_l2, feo_l3, db)
    else:
        raise ValueError(f'Unknown kind: {kind}')


async def _execute_list(base, config, feo_l1, feo_l2, feo_l3, db) -> Dict:
    """Плоский реестр — выбираем покупки целиком + связанные."""
    columns = config.get('columns', [])
    limit = min(int(config.get('limit', 5000)), 10000)
    offset = int(config.get('offset', 0))
    order_by = config.get('order_by', [])

    for ob in order_by:
        key = ob.get('field')
        direction = ob.get('dir', 'asc')
        if key in ALLOWED_KEYS:
            f = get_field(key)
            col = _resolve_column(f, feo_l1, feo_l2, feo_l3)
            base = base.order_by(col.desc() if direction == 'desc' else col.asc())

    # Count total
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    base = base.limit(limit).offset(offset)
    rows_raw = (await db.execute(base)).all()

    rows = []
    for row in rows_raw:
        purchase, contractor, subsidy, feo_cat, l1, l2, l3 = row
        row_dict = {}
        for key in columns:
            if key not in ALLOWED_KEYS:
                continue
            row_dict[key] = _extract_value(key, purchase, contractor, subsidy, feo_cat, l1, l2, l3)
        row_dict['_id'] = purchase.id if purchase else None
        rows.append(row_dict)

    # Phase 25-05: composite/constant columns + group_by
    from app.services.composite_columns import apply_composite_columns, group_rows

    composite_specs = config.get('computed_columns', [])
    if composite_specs:
        rows = apply_composite_columns(rows, composite_specs)

    group_by = config.get('group_by', [])
    measures_for_subtotal = config.get('group_measures', [])
    if group_by:
        rows = group_rows(rows, group_by, measures_for_subtotal)

    return {
        'kind': 'list',
        'rows': rows,
        'rows_count': total,
        'limit': limit,
        'offset': offset,
    }


def _extract_value(key, purchase, contractor, subsidy, feo_cat, feo_l1, feo_l2, feo_l3):
    """Пост-SQL-выборка значения по ключу (для list-mode где грузим целые объекты)."""
    f = get_field(key)
    if f is None:
        return None
    expr = f.sql_expr.strip()
    if '.' in expr and 'CASE' not in expr.upper():
        parts = expr.split('.', 1)
        if len(parts) == 2:
            t, c = parts
            obj_map = {
                'purchases': purchase,
                'contractors': contractor,
                'subsidies': subsidy,
                'feo_categories': feo_cat,
                'feo_l1': feo_l1,
                'feo_l2': feo_l2,
                'feo_l3': feo_l3,
            }
            obj = obj_map.get(t)
            if obj is not None:
                return getattr(obj, c, None)
    # Computed (CASE/EXTRACT) — для list-режима не поддерживаем
    return None


async def _execute_pivot(base, config, feo_l1, feo_l2, feo_l3, db) -> Dict:
    """Сводная: SELECT dim1, dim2, ..., agg(measure) FROM ... GROUP BY ..."""
    rows_dims = config.get('rows', [])
    cols_dims = config.get('cols', [])
    measures = config.get('measures', [])
    limit = min(int(config.get('limit', 5000)), 10000)

    if not measures:
        return {'kind': 'pivot', 'rows': [], 'totals': {}, 'rows_count': 0}

    all_dims = rows_dims + cols_dims

    select_cols = []
    select_labels = []

    for dim_key in all_dims:
        if dim_key not in ALLOWED_KEYS:
            continue
        f = get_field(dim_key)
        col = _resolve_column(f, feo_l1, feo_l2, feo_l3)
        select_cols.append(col.label(dim_key))
        select_labels.append(dim_key)

    measure_labels = []
    for m in measures:
        m_field = m.get('field')
        m_agg = m.get('agg', 'sum')
        if m_field not in ALLOWED_KEYS or m_agg not in ALLOWED_AGGS:
            continue
        f = get_field(m_field)
        col = _resolve_column(f, feo_l1, feo_l2, feo_l3)
        agg_col = _apply_agg(col, m_agg)
        label = f'{m_agg}_{m_field}'
        select_cols.append(agg_col.label(label))
        measure_labels.append(label)

    if not select_cols:
        return {'kind': 'pivot', 'rows': [], 'totals': {}, 'rows_count': 0}

    pivot_q = select(*select_cols).select_from(base.subquery())

    if all_dims:
        group_exprs = []
        for dim_key in all_dims:
            if dim_key not in ALLOWED_KEYS:
                continue
            f = get_field(dim_key)
            group_exprs.append(_resolve_column(f, feo_l1, feo_l2, feo_l3))
        pivot_q = pivot_q.group_by(*group_exprs)

    pivot_q = pivot_q.limit(limit)

    rows_raw = (await db.execute(pivot_q)).mappings().all()
    rows = [dict(r) for r in rows_raw]

    totals = {}
    for label in measure_labels:
        try:
            totals[label] = sum(float(r.get(label) or 0) for r in rows)
        except (TypeError, ValueError):
            totals[label] = 0

    return {
        'kind': 'pivot',
        'rows': rows,
        'totals': totals,
        'rows_count': len(rows),
        'dimensions': all_dims,
        'measures': measure_labels,
    }


async def execute_drill(
    config: Dict[str, Any],
    dimension_values: Dict[str, Any],
    user: User,
    db: AsyncSession,
) -> Dict:
    """Drill-down: возвращает плоский список Purchase для пересечения dimension_values."""
    new_filters = dict(config.get('filters', {}))
    for k, v in dimension_values.items():
        new_filters[k] = v

    list_config = {
        'kind': 'list',
        'columns': config.get('drill_columns', [
            'purchase_number', 'item_name', 'contractor_name',
            'subsidy_name', 'status', 'planned_total_price',
        ]),
        'filters': new_filters,
        'limit': 1000,
    }
    return await execute_query(list_config, user, db)
