"""feo_export_xlsx.py — построение книги Excel «Выгрузить ФЭО»
(GET /api/feo-categories/export, задача владельца 20.10.2026).

Вынесено из app.routers.feo_import_export (ПРАВИЛО №5 — роутер тонкий,
только читает параметры/права и зовёт builder). Источник сумм по стадиям —
ЕДИНСТВЕННЫЙ app.services.plan_item_stage (planned_item_stage_segments —
позиции с собственной FeoPlannedItem, category_plan_stage_segments — план на
самой листовой категории без собственной FeoPlannedItem; ПРАВИЛО №6, второй
расчёт стадии закупки здесь не заводится).

Стадии и накопление (владелец 20.10.2026):
  Шкала рангов — app.services.plan_item_stage._STAGE_RANK (in_work < contracted
  < ordered < paid_marked < paid_confirmed). Сумма/доля стадии X = Σ amount/
  share сегментов, чей ранг >= ранга X («дошло до X или дальше»), т.е. ТОТ ЖЕ
  каскадный приём, что app.services.plan_graph_export_xlsx._money_cols_dict
  (contract_cum/ordered_cum/...) — здесь применён к segments[] вместо
  status_sums_map, второй алгоритм каскада не придумываем.
  «Товар поставлен» — НЕ по рангу шкалы (delivered сливается в ordered в
  _resolve_stage), а по отдельному признаку segments[].delivered.
"""
from __future__ import annotations

from typing import Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:  # pragma: no cover
    Workbook = None

from app.services.feo_export_columns import (
    MONEY_KEYS,
    STAGE_AMOUNT_KEYS,
    STAGE_DEFS,
    column_index,
    headers_and_widths,
)
from app.services.plan_item_stage import _STAGE_RANK

HEADER_ROW = 3
DATA_FIRST_ROW = 4
_ORDERED_RANK = _STAGE_RANK["ordered"]
_DONE_EPS = 0.999


def _stage_amounts(segments: list) -> dict:
    """{stage_key: (amount_sum, share_sum)} по каждой из шести колонок
    «Стадии» для одного набора segments[] (одна плановая позиция ИЛИ одна
    листовая категория с собственным планом) — см. докстринг модуля."""
    out: dict = {}
    for key, _label in STAGE_DEFS:
        if key == "delivered":
            amt = sum(s["amount"] for s in segments if s.get("delivered"))
            share = sum(s["share"] for s in segments if s.get("delivered"))
        else:
            rank = _STAGE_RANK[key if key != "ordered_flag" else "ordered"]
            amt = sum(s["amount"] for s in segments if _STAGE_RANK.get(s["stage"], 0) >= rank)
            share = sum(s["share"] for s in segments if _STAGE_RANK.get(s["stage"], 0) >= rank)
        out[key] = (amt, share)
    return out


def _stage_status_label(share: float) -> str:
    if share >= _DONE_EPS:
        return "Да"
    if share > 0:
        return "Частично"
    return "Нет"


def compute_row_stage_values(segments: list, plan_amount: float) -> dict:
    """Проекция segments[] в значения колонок листа: 6 пар («стадия»→Да/
    Частично/Нет, «стадия, ₽») + ordered/to_order/residual (сумма — без
    residual, residual считает вызывающий код формулой/числом).

    Заказано (₽) = сумма стадии "ordered" (накопительно); «Надо заказать» = 0,
    если доля ordered >= 0.999, иначе max(0, План − Заказано) — владелец
    20.10.2026."""
    stage_vals = _stage_amounts(segments)
    out: dict = {}
    for key, _label in STAGE_DEFS:
        amt, share = stage_vals[key]
        out[key] = _stage_status_label(share)
        out[f"{key}_amt"] = round(amt, 2) if abs(amt) > 0.005 else 0.0

    ordered_amt, ordered_share = stage_vals["ordered_flag"]
    out["ordered"] = round(ordered_amt, 2) if abs(ordered_amt) > 0.005 else 0.0
    if ordered_share >= _DONE_EPS:
        out["to_order"] = 0.0
    else:
        out["to_order"] = round(max(0.0, plan_amount - ordered_amt), 2)
    return out


async def build_feo_export_workbook(db, sub, selected_keys: list):
    """Строит openpyxl.Workbook «Выгрузить ФЭО» по субсидии `sub` (столбцы —
    `selected_keys`, см. app.services.feo_export_columns). Единственная точка
    обращения к БД для этой выгрузки — одна выборка категорий, одна выборка
    позиций (_active_feo_items_with_amount), один вызов
    planned_item_stage_segments на ВСЕ позиции субсидии и один вызов
    category_plan_stage_segments на ВСЕ листовые категории (не в цикле —
    задача владельца, п.3: «одним вызовом на все позиции субсидии»)."""
    if Workbook is None:
        raise RuntimeError("openpyxl не установлен")

    from sqlalchemy import select
    from app.models.feo_category import FeoCategory
    from app.services.subsidy_budget import _active_feo_items_with_amount
    from app.services.plan_item_stage import (
        category_plan_stage_segments,
        planned_item_stage_segments,
    )

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == sub.id)
        .order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()
    cat_ids = [c.id for c in cats]

    feo_items = await _active_feo_items_with_amount(db, cat_ids)
    items_by_cat: dict = {}
    for it in sorted(feo_items, key=lambda x: (x.sort_order is None, x.sort_order or 0, x.id)):
        items_by_cat.setdefault(it.feo_category_id, []).append(it)

    by_id = {c.id: {"cat": c, "children": []} for c in cats}
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(by_id[c.id])
        else:
            roots.append(by_id[c.id])

    leaf_cat_ids = [c.id for c in cats if not by_id[c.id]["children"]]
    item_ids = [it.id for it in feo_items]
    item_segments_map = await planned_item_stage_segments(db, item_ids)
    cat_segments_map = await category_plan_stage_segments(db, leaf_cat_ids)

    wb = Workbook()
    ws = wb.active
    ws.title = sub.name[:31]
    ws.sheet_properties.outlinePr.summaryBelow = False

    HEADER_FILL = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
    L1_FILL = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    L2_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    BOLD_FONT = Font(bold=True)
    SEMI_FONT = Font(bold=False)
    ITEM_FONT = Font(italic=True, color="475569")
    TOTAL_FONT = Font(bold=True, color="1E3A5F")
    NUM_FMT = "#,##0.00"
    _MAX_OUTLINE = 7

    headers, widths = headers_and_widths(selected_keys)
    n_cols = len(selected_keys)

    ws.cell(row=1, column=1, value=f"{sub.name} — итого всего").font = TOTAL_FONT
    ws.cell(row=2, column=1, value="Итого по фильтру").font = TOTAL_FONT

    for col_idx, (header, width) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[HEADER_ROW].height = 32
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    row_num = DATA_FIRST_ROW

    def _write_row(values: dict, fill, font) -> int:
        nonlocal row_num
        for ci, key in enumerate(selected_keys, 1):
            val = values.get(key, "")
            cell = ws.cell(row=row_num, column=ci, value=val if val != "" else None)
            if fill:
                cell.fill = fill
            cell.font = font
            if key in MONEY_KEYS and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        r = row_num
        row_num += 1
        return r

    def write_item_row(item, depth):
        feo_amount = float(item.feo_amount) if item.feo_amount is not None else None
        plan_amount = float(item.amount) if item.amount is not None else 0.0
        segments = item_segments_map.get(item.id, {}).get("segments", [])
        stage_vals = compute_row_stage_values(segments, plan_amount)
        ordered_amt = stage_vals["ordered"]
        to_order = stage_vals["to_order"]
        values = {
            "name": "  " * depth + item.name,
            "feo_qty": float(item.quantity) if item.quantity is not None else "",
            "feo_unit": item.unit or "",
            "feo": feo_amount if feo_amount is not None else "",
            "plan": plan_amount,
            "active": "Да" if item.is_active else "Нет",
            **stage_vals,
        }
        row_idx = _write_row(values, None, ITEM_FONT)
        ci_feo = column_index(selected_keys, "feo")
        ci_ordered = column_index(selected_keys, "ordered")
        ci_to_order = column_index(selected_keys, "to_order")
        ci_residual = column_index(selected_keys, "residual")
        if ci_residual is not None:
            if ci_feo is not None and ci_ordered is not None and ci_to_order is not None:
                lf, lo, lt = (ws.cell(row_idx, c).column_letter for c in (ci_feo, ci_ordered, ci_to_order))
                ws.cell(row_idx, ci_residual, value=f"={lf}{row_idx}-{lo}{row_idx}-{lt}{row_idx}")
            else:
                feo_val = feo_amount if feo_amount is not None else 0.0
                ws.cell(row_idx, ci_residual, value=round(feo_val - ordered_amt - to_order, 2))
            ws.cell(row_idx, ci_residual).number_format = NUM_FMT
        ws.row_dimensions[row_idx].outline_level = min(depth, _MAX_OUTLINE)
        ws.row_dimensions[row_idx].hidden = True
        return row_idx

    def _money_subtotal(row_idx: int, child_rows: list) -> None:
        """Денежные/стадийные столбцы строки-категории = SUBTOTAL(9, ...) по
        строкам ПРЯМЫХ детей (функция 9 — считает и скрытые строки, владелец
        20.10.2026, п.5: строки позиций скрыты группировкой и ДОЛЖНЫ
        учитываться)."""
        keys = ("feo", "plan", "ordered", "to_order", "residual") + STAGE_AMOUNT_KEYS
        for key in keys:
            ci = column_index(selected_keys, key)
            if ci is None:
                continue
            if not child_rows:
                continue
            col_letter = ws.cell(row=row_idx, column=ci).column_letter
            refs = ",".join(f"{col_letter}{cr}" for cr in child_rows)
            cell = ws.cell(row_idx, ci, value=f"=SUBTOTAL(9,{refs})")
            cell.number_format = NUM_FMT

    def write_node(node, depth=0):
        c = node["cat"]
        # «Есть дети» — ТЕ ЖЕ строки-прямые-дети, что раньше считал старый
        # роутер (child_rows = собственные плановые позиции + подкатегории),
        # а не только подкатегории: категория-лист без собственных подкатегорий,
        # но с плановыми позициями — всё равно агрегирует их формулой
        # (иначе своя "feo" литералом конфликтовала бы с budget, заданным
        # вручную "для сверки", и терялась бы сумма позиций).
        has_own_items = bool(items_by_cat.get(c.id))
        has_subcats = bool(node["children"])
        is_leaf = not has_own_items and not has_subcats
        leaf_segments = cat_segments_map.get(c.id, {}).get("segments", []) if is_leaf else []
        # «План» листовой категории — та же величина, что и в прежнем
        # экспорте (сумма покупок, привязанных НАПРЯМУЮ к категории, не
        # через плановую позицию) — ПРАВИЛО №6, второй расчёт плана
        # категории не заводим; для категории с детьми план — SUBTOTAL ниже.
        own_plan = sum(float(s["amount"]) for s in leaf_segments) if leaf_segments else 0.0
        stage_vals = compute_row_stage_values(leaf_segments, own_plan) if is_leaf else {}

        values = {
            "name": "  " * depth + c.name,
            "code": c.code or "",
            "app": c.appendix or "",
            "feo": float(c.budget) if c.budget is not None else "",
            "active": "Да" if c.is_active else "Нет",
        }
        if is_leaf:
            values["plan"] = own_plan
            values.update(stage_vals)
        fill = L1_FILL if c.level == 1 else (L2_FILL if c.level == 2 else None)
        font = BOLD_FONT if c.level == 1 else SEMI_FONT
        row_idx = _write_row(values, fill, font)
        if depth > 0:
            ws.row_dimensions[row_idx].outline_level = min(depth, _MAX_OUTLINE)

        child_rows = [write_item_row(it, depth + 1) for it in items_by_cat.get(c.id, [])]
        child_rows += [write_node(ch, depth + 1) for ch in node["children"]]

        if child_rows:
            _money_subtotal(row_idx, child_rows)
        else:
            ci_ordered = column_index(selected_keys, "ordered")
            ci_feo = column_index(selected_keys, "feo")
            ci_to_order = column_index(selected_keys, "to_order")
            ci_residual = column_index(selected_keys, "residual")
            if ci_residual is not None:
                if ci_feo is not None and ci_ordered is not None and ci_to_order is not None:
                    lf, lo, lt = (ws.cell(row_idx, c_).column_letter for c_ in (ci_feo, ci_ordered, ci_to_order))
                    ws.cell(row_idx, ci_residual, value=f"={lf}{row_idx}-{lo}{row_idx}-{lt}{row_idx}")
                else:
                    feo_val = float(c.budget) if c.budget is not None else 0.0
                    ws.cell(row_idx, ci_residual, value=round(feo_val - stage_vals.get("ordered", 0.0) - stage_vals.get("to_order", 0.0), 2))
                ws.cell(row_idx, ci_residual).number_format = NUM_FMT

        return row_idx

    top_rows = [write_node(root) for root in roots]
    last_row = row_num - 1

    # Строка 1 «Итого всего» — SUM по корневым категориям; строка 2
    # «Итого по фильтру» — SUBTOTAL(9, весь столбец данных) (владелец, п.5).
    money_keys = ("feo", "plan", "ordered", "to_order", "residual") + STAGE_AMOUNT_KEYS
    for key in money_keys:
        ci = column_index(selected_keys, key)
        if ci is None:
            continue
        col_letter = ws.cell(row=1, column=ci).column_letter
        if top_rows:
            refs = ",".join(f"{col_letter}{r}" for r in top_rows)
            ws.cell(row=1, column=ci, value=f"=SUM({refs})").font = TOTAL_FONT
        if last_row >= DATA_FIRST_ROW:
            ws.cell(row=2, column=ci, value=f"=SUBTOTAL(9,{col_letter}{DATA_FIRST_ROW}:{col_letter}{last_row})").font = TOTAL_FONT

    last_col_letter = ws.cell(row=HEADER_ROW, column=n_cols).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"

    return wb
