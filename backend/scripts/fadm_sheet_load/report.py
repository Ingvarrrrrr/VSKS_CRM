"""Отчёт после --dry-run/commit (build.py, BuildCounters). Для --match-only
см. report_match_only.py — отдельный файл НАРОЧНО: этот модуль импортирует
build.py (писатели), report_match_only.py — нет (условие задания: match-only
не должен тянуть ни одной функции записи по цепочке импортов)."""
from __future__ import annotations

from .build import BuildCounters
from .parse import SheetRow
from .report_common import matched_section, old_without_pair_section, totals_section, unmatched_ambiguous_section


def render_report(rows: list[SheetRow], subsidy_name: str, counters: BuildCounters, dry_run: bool) -> str:
    lines: list[str] = []
    mode = "DRY-RUN (откат в конце)" if dry_run else "COMMIT"
    lines.append(f"=== Загрузка «{subsidy_name}» — {mode} ===")
    lines.append("")
    lines.append("Закупки:")
    lines.append(f"  разовые: {counters.single_purchases}")
    lines.append(f"  рамочные (голов): {counters.framework_heads}, заказов внутри: {counters.framework_orders}")
    lines.append(f"  помесячные: {counters.monthly_purchases}")
    lines.append("")
    lines.append("Плановые позиции (reserve/likely):")
    lines.append(f"  'likely' (Скорее всего понадобится): {counters.planned_items_likely}")
    lines.append(f"  'nice_to_have' (Резерв, можно отказаться): {counters.planned_items_nice_to_have}")
    if counters.need_level_column_missing:
        lines.append("  ⚠️ колонка feo_planned_items.need_level отсутствует в этой БД — "
                     "признак записан в notes текстом, не колонкой.")
    lines.append("")
    lines.append(f"Контрагентов: найдено существующих {counters.contractors_found_existing}, "
                 f"создано новых {counters.contractors_created}")
    if counters.contractors_created_names:
        lines.append("  созданы: " + ", ".join(counters.contractors_created_names))
    lines.append("")

    lines += totals_section(rows)
    lines += matched_section([{
        "label": m.label, "old_registry": m.old_registry, "method": m.method,
        "assigned_user_id": m.assigned_user_id,
    } for m in counters.matched])
    lines += unmatched_ambiguous_section(counters.unmatched, counters.ambiguous)
    lines += old_without_pair_section(counters.old_without_pair)

    return "\n".join(lines)
