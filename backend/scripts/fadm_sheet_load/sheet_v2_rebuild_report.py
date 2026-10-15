"""Текстовый отчёт `--rebuild-in-place` (задание 15.10.2026, п.7) —
переиспользует render_report_v2 для части «что собралось из листа» (ПРАВИЛО
№6), сверху добавляет блок удаления и сверку бюджета корней с 15 880 100."""
from __future__ import annotations

from decimal import Decimal

from .sheet_v2_parse import SheetRowV2
from .sheet_v2_report import render_report_v2
from .sheet_v2_rebuild import RebuildResult

EXPECTED_BUDGET_TOTAL = Decimal("15880100.00")


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def render_rebuild_report(rows: list[SheetRowV2], result: RebuildResult, *, dry_run: bool) -> str:
    lines = []
    lines.append(f"=== --rebuild-in-place — субсидия id={result.subsidy.id} «{result.subsidy.name}» "
                 f"({'DRY-RUN' if dry_run else 'COMMIT'}) ===")
    lines.append("")
    lines.append("Снимок перед удалением:")
    lines.append(f"  Закупок загрузчика в снимке: {len(result.snapshot.get('purchases', []))}")
    lines.append(f"  Файл снимка: {result.snapshot_path}")
    with_manual = [p for p in result.snapshot.get("purchases", []) if p.get("manual_events_since_2026-10-06")]
    if with_manual:
        lines.append(f"  ВНИМАНИЕ: у {len(with_manual)} закупок загрузчика есть события ПОСЛЕ 2026-10-06 "
                     "(ручные правки людей после загрузки листа) — пропадут при пересборке, см. снимок:")
        for p in with_manual[:30]:
            lines.append(f"    - закупка #{p['purchase_id']} (РЕЕ {p.get('registry_number')}): "
                         f"{len(p['manual_events_since_2026-10-06'])} событий")
        if len(with_manual) > 30:
            lines.append(f"    ... и ещё {len(with_manual) - 30}")
    lines.append("")

    lines.append("Удалено (только созданное загрузчиком — дерево ФЭО/budget/участники/шаблоны не тронуты):")
    lines.append(f"  Закупок: {result.delete_counters.purchases_deleted}")
    lines.append(f"  Договоров: {result.delete_counters.contracts_deleted}")
    if result.delete_counters.contracts_kept_shared:
        lines.append(f"  Договоров ОСТАВЛЕНО (делят их с чужой закупкой этой субсидии): "
                     f"{result.delete_counters.contracts_kept_shared}")
    lines.append(f"  Плановых позиций листа (feo_planned_items): {result.delete_counters.plan_items_deleted}")
    lines.append("")

    diff = result.root_budget_total - EXPECTED_BUDGET_TOTAL
    mark = "OK" if abs(diff) < Decimal("1") else "РАСХОЖДЕНИЕ"
    lines.append(f"Бюджет ФЭО (Σ budget корневых категорий, строки F1/G1 в rebuild-in-place НЕ создаются): "
                 f"{_fmt(result.root_budget_total)} / контроль {_fmt(EXPECTED_BUDGET_TOTAL)} / "
                 f"разница {_fmt(diff)} [{mark}]")
    lines.append("")

    lines.append("--- Пересборка из листа GoodsService ---")
    lines.append(render_report_v2(rows, result.subsidy.name, result.counters, dry_run=dry_run))
    return "\n".join(lines)
