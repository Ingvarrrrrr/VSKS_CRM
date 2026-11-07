"""Генератор стандартизированного бланка ТКП «Приложение_2_Форма_ТКП.xlsx».

ПРАВИЛО №5: компактный модуль (< 280 строк).
ПРАВИЛО №6: единый источник строк ТЗ build_tz_rows и значений _purchase_item_doc_values.
"""
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.documents.contexts import (
    _purchase_item_doc_values,
    _require_tz_duplicates_resolved_for_doc,
)
from app.services.tz_items import build_tz_rows

TKP_FORM_ZIP_FILE_NAME = "Приложение_2_Форма_ТКП.xlsx"
TKP_FORM_MARKER = "GALA_TKP_V1"


def build_standardized_tkp_xlsx(
    rows: List[Dict[str, Any]],
    *,
    purchase_id: Optional[int] = None,
    purchase_subject: str = "",
    customer_name: str = "",
) -> bytes:
    """Создаёт стандартизированный файл Excel «Приложение № 2 — Форма ТКП»."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Форма ТКП"
    ws.views.sheetView[0].showGridLines = True

    # Стили
    font_title = Font(name="Calibri", size=12, bold=True)
    font_bold = Font(name="Calibri", size=10, bold=True)
    font_regular = Font(name="Calibri", size=10)
    font_hint = Font(name="Calibri", size=9, italic=True, color="757575")
    font_header = Font(name="Calibri", size=10, bold=True)

    fill_yellow = PatternFill(start_color="FFFDE7", end_color="FFFDE7", fill_type="solid")
    fill_header = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")

    thin_border_side = Side(style="thin", color="CCCCCC")
    thin_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side,
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="center")

    protect_unlocked = Protection(locked=False)
    protect_locked = Protection(locked=True)

    def _style_range(row: int, col_start: int, col_end: int, fill=None, border=None, font=None, alignment=None, protection=None):
        for c in range(col_start, col_end + 1):
            cell = ws.cell(row=row, column=c)
            if fill:
                cell.fill = fill
            if border:
                cell.border = border
            if font:
                cell.font = font
            if alignment:
                cell.alignment = alignment
            if protection:
                cell.protection = protection

    # Строка 1: Заголовок и технический маркер
    ws.cell(row=1, column=1, value="ПРИЛОЖЕНИЕ № 2 — ФОРМА ТЕХНИКО-КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ (ТКП)")
    ws.cell(row=1, column=1).font = font_title
    ws.cell(row=1, column=10, value=TKP_FORM_MARKER)
    ws.cell(row=1, column=10).font = Font(name="Calibri", size=9, color="A0A0A0")

    # Строка 2: Закупка
    subj = purchase_subject or (f"Закупка #{purchase_id}" if purchase_id else "")
    ws.cell(row=2, column=1, value="Закупка:").font = font_bold
    ws.cell(row=2, column=3, value=subj).font = font_regular
    ws.cell(row=2, column=10, value=purchase_id or "")

    # Строка 3: Заказчик
    ws.cell(row=3, column=1, value="Заказчик:").font = font_bold
    ws.cell(row=3, column=3, value=customer_name or "ВСКС").font = font_regular

    # Блок реквизитов участника (строки 4-10)
    requisites = [
        (4, "Наименование участника (ЮЛ / ИП / ФЛ)*", "", "Полное или краткое наименование организации / ИП", None),
        (5, "ИНН участника*", "", "10 или 12 цифр", "@"),
        (6, "КПП участника", "", "9 цифр (для юр. лиц)", "@"),
        (7, "Контактный телефон и E-mail", "", "Контактные данные ответственного лица", None),
        (8, "Ставка НДС*", "Без НДС", "Выберите из списка (Без НДС / в т.ч. НДС 20% / 22% / 10% / 5% / 7%)", None),
        (9, "Срок действия ТКП (рабочих дней)*", 30, "Обязательное требование: не менее 30 рабочих дней со дня окончания приёма заявок", "0"),
        (10, "Исходящий № и дата ТКП", "", "Например: исх. № 15 от 10.11.2026", None),
    ]

    for r_idx, label, default_val, hint, num_fmt in requisites:
        ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=2)
        c_lbl = ws.cell(row=r_idx, column=1, value=label)
        c_lbl.font = font_bold
        c_lbl.alignment = align_left
        c_lbl.protection = protect_locked

        ws.merge_cells(start_row=r_idx, start_column=3, end_row=r_idx, end_column=6)
        c_val = ws.cell(row=r_idx, column=3, value=default_val)
        c_val.font = font_bold if r_idx == 9 else font_regular
        c_val.alignment = align_left
        if num_fmt:
            c_val.number_format = num_fmt
        _style_range(r_idx, 3, 6, fill=fill_yellow, border=thin_border, protection=protect_unlocked)

        ws.merge_cells(start_row=r_idx, start_column=7, end_row=r_idx, end_column=10)
        c_hint = ws.cell(row=r_idx, column=7, value=hint)
        c_hint.font = font_hint
        c_hint.alignment = align_left
        c_hint.protection = protect_locked

    # Валидация списка НДС в C8
    dv_vat = DataValidation(
        type="list",
        formula1='"Без НДС,в т.ч. НДС 20%,в т.ч. НДС 22%,в т.ч. НДС 10%,в т.ч. НДС 5%,в т.ч. НДС 7%"',
        allow_blank=True,
    )
    ws.add_data_validation(dv_vat)
    dv_vat.add("C8")

    # Шапка таблицы позиций (строка 12)
    headers = [
        "№ п/п",
        "ID поз.",
        "Название продукции (по ТЗ Заказчика)",
        "Требования Заказчика к характеристикам (ТЗ)",
        "Ед. изм.",
        "Кол-во",
        "Тип предложения (По ТЗ / Аналог)*",
        "Предложение участника (марка, модель, характеристики предлагаемого товара)",
        "Цена за ед., руб.*",
        "Ставка НДС*",
        "Стоимость, руб.",
    ]
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=12, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.border = thin_border
        cell.alignment = align_center
    ws.row_dimensions[12].height = 36

    # Позиции (начиная со строки 13)
    start_row = 13
    for idx, row in enumerate(rows):
        r = start_row + idx
        ws.row_dimensions[r].height = 28

        # A: № п/п
        c_num = ws.cell(row=r, column=1, value=idx + 1)
        c_num.alignment = align_center

        # B: ID поз.
        c_id = ws.cell(row=r, column=2, value=row.get("item_id") or (idx + 1))
        c_id.alignment = align_center

        # C: Название продукции
        c_name = ws.cell(row=r, column=3, value=str(row.get("name") or "").strip())
        c_name.alignment = align_left

        # D: Требования Заказчика
        c_desc = ws.cell(row=r, column=4, value=str(row.get("description") or "").strip())
        c_desc.alignment = align_left

        # E: Ед. изм.
        c_unit = ws.cell(row=r, column=5, value=str(row.get("unit") or "").strip() or "шт.")
        c_unit.alignment = align_center

        # F: Кол-во
        qty = 0.0
        try:
            qty = float(row.get("quantity") or 0.0)
        except (ValueError, TypeError):
            qty = 0.0
        c_qty = ws.cell(row=r, column=6, value=qty)
        c_qty.alignment = align_right
        c_qty.number_format = "#,##0.00"

        # G: Тип предложения (По ТЗ / Эквивалент)
        c_type = ws.cell(row=r, column=7, value="По ТЗ Заказчика")
        c_type.fill = fill_yellow
        c_type.alignment = align_center
        c_type.protection = protect_unlocked

        # H: Предложение участника
        c_off = ws.cell(row=r, column=8, value="")
        c_off.fill = fill_yellow
        c_off.alignment = align_left
        c_off.protection = protect_unlocked

        # I: Цена за ед.
        c_price = ws.cell(row=r, column=9, value=None)
        c_price.fill = fill_yellow
        c_price.alignment = align_right
        c_price.number_format = "#,##0.00"
        c_price.protection = protect_unlocked

        # J: Ставка НДС позиции
        c_vat = ws.cell(row=r, column=10, value="Без НДС")
        c_vat.fill = fill_yellow
        c_vat.alignment = align_center
        c_vat.protection = protect_unlocked

        # K: Стоимость
        c_cost = ws.cell(row=r, column=11, value=f"=ROUND(F{r}*I{r}, 2)")
        c_cost.alignment = align_right
        c_cost.number_format = "#,##0.00"
        c_cost.protection = protect_locked

        for c in range(1, 12):
            cell = ws.cell(row=r, column=c)
            cell.font = font_regular
            cell.border = thin_border
            if c not in (7, 8, 9, 10):
                cell.protection = protect_locked

    # Валидация выпадающих списков
    if rows:
        end_row = start_row + len(rows) - 1
        dv_offer = DataValidation(
            type="list",
            formula1='"По ТЗ Заказчика,Эквивалент (аналог)"',
            allow_blank=True,
        )
        ws.add_data_validation(dv_offer)
        dv_offer.add(f"G{start_row}:G{end_row}")

        dv_item_vat = DataValidation(
            type="list",
            formula1='"Без НДС,в т.ч. НДС 20%,в т.ч. НДС 22%,в т.ч. НДС 10%,в т.ч. НДС 5%,в т.ч. НДС 7%"',
            allow_blank=True,
        )
        ws.add_data_validation(dv_item_vat)
        dv_item_vat.add(f"J{start_row}:J{end_row}")

    # Строка ИТОГО
    r_total = start_row + len(rows)
    ws.merge_cells(start_row=r_total, start_column=1, end_row=r_total, end_column=10)
    c_tot_label = ws.cell(row=r_total, column=1, value="ИТОГО по технико-коммерческому предложению, руб.:")
    c_tot_label.font = font_bold
    c_tot_label.alignment = align_right

    for c in range(1, 11):
        ws.cell(row=r_total, column=c).border = thin_border

    c_tot_sum = ws.cell(
        row=r_total,
        column=11,
        value=f"=SUM(K{start_row}:K{r_total - 1})" if rows else 0,
    )
    c_tot_sum.font = font_bold
    c_tot_sum.border = thin_border
    c_tot_sum.alignment = align_right
    c_tot_sum.number_format = "#,##0.00"

    # Памятка участнику
    r_memo = r_total + 2
    memo_lines = [
        "* Внимание! Участник заполняет ячейки с жёлтым фоном (реквизиты в строках 4–10 и предложение в колонках G, H, I, J).",
        "* При предложении точного соответствия ТЗ выберите «По ТЗ Заказчика» в графе 7. При предложении эквивалента выберите «Эквивалент (аналог)» и подробно опишите характеристики в графе 8.",
        "* Цену за ед. укажите в графе 9. Ставку НДС выберите в графе 10 (Без НДС / в т.ч. НДС 20% / 22% / 10% / 5% / 7%).",
        "* Заполненный файл в формате .xlsx вместе с подписанной скан-копией в формате .pdf прикрепите в составе заявки на электронной торговой площадке.",
    ]
    for i, line in enumerate(memo_lines):
        r_m = r_memo + i
        ws.merge_cells(start_row=r_m, start_column=1, end_row=r_m, end_column=11)
        cell = ws.cell(row=r_m, column=1, value=line)
        cell.font = font_hint
        cell.alignment = align_left

    # Настройка ширин колонок
    col_widths = {
        "A": 6,
        "B": 9,
        "C": 26,
        "D": 38,
        "E": 9,
        "F": 9,
        "G": 20,
        "H": 36,
        "I": 16,
        "J": 15,
        "K": 18,
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Защита листа (Sheet Protection с запретом выделения заблокированных ячеек)
    ws.protection.sheet = True
    ws.protection.password = "vsks2026"
    ws.protection.selectLockedCells = False

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def load_standardized_tkp_rows(
    db: AsyncSession,
    purchase_id: int,
) -> Tuple[Optional[Purchase], List[Dict[str, Any]], List[str]]:
    """Единый загрузчик строк ТЗ закупки для бланков ТКП (xlsx, pdf) и пакета Росэлторга.

    ПРАВИЛО №6: единый источник истины.
    """
    result = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.id == purchase_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        return None, [], [f"Закупка {purchase_id} не найдена"]

    _require_tz_duplicates_resolved_for_doc(p)

    _tz = build_tz_rows(getattr(p, "items", None) or [], getattr(p, "tz_duplicate_decisions", None))

    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for row in _tz["rows"]:
        item = row["item"]
        try:
            raw = _purchase_item_doc_values(p, item, row)
        except Exception as e:
            errors.append(f"Позиция «{getattr(item, 'item_name', '') or item.id}»: {type(e).__name__}: {e}")
            continue

        rows.append({
            "item_id": getattr(item, "id", None),
            "okpd2": "",
            "name": raw["name"],
            "quantity": raw["quantity"],
            "unit": raw["unit"],
            "unit_price": raw["unit_price"],
            "description": raw["description"],
        })

    return p, rows, errors


async def render_standardized_tkp_xlsx(
    db: AsyncSession,
    purchase_id: int,
) -> Tuple[Optional[bytes], List[str]]:
    """Собирает стандартизированный файл бланка ТКП для закупки purchase_id."""
    p, rows, errors = await load_standardized_tkp_rows(db, purchase_id)
    if not p:
        return None, errors or [f"Закупка {purchase_id} не найдена"]
    if not rows:
        return None, errors or [f"У закупки {purchase_id} нет позиций для бланка ТКП"]

    subject = str(getattr(p, "subject", "") or getattr(p, "registry_number", "") or f"Закупка #{p.id}")
    xlsx_bytes = build_standardized_tkp_xlsx(
        rows,
        purchase_id=p.id,
        purchase_subject=subject,
        customer_name="ВСКС",
    )
    return xlsx_bytes, errors
