"""Рендер живой (текущей) книги Excel плана-графика субсидии.

Вынесено из app/routers/subsidy_plan_graph_export.py::export_plan_graph_excel
(Правило №5, рефакторинг 2026-09-08). Принимает уже собранные данные из
app.services.plan_graph_export_data.gather_live_plan_graph_data — сам к БД не
обращается.

Отличается от app.services.plan_graph_export_render.render_plan_graph_workbook
(используется для экспорта снапшота версии): здесь каскад статусов по пяти
стадиям, факт по каждой закупленной позиции с гиперссылкой на заказ, выбор
столбцов (Задача D) и лист «Сводная» (вынесен в
app.services.plan_graph_export_summary_sheet, Задача А).

ИЗМЕНЕНО (владелец 07.10.2026, план .planning/quick/2026-10-07-plan-graph-
export/PLAN.md):
  Задача B — суммы по стадиям теперь НАКОПИТЕЛЬНЫЕ (Запланировано ⊇ Договор ⊇
    Заказано ⊇ Поставлено ⊇ Оплачено) везде на листе: роллап направлений/
    групп/статей (_money_cols_dict), строки плановых позиций, под-строки
    фактических позиций (cascade_by_stage — ЕДИНСТВЕННАЯ функция каскада на
    весь модуль). Отменённые закупки (status='cancelled') — 0 на всех
    стадиях (не входят и в «Фактически (итого)»).
  Задача C — высота строк по тексту (app.utils.xlsx_row_height), не константы.
  Задача D — выбор столбцов (app.services.plan_graph_export_columns);
    рендерятся только выбранные ключи, порядок фиксирован.

ДОБАВЛЕНО (владелец 07.10.2026, группа «Договор и оплата»): к каждому
фактическому под-строке (есть purchase_id) — № ПП, № договора, контрагента по
платежу и т.д., читается через get_cell_value (ПРАВИЛО №6, та же функция, что
экспорт закупок) по Purchase из data["purchase_rows_by_id"]. В строках
направлений/статей/плановых позиций эти столбцы не заполняются (нет одной
закупки, к которой это можно отнести)."""
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

from app.routers.purchases import STATUS_ORDER as _STATUS_ORDER
from app.services.plan_graph_export_columns import (
    CONTRACT_PAYMENT_COL_KEYS,
    MONEY_COL_KEYS,
    column_index,
    headers_and_widths,
    resolve_selected_keys,
)
from app.services.plan_graph_export_summary_sheet import write_summary_sheet
from app.services.purchase_export_cells import get_cell_value as _purchase_cell_value
from app.utils.numbers import format_ru_money
from app.utils.xlsx_row_height import apply_row_heights

# ── Каскад стадий (Задача B) — ЕДИНСТВЕННАЯ реализация на весь модуль ───────
_PLANNED_STATUS_SET = {"wishes", "plan_schedule", "work_in_progress"}
_STAGE_BY_STATUS: dict = {}
for _s in _STATUS_ORDER:
    if _s in _PLANNED_STATUS_SET:
        _STAGE_BY_STATUS[_s] = 0
    elif _s == "contracted":
        _STAGE_BY_STATUS[_s] = 1
    elif _s == "ordered":
        _STAGE_BY_STATUS[_s] = 2
    elif _s == "delivered":
        _STAGE_BY_STATUS[_s] = 3
    elif _s == "paid":
        _STAGE_BY_STATUS[_s] = 4


def cascade_by_stage(raw_status: str, total: float) -> tuple:
    """(planned, contract, ordered, delivered, paid) — сумма позиции попадает
    НАКОПИТЕЛЬНО во все столбцы ДО текущей стадии включительно (Задача B):
    Запланировано ⊇ Договор ⊇ Заказано ⊇ Поставлено ⊇ Оплачено. Отменённые
    (status='cancelled') и статусы вне STATUS_ORDER (purchases.py) — везде 0."""
    t = round(total or 0, 2)
    idx = _STAGE_BY_STATUS.get(raw_status)
    if idx is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return tuple(t if i <= idx else 0.0 for i in range(5))


def build_live_plan_graph_xlsx(
    sub, base_url: str, data: dict, *,
    selected_columns=None, summary_by_kind: dict = None,
):
    """Строит openpyxl.Workbook живого плана-графика.

    Args:
        sub: Subsidy — для заголовка (name, year).
        base_url: базовый URL запроса (для гиперссылок «Открыть» на заказ).
        data: dict из gather_live_plan_graph_data(...).
        selected_columns: список ключей столбцов листа «План закупок»
            (app.services.plan_graph_export_columns) в порядке вывода; None —
            все столбцы.
        summary_by_kind: результат app.services.subsidy_summary_by_kind.
            subsidy_summary_by_kind(...); None — лист «Сводная» не строится
            (Задача D — параметр `summary=false`).

    Returns:
        openpyxl.Workbook

    Примечание: наличие openpyxl проверяет вызывающий роутер (дважды, включая
    унаследованный дефект-дубль — см. app/routers/subsidy_plan_graph_export.py);
    здесь отдельной проверки нет, чтобы не дублировать исключение сверх
    существовавших в дорефакторинговом коде.
    """
    selected_keys = list(selected_columns) if selected_columns else resolve_selected_keys(None)

    cats = data["cats"]
    items_by_cat = data["items_by_cat"]
    used_map = data["used_map"]
    contractor_map = data["contractor_map"]
    status_sums_map = data["status_sums_map"]
    purchased_by_item = data["purchased_by_item"]
    cat_status_map = data["cat_status_map"]
    cat_monthly_map = data["cat_monthly_map"]
    cat_contractor_map = data["cat_contractor_map"]
    purchased_by_cat = data["purchased_by_cat"]
    unlinked_purchases = data["unlinked_purchases"]
    # Группа «Договор и оплата» — отсутствуют в синтетических данных тестов
    # рендера (test_plan_graph_export_cascade.py строит `data` вручную, без
    # БД) — .get с пустыми фолбэками, чтобы они и дальше проходили как есть.
    purchase_rows_by_id = data.get("purchase_rows_by_id") or {}
    purchase_export_ctx = data.get("purchase_export_ctx") or {}

    def _st(item_id: int, *statuses: str) -> float:
        d = status_sums_map.get(item_id, {})
        return sum(d.get(s, 0.0) for s in statuses)

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    L1_FILL      = PatternFill("solid", fgColor="DBEAFE")
    L1_FONT      = Font(bold=True, size=9)
    L2_FILL      = PatternFill("solid", fgColor="F0F9FF")
    L2_FONT      = Font(bold=True, size=9, color="0C4A6E")
    L3_FILL      = PatternFill("solid", fgColor="F0FDF4")
    L3_FONT      = Font(size=9, color="166534")
    ITEM_FONT    = Font(size=9)
    RED_FONT     = Font(size=9, color="EF4444", bold=True)
    SUB_FONT     = Font(size=8, italic=True, color="6B7280")
    TOTAL_FONT   = Font(size=8, bold=True, color="374151")
    SUB_FILL     = PatternFill("solid", fgColor="FAFAFA")
    NO_FILL      = PatternFill()
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center", wrap_text=True)
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    LINK_FONT = Font(size=8, italic=True, color="2563EB", underline="single")
    NUM_FMT = "#,##0.00"
    E = ""  # пустая ячейка

    HEADERS, COL_WIDTHS = headers_and_widths(selected_keys)

    cats_by_parent: dict = {}
    for c in cats:
        cats_by_parent.setdefault(c.parent_id, []).append(c)

    # Роллап факта/бюджета вверх по дереву: направление (ур.1) и группа (ур.2)
    # показывают суммарные итоги по всем листовым категориям-потомкам.
    subtree_map: dict[int, dict] = {}

    def _compute_subtree(cat) -> dict:
        if cat.id in subtree_map:
            return subtree_map[cat.id]
        children = cats_by_parent.get(cat.id, [])
        status_agg: dict[str, float] = {}
        if not children:
            for k, v in cat_status_map.get(cat.id, {}).items():
                status_agg[k] = status_agg.get(k, 0.0) + v
            monthly = cat_monthly_map.get(cat.id, 0.0)
            if cat.budget is not None:
                budget = float(cat.budget)
            else:
                budget = sum(float(it.amount or 0) for it in items_by_cat.get(cat.id, []))
        else:
            budget = 0.0
            monthly = 0.0
            for ch in children:
                r = _compute_subtree(ch)
                for k, v in r["status"].items():
                    status_agg[k] = status_agg.get(k, 0.0) + v
                budget += r["budget"]
                monthly += r["monthly"]
        res = {"status": status_agg, "budget": budget, "monthly": monthly}
        subtree_map[cat.id] = res
        return res

    for c in cats:
        _compute_subtree(c)

    def _sub(cat_id: int, *statuses: str) -> float:
        d = subtree_map.get(cat_id, {}).get("status", {})
        return sum(d.get(s, 0.0) for s in statuses)

    def _money_cols_dict(cat_id: int, contractor: str) -> dict:
        """Денежные значения роллапа поддерева по стадиям, НАКОПИТЕЛЬНО
        (Задача B) — Запланировано == Фактически (итого) по построению (сумма
        всех пяти стадий), Договор/Заказано/Поставлено/Оплачено — хвосты
        каскада."""
        st = subtree_map.get(cat_id, {})
        budget = st.get("budget", 0.0)
        monthly = st.get("monthly", 0.0)
        plan0 = _sub(cat_id, "plan_schedule", "work_in_progress", "wishes")
        contract0 = _sub(cat_id, "contracted")
        ordered0 = _sub(cat_id, "ordered")
        delivered0 = _sub(cat_id, "delivered")
        paid0 = _sub(cat_id, "paid")
        used = plan0 + contract0 + ordered0 + delivered0 + paid0
        contract_cum = contract0 + ordered0 + delivered0 + paid0
        ordered_cum = ordered0 + delivered0 + paid0
        delivered_cum = delivered0 + paid0
        paid_cum = paid0
        resid = budget - used

        def _nz(v):
            return round(v, 2) if abs(v) > 0.005 else E

        return {
            "feo_budget": round(budget, 2) if budget else E,
            "planned": _nz(used),
            "contract": _nz(contract_cum),
            "ordered": _nz(ordered_cum),
            "delivered": _nz(delivered_cum),
            "paid": _nz(paid_cum),
            "fact_total": _nz(used),
            "residual": round(resid, 2) if (budget or abs(used) > 0.005) else E,
            "pct": (f"{round(used / budget * 100)}%" if budget > 0 else E),
            "contractor": contractor,
            "monthly": _nz(monthly),
        }

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План закупок"

    n_cols = len(HEADERS)
    last_col_letter = ws.cell(row=1, column=n_cols).column_letter

    title_cell = ws.cell(row=1, column=1, value=f"ПЛАН-ГРАФИК — {sub.name} ({sub.year})")
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{last_col_letter}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A3"

    row_num = 3
    seq = 0

    def _write_row_projected(values: dict, fill, font, height=None) -> int:
        """Пишет строку по словарю {key: значение} в порядке selected_keys —
        единственная точка записи строки листа «План закупок» (Задача D:
        проекция на выбранные столбцы, Задача B: number_format для денежных
        столбцов)."""
        nonlocal row_num
        for ci, key in enumerate(selected_keys, 1):
            val = values.get(key, "")
            cell = ws.cell(row=row_num, column=ci, value=val)
            cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            is_money = key in MONEY_COL_KEYS
            cell.alignment = RIGHT_ALIGN if (is_money or key in ("qty", "pct", "num")) else LEFT_ALIGN
            if is_money and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        if height is not None:
            ws.row_dimensions[row_num].height = height
        row_idx = row_num
        row_num += 1
        return row_idx

    def _set_doc_link(purchase_id, row_idx: int):
        """Гиперлинк «Открыть» в колонку docs (если выбрана) строки row_idx —
        ведёт на страницу заказа, где под авторизацией доступны все документы."""
        if not purchase_id:
            return
        ci = column_index(selected_keys, "docs")
        if ci is None:
            return
        cell = ws.cell(row=row_idx, column=ci)
        cell.value = "Открыть"
        cell.hyperlink = f"{base_url}/orders/{purchase_id}"
        cell.font = LINK_FONT

    def _purchased_item_values(pi: dict) -> tuple:
        """Готовит (values-словарь без name/money, price_note, cascade) для
        под-строки фактически закупленной позиции — общий код для трёх мест
        (под плановой позицией, под категорией, в секции «без категории»)."""
        price_note = f"    └ {pi['name']} — {format_ru_money(pi['unit_price'])} ₽/ед."
        status_txt = pi["status"]
        monthly_val = ""
        if pi.get("is_monthly"):
            cnt = pi.get("monthly_count")
            amt = pi.get("monthly_amount") or 0
            status_txt = f"{status_txt} · ежемес." + (f" ×{cnt}" if cnt else "")
            monthly_val = round(pi["total"], 2)
            if amt:
                price_note += f" ({format_ru_money(amt)} ₽/мес)"
        planned_a, contract_a, ordered_a, delivered_a, paid_a = cascade_by_stage(pi["raw_status"], pi["total"])
        total_display = 0.0 if pi["raw_status"] == "cancelled" else round(pi["total"], 2)
        values = {
            "name": price_note, "unit": pi["unit"], "qty": round(pi["qty"], 3),
            "planned": planned_a, "contract": contract_a, "ordered": ordered_a,
            "delivered": delivered_a, "paid": paid_a, "fact_total": total_display,
            "contractor": pi["contractor"], "status": status_txt,
            "monthly": monthly_val, "act": pi["act_number"],
        }
        # Группа «Договор и оплата» — только для под-строк фактических позиций
        # (есть purchase_id → сама закупка найдена) и только если хоть один из
        # этих столбцов выбран (CONTRACT_PAYMENT_COL_KEYS ∩ selected_keys).
        purchase_row = purchase_rows_by_id.get(pi.get("purchase_id"))
        if purchase_row is not None and CONTRACT_PAYMENT_COL_KEYS.intersection(selected_keys):
            for ck in CONTRACT_PAYMENT_COL_KEYS:
                if ck in selected_keys:
                    values[ck] = _purchase_cell_value(ck, purchase_row, purchase_export_ctx)
        return values, (planned_a, contract_a, ordered_a, delivered_a, paid_a)

    def _traverse(cat, direction_name="", type_name=""):
        nonlocal seq
        if cat.level == 1:
            direction_name = cat.name
            values = {"num": cat.code or "", "direction": cat.name}
            values.update(_money_cols_dict(cat.id, ""))
            _write_row_projected(values, L1_FILL, L1_FONT, height=22)
        elif cat.level == 2:
            type_name = cat.name
            values = {"direction": direction_name, "type": cat.name}
            values.update(_money_cols_dict(cat.id, ""))
            _write_row_projected(values, L2_FILL, L2_FONT)
        elif cat.level == 3:
            values = {"direction": direction_name, "type": type_name, "name": cat.name}
            values.update(_money_cols_dict(cat.id, cat_contractor_map.get(cat.id, "")))
            _write_row_projected(values, L3_FILL, L3_FONT)

            # Под-строки: закупки, привязанные напрямую к категории (без плановой статьи).
            cat_purchases = purchased_by_cat.get(cat.id, [])
            cat_sums = [0.0] * 5
            for pi in cat_purchases:
                sub_values, stages = _purchased_item_values(pi)
                for i in range(5):
                    cat_sums[i] += stages[i]
                row_idx = _write_row_projected(sub_values, SUB_FILL, SUB_FONT, height=16)
                _set_doc_link(pi["purchase_id"], row_idx)
            if cat_purchases:
                totals = {
                    "name": "    Итого по факту:",
                    "planned": round(cat_sums[0], 2), "contract": round(cat_sums[1], 2),
                    "ordered": round(cat_sums[2], 2), "delivered": round(cat_sums[3], 2),
                    "paid": round(cat_sums[4], 2),
                }
                _write_row_projected(totals, SUB_FILL, TOTAL_FONT, height=16)

            for item in items_by_cat.get(cat.id, []):
                seq += 1
                feo_budget = float(item.amount or 0)
                plan0 = _st(item.id, "plan_schedule", "work_in_progress", "wishes")
                contract0 = _st(item.id, "contracted")
                ordered0 = _st(item.id, "ordered")
                delivered0 = _st(item.id, "delivered")
                paid0 = _st(item.id, "paid")
                used = used_map.get(item.id, 0.0)
                contract_cum = contract0 + ordered0 + delivered0 + paid0
                ordered_cum = ordered0 + delivered0 + paid0
                delivered_cum = delivered0 + paid0
                paid_cum = paid0
                residual = feo_budget - used
                pct = round(used / feo_budget * 100) if feo_budget > 0 else 0
                contractor = contractor_map.get(item.id, "")
                status = "Выполнено" if pct >= 100 else ("В работе" if used > 0 else "Не начато")
                font = RED_FONT if used > feo_budget else ITEM_FONT
                values = {
                    "num": seq, "direction": direction_name, "type": type_name, "name": item.name,
                    "unit": item.unit or "", "qty": float(item.quantity or 0),
                    "feo_budget": round(feo_budget, 2), "planned": round(used, 2),
                    "contract": round(contract_cum, 2), "ordered": round(ordered_cum, 2),
                    "delivered": round(delivered_cum, 2), "paid": round(paid_cum, 2),
                    "fact_total": round(used, 2), "residual": round(residual, 2),
                    "pct": f"{pct}%", "contractor": contractor, "status": status,
                }
                _write_row_projected(values, NO_FILL, font)

                for pi in purchased_by_item.get(item.id, []):
                    sub_values, _stages = _purchased_item_values(pi)
                    row_idx = _write_row_projected(sub_values, SUB_FILL, SUB_FONT, height=16)
                    _set_doc_link(pi["purchase_id"], row_idx)

        for child in cats_by_parent.get(cat.id, []):
            _traverse(child, direction_name, type_name)

    for root in cats_by_parent.get(None, []):
        _traverse(root)

    # ── Секция: закупки, привязанные к субсидии, но без категории ФЭО ────────
    if unlinked_purchases:
        _write_row_projected(
            {"direction": "Закупки по субсидии без привязки к категории ФЭО"},
            L1_FILL, L1_FONT, height=22,
        )
        u_sums = [0.0] * 5
        for pi in unlinked_purchases:
            sub_values, stages = _purchased_item_values(pi)
            for i in range(5):
                u_sums[i] += stages[i]
            row_idx = _write_row_projected(sub_values, SUB_FILL, SUB_FONT, height=16)
            _set_doc_link(pi["purchase_id"], row_idx)
        _write_row_projected(
            {
                "name": "    Итого по факту:",
                "planned": round(u_sums[0], 2), "contract": round(u_sums[1], 2),
                "ordered": round(u_sums[2], 2), "delivered": round(u_sums[3], 2),
                "paid": round(u_sums[4], 2),
            },
            SUB_FILL, TOTAL_FONT, height=16,
        )

    last_row = row_num - 1
    # Задача C — высота строк по тексту (заголовок строка 2 + все строки данных).
    apply_row_heights(ws, range(2, last_row + 1))

    if summary_by_kind is not None:
        write_summary_sheet(wb, sub, summary_by_kind)
        sm = wb["Сводная"]
        apply_row_heights(sm, range(2, sm.max_row + 1))

    return wb
