"""unified_template.py — генератор единого многолистового шаблона импорта GALA
(объединяет план ФЭО, выгрузку ФЭО и шаблоны факта/GoodsService в один .xlsx).

Листы в итоговой книге:
1. «Как выбрать лист» — таблица-памятка по всем вкладкам + про Google/Яндекс Таблицы и выбор строки заголовков.
2. «План ФЭО (и факт)» — реальный лист из app.routers.feo_import_template.download_feo_template.
3. «Выгрузка ФЭО (правки)» — реальный лист из app.services.feo_export_xlsx.build_feo_roundtrip_template_workbook.
4. «Факт — 1 колонка» — реальный лист из app.services.historical_fact_import.template (или заголовки TEMPLATE_HEADER + пример, если субсидия не выбрана).
5. «Факт — этапы Да_Нет» — реальный лист из app.services.historical_fact_import.template_stages (или заголовки _HEADER + пример, если субсидия не выбрана).

Правило №6 (Single Source of Truth): переиспользует существующие генераторы и списки колонок, не дублирует их вручную.
"""
from __future__ import annotations

from copy import copy
from io import BytesIO
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession


_THIN = Side(style="thin", color="D9D9D9")
_THIN_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_NORMAL_FONT = Font(name="Calibri", size=11)


def _copy_sheet_content(source_ws, target_ws) -> None:
    """Копирует значения, стили, ширины столбцов, высоты строк, объединения и freeze_panes."""
    target_ws.sheet_view.showGridLines = getattr(source_ws.sheet_view, "showGridLines", True)
    if source_ws.freeze_panes:
        target_ws.freeze_panes = source_ws.freeze_panes

    for row in source_ws.iter_rows():
        for cell in row:
            t_cell = target_ws.cell(row=cell.row, column=cell.column, value=cell.value)
            if cell.has_style:
                t_cell.font = copy(cell.font)
                t_cell.fill = copy(cell.fill)
                t_cell.border = copy(cell.border)
                t_cell.alignment = copy(cell.alignment)
                t_cell.number_format = cell.number_format

    for col_key, dim in source_ws.column_dimensions.items():
        if dim.width:
            target_ws.column_dimensions[col_key].width = dim.width
    for row_idx, rdim in source_ws.row_dimensions.items():
        if rdim.height:
            target_ws.row_dimensions[row_idx].height = rdim.height
    for merged_range in source_ws.merged_cells.ranges:
        target_ws.merge_cells(str(merged_range))


def _build_guide_sheet(wb_out: Workbook) -> None:
    ws = wb_out.create_sheet(title="Как выбрать лист")
    ws.sheet_view.showGridLines = True
    ws.append(["Единый шаблон импорта GALA — выберите нужный лист"])
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="1F4E78")
    ws.append([])

    headers = [
        "Название листа в книге",
        "Для чего нужен этот шаблон",
        "Куда загружать в GALA",
        "Строка заголовков",
        "Примечания / Google и Яндекс Таблицы",
    ]
    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        c = ws.cell(row=3, column=col_num)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.border = _THIN_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[3].height = 28

    rows = [
        (
            "План ФЭО (и факт)",
            "Первичная загрузка дерева ФЭО и плановых позиций (с опциональным блоком «Факт» в тех же строках)",
            "Карточка субсидии → Ещё → Импорт плана ФЭО",
            "Строка 1",
            "Можно загружать файл .xlsx или вставить публичную ссылку Google / Яндекс Таблицы (доступ «Читатель»).",
        ),
        (
            "Выгрузка ФЭО (правки)",
            "Правки существующего ФЭО (формат «Выгрузить ФЭО»): изменение сумм, названий, добавление строк",
            "Карточка субсидии → Ещё → Загрузить правки из выгрузки ФЭО",
            "Строка 1 (структура выгрузки)",
            "Удобно для корректировки уже загруженного дерева ФЭО.",
        ),
        (
            "Факт — 1 колонка",
            "Импорт факта закупок и оплат, когда статус указан в одной колонке («Правильный статус»)",
            "Карточка субсидии → Ещё → Импорт факта и оплат",
            "Строка 1 (или укажите вручную)",
            "Если в вашей таблице шапка в 3-й строке (как в «ХРО Импорт»), укажите «3» в поле «Строка с названиями колонок».",
        ),
        (
            "Факт — этапы Да_Нет",
            "Импорт факта и оплат со стадиями в отдельных колонках Да/Нет (формат GoodsService / ХРО Импорт)",
            "Карточка субсидии → Ещё → Импорт факта и оплат",
            "Строка 1 (или укажите вручную)",
            "Поддерживает колонки стадий (Закупка проведена, Договор заключен, Товар заказан, Товар поставлен, Оплачено) и суммы оплат.",
        ),
    ]
    for r_idx, r_data in enumerate(rows, start=4):
        ws.append(list(r_data))
        ws.row_dimensions[r_idx].height = 42
        for col_num in range(1, len(r_data) + 1):
            c = ws.cell(row=r_idx, column=col_num)
            c.font = _NORMAL_FONT
            c.border = _THIN_BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)

    for col_letter, width in {"A": 26, "B": 46, "C": 42, "D": 24, "E": 50}.items():
        ws.column_dimensions[col_letter].width = width


def _fill_neutral_fact_single(ws) -> None:
    """Нейтральный шаблон факта (1 колонка статуса), когда субсидия не выбрана."""
    from app.services.historical_fact_import import columns as columns_mod
    from app.services.historical_fact_import import statuses as statuses_mod

    ws.sheet_view.showGridLines = True
    header = list(columns_mod.TEMPLATE_HEADER)
    ws.append(header)
    for col_idx in range(1, len(header) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.border = _THIN_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(14, min(32, len(str(header[col_idx - 1])) + 4))
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"

    sample = [None] * len(header)
    sample[0] = "Название субсидии"
    sample[4] = "Материально-техническое обеспечение"
    sample[5] = "Приобретение оборудования"
    sample[7] = "Ноутбук (пример позиции)"
    sample[15] = 2
    sample[16] = 75000
    sample[17] = 150000
    if len(sample) > 24:
        status_label = statuses_mod.STATUS_CHOICES[2]["label"] if len(statuses_mod.STATUS_CHOICES) > 2 else "Заключён договор"
        sample[24] = status_label
    ws.append(sample)
    for cell in ws[2]:
        cell.font = _NORMAL_FONT
        cell.border = _THIN_BORDER


def _fill_neutral_fact_stages(ws) -> None:
    """Нейтральный шаблон факта (этапы Да/Нет — GoodsService / ХРО Импорт), когда субсидия не выбрана."""
    from app.services.historical_fact_import import template_stages

    ws.sheet_view.showGridLines = True
    header = list(template_stages._HEADER)
    ws.append(header)
    for col_idx in range(1, len(header) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.border = _THIN_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(14, min(32, len(str(header[col_idx - 1])) + 4))
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"

    sample = [None] * len(header)
    sample[0] = "З-001"
    sample[1] = "Ноутбук (пример позиции)"
    sample[2] = "ООО «Ромашка»"
    sample[3] = "7701234567"
    sample[4] = 2
    sample[5] = "шт"
    sample[6] = 75000
    sample[7] = 150000
    sample[8] = 72000
    sample[9] = 144000
    sample[10] = "Товар"
    sample[11] = "Материально-техническое обеспечение"
    sample[12] = "Приобретение оборудования"
    sample[15] = "Да"
    sample[16] = "Да"
    sample[17] = "Да"
    sample[18] = "Нет"
    sample[19] = "Нет"
    sample[20] = 72000
    sample[21] = "Да"
    ws.append(sample)
    for cell in ws[2]:
        cell.font = _NORMAL_FONT
        cell.border = _THIN_BORDER


async def _load_feo_template_wb(subsidy_id: Optional[int], db: Optional[AsyncSession]):
    from app.routers.feo_import_template import download_feo_template

    resp = await download_feo_template(subsidy_id=subsidy_id, db=db, current_user=None)
    chunks: list[bytes] = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return load_workbook(BytesIO(b"".join(chunks)))


async def build_unified_template_bytes(
    subsidy_id: Optional[int] = None,
    db: Optional[AsyncSession] = None,
) -> bytes:
    """Собирает единый многолистовой Excel-шаблон импорта GALA со всеми 5 реальными листами."""
    wb_out = Workbook()
    default_sheet = wb_out.active

    # 1. Памятка
    _build_guide_sheet(wb_out)

    # 2. План ФЭО (и факт) — реальный лист из download_feo_template
    ws_feo = wb_out.create_sheet(title="План ФЭО (и факт)")
    wb_feo = await _load_feo_template_wb(subsidy_id, db)
    _copy_sheet_content(wb_feo.worksheets[0], ws_feo)

    # 3. Выгрузка ФЭО (правки) — реальный лист из build_feo_roundtrip_template_workbook
    from app.services.feo_export_xlsx import build_feo_roundtrip_template_workbook

    ws_rt = wb_out.create_sheet(title="Выгрузка ФЭО (правки)")
    wb_rt = build_feo_roundtrip_template_workbook()
    _copy_sheet_content(wb_rt.worksheets[0], ws_rt)

    # 4. Факт — 1 колонка
    ws_f1 = wb_out.create_sheet(title="Факт — 1 колонка")
    if subsidy_id is not None and db is not None:
        from app.services.historical_fact_import.template import build_template_workbook

        wb_f1 = load_workbook(BytesIO(await build_template_workbook(db, subsidy_id)))
        _copy_sheet_content(wb_f1.worksheets[0], ws_f1)
    else:
        _fill_neutral_fact_single(ws_f1)

    # 5. Факт — этапы Да_Нет (GoodsService / ХРО Импорт)
    ws_f2 = wb_out.create_sheet(title="Факт — этапы Да_Нет")
    if subsidy_id is not None and db is not None:
        from app.services.historical_fact_import.template_stages import build_stages_template_workbook

        wb_f2 = load_workbook(BytesIO(await build_stages_template_workbook(db, subsidy_id)))
        _copy_sheet_content(wb_f2.worksheets[0], ws_f2)
    else:
        _fill_neutral_fact_stages(ws_f2)

    # Обязательно удаляем дефолтный пустой лист «Sheet» (раньше было `default_sheet in sheetnames` — баг!)
    wb_out.remove(default_sheet)
    wb_out.active = 0

    buf = BytesIO()
    wb_out.save(buf)
    return buf.getvalue()
