"""Builds the purchase import-template Excel workbook.

Split out of purchase_import_template.py (refactor, 2026-09, Правило №5).
Owns: sheet layout («Закупки» / «Справочники» / «Справочник колонок»),
DataValidation wiring, and the cascading ФЭО Ур.1..5 dropdown lists built
from the subsidy's FeoCategory tree. The router stays thin: auth/visibility
checks + calling build_purchase_import_template_workbook() + streaming the
result.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services.import_template_spec import _COL_SPEC
from app.services.import_template_examples import (
    _TEMPLATE_EXAMPLE_ROW,
    _TEMPLATE_EXAMPLE_ROW_2,
)
from app.services.import_template_dropdowns import (
    _DD_CONTRACT_TYPE,
    _DD_STATUS,
    _DD_SUBSTATUS,
    _DD_METHOD,
    _DD_BASIS,
    _DD_VAT_APPLICABLE,
    _DD_VAT_RATE,
    _DD_PREPAYMENT,
    _DD_MONTHLY,
    _DD_ITEM_TYPE,
    _DD_PAYMENT_BASIS,
    _DD_UNIT,
    _DD_QUARTER,
    _DD_VAT_MODE,
    _DD_DELIVERY_REGION,
    _DD_EVENT_REGION,
)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.workbook.defined_name import DefinedName
except ImportError:
    Workbook = None
    DataValidation = None
    DefinedName = None

logger = logging.getLogger(__name__)


def _build_dv_prompt(spec: dict) -> tuple[str, str]:
    """Строит (promptTitle, prompt) для DataValidation, соблюдая лимиты Excel:
    promptTitle <= 32 символа, prompt <= 255 символов (обрезка по границе слова)."""

    # --- promptTitle: заголовок колонки, макс 32 символа ---
    title_raw = spec["header"]
    prompt_title = title_raw if len(title_raw) <= 32 else title_raw[:32]

    # --- prompt: короткий текст из полей spec ---
    parts: list[str] = []
    if spec.get("required"):
        parts.append("Обязательное поле.")

    # Первое предложение/строка comment
    comment_raw = spec.get("comment", "")
    first_sentence = comment_raw.split("\n")[0].split(". ")[0]
    if first_sentence and not first_sentence.endswith("."):
        first_sentence += "."
    if first_sentence:
        parts.append(first_sentence)

    if spec.get("if_empty"):
        parts.append(f"Если не заполнено: {spec['if_empty']}")

    if spec.get("_dd"):
        parts.append("Можно выбрать из списка или вписать своё.")

    full_prompt = "\n".join(parts)

    # Обрезка до 255 символов по границе слова
    MAX_PROMPT = 255
    if len(full_prompt) > MAX_PROMPT:
        cut = full_prompt[:MAX_PROMPT - 1]
        # ищем последний пробел или перенос
        boundary = max(cut.rfind(" "), cut.rfind("\n"))
        if boundary > 0:
            cut = cut[:boundary]
        full_prompt = cut.rstrip() + "…"

    return prompt_title, full_prompt


async def build_purchase_import_template_workbook(
    db: AsyncSession,
    subsidy_id: Optional[int],
    subsidy_name: Optional[str],
) -> "Workbook":
    """Builds the full workbook for GET /api/purchases/import/template.

    Caller (router) is responsible for: checking Workbook is not None,
    checking subsidy visibility, resolving subsidy_name, and streaming the
    saved workbook back as an .xlsx response. Behaviour (cell content, sheet
    layout, DataValidation, cascading ФЭО lists) is unchanged from the
    pre-split monolithic router.
    """
    feo_warning: Optional[str] = None
    if subsidy_id is None:
        feo_warning = (
            "Шаблон скачан без выбранной субсидии — направления расходов (ФЭО) в него не подставлены "
            "и связанные списки Ур.1→Ур.5 не работают. Выберите субсидию в диалоге импорта и скачайте шаблон заново."
        )

    wb = Workbook()

    fill_req  = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    fill_opt  = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    font_hdr  = Font(color="FFFFFF", bold=True, size=11)
    align_c   = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # =========================================================================
    # Sheet «Справочники» — создаём ДО «Закупки», чтобы потом добавить DataValidation
    # =========================================================================
    # Карта: имя переменной → (defined_name, header_label, dd_list)
    _DD_REGISTRY = {
        "_DD_CONTRACT_TYPE":   ("dd_contract_type",  "Тип договора",             _DD_CONTRACT_TYPE),
        "_DD_STATUS":          ("dd_status",          "Этап закупки",             _DD_STATUS),
        "_DD_SUBSTATUS":       ("dd_substatus",       "Подстатус",                _DD_SUBSTATUS),
        "_DD_METHOD":          ("dd_method",          "Способ закупки",           _DD_METHOD),
        "_DD_BASIS":           ("dd_basis",           "Основание закупки",        _DD_BASIS),
        "_DD_VAT_APPLICABLE":  ("dd_vat_applicable",  "НДС применяется",         _DD_VAT_APPLICABLE),
        "_DD_VAT_RATE":        ("dd_vat_rate",        "Ставка НДС",               _DD_VAT_RATE),
        "_DD_PREPAYMENT":      ("dd_prepayment",      "Предоплата",               _DD_PREPAYMENT),
        "_DD_MONTHLY":         ("dd_monthly",         "Ежемесячный платёж",       _DD_MONTHLY),
        "_DD_ITEM_TYPE":       ("dd_item_type",       "Тип позиции",              _DD_ITEM_TYPE),
        "_DD_PAYMENT_BASIS":   ("dd_payment_basis",   "Основание для оплаты",     _DD_PAYMENT_BASIS),
        "_DD_UNIT":            ("dd_unit",            "Ед. изм.",                 _DD_UNIT),
        "_DD_QUARTER":         ("dd_quarter",         "Квартал обязательств",     _DD_QUARTER),
        "_DD_VAT_MODE":        ("dd_vat_mode",        "Режим НДС",                _DD_VAT_MODE),
        "_DD_DELIVERY_REGION": ("dd_delivery_region", "Регион поставки",          _DD_DELIVERY_REGION),
        "_DD_EVENT_REGION":    ("dd_event_region",    "Регион мероприятия",       _DD_EVENT_REGION),
    }

    # Добавляем лист «Справочники» как второй (будет Sheet2)
    # Сначала создаём активный лист, потом переименуем
    wb_ref_ws = wb.create_sheet(title="Справочники")

    ref_hdr_font  = Font(bold=True, size=10)
    ref_hdr_fill  = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
    ref_val_align = Alignment(wrap_text=False, vertical="top")
    ref_hint_font = Font(italic=True, color="6B7280", size=9)

    # Строка-подсказка в строке 1
    hint_cell = wb_ref_ws.cell(1, 1,
        "Допишите свои значения в пустые ячейки под списком — они появятся в выпадающих списках на листе «Закупки»")
    hint_cell.font = ref_hint_font
    hint_cell.alignment = Alignment(wrap_text=True)
    wb_ref_ws.row_dimensions[1].height = 28

    # Словарь: dd_var_name → (col_letter, first_data_row, last_data_row)
    # для построения формул DataValidation
    _dd_ref_ranges: dict[str, str] = {}

    # Каждый справочник — отдельная колонка, начиная со строки 2
    for col_i, (dd_var_name, (dn_name, hdr_label, dd_list)) in enumerate(_DD_REGISTRY.items(), 1):
        # Заголовок колонки
        hdr_cell = wb_ref_ws.cell(2, col_i, hdr_label)
        hdr_cell.font = ref_hdr_font
        hdr_cell.fill = ref_hdr_fill
        hdr_cell.alignment = Alignment(horizontal="center")

        n_values = len(dd_list)
        # Диапазон = 2× числа значений (пользователь может дописать в пустые ячейки)
        slot_count = n_values * 2

        # Записываем значения начиная со строки 3
        for row_j, (label, _key) in enumerate(dd_list, 1):
            wb_ref_ws.cell(2 + row_j, col_i, label).alignment = ref_val_align

        col_letter = wb_ref_ws.cell(1, col_i).column_letter
        first_data_row = 3               # строка 3 = первое значение
        last_data_row  = 2 + slot_count  # = строка 3 + (slot_count-1)

        # Именованный диапазон уровня книги (надёжнее прямой ссылки на лист в DV)
        if DefinedName is not None:
            attr_text = f"'Справочники'!${col_letter}${first_data_row}:${col_letter}${last_data_row}"
            wb.defined_names[dn_name] = DefinedName(dn_name, attr_text=attr_text)

        # Ключ → имя именованного диапазона для DataValidation
        _dd_ref_ranges[dd_var_name] = dn_name

        # Ширина колонки
        max_len = max((len(lbl) for lbl, _ in dd_list), default=10)
        wb_ref_ws.column_dimensions[col_letter].width = max(max_len + 4, len(hdr_label) + 2, 16)

    wb_ref_ws.freeze_panes = "A3"

    # =========================================================================
    # Sheet 1: «Закупки»
    # =========================================================================
    ws = wb.active
    ws.title = "Закупки"

    headers = [s["header"] for s in _COL_SPEC]
    ws.append(headers)

    for i, spec in enumerate(_COL_SPEC, 1):
        c = ws.cell(1, i)
        c.fill = fill_req if spec["required"] else fill_opt
        c.font = font_hdr
        c.alignment = align_c

    ws.append(_TEMPLATE_EXAMPLE_ROW)
    ws.append(_TEMPLATE_EXAMPLE_ROW_2)

    for i, spec in enumerate(_COL_SPEC, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = spec["width"]

    ws.row_dimensions[1].height = 38
    ws.freeze_panes = "A2"

    # ---- DataValidation: два DV на каждую колонку — шапка (строка 1) и данные (2:1000) ----
    # Два непересекающихся диапазона не конфликтуют в Excel.
    # Шапка: только подсказка (type=None), данные: подсказка + список (если есть).
    if DataValidation is not None:
        for col_i, spec in enumerate(_COL_SPEC, 1):
            col_letter = ws.cell(1, col_i).column_letter
            dd_var = spec.get("_dd")
            ref_formula = _dd_ref_ranges.get(dd_var) if dd_var else None

            prompt_title, prompt_text = _build_dv_prompt(spec)

            # DV на шапку (строка 1): только подсказка, без списка
            dv_hdr = DataValidation(
                type=None,
                showInputMessage=True,
            )
            dv_hdr.promptTitle = prompt_title
            dv_hdr.prompt      = prompt_text
            dv_hdr.sqref       = f"{col_letter}1"
            ws.add_data_validation(dv_hdr)

            # DV на строки данных (2:1000): подсказка + список если есть
            if ref_formula:
                dv_data = DataValidation(
                    type="list",
                    formula1=f"={ref_formula}",
                    allow_blank=True,
                    showErrorMessage=False,
                    showInputMessage=True,
                )
                dv_data.error      = "Значение не из списка — будет принято как есть"
                dv_data.errorTitle = "Нестандартное значение"
            else:
                dv_data = DataValidation(
                    type=None,
                    showInputMessage=True,
                )
            dv_data.promptTitle = prompt_title
            dv_data.prompt      = prompt_text
            dv_data.sqref       = f"{col_letter}2:{col_letter}1000"
            ws.add_data_validation(dv_data)

    # =========================================================================
    # Sheet «Справочник колонок»
    # =========================================================================
    ref_ws = wb.create_sheet(title="Справочник колонок")

    ref_headers = ["Колонка", "Обязательная", "Формат/пример", "На что влияет", "Что будет, если не заполнить"]
    ref_ws.append(ref_headers)

    ref_hdr_fill2 = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    for cell in ref_ws[1]:
        cell.font = Font(color="FFFFFF", bold=True, size=11)
        cell.fill = ref_hdr_fill2
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    fill_req_row = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    align_wrap = Alignment(wrap_text=True, vertical="top")

    # Строки колонок «ФЭО Ур.N» на этом листе — запоминаем, чтобы после построения каскада
    # (ниже по коду) дописать в «Формат/пример», что это связанный список.
    _feo_fmt_rows: dict[int, int] = {}
    _feo_headers_set = {"ФЭО Ур.1", "ФЭО Ур.2", "ФЭО Ур.3", "ФЭО Ур.4", "ФЭО Ур.5"}

    for spec in _COL_SPEC:
        fmt_val = spec["fmt"]
        # Если у колонки есть dd — добавляем ключи в формат
        if spec.get("_dd"):
            fmt_val += " (выпадающий список)"
        row_vals = [
            spec["header"],
            "Да" if spec["required"] else "Нет",
            fmt_val,
            spec["effect"],
            spec["if_empty"],
        ]
        ref_ws.append(row_vals)
        row_idx = ref_ws.max_row
        if spec["header"] in _feo_headers_set:
            _feo_fmt_rows[int(spec["header"][-1])] = row_idx
        if spec["required"]:
            for col_idx2 in range(1, 6):
                ref_ws.cell(row_idx, col_idx2).fill = fill_req_row
        for col_idx2 in range(1, 6):
            ref_ws.cell(row_idx, col_idx2).alignment = align_wrap

    # Column widths on reference sheet
    ref_col_widths = [34, 13, 34, 50, 45]
    for i, w in enumerate(ref_col_widths, 1):
        ref_ws.column_dimensions[ref_ws.cell(1, i).column_letter].width = w

    ref_ws.row_dimensions[1].height = 28
    ref_ws.freeze_panes = "A2"

    # =========================================================================
    # Каскадные ФЭО-списки (только при subsidy_id)
    # =========================================================================
    # Реализован настоящий INDIRECT-каскад через скрытые хелпер-колонки:
    #   Ур.1 = feo_roots (корни субсидии)
    #   Ур.2 = INDIRECT("feo_" & helper1)  — дети выбранного Ур.1
    #   Ур.3 = INDIRECT("feo_" & helper2)  — дети выбранного Ур.2
    #   Ур.4 = INDIRECT("feo_" & helper3)  — дети выбранного Ур.3
    #   Ур.5 = INDIRECT("feo_" & helper4)  — дети выбранного Ур.4
    # Хелпер L для строки r: =IFERROR(INDEX(lvlL_ids, MATCH(<ФЭО-ячейка L>, lvlL_names, 0)), "")
    # Примечание: при дублях имён внутри уровня MATCH возьмёт первое совпадение (допустимое ограничение).
    feo_dd_levels: set[int] = set()  # уровни, для которых реально построен связанный список (для «Справочник колонок»)
    if subsidy_id is not None and DataValidation is not None and DefinedName is not None:
        try:
            feo_q = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(
                FeoCategory.sort_order.is_(None), FeoCategory.sort_order, FeoCategory.id
            )
            feo_all_cats = (await db.execute(feo_q)).scalars().all()

            if not feo_all_cats:
                feo_warning = (
                    f"У субсидии «{subsidy_name or subsidy_id}» не заполнено дерево направлений расходов (ФЭО), "
                    "поэтому связанных списков в шаблоне нет. Заполните направления в карточке субсидии."
                )
            else:
                # Уровень считаем по цепочке родителей, а не по колонке level (она может быть
                # NULL/0-based/рассинхронизирована с parent_id — тогда фильтр по level молчаливо
                # ничего не находит и каждый уровень тихо получает fallback на корни).
                by_id = {c.id: c for c in feo_all_cats}

                def _depth_of(cat) -> int:
                    d, cur, guard = 1, cat, 0
                    while cur.parent_id in by_id and guard < 12:
                        cur = by_id[cur.parent_id]
                        d += 1
                        guard += 1
                    return d

                cats_by_depth: dict[int, list] = {}
                for cat in feo_all_cats:
                    cats_by_depth.setdefault(_depth_of(cat), []).append(cat)

                roots = cats_by_depth.get(1, [])
                root_names = [c.name for c in roots]

                if not roots:
                    feo_warning = (
                        f"В дереве направлений расходов (ФЭО) субсидии «{subsidy_name or subsidy_id}» не найдено "
                        "ни одного корневого узла — связанные списки в шаблоне не построены."
                    )
                else:
                    max_depth = max(cats_by_depth)

                    # Строим карту детей: parent_id → [children] (для служебных колонок «ФЭО дети <id>»)
                    children_map: dict[int, list] = {}
                    for cat in feo_all_cats:
                        if cat.parent_id is not None and cat.parent_id in by_id:
                            children_map.setdefault(cat.parent_id, []).append(cat)

                    # Находим последнюю занятую колонку «Справочники»
                    feo_ref_start_col = len(_DD_REGISTRY) + 1

                    # ---------------------------------------------------------------
                    # 1. Колонка корней (Ур.1) + defined name feo_roots — видимая, понятная пользователю
                    # ---------------------------------------------------------------
                    feo_root_col = feo_ref_start_col
                    feo_root_col_letter = wb_ref_ws.cell(1, feo_root_col).column_letter
                    root_hdr_label = f"Направления расходов — {(subsidy_name or '')[:40]} (Ур.1)"
                    wb_ref_ws.cell(2, feo_root_col, root_hdr_label).font = ref_hdr_font
                    wb_ref_ws.cell(2, feo_root_col).fill = ref_hdr_fill
                    for ri, name in enumerate(root_names, 1):
                        wb_ref_ws.cell(2 + ri, feo_root_col, name).alignment = ref_val_align
                    # Диапазон без пустого хвоста — ровно столько строк, сколько корневых направлений
                    feo_root_last = 2 + len(root_names)
                    feo_root_attr = f"'Справочники'!${feo_root_col_letter}$3:${feo_root_col_letter}${feo_root_last}"
                    wb.defined_names["feo_roots"] = DefinedName("feo_roots", attr_text=feo_root_attr)
                    wb_ref_ws.column_dimensions[feo_root_col_letter].width = 36

                    # ---------------------------------------------------------------
                    # 2. Для каждого узла с детьми — отдельная СЛУЖЕБНАЯ (скрытая) колонка + defined name feo_<id>
                    # ---------------------------------------------------------------
                    feo_node_next_col = feo_ref_start_col + 1  # следующая свободная колонка
                    for parent_cat in feo_all_cats:
                        kids = children_map.get(parent_cat.id)
                        if not kids:
                            continue
                        kid_names = [k.name for k in kids]
                        nc = feo_node_next_col
                        nc_letter = wb_ref_ws.cell(1, nc).column_letter
                        hdr_label_node = f"ФЭО дети {parent_cat.id}"
                        wb_ref_ws.cell(2, nc, hdr_label_node).font = ref_hdr_font
                        wb_ref_ws.cell(2, nc).fill = ref_hdr_fill
                        for ki, kname in enumerate(kid_names, 1):
                            wb_ref_ws.cell(2 + ki, nc, kname).alignment = ref_val_align
                        node_last = 2 + len(kid_names)
                        node_attr = f"'Справочники'!${nc_letter}$3:${nc_letter}${node_last}"
                        dn_node = f"feo_{parent_cat.id}"
                        wb.defined_names[dn_node] = DefinedName(dn_node, attr_text=node_attr)
                        wb_ref_ws.column_dimensions[nc_letter].width = 32
                        wb_ref_ws.column_dimensions[nc_letter].hidden = True
                        feo_node_next_col += 1

                    # ---------------------------------------------------------------
                    # 3. Для каждой глубины 1..4: колонка имён (видимая) + id (служебная, скрытая)
                    #    Нужны для хелперов INDEX/MATCH: по имени выбранной ячейки → id узла
                    # ---------------------------------------------------------------
                    lvl_cols: dict[int, dict] = {}  # глубина → {names_col, ids_col, names_letter, ids_letter}
                    for lvl in range(1, 5):
                        cats_at_lvl = cats_by_depth.get(lvl)
                        if not cats_at_lvl:
                            continue
                        names_col = feo_node_next_col
                        ids_col   = feo_node_next_col + 1
                        names_letter = wb_ref_ws.cell(1, names_col).column_letter
                        ids_letter   = wb_ref_ws.cell(1, ids_col).column_letter

                        wb_ref_ws.cell(2, names_col, f"Направления Ур.{lvl} (все)").font = ref_hdr_font
                        wb_ref_ws.cell(2, names_col).fill = ref_hdr_fill
                        wb_ref_ws.cell(2, ids_col, f"Ур.{lvl} id (служ.)").font = ref_hdr_font
                        wb_ref_ws.cell(2, ids_col).fill = ref_hdr_fill

                        for ri, cat in enumerate(cats_at_lvl, 1):
                            wb_ref_ws.cell(2 + ri, names_col, cat.name).alignment = ref_val_align
                            wb_ref_ws.cell(2 + ri, ids_col, cat.id).alignment = ref_val_align

                        lvl_last = 2 + len(cats_at_lvl)
                        names_attr = f"'Справочники'!${names_letter}$3:${names_letter}${lvl_last}"
                        ids_attr   = f"'Справочники'!${ids_letter}$3:${ids_letter}${lvl_last}"
                        wb.defined_names[f"lvl{lvl}_names"] = DefinedName(f"lvl{lvl}_names", attr_text=names_attr)
                        wb.defined_names[f"lvl{lvl}_ids"]   = DefinedName(f"lvl{lvl}_ids",   attr_text=ids_attr)

                        wb_ref_ws.column_dimensions[names_letter].width = 30
                        wb_ref_ws.column_dimensions[ids_letter].width = 10
                        wb_ref_ws.column_dimensions[ids_letter].hidden = True

                        lvl_cols[lvl] = {
                            "names_col": names_col, "ids_col": ids_col,
                            "names_letter": names_letter, "ids_letter": ids_letter,
                            "lvl_last": lvl_last,
                        }
                        feo_node_next_col += 2

                    # ---------------------------------------------------------------
                    # 4. Скрытые хелпер-колонки на листе «Закупки» (col 70+)
                    #    helperL → id выбранного узла уровня L в этой строке
                    # ---------------------------------------------------------------
                    # Находим колонки ФЭО Ур.1..5 на листе «Закупки»
                    feo_headers_map: dict[int, str] = {}  # уровень → col_letter
                    for feo_col_i, spec in enumerate(_COL_SPEC, 1):
                        hdr = spec["header"]
                        if hdr in ("ФЭО Ур.1", "ФЭО Ур.2", "ФЭО Ур.3", "ФЭО Ур.4", "ФЭО Ур.5"):
                            lvl_num = int(hdr[-1])
                            feo_headers_map[lvl_num] = ws.cell(1, feo_col_i).column_letter

                    # Хелпер-колонки начинаем с col=70 (заведомо за _COL_SPEC)
                    helper_start_col = 70
                    helper_cols: dict[int, str] = {}  # уровень → col_letter хелпера
                    from openpyxl.utils import get_column_letter

                    for lvl in range(1, 5):
                        # Хелпер уровня lvl нужен только чтобы вести список СЛЕДУЮЩЕГО уровня —
                        # если lvl уже листовой (глубже дерева нет), строить его не нужно: он бы
                        # ссылался на defined name feo_<id> для узла без детей, которого не существует.
                        if lvl not in lvl_cols or lvl not in feo_headers_map or lvl >= max_depth:
                            continue
                        h_col = helper_start_col + (lvl - 1)
                        h_letter = get_column_letter(h_col)
                        helper_cols[lvl] = h_letter

                        feo_letter = feo_headers_map[lvl]
                        names_dn = f"lvl{lvl}_names"
                        ids_dn   = f"lvl{lvl}_ids"

                        # Формулы для строк 2..1000
                        for r in range(2, 1001):
                            formula = (
                                f"=IFERROR(INDEX({ids_dn},"
                                f"MATCH({feo_letter}{r},{names_dn},0)),\"\")"
                            )
                            ws.cell(r, h_col, formula)

                        # Скрываем хелпер-колонку
                        ws.column_dimensions[h_letter].hidden = True

                    # ---------------------------------------------------------------
                    # 5. DataValidation на листе «Закупки»
                    # Заменяем ранее добавленный DV (из основного цикла) на каскадный.
                    # Ровно ОДИН DataValidation на каждую ФЭО-колонку.
                    # Ур.1 → всегда feo_roots; Ур.N>1 → INDIRECT от хелпера предыдущего уровня,
                    # ЕСЛИ хелпер есть; иначе (в т.ч. N > глубины дерева субсидии) — списка НЕТ,
                    # только подсказка, что уровня в дереве субсидии нет. Никакого fallback на корни.
                    # ---------------------------------------------------------------
                    feo_headers_list = ["ФЭО Ур.1", "ФЭО Ур.2", "ФЭО Ур.3", "ФЭО Ур.4", "ФЭО Ур.5"]
                    for feo_col_i, spec in enumerate(_COL_SPEC, 1):
                        if spec["header"] not in feo_headers_list:
                            continue
                        level_num = int(spec["header"][-1])
                        col_letter = ws.cell(1, feo_col_i).column_letter

                        dn_formula = None
                        if level_num == 1:
                            dn_formula = "=feo_roots"
                        else:
                            prev_lvl = level_num - 1
                            h_letter = helper_cols.get(prev_lvl)
                            if h_letter:
                                # Относительная ссылка на хелпер (без фиксации строки)
                                # Excel применит её построчно в диапазоне sqref
                                dn_formula = f'=INDIRECT("feo_"&${h_letter}2)'

                        # Удаляем ранее добавленный DV данных этой колонки из основного цикла
                        # (sqref данных основного цикла = "{col_letter}2:{col_letter}1000")
                        # DV шапки ("{col_letter}1") не трогаем — он нужен пользователю.
                        old_data_sqref = f"{col_letter}2:{col_letter}1000"
                        ws.data_validations.dataValidation = [
                            dv for dv in ws.data_validations.dataValidation
                            if str(dv.sqref) != old_data_sqref
                        ]

                        base_prompt_title, base_prompt_text = _build_dv_prompt(spec)

                        if dn_formula:
                            # Строим prompt: базовый из _build_dv_prompt + строка о ФЭО
                            extra_line = f"Выберите категорию ФЭО уровня {level_num}."
                            candidate_prompt = (
                                (base_prompt_text + "\n" + extra_line).strip() if base_prompt_text else extra_line
                            )
                            final_prompt = candidate_prompt if len(candidate_prompt) <= 255 else base_prompt_text

                            feo_dv = DataValidation(
                                type="list",
                                formula1=dn_formula,
                                allow_blank=True,
                                showErrorMessage=False,
                                showInputMessage=True,
                            )
                            feo_dv.promptTitle = base_prompt_title
                            feo_dv.prompt      = final_prompt
                            feo_dv.sqref       = f"{col_letter}2:{col_letter}1000"
                            ws.add_data_validation(feo_dv)
                            feo_dd_levels.add(level_num)
                        else:
                            # В дереве субсидии нет такого уровня — списка нет, только подсказка
                            extra_line = (
                                f"В дереве субсидии «{subsidy_name or subsidy_id}» нет уровня {level_num} — "
                                "колонку можно оставить пустой."
                            )
                            candidate_prompt = (
                                (base_prompt_text + "\n" + extra_line).strip() if base_prompt_text else extra_line
                            )
                            final_prompt = candidate_prompt if len(candidate_prompt) <= 255 else base_prompt_text

                            feo_dv = DataValidation(
                                type=None,
                                showInputMessage=True,
                            )
                            feo_dv.promptTitle = base_prompt_title
                            feo_dv.prompt      = final_prompt
                            feo_dv.sqref       = f"{col_letter}2:{col_letter}1000"
                            ws.add_data_validation(feo_dv)

        except Exception as exc:
            logger.exception("Не удалось построить каскад ФЭО для субсидии %s", subsidy_id)
            feo_warning = (
                f"Связанные списки ФЭО не построены из-за ошибки на сервере: {type(exc).__name__}: {exc}. "
                "Сообщите администратору — в логах бэкенда есть подробности."
            )

    # Дописываем в «Справочник колонок», что колонки ФЭО с реально построенным списком — связанные
    if feo_dd_levels:
        note = " (выпадающий список направлений субсидии, привязан к предыдущему уровню)"
        for lvl_num, row_idx in _feo_fmt_rows.items():
            if lvl_num in feo_dd_levels:
                cell = ref_ws.cell(row_idx, 3)
                cell.value = (cell.value or "") + note

    # Если каскада ФЭО в файле нет (или он не построился из-за ошибки) — делаем это заметным
    # прямо в файле, а не только в API/логах, чтобы пользователь не листал пустые списки молча.
    if feo_warning:
        logger.warning("Шаблон импорта закупок отдан без каскада ФЭО (subsidy_id=%s): %s", subsidy_id, feo_warning)

        # На листе «Справочники»: дописываем предупреждение к подсказке в A1
        warn_cell = wb_ref_ws.cell(1, 1)
        base_hint = (
            "Допишите свои значения в пустые ячейки под списком — они появятся в выпадающих списках "
            "на листе «Закупки»"
        )
        warn_cell.value = base_hint + "\n⚠ " + feo_warning
        warn_cell.font = Font(bold=True, color="B91C1C", size=10)
        warn_cell.alignment = Alignment(wrap_text=True)
        wb_ref_ws.row_dimensions[1].height = 46

        # На листе «Закупки»: серая заливка шапки + предупреждение в подсказке DV колонок ФЭО Ур.1..5
        fill_warn = PatternFill(start_color="9CA3AF", end_color="9CA3AF", fill_type="solid")
        feo_headers_list = ["ФЭО Ур.1", "ФЭО Ур.2", "ФЭО Ур.3", "ФЭО Ур.4", "ФЭО Ур.5"]
        for feo_col_i, spec in enumerate(_COL_SPEC, 1):
            if spec["header"] not in feo_headers_list:
                continue
            col_letter = ws.cell(1, feo_col_i).column_letter
            ws.cell(1, feo_col_i).fill = fill_warn
            for dv in ws.data_validations.dataValidation:
                if str(dv.sqref) != f"{col_letter}2:{col_letter}1000":
                    continue
                combined = (dv.prompt + "\n⚠ " + feo_warning) if dv.prompt else ("⚠ " + feo_warning)
                if len(combined) > 255:
                    cut = combined[:254]
                    boundary = max(cut.rfind(" "), cut.rfind("\n"))
                    if boundary > 0:
                        cut = cut[:boundary]
                    combined = cut.rstrip() + "…"
                dv.prompt = combined


    return wb
