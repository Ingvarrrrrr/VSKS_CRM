"""Отчёт --match-only (match_only.MatchOnlyResult). НАРОЧНО отдельный файл от
report.py — тот импортирует build.py (писатели), этот — нет, ни напрямую, ни
транзитивно (условие задания: --match-only не должен тянуть ни одной функции
записи по цепочке импортов)."""
from __future__ import annotations

from .match_only import MatchOnlyResult
from .parse import SheetRow
from .report_common import matched_section, old_without_pair_section, totals_section, unmatched_ambiguous_section


def render_match_only_report(rows: list[SheetRow], result: MatchOnlyResult) -> str:
    lines: list[str] = []
    lines.append(f"=== --match-only: «{result.source_subsidy_name}» (id={result.source_subsidy_id}) ===")
    lines.append("")
    lines.append(f"Контрагентов: найдено существующих {result.contractors_existing}, "
                 f"было бы создано новых {len(result.contractors_would_create)}")
    if result.contractors_would_create:
        lines.append("  были бы созданы: " + ", ".join(result.contractors_would_create))
    lines.append("")
    lines += totals_section(rows)
    lines += matched_section(result.matched)
    lines += unmatched_ambiguous_section(result.unmatched, result.ambiguous)
    lines += old_without_pair_section(result.old_without_pair)
    lines.append("READ ONLY — ничего не создано и не изменено.")
    return "\n".join(lines)
