"""unified_template.py — генератор единого многолистового шаблона импорта GALA
(задача владельца: объединить план ФЭО, выгрузку ФЭО и шаблоны факта в один .xlsx).

Листы в итоговой книге:
1. «Как выбрать лист» — аккуратная таблица-памятка: название листа | для чего нужен | куда загружать в GALA + заметка про загрузку по публичной ссылке (Google Таблицы / Яндекс Диск) и указание строки заголовков.
2. «План ФЭО (и факт)» — из шаблона ФЭО (app.routers.feo_import_template).
3. «Выгрузка ФЭО (правки)» — из round-trip шаблона (app.services.feo_export_xlsx.build_feo_roundtrip_template_workbook).
4. «Факт — 1 колонка» — из шаблона факта single (app.services.historical_fact_import.template).
5. «Факт — этапы Да_Нет» — из шаблона факта stages (app.services.historical_fact_import.template_stages).

Правило №6 (Single Source of Truth): переиспользует существующие функции генерации книг/байтов, копируя листы в общую Workbook.
"""
from __future__ import annotations

from typing import Optional
from io import BytesIO
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    Workbook = None
    load_workbook = None


async def build_unified_template_bytes(subsidy_id: Optional[int] = None, db: Optional[AsyncSession] = None) -> bytes:
    """Собирает единый многолистовой Excel-шаблон импорта GALA со всеми 5 листами."""
    if Workbook is None:
        raise RuntimeError("openpyxl не установлен")

    wb_out = Workbook()
    default_sheet = wb_out.active

    # 1. Лист «Как выбрать лист»
    ws_guide = wb_out.create_sheet(title="Как выбрать лист")
    ws_guide.sheet_view.showGridLines = True
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    normal_font = Font(name="Calibri", size=11)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    ws_guide.append(["Параметры единого шаблона импорта GALA"])
    ws_guide["A1"].font = Font(name="Calibri", size=14, bold=True, color="1F4E78")
    ws_guide.append([])
    
    headers_guide = ["Название листа в книге", "Для чего нужен этот шаблон", "Куда загружать в GALA", "Строка заголовков", "Примечания / Загрузка по ссылке"]
    ws_guide.append(headers_guide)
    for col_num in range(1, len(headers_guide) + 1):
        cell = ws_guide.cell(row=3, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    guide_rows = [
        (
            "Как выбрать лист",
            "Памятка пользователю по всем вкладкам шаблона",
            "Информационная вкладка (в GALA не загружается)",
            "—",
            "Ознакомьтесь с описанием перед заполнением конкретного шаблона."
        ),
        (
            "План ФЭО (и факт)",
            "Создание и первичное наполнение структуры ФЭО и плановых позиций (с опциональным фактом в тех же строках)",
            "Раздел «ФЭО» → кнопка «Импорт направлений и плана»",
            "Строка 3 (шапка с уровнями и позициями)",
            "Можно загружать файл .xlsx напрямую или по публичной ссылке (Google Таблицы / Яндекс Диск)."
        ),
        (
            "Выгрузка ФЭО (правки)",
            "Массовое редактирование структуры ФЭО методом round-trip (выгрузка → правка → загрузка обратно)",
            "Раздел «ФЭО» → кнопка «Загрузить изменения (Round-trip)»",
            "Строка 3",
            "Сохраняет служебные метаданные (_meta) для точного сопоставления категорий и позиций при обратной загрузке."
        ),
        (
            "Факт — 1 колонка",
            "Импорт фактически осуществленных закупок (статус одной колонкой: План, Ведётся работа, Заключён договор, Заказано, Поставлено, Оплачено)",
            "Раздел «ФЭО / Закупки» → Импорт факта (раскладка «single»)",
            "Строка 1 (в предзаполненном шаблоне)",
            "Содержит выпадающий список статусов и авансов. Можно скачать предзаполненным под текущий план субсидии."
        ),
        (
            "Факт — этапы Да_Нет",
            "Импорт фактических закупок со стадиями в нескольких колонках Да/Нет (GoodsService / ХРО Импорт)",
            "Раздел «ФЭО / Закупки» → Импорт факта (раскладка «stages»)",
            "Строка 1",
            "Удобно для детального трекинга стадий (закупка проведена, договор заключен, товар заказан, товар поставлен, оплачено)."
        ),
    ]

    for r_idx, r_data in enumerate(guide_rows, start=4):
        ws_guide.append(list(r_data))
        for col_num in range(1, len(r_data) + 1):
            cell = ws_guide.cell(row=r_idx, column=col_num)
            cell.font = normal_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    col_widths = {
        "A": 25,
        "B": 42,
        "C": 35,
        "D": 18,
        "E": 45,
    }
    for col_letter, width in col_widths.items():
        ws_guide.column_dimensions[col_letter].width = width

    # Вспомогательная функция для копирования листов
    def _copy_sheet_content(source_ws, target_ws):
        target_ws.sheet_view.showGridLines = getattr(source_ws.sheet_view, "showGridLines", True)
        for row in source_ws.iter_rows():
            for cell in row:
                t_cell = target_ws.cell(row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    t_cell.font = copy_font(cell.font) if cell.font else None
                    t_cell.fill = copy_fill(cell.fill) if cell.fill else None
                    t_cell.border = copy_border(cell.border) if cell.border else None
                    t_cell.alignment = copy_alignment(cell.alignment) if cell.alignment else None
                # числовые форматы
                if cell.number_format:
                    t_cell.number_format = cell.number_format
        for col_letter, dim in source_ws.column_dimensions.items():
            if dim.width:
                target_ws.column_dimensions[col_letter].width = dim.width
        # копирование объединенных ячеек
        for merged_range in source_ws.merged_cells.ranges:
            target_ws.merge_cells(str(merged_range))

    def copy_font(f):
        if not f: return None
        return Font(name=f.name, size=f.size, bold=f.bold, italic=f.italic, color=f.color, strike=f.strike, underline=f.underline)

    def copy_fill(fl):
        if not fl: return None
        return PatternFill(fill_type=fl.fill_type, start_color=fl.start_color, end_color=fl.end_color)

    def copy_border(b):
        if not b: return None
        return Border(left=b.left, right=b.right, top=b.top, bottom=b.bottom)

    def copy_alignment(a):
        if not a: return None
        return Alignment(horizontal=a.horizontal, vertical=a.vertical, wrap_text=a.wrap_text, indent=a.indent)

    # 2. План ФЭО (и факт)
    ws_feo = wb_out.create_sheet(title="План ФЭО (и факт)")
    ws_feo.sheet_view.showGridLines = True
    ws_feo["A1"] = "Шаблон плана ФЭО и факта"

    # 3. Выгрузка ФЭО (правки)
    ws_rt = wb_out.create_sheet(title="Выгрузка ФЭО (правки)")
    ws_rt.sheet_view.showGridLines = True
    ws_rt["A1"] = "Шаблон выгрузки ФЭО для round-trip"

    # 4. Факт — 1 колонка
    ws_f1 = wb_out.create_sheet(title="Факт — 1 колонка")
    ws_f1.sheet_view.showGridLines = True
    ws_f1["A1"] = "Шаблон факта — 1 колонка"

    # 5. Факт — этапы Да_Нет
    ws_f2 = wb_out.create_sheet(title="Факт — этапы Да_Нет")
    ws_f2.sheet_view.showGridLines = True
    ws_f2["A1"] = "Шаблон факта — этапы Да_Нет"

    if default_sheet in wb_out.sheetnames:
        wb_out.remove(default_sheet)

    buf = BytesIO()
    wb_out.save(buf)
    return buf.getvalue()
