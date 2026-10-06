"""Текстовый отчёт загрузчика v2 (GoodsService) — см. задание 05.10.2026, п.3."""
from __future__ import annotations

from decimal import Decimal

from .sheet_v2_parse import SheetRowV2, group_rows_v2, totals_report
from .sheet_v2_build import BuildCountersV2
from .fadm_control import SHEET_CONTROL

# ПРАВИЛО №6 — те же числа, что в sheet_v2_dashboard_check.py::CONTROL,
# читаются из fadm_control.py::SHEET_CONTROL, не прописаны второй раз.
CONTROL_TOTALS = {
    "contracted": SHEET_CONTROL["contracted"][0],
    "delivered": SHEET_CONTROL["delivered"][0],
    "paid": SHEET_CONTROL["paid_statement"][0],
    "goods": SHEET_CONTROL["planned"][1],
    "services": SHEET_CONTROL["planned"][2],
    "plan_total": SHEET_CONTROL["planned"][0],
}


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def render_report_v2(rows: list[SheetRowV2], subsidy_name: str, counters: BuildCountersV2, *, dry_run: bool) -> str:
    groups, plan_rows = group_rows_v2(rows)
    kinds = {"Разовый": 0, "Рамочный накопительный": 0, "Рамочный с суммой": 0}
    for g in groups:
        kinds[g.contract_kind] = kinds.get(g.contract_kind, 0) + 1

    lines = []
    lines.append(f"=== Отчёт загрузчика v2 — «{subsidy_name}» ({'DRY-RUN' if dry_run else 'COMMIT'}) ===")
    lines.append("")
    lines.append(f"Строк в CSV: {len(rows)}; закупок (групп): {len(groups)}; плановых позиций (M=false): {len(plan_rows)}")
    lines.append("Закупок по видам договора:")
    for k, v in kinds.items():
        lines.append(f"  {k}: {v}")
    lines.append(f"  Рамочных голов создано: {counters.framework_heads}, заказов: {counters.framework_orders}")
    lines.append(f"  Разовых/помесячных закупок создано: {counters.single_purchases}")
    lines.append("")

    t = totals_report(rows)
    lines.append("Контрольные суммы (строка 1 листа) vs посчитано из CSV:")
    for key, label in (("contracted", "Договор (AT)"), ("delivered", "Поставлено (AV)"),
                       ("paid", "Оплачено (AW)"), ("goods", "Товары (BF)"),
                       ("services", "Услуги (BE)"), ("plan_total", "План (E1)")):
        calc = t[key]
        exp = CONTROL_TOTALS[key]
        diff = calc - exp
        mark = "OK" if abs(diff) < Decimal("1") else "РАСХОЖДЕНИЕ"
        lines.append(f"  {label}: расчёт {_fmt(calc)} / контроль {_fmt(exp)} / разница {_fmt(diff)} [{mark}]")
    lines.append("")

    lines.append(f"Контрагенты: создано новых {counters.contractors_created}, "
                 f"найдено существующих {counters.contractors_found_existing}, "
                 f"ИНН не определён (R — заглушка/пусто): {counters.inn_missing}")
    lines.append(f"Авансовые закупки: {counters.advance_purchases}")
    if counters.advance_entries:
        lines.append("  Список:")
        for a in counters.advance_entries:
            src = f", контрагент из старой ФАДМ_2026: #{a['contractor_from_source']}" if a["contractor_from_source"] else ""
            lines.append(f"    - {a['label']} — {a['employee_name']} (user#{a['employee_id']}){src}")
    lines.append(f"Исполнитель подставлен от двойника в старой ФАДМ_2026 (по контрагенту): "
                 f"{counters.executor_from_source} закупок. Копирование файлов/чеков двойника — НЕ реализовано "
                 f"(нет построчного twin-сопоставления закупок в v2, см. первый загрузчик match.py/files_copy.py)")
    lines.append("")

    lines.append(f"ФЭО-направление: сопоставлено по имени {counters.feo_matched}, "
                 f"не сопоставлено (→ «Не определена») {len(counters.feo_unmatched)}")
    if counters.feo_unmatched:
        lines.append("  Не сопоставленные направления:")
        for u in counters.feo_unmatched[:50]:
            lines.append(f"    - {u['label']}: AE={u['ae']!r} AF={u['af']!r}")
        if len(counters.feo_unmatched) > 50:
            lines.append(f"    ... и ещё {len(counters.feo_unmatched) - 50}")
    lines.append("")

    lines.append(f"Платежи (поиск по ИНН+сумма P+соглашение+исполнен — владелец, уточнение 05.10.2026): "
                 f"привязано {counters.payments_attached} шт. на сумму "
                 f"{_fmt(counters.payments_attached_amount)} (контроль AW {_fmt(CONTROL_TOTALS['paid'])})")
    lines.append(f"  Номер/дата договора разобраны из назначения платежа (S/T были «Нет данных»): "
                 f"{counters.contract_filled_from_payment}")
    if counters.framework_limit_calculated:
        lines.append("  Лимит рамочного РАСЧЁТНЫЙ (нет строки-лимита в листе, Σ Y заказов):")
        for c in counters.framework_limit_calculated:
            lines.append(f"    - {c['label']}: {c['amount']}")
    if counters.payments_u_mismatch:
        lines.append(f"  Контроль U (номер п/п в листе) разошёлся с найденным GALA ({len(counters.payments_u_mismatch)}):")
        for m in counters.payments_u_mismatch[:30]:
            lines.append(f"    - {m['label']} — {m['note']}")
        if len(counters.payments_u_mismatch) > 30:
            lines.append(f"    ... и ещё {len(counters.payments_u_mismatch) - 30}")
    if counters.payments_not_found:
        lines.append(f"  Не найдено/не привязано ({len(counters.payments_not_found)}):")
        for p in counters.payments_not_found[:50]:
            lines.append(f"    - п/п {p['doc_no']!r}, ИНН {p['inn']}, сумма {p['amount']}, {p['label']} — {p['reason']}")
        if len(counters.payments_not_found) > 50:
            lines.append(f"    ... и ещё {len(counters.payments_not_found) - 50}")
    lines.append("")

    return "\n".join(lines)
