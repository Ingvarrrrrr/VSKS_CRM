"""Текстовый отчёт --copy-docs — см. sheet_v2_docs.py."""
from __future__ import annotations

from .files_copy import DocCopyCounters
from .sheet_v2_docs import DocPair


def render_copy_docs_report(pairs: list[DocPair], counters: DocCopyCounters, *, dry_run: bool) -> str:
    lines = []
    lines.append(f"=== Отчёт --copy-docs ({'DRY-RUN' if dry_run else 'COMMIT'}) ===")
    lines.append("")
    lines.append(f"Найдено пар (новая закупка ↔ двойник в старой субсидии): {len(pairs)}")
    by_method: dict[str, int] = {}
    for p in pairs:
        by_method[p.method] = by_method.get(p.method, 0) + 1
    lines.append("  По способу: " + ", ".join(f"{m} — {c}" for m, c in sorted(by_method.items())))
    for p in pairs:
        tie = " [тай-брейк]" if p.tie_break else ""
        lines.append(f"  - новая #{p.new_purchase_id} ↔ старая #{p.old_purchase_id} "
                     f"[{p.method}] (contractor#{p.contractor_id}, {p.amount_new} ~ {p.amount_old}){tie}")
    lines.append("")
    lines.append(f"Закупок с скопированными документами: {counters.pairs_with_docs}")
    lines.append(f"Файлов скопировано: {counters.files_copied} (уже было: {counters.files_skipped_existing})")
    if counters.by_file_type:
        for ft, cnt in sorted(counters.by_file_type.items()):
            lines.append(f"    - {ft}: {cnt}")
    lines.append(f"Чеков скопировано: {counters.receipts_copied} (уже было: {counters.receipts_skipped_existing})")
    lines.append("")
    return "\n".join(lines)
