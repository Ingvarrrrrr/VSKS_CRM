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

from app.services.plan_graph_export_columns import (
    MONEY_COL_KEYS,
    STAGE_MONEY_COL_KEYS,
    TOP_SUMMARY_EXCLUDED_KEYS,
    column_index,
    headers_and_widths,
    resolve_selected_keys,
)
from app.services.plan_graph_export_rows import MAX_DATA_ROW, cascade_by_stage, collect_plan_graph_rows
from app.services.plan_graph_export_summary_sheet import write_summary_sheet
from app.utils.xlsx_row_height import apply_row_heights

HEADER_ROW = 3
DATA_FIRST_ROW = 4
# Денежные столбцы, которые НИКОГДА не дублируются между уровнем-родителем и
# его потомками (payment_amount/unit_price — атрибуты КОНКРЕТНОЙ закупленной
# позиции, заполнены только в строках уровня «Закупка», в строках групп
# всегда пусто) — верхние строки 1/2 считают их ПРОСТЫМ SUM/SUBTOTAL по
# всему столбцу, без SUMIFS по уровню (владелец 08.10.2026, часть B).
_SIMPLE_TOTAL_MONEY_KEYS = MONEY_COL_KEYS - set(STAGE_MONEY_COL_KEYS) - {
    "feo_budget", "residual", "pct",
} - TOP_SUMMARY_EXCLUDED_KEYS

__all__ = ["build_live_plan_graph_xlsx", "cascade_by_stage"]

# Подписи столбца «Уровень» (владелец 09.10.2026) — 1/2/3 именованы как
# раньше; 4+ (дерево местами глубже) — обобщённая подпись.
_LEVEL_LABELS = {1: "Направление", 2: "Тип", 3: "Статья"}


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
    cat_status_map = data["cat_status_map"]
    cat_monthly_map = data["cat_monthly_map"]
    cat_contractor_map = data["cat_contractor_map"]
    # Факт по закупкам (под-строки) — читается из rows_info, см. ниже
    # (plan_graph_export_rows.collect_plan_graph_rows), не напрямую из data.

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
        """Роллап поддерева категории `cat` — СОБСТВЕННЫЙ факт/бюджет
        (cat_status_map/cat_monthly_map/items_by_cat для ЭТОЙ категории,
        независимо от того, есть ли у неё подкатегории) ПЛЮС рекурсивно
        поддеревья детей (владелец 09.10.2026, прод ФАДМ 2026_2: «плановые
        позиции и закупки висят и на level 1/2» — раньше категория с детьми
        игнорировала СВОИ прямые позиции/закупки целиком, считая только от
        детей). cat.budget (ручной) — ОТМЕНЯЕТ авторасчёт (свой + детей), как
        и раньше для листа (см. docstring FeoCategory.budget)."""
        if cat.id in subtree_map:
            return subtree_map[cat.id]
        children = cats_by_parent.get(cat.id, [])
        status_agg: dict[str, float] = {}
        for k, v in cat_status_map.get(cat.id, {}).items():
            status_agg[k] = status_agg.get(k, 0.0) + v
        monthly = cat_monthly_map.get(cat.id, 0.0)
        children_budget = 0.0
        for ch in children:
            r = _compute_subtree(ch)
            for k, v in r["status"].items():
                status_agg[k] = status_agg.get(k, 0.0) + v
            children_budget += r["budget"]
            monthly += r["monthly"]
        if cat.budget is not None:
            budget = float(cat.budget)
        else:
            own_items_budget = sum(float(it.amount or 0) for it in items_by_cat.get(cat.id, []))
            budget = own_items_budget + children_budget
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

    # Сбор пронумерованных («N»/«N.k») строк фактических закупленных позиций —
    # ОДИН проход, общий с листом «План закупок (по порядку)»
    # (app.services.plan_graph_export_flat_sheet), см. plan_graph_export_rows.
    rows_info = collect_plan_graph_rows(data)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План закупок (по направлениям)"

    n_cols = len(HEADERS)
    last_col_letter = ws.cell(row=1, column=n_cols).column_letter
    level_ci = column_index(selected_keys, "level")

    # Часть B (владелец 08.10.2026): строка 1 — «Итого всего» (подпись + SUM/
    # SUMIFS), строка 2 — «Итого по фильтру» (SUBTOTAL), строка 3 — шапка,
    # данные — с 4-й. Лист иерархический: SUM обычный задвоил бы группы, —
    # «Запланировано/Договор/Заказано/Поставлено/Оплачено/Фактически/Ежемес.»
    # считаются SUMIFS по служебному столбцу «Уровень» = "Закупка" (листовые
    # строки закупок — единственные НЕ формула-SUBTOTAL ячейки этих
    # столбцов); «Бюджет ФЭО» — SUMIFS по «Уровень» = "Направление" (бюджет
    # уже агрегирован вручную/по дереву на уровне направления); «Остаток»/
    # «% исполнения» — верхние ячейки пустые (ФЭО статьи не обязан совпадать
    # с суммой позиций, см. _money_cols_dict); остальные денежные столбцы
    # (unit_price/payment_amount — атрибуты конкретной закупки, никогда не
    # дублируются по дереву) — простой SUM/SUBTOTAL по всему столбцу.
    label_font = Font(bold=True, size=9, color="1E3A5F")
    ws.cell(row=1, column=1, value=f"{sub.name} ({sub.year}) — итого всего").font = label_font
    ws.cell(row=2, column=1, value="Итого по фильтру").font = label_font
    for ci, key in enumerate(selected_keys, 1):
        if key not in MONEY_COL_KEYS or key in TOP_SUMMARY_EXCLUDED_KEYS:
            continue
        col_letter = ws.cell(row=1, column=ci).column_letter
        rng = f"{col_letter}{DATA_FIRST_ROW}:{col_letter}{MAX_DATA_ROW}"
        if key in STAGE_MONEY_COL_KEYS and level_ci is not None:
            level_letter = ws.cell(row=1, column=level_ci).column_letter
            level_rng = f"{level_letter}{DATA_FIRST_ROW}:{level_letter}{MAX_DATA_ROW}"
            ws.cell(row=1, column=ci, value=f'=SUMIFS({rng},{level_rng},"Закупка")').font = label_font
            ws.cell(row=2, column=ci, value=f"=SUBTOTAL(109,{rng})").font = label_font
        elif key == "feo_budget" and level_ci is not None:
            level_letter = ws.cell(row=1, column=level_ci).column_letter
            level_rng = f"{level_letter}{DATA_FIRST_ROW}:{level_letter}{MAX_DATA_ROW}"
            ws.cell(row=1, column=ci, value=f'=SUMIFS({rng},{level_rng},"Направление")').font = label_font
        elif key in _SIMPLE_TOTAL_MONEY_KEYS:
            ws.cell(row=1, column=ci, value=f"=SUM({rng})").font = label_font
            ws.cell(row=2, column=ci, value=f"=SUBTOTAL(109,{rng})").font = label_font

    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    row_num = DATA_FIRST_ROW

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

    def _write_fact_rows(rows: list) -> None:
        """Пишет строки фактических позиций (уже собранные
        plan_graph_export_rows.collect_plan_graph_rows) — leaf-уровень
        «Закупка», значения литеральные (не формула)."""
        for row in rows:
            row_idx = _write_row_projected(row, SUB_FILL, SUB_FONT, height=16)
            _set_doc_link(row.get("_purchase_id"), row_idx)

    def _apply_group_subtotal(row_idx: int, start: int, end: int) -> None:
        """Перезаписывает денежные столбцы-стадии (STAGE_MONEY_COL_KEYS)
        строки-группы `row_idx` формулой =SUBTOTAL(109, start:end) — владелец
        08.10.2026, часть B: группа (направление/тип/статья/плановая
        позиция) больше не несёт литеральное число по этим столбцам сама —
        его считает Excel по диапазону строк-потомков (сплошной блок под
        родителем). Диапазон пуст (нет потомков, start > end) — литеральное
        значение (уже записанное при _write_row_projected, обычно 0) не
        трогаем."""
        if end < start:
            return
        for key in STAGE_MONEY_COL_KEYS:
            ci = column_index(selected_keys, key)
            if ci is None:
                continue
            col_letter = ws.cell(row=row_idx, column=ci).column_letter
            ws.cell(row=row_idx, column=ci, value=f"=SUBTOTAL(109,{col_letter}{start}:{col_letter}{end})")

    def _traverse(cat, direction_name="", type_name=""):
        """Пишет строку категории `cat` ЛЮБОГО уровня (1, 2, 3, 4+) и ВСЁ её
        содержимое — собственные закупки (fact_rows_by_cat), собственные
        плановые позиции (items_order_by_cat) с их закупками, затем
        подкатегории — владелец 09.10.2026, прод ФАДМ 2026_2: «плановые
        позиции и закупки висят и на level 1/2» (раньше это содержимое
        писалось ТОЛЬКО для level==3, выше/глубже — молча терялось)."""
        if cat.level == 1:
            direction_name = cat.name
            values = {"num": cat.code or "", "direction": cat.name, "level": _LEVEL_LABELS.get(1, "Направление")}
            fill, font, height = L1_FILL, L1_FONT, 22
        elif cat.level == 2:
            type_name = cat.name
            values = {"direction": direction_name, "type": cat.name, "level": _LEVEL_LABELS.get(2, "Тип")}
            fill, font, height = L2_FILL, L2_FONT, None
        else:
            values = {
                "direction": direction_name, "type": type_name, "name": cat.name,
                "level": _LEVEL_LABELS.get(cat.level, f"Категория {cat.level}"),
            }
            fill, font, height = L3_FILL, L3_FONT, None
        values.update(_money_cols_dict(cat.id, cat_contractor_map.get(cat.id, "")))
        row_idx = _write_row_projected(values, fill, font, height=height)

        start_row = row_num

        # Собственные закупки категории (ЛЮБОЙ уровень — без плановой статьи).
        _write_fact_rows(rows_info["fact_rows_by_cat"].get(cat.id, []))

        # Собственные плановые позиции категории (ЛЮБОЙ уровень).
        for item in rows_info["items_order_by_cat"].get(cat.id, []):
            seq = rows_info["item_seq"][item.id]
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
            item_font = RED_FONT if used > feo_budget else ITEM_FONT
            item_values = {
                "num": seq, "direction": direction_name, "type": type_name, "name": item.name,
                "level": "Позиция",
                "unit": item.unit or "", "qty": float(item.quantity or 0),
                "feo_budget": round(feo_budget, 2), "planned": round(used, 2),
                "contract": round(contract_cum, 2), "ordered": round(ordered_cum, 2),
                "delivered": round(delivered_cum, 2), "paid": round(paid_cum, 2),
                "fact_total": round(used, 2), "residual": round(residual, 2),
                "pct": f"{pct}%", "contractor": contractor, "status": status,
            }
            item_row_idx = _write_row_projected(item_values, NO_FILL, item_font)

            item_start = row_num
            _write_fact_rows(rows_info["fact_rows_by_item"].get(item.id, []))
            _apply_group_subtotal(item_row_idx, item_start, row_num - 1)

        for child in cats_by_parent.get(cat.id, []):
            _traverse(child, direction_name, type_name)

        end_row = row_num - 1
        _apply_group_subtotal(row_idx, start_row, end_row)

    for root in cats_by_parent.get(None, []):
        _traverse(root)

    # ── Секция: закупки, привязанные к субсидии, но без категории ФЭО ────────
    unlinked_rows = rows_info["fact_rows_unlinked"]
    if unlinked_rows:
        unlinked_header_idx = _write_row_projected(
            {"direction": "Закупки по субсидии без привязки к категории ФЭО", "level": "Направление"},
            L1_FILL, L1_FONT, height=22,
        )
        unlinked_start = row_num
        _write_fact_rows(unlinked_rows)
        _apply_group_subtotal(unlinked_header_idx, unlinked_start, row_num - 1)

    last_row = row_num - 1
    # Автофильтр по строке заголовков (владелец 08.10.2026, часть B).
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"
    # Задача C — высота строк по тексту (строки 1-3 + все строки данных).
    apply_row_heights(ws, range(1, last_row + 1))

    if summary_by_kind is not None:
        # Часть C (владелец 08.10.2026): «Остаток на договорах, ₽» по видам —
        # Σ remaining групп contract_balances (ПРАВИЛО №6, читаем уже
        # посчитанные группы, не второй расчёт).
        contract_remaining_by_kind: dict = {}
        for _g in data.get("contract_balance_groups") or []:
            contract_remaining_by_kind[_g["kind"]] = contract_remaining_by_kind.get(_g["kind"], 0.0) + _g["remaining"]
        write_summary_sheet(wb, sub, summary_by_kind, contract_remaining_by_kind)
        sm = wb["Сводная"]
        apply_row_heights(sm, range(2, sm.max_row + 1))

    return wb
