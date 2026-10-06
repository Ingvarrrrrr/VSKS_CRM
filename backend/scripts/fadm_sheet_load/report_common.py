"""Общие куски текстового отчёта, НЕ зависящие от build.py (ПРАВИЛО №6 —
report.py и report_match_only.py используют их же, чтобы вывод --dry-run/
--commit и --match-only не разъезжался по форматированию).

ВАЖНО: этот модуль не импортирует build.py и ни одной функции записи — его
держит в том числе match_only-путь (см. report_match_only.py), для которого
обязано не тянуться НИ ОДНОГО писателя по цепочке импортов."""
from __future__ import annotations

from decimal import Decimal

from .parse import SheetRow, totals_by_kind, totals_by_status
from .fadm_control import SHEET_CONTROL

# ПРАВИЛО №6 — тот же план (товары/услуги/итого), что и в sheet_v2_report.py/
# sheet_v2_dashboard_check.py, читается из fadm_control.py::SHEET_CONTROL.
EXPECTED_TOTALS = {
    "goods": SHEET_CONTROL["planned"][1],
    "services": SHEET_CONTROL["planned"][2],
    "total": SHEET_CONTROL["planned"][0],
}


def fmt_money(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def totals_section(rows: list[SheetRow]) -> list[str]:
    lines = []
    by_kind = totals_by_kind(rows)
    by_status = totals_by_status(rows)
    lines.append("Суммы по kind (из CSV, вся таблица):")
    for k in ("goods", "services"):
        v = by_kind.get(k, Decimal("0"))
        exp = EXPECTED_TOTALS.get(k)
        diff = f" (контроль {fmt_money(exp)}, расхождение {fmt_money(v - exp)})" if exp is not None else ""
        lines.append(f"  {k}: {fmt_money(v)}{diff}")
    total = sum(by_kind.values(), Decimal("0"))
    exp_total = EXPECTED_TOTALS["total"]
    lines.append(f"  ИТОГО: {fmt_money(total)} (контроль {fmt_money(exp_total)}, расхождение {fmt_money(total - exp_total)})")
    lines.append("")
    lines.append("Суммы по status строк:")
    for k, v in by_status.items():
        lines.append(f"  {k}: {fmt_money(v)}")
    lines.append("")
    return lines


def matched_section(matched: list) -> list[str]:
    lines = [f"Сопоставлено со старой субсидией ({len(matched)}):"]
    for m in matched:
        lines.append(
            f"  - {m['label']} → {m.get('old_registry') or '(без РЕЕ)'} "
            f"[{m.get('method') or '?'}], исполнитель user#{m.get('assigned_user_id') or '-'}"
        )
    lines.append("")
    return lines


def unmatched_ambiguous_section(unmatched: list, ambiguous: list) -> list[str]:
    lines = []
    if unmatched:
        lines.append(f"НЕ сопоставлено двойников ({len(unmatched)}):")
        for u in unmatched:
            lines.append(f"  - {u['label']} — {u['amount']}")
        lines.append("")
    if ambiguous:
        lines.append(f"Неоднозначные совпадения ({len(ambiguous)}):")
        for a in ambiguous:
            lines.append(f"  - {a['label']} — {a['amount']}")
        lines.append("")
    return lines


def old_without_pair_section(old_without_pair: list) -> list[str]:
    lines = [f"Старые закупки ФАДМ_2026 без пары ({len(old_without_pair)}):"]
    for o in old_without_pair:
        lines.append(
            f"  - {o.get('registry_number') or '(без РЕЕ)'} — {o.get('contractor') or '(без контрагента)'} "
            f"— {o['amount']} — {o['status']}"
        )
    lines.append("")
    return lines
