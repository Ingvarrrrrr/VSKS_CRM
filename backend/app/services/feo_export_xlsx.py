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
# Формат выгрузки «туда-обратно» (задача владельца 20.10.2026) — лист _meta
# несёт версию формата, читает app.services.feo_roundtrip_import.parse
# (ПРАВИЛО №6: одна константа версии на экспорт и импорт, не дублировать
# строкой по месту).
ROUNDTRIP_FORMAT_VERSION = "feo-export-1"
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


async def build_feo_export_workbook(db, sub, selected_keys: list, with_summary: bool = False):
    """Строит openpyxl.Workbook «Выгрузить ФЭО» по субсидии `sub` (столбцы —
    `selected_keys`, см. app.services.feo_export_columns). Единственная точка
    обращения к БД для этой выгрузки — одна выборка категорий, одна выборка
    позиций (_active_feo_items_with_amount), один вызов
    planned_item_stage_segments на ВСЕ позиции субсидии и один вызов
    category_plan_stage_segments на ВСЕ листовые категории (не в цикле —
    задача владельца, п.3: «одним вызовом на все позиции субсидии»).

    Само рисование дерева по готовым данным (без обращения к БД) — в
    render_feo_tree_sheet ниже, ПРАВИЛО №6: шаблон «Загрузить выгрузку ФЭО»
    (app.routers.feo_roundtrip_import, GET .../roundtrip/template) зовёт ТОТ
    ЖЕ render_feo_tree_sheet с вымышленным деревом в памяти вместо второй
    копии оформления/формул."""
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
    ws, top_rows, last_row = render_feo_tree_sheet(
        wb, sub.name[:31], selected_keys, roots, items_by_cat,
        item_segments_map, cat_segments_map, totals_label=f"{sub.name} — итого всего",
    )

    if with_summary:
        from app.services.feo_export_summary import write_feo_summary_and_dashboard
        top_rows_info = [{"name": root["cat"].name, "row": tr} for root, tr in zip(roots, top_rows)]
        write_feo_summary_and_dashboard(wb, sub, ws.title, selected_keys, top_rows_info)

    _write_roundtrip_meta_sheet(wb, sub.id)

    return wb


def render_feo_tree_sheet(
    wb, sheet_title: str, selected_keys: list, roots: list,
    items_by_cat: dict, item_segments_map: dict, cat_segments_map: dict,
    *, totals_label: str, include_row_ids: bool = True,
):
    """Рисует дерево категорий/позиций на активном листе новой книги `wb` —
    ЕДИНСТВЕННОЕ место, которое знает оформление/формулы выгрузки «Выгрузить
    ФЭО» (ПРАВИЛО №6). Без обращения к БД: `roots`/`items_by_cat` — те же
    структуры, что строит build_feo_export_workbook (`cat`-объекты нужны
    атрибуты name/code/appendix/budget/is_active/level/id; `item`-объекты —
    name/quantity/unit/feo_amount/amount/is_active/id), `item_segments_map`/
    `cat_segments_map` — {id: {"segments": [...]}}  (пустой словарь — у строк
    просто не будет накопленных стадий, безопасно для вымышленного дерева
    шаблона). `id` объекта нужен настоящим (хотя бы синтетическим уникальным),
    чтобы items_by_cat.get(c.id)/сегменты работали, НО колонка «№ в системе»
    в файле всё равно пишется пустой у всех строк — пример в шаблоне
    «Загрузить выгрузку ФЭО» (GET .../roundtrip/template) весь состоит из
    НОВЫХ строк (include_row_ids=False, см. app.routers.feo_roundtrip_import).

    Возвращает (ws, top_rows, last_row) — top_rows/last_row нужны вызывающему
    коду только для необязательных листов «Сводная»/«Дашборд» выгрузки."""
    ws = wb.active
    ws.title = sheet_title
    ws.sheet_properties.outlinePr.summaryBelow = False

    HEADER_FILL = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
    L1_FILL = PatternFill(start_color="9DC3E6", end_color="9DC3E6", fill_type="solid")
    L2_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
    L3_FILL = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
    L4_FILL = PatternFill(start_color="EEF4FB", end_color="EEF4FB", fill_type="solid")
    BOLD_FONT = Font(bold=True)
    SEMI_FONT = Font(bold=False)
    ITEM_FONT = Font(italic=True, color="475569")
    TOTAL_FONT = Font(bold=True, color="1E3A5F")
    NUM_FMT = "#,##0.00"
    _MAX_OUTLINE = 7

    headers, widths = headers_and_widths(selected_keys)
    n_cols = len(selected_keys)

    ws.cell(row=1, column=1, value=totals_label).font = TOTAL_FONT
    ws.cell(row=2, column=1, value="Итого по фильтру").font = TOTAL_FONT

    for col_idx, (header, width) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[HEADER_ROW].height = 32
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    # Загрузка обратно (владелец 20.10.2026): колонка «№ в системе» всегда
    # есть в файле (row_id — в DEFAULT_KEYS, см. feo_export_columns.py), но
    # скрыта от человека — несёт только id для app.services.
    # feo_roundtrip_import.parse при обратной загрузке.
    ci_row_id = column_index(selected_keys, "row_id")
    if ci_row_id is not None:
        ws.column_dimensions[ws.cell(row=HEADER_ROW, column=ci_row_id).column_letter].hidden = True

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
            "row_type": "Позиция",
            "row_id": (f"p{item.id}" if item.id is not None else "") if include_row_ids else "",
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
        """Денежные/стадийные столбцы строки-категории = SUM(прямые дети).
        НЕ SUBTOTAL: SUBTOTAL(9,...) игнорирует ячейки, которые сами —
        результат другого SUBTOTAL (Excel пропускает вложенные subtotal-
        формулы при агрегации), поэтому категория с подкатегориями получала
        0 — баг владельца 20.10.2026 (п.1). SUM считает обычные ссылки на
        ячейки честно, независимо от того, что там — число или формула."""
        keys = ("feo", "plan", "ordered", "to_order", "residual") + STAGE_AMOUNT_KEYS
        for key in keys:
            ci = column_index(selected_keys, key)
            if ci is None:
                continue
            if not child_rows:
                continue
            col_letter = ws.cell(row=row_idx, column=ci).column_letter
            refs = ",".join(f"{col_letter}{cr}" for cr in child_rows)
            cell = ws.cell(row_idx, ci, value=f"=SUM({refs})")
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
            # «Категория» — есть дети (подкатегории и/или собственные
            # плановые позиции, т.е. в строке будет SUM-формула по ним);
            # «Категория без позиций» — лист без детей (значения — литералы
            # budget/stage_vals выше), см. колонку row_type в
            # feo_export_columns.py.
            "row_type": "Категория без позиций" if is_leaf else "Категория",
            "row_id": (f"c{c.id}" if c.id is not None else "") if include_row_ids else "",
        }
        if is_leaf:
            values["plan"] = own_plan
            values.update(stage_vals)
        if c.level == 1:
            fill = L1_FILL
        elif c.level == 2:
            fill = L2_FILL
        elif c.level == 3:
            fill = L3_FILL
        else:
            fill = L4_FILL
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

    # Строка 1 «Итого всего» — SUM по корневым категориям верхнего уровня
    # (их собственные значения — уже SUM по всем потомкам рекурсивно).
    #
    # Строка 2 «Итого по фильтру» — НЕ SUBTOTAL(9, весь_столбец): это
    # задвоило бы суммы (строки категорий сами содержат SUM по детям, и
    # SUBTOTAL(9,...) сложил бы и категорию, и её же позиции ещё раз).
    # SUMPRODUCT(SUBTOTAL(9,OFFSET(...)),--(тип<>"Категория")) — считает
    # по каждой строке данных отдельный SUBTOTAL(9, одна ячейка) (= 0, если
    # строка скрыта автофильтром «по фильтру», иначе — значение ячейки) и
    # умножает на 1/0 по столбцу «Тип строки» (row_type): складываются
    # только «Позиция» и «Категория без позиций», категории с SUM-формулой
    # исключены, чтобы не задваивать.
    money_keys = ("feo", "plan", "ordered", "to_order", "residual") + STAGE_AMOUNT_KEYS
    ci_row_type = column_index(selected_keys, "row_type")
    row_type_col_letter = ws.cell(row=1, column=ci_row_type).column_letter if ci_row_type else None
    for key in money_keys:
        ci = column_index(selected_keys, key)
        if ci is None:
            continue
        col_letter = ws.cell(row=1, column=ci).column_letter
        if top_rows:
            refs = ",".join(f"{col_letter}{r}" for r in top_rows)
            ws.cell(row=1, column=ci, value=f"=SUM({refs})").font = TOTAL_FONT
        if last_row >= DATA_FIRST_ROW and row_type_col_letter:
            first_cell = f"{col_letter}{DATA_FIRST_ROW}"
            formula = (
                f"=SUMPRODUCT(SUBTOTAL(9,OFFSET({first_cell},"
                f"ROW({col_letter}{DATA_FIRST_ROW}:{col_letter}{last_row})-ROW({first_cell}),0)),"
                f"--(${row_type_col_letter}${DATA_FIRST_ROW}:${row_type_col_letter}${last_row}<>\"Категория\"))"
            )
            ws.cell(row=2, column=ci, value=formula).font = TOTAL_FONT
        ws.cell(row=1, column=ci).number_format = NUM_FMT
        ws.cell(row=2, column=ci).number_format = NUM_FMT

    last_col_letter = ws.cell(row=HEADER_ROW, column=n_cols).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"

    return ws, top_rows, last_row


def _write_roundtrip_meta_sheet(wb, subsidy_id: Optional[int]) -> None:
    """Скрытый лист `_meta` — subsidy_id/дата выгрузки/версия формата, чтобы
    app.services.feo_roundtrip_import.parse могла при загрузке назад
    отличить «файл этой субсидии» от «файл другой субсидии» (см. докстринг
    модуля parse.py — расхождение subsidy_id там жёстко отклоняется, без
    флага-обхода). Пустая субсидия (нет категорий) экспортируется тем же
    кодом ВЫШЕ без единой строки данных — лист _meta пишется всегда, это и
    есть «шаблон для заполнения с нуля» из задачи владельца."""
    from datetime import datetime, timezone

    meta = wb.create_sheet("_meta")
    meta.sheet_state = "hidden"
    meta["A1"] = "subsidy_id"
    meta["B1"] = subsidy_id
    meta["A2"] = "exported_at"
    meta["B2"] = datetime.now(timezone.utc).isoformat()
    meta["A3"] = "format_version"
    meta["B3"] = ROUNDTRIP_FORMAT_VERSION


def build_feo_roundtrip_template_workbook():
    """Шаблон формата «Выгрузить ФЭО» для загрузки обратно (GET
    .../roundtrip/template, задача владельца 20.10.2026, часть «шаблон»).
    Строится ТЕМ ЖЕ render_feo_tree_sheet, что и настоящая выгрузка (ПРАВИЛО
    №6) — дерево ниже вымышленное (волонтёрская тематика, никаких реальных
    субсидий/организаций), БД не трогаем вовсе (синхронная функция).

    Колонки — Наименование/Код/Прил./Кол-во по ФЭО/Ед./Финансирование по
    ФЭО/Запланировано/Активна/Тип строки (+ скрытая «№ в системе», всегда
    пустая — include_row_ids=False, строки примера «новые»). Колонки заказов/
    стадий сюда не включаем (задача владельца, п.2) — их нет в
    READABLE_KEYS (feo_roundtrip_import/parse.py), шаблон человек заполняет
    руками, стадии считает система.

    _meta пишется с subsidy_id=None — check_meta_mismatch (feo_roundtrip_
    import/diff.py) не отклоняет файл ни для какой субсидии (мета без
    subsidy_id трактуется как «не привязан», это НЕ второй случай
    расхождения, которое там же жёстко отклоняется)."""
    if Workbook is None:
        raise RuntimeError("openpyxl не установлен")

    from types import SimpleNamespace

    from app.services.feo_export_columns import resolve_selected_keys

    selected_keys = resolve_selected_keys("code,app,feo_qty,feo_unit,feo,plan,active")

    def _cat(id_, name, level, *, code="", appendix="", budget=None, active=True):
        return SimpleNamespace(id=id_, name=name, code=code, appendix=appendix, budget=budget, is_active=active, level=level)

    def _item(id_, name, *, qty, unit, feo, plan, active=True):
        return SimpleNamespace(id=id_, name=name, quantity=qty, unit=unit, feo_amount=feo, amount=plan, is_active=active)

    cat_lager = _cat(-1, "Оснащение полевого лагеря", 1)
    cat_tents = _cat(-2, "Палатки и спальное", 2)
    cat_kitchen_parent = _cat(-3, "Освещение и кухня", 2)
    cat_kitchen = _cat(-4, "Кухонный инвентарь", 3)
    cat_power = _cat(-5, "Электроснабжение", 2, budget=80000)

    cat_training = _cat(-6, "Обучение добровольцев", 1)
    cat_training_org = _cat(-7, "Организация обучения", 2)

    items_by_cat = {
        cat_tents.id: [
            _item(-101, "Палатка 4-местная", qty=5, unit="шт", feo=250000, plan=250000),
            _item(-102, "Спальник", qty=20, unit="шт", feo=100000, plan=90000),
        ],
        cat_kitchen.id: [
            _item(-103, "Казан походный", qty=3, unit="шт", feo=27000, plan=27000),
            _item(-104, "Горелка газовая", qty=4, unit="шт", feo=18000, plan=18000, active=False),
        ],
        cat_training_org.id: [
            _item(-105, "Аренда зала", qty=3, unit="дн.", feo=120000, plan=120000),
            _item(-106, "Печать методичек", qty=200, unit="шт", feo=45000, plan=40000),
        ],
    }

    node_tents = {"cat": cat_tents, "children": []}
    node_kitchen = {"cat": cat_kitchen, "children": []}
    node_kitchen_parent = {"cat": cat_kitchen_parent, "children": [node_kitchen]}
    node_power = {"cat": cat_power, "children": []}
    node_lager = {"cat": cat_lager, "children": [node_tents, node_kitchen_parent, node_power]}

    node_training_org = {"cat": cat_training_org, "children": []}
    node_training = {"cat": cat_training, "children": [node_training_org]}

    roots = [node_lager, node_training]

    wb = Workbook()
    render_feo_tree_sheet(
        wb, "Шаблон", selected_keys, roots, items_by_cat, {}, {},
        totals_label="Шаблон — итого всего", include_row_ids=False,
    )

    _write_feo_roundtrip_howto_sheet(wb)
    _write_roundtrip_meta_sheet(wb, None)

    wb.active = 0
    return wb


def _write_feo_roundtrip_howto_sheet(wb) -> None:
    """Лист «Как заполнять» шаблона «Выгрузить ФЭО» (загрузка обратно) —
    текстовые правила, см. docstring build_feo_roundtrip_template_workbook."""
    ws = wb.create_sheet("Как заполнять")
    ws.column_dimensions["A"].width = 115
    rules = [
        "Как заполнять шаблон «Выгрузить ФЭО» (загрузка обратно)",
        "",
        "Этот файл — тот же формат, что скачивается через «Ещё» → «Выгрузить ФЭО». "
        "Загружается обратно через «Ещё» → «Загрузить выгрузку ФЭО»: сначала показывается предпросмотр "
        "(что изменится/что создастся), и только после подтверждения — запись в систему.",
        "",
        "Примеры на листе «Шаблон» ВЫМЫШЛЕННЫЕ («Оснащение полевого лагеря», «Обучение добровольцев» и т.п.) — "
        "удалите их и впишите свои направления/категории/позиции.",
        "",
        "«Тип строки»:",
        "  Категория — у строки есть вложенные строки (подкатегории и/или плановые позиции); суммы в такой строке считаются формулой по детям, вручную их менять не нужно.",
        "  Категория без позиций — лист дерева без вложенных строк, но сам несёт сумму по ФЭО (например «Электроснабжение» в примере).",
        "  Позиция — конкретный товар/услуга внутри категории (у неё есть количество/ед./сумма по ФЭО и план).",
        "",
        "Уровень вложенности задаётся ОДНИМ из двух способов:",
        "  — группировкой Excel (выделите строки → Данные → Группировать) — предпочтительно, так же сделан этот шаблон;",
        "  — ИЛИ отступом: 2 пробела в начале «Наименования» на каждый уровень вложенности (если группировку не ставили).",
        "",
        "Какие колонки загружаются: Наименование, Код, Прил., Кол-во по ФЭО, Ед., «Финансирование по ФЭО» (у позиций и у «Категория без позиций»), "
        "«Запланировано» (только у позиций), Активна (Да/Нет). Суммы категорий с детьми — формулы, считаются сами, их трогать не нужно. "
        "Колонки заказов и стадий закупки в этот шаблон не включены — их считает система, в загрузке они не участвуют.",
        "",
        "«№ в системе» — скрытая служебная колонка. В выгрузке УЖЕ существующей субсидии по ней строки находят себя в базе при повторной загрузке; "
        "в этом шаблоне она пустая у всех строк — все строки примера новые. Не копируйте номер из одной строки в другую.",
        "",
        "Числа — без знака «₽», пробелы-разделители тысяч и запятая вместо точки допускаются.",
        "",
        "Строки, которые вы удалите из файла перед загрузкой, в системе НЕ удаляются — чтобы отключить существующую категорию/позицию, "
        "поставьте ей «Активна = Нет», а не убирайте строку из файла.",
    ]
    for line in rules:
        ws.append([line])
    ws["A1"].font = Font(bold=True, size=12)
