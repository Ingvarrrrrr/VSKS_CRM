"""Post-processing для calculated columns (% от итога, нарастающий итог, и т.п.)."""

from typing import List, Dict, Any


def apply_share_of_total(rows: List[Dict], measure_label: str, target: str = 'grand') -> List[Dict]:
    """Добавляет колонку share_{measure} = value / grand_total."""
    total = sum(float(r.get(measure_label) or 0) for r in rows)
    if total == 0:
        return rows
    new_label = f'share_{measure_label}'
    for r in rows:
        v = float(r.get(measure_label) or 0)
        r[new_label] = v / total
    return rows


def apply_cumulative_sum(rows: List[Dict], measure_label: str) -> List[Dict]:
    """Добавляет нарастающий итог (предполагает что rows отсортированы)."""
    new_label = f'cumulative_{measure_label}'
    running = 0.0
    for r in rows:
        running += float(r.get(measure_label) or 0)
        r[new_label] = running
    return rows


def apply_delta_to_plan(rows: List[Dict], actual: str, plan: str) -> List[Dict]:
    """Δ = plan - actual; pct = (plan - actual) / plan."""
    for r in rows:
        a = float(r.get(actual) or 0)
        p = float(r.get(plan) or 0)
        r[f'delta_{actual}_vs_{plan}'] = p - a
        r[f'pct_{actual}_vs_{plan}'] = (p - a) / p if p else 0
    return rows


def apply_contract_savings(
    rows: List[Dict],
    planned_key: str = 'planned_total_price',
    contracted_key: str = 'contracted_total',
    output_key: str = 'contract_savings',
) -> List[Dict]:
    """Phase 27.1 D-15: post-process calc-column для экономии на торгах.

    contract_savings = planned_total_price - contracted_total.
    Положительное = экономия (план дороже договора).
    Отрицательное = переплата (редкий случай).
    None если любой из операндов отсутствует.
    """
    for row in rows:
        plan_val = row.get(planned_key)
        contracted_val = row.get(contracted_key)
        if plan_val is None or contracted_val is None:
            row[output_key] = None
        else:
            try:
                row[output_key] = float(plan_val) - float(contracted_val)
            except (TypeError, ValueError):
                row[output_key] = None
    return rows


def apply_calc_columns(rows: List[Dict], calc_specs: List[Dict[str, Any]]) -> List[Dict]:
    """Применяет список calc-spec'ов в порядке.

    calc_specs: [{type: 'share'|'cumulative'|'delta'|'contract_savings', measure: str, ...}]
    """
    for spec in calc_specs:
        ctype = spec.get('type')
        if ctype == 'share':
            apply_share_of_total(rows, spec['measure'])
        elif ctype == 'cumulative':
            apply_cumulative_sum(rows, spec['measure'])
        elif ctype == 'delta':
            apply_delta_to_plan(rows, spec['actual'], spec['plan'])
        elif ctype == 'contract_savings':
            apply_contract_savings(
                rows,
                planned_key=spec.get('planned_key', 'planned_total_price'),
                contracted_key=spec.get('contracted_key', 'contracted_total'),
                output_key=spec.get('output_key', 'contract_savings'),
            )
    return rows
