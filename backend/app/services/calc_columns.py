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


def apply_calc_columns(rows: List[Dict], calc_specs: List[Dict[str, Any]]) -> List[Dict]:
    """Применяет список calc-spec'ов в порядке.

    calc_specs: [{type: 'share'|'cumulative'|'delta', measure: str, ...}]
    """
    for spec in calc_specs:
        ctype = spec.get('type')
        if ctype == 'share':
            apply_share_of_total(rows, spec['measure'])
        elif ctype == 'cumulative':
            apply_cumulative_sum(rows, spec['measure'])
        elif ctype == 'delta':
            apply_delta_to_plan(rows, spec['actual'], spec['plan'])
    return rows
