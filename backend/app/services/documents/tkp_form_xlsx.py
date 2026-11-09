"""Генератор стандартизированного бланка ТКП «Приложение_2_Форма_ТКП.xlsx».

ПРАВИЛО №5: компактный модуль (< 450 строк).
ПРАВИЛО №6: единый источник строк ТЗ load_standardized_tkp_rows и характеристик extract_item_structured_chars.
"""
from io import BytesIO
import json
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
from app.services.roseltorg.analog_matcher import (
    extract_default_exact_value,
    extract_item_structured_chars,
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

    font_title = Font(name="Calibri", size=12, bold=True)
    font_bold = Font(name="Calibri", size=10, bold=True)
    font_regular = Font(name="Calibri", size=10)
    font_sub = Font(name="Calibri", size=9, color="555555")
    font_hint = Font(name="Calibri", size=9, italic=True, color="757575")
    font_header = Font(name="Calibri", size=10, bold=True)

    fill_yellow = PatternFill(start_color="FFFDE7", end_color="FFFDE7", fill_type="solid")
    fill_header = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")
    fill_sub = PatternFill(start_color="FAFAFA", end_color="FAFAFA", fill_type="solid")

    thin_border_side = Side(style="thin", color="CCCCCC")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="center", wrap_text=True)

    protect_unlocked = Protection(locked=False)
    protect_locked = Protection(locked=True)

    def _calc_row_height(
        text_width_pairs: List[Tuple[Any, int]],
        min_h: float = 24.0,
        line_h: float = 14.0,
        pad: float = 8.0,
    ) -> float:
        """Оценивает высоту строки Excel для ячеек с переносом текста (wrap_text)."""
        max_lines = 1
        for text, col_w in text_width_pairs:
            s = str(text or "").strip()
            if not s:
                continue
            for line in s.split("\n"):
                eff_w = max(int(col_w * 0.85), 6)
                lines = max(1, (len(line) + eff_w - 1) // eff_w)
                if lines > max_lines:
                    max_lines = lines
        return max(min_h, round(max_lines * line_h + pad, 1))

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

    # Заголовок
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 24
    ws.row_dimensions[3].height = 22
    ws.cell(row=1, column=1, value="ПРИЛОЖЕНИЕ № 2 — ФОРМА ТЕХНИКО-КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ (ТКП)").font = font_title
    ws.cell(row=1, column=10, value=TKP_FORM_MARKER).font = Font(name="Calibri", size=9, color="A0A0A0")

    subj = purchase_subject or (f"Закупка #{purchase_id}" if purchase_id else "")
    ws.cell(row=2, column=1, value="Закупка:").font = font_bold
    ws.cell(row=2, column=3, value=subj).font = font_regular
    ws.cell(row=2, column=10, value=purchase_id or "")

    ws.cell(row=3, column=1, value="Заказчик:").font = font_bold
    ws.cell(row=3, column=3, value=customer_name or "ВСКС").font = font_regular

    requisites = [
        (4, "Наименование участника (ЮЛ / ИП / ФЛ)*", "", "Полное или краткое наименование организации / ИП", None),
        (5, "ИНН участника*", "", "10 или 12 цифр", "@"),
        (6, "КПП участника", "", "9 цифр (для юр. лиц)", "@"),
        (7, "Контактный телефон и E-mail", "", "Контактные данные ответственного лица", None),
        (8, "Ставка НДС*", "Без НДС", "Выберите из списка (Без НДС / в т.ч. НДС 20% / 22% / 10% / 5% / 7%)", None),
        (9, "Срок действия ТКП (рабочих дней)*", 30, "Обязательное требование: не менее 30 рабочих дней", "0"),
        (10, "Исходящий № и дата ТКП", "", "Например: исх. № 15 от 10.11.2026", None),
    ]

    for r_idx, label, default_val, hint, num_fmt in requisites:
        ws.row_dimensions[r_idx].height = 28
        ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=2)
        c_lbl = ws.cell(row=r_idx, column=1, value=label)
        c_lbl.font, c_lbl.alignment, c_lbl.protection = font_bold, align_left, protect_locked

        ws.merge_cells(start_row=r_idx, start_column=3, end_row=r_idx, end_column=6)
        c_val = ws.cell(row=r_idx, column=3, value=default_val)
        c_val.font = font_bold if r_idx == 9 else font_regular
        c_val.alignment = align_left
        if num_fmt:
            c_val.number_format = num_fmt
        _style_range(r_idx, 3, 6, fill=fill_yellow, border=thin_border, protection=protect_unlocked)

        ws.merge_cells(start_row=r_idx, start_column=7, end_row=r_idx, end_column=10)
        c_hint = ws.cell(row=r_idx, column=7, value=hint)
        c_hint.font, c_hint.alignment, c_hint.protection = font_hint, align_left, protect_locked

    dv_vat = DataValidation(type="list", formula1='"Без НДС,в т.ч. НДС 20%,в т.ч. НДС 22%,в т.ч. НДС 10%,в т.ч. НДС 5%,в т.ч. НДС 7%"', allow_blank=True)
    ws.add_data_validation(dv_vat)
    dv_vat.add("C8")

    # Шапка таблицы позиций (строка 12)
    headers = [
        "№ п/п", "ID поз.", "Название продукции (по ТЗ Заказчика)",
        "Требования Заказчика к характеристикам (ТЗ)", "Ед. изм.", "Кол-во",
        "Тип предложения (По ТЗ / Аналог)*",
        "Предложение участника: конкретная марка, модель, производитель и точные значения характеристик (без слов «не менее», «не более», «от… до…»)*",
        "Цена за ед., руб.*", "Ставка НДС*", "Стоимость, руб.",
    ]
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=12, column=c_idx, value=h)
        cell.font, cell.fill, cell.border, cell.alignment = font_header, fill_header, thin_border, align_center
    ws.row_dimensions[12].height = 48

    curr_row = 13
    item_rows_indices: List[int] = []

    for idx, row in enumerate(rows):
        r_item = curr_row
        item_rows_indices.append(r_item)

        item_id = row.get("item_id") or (idx + 1)
        name = str(row.get("name") or "").strip()
        desc = str(row.get("description") or "").strip()
        unit = str(row.get("unit") or "").strip() or "шт."
        try:
            qty = float(row.get("quantity") or 0.0)
        except (ValueError, TypeError):
            qty = 0.0
        chars = row.get("characteristics") or []

        desc_tz = f"{desc} — указать конкретную марку/модель" if desc else "Указать конкретную марку, модель, товарный знак и производителя товара"
        offered_item_val = str(row.get("offered_model") or row.get("offered_name") or "").strip()
        ws.row_dimensions[r_item].height = _calc_row_height(
            [(name, 36), (desc_tz, 40), (offered_item_val, 42)],
            min_h=34.0,
            line_h=14.0,
            pad=8.0,
        )

        # Строка товара
        ws.cell(row=r_item, column=1, value=idx + 1).alignment = align_center
        ws.cell(row=r_item, column=2, value=item_id).alignment = align_center
        ws.cell(row=r_item, column=3, value=name).alignment = align_left
        ws.cell(row=r_item, column=4, value=desc_tz).alignment = align_left
        ws.cell(row=r_item, column=5, value=unit).alignment = align_center

        c_qty = ws.cell(row=r_item, column=6, value=qty)
        c_qty.alignment, c_qty.number_format = align_right, "#,##0.00"

        c_type = ws.cell(row=r_item, column=7, value="Предоставляю модель Заказчика (по ТЗ)")
        c_type.fill, c_type.alignment, c_type.protection = fill_yellow, align_center, protect_unlocked

        ref_model = str(row.get("ref_model") or row.get("offered_model") or name).strip()
        if "offered_model" in row or "offered_name" in row:
            offered_item_val = str(row.get("offered_model") or row.get("offered_name") or "").strip()
            c_off = ws.cell(row=r_item, column=8, value=offered_item_val)
        else:
            c_off = ws.cell(row=r_item, column=8, value=f'=IF(ISNUMBER(SEARCH("Заказчика", $G${r_item})), M{r_item}, "")')
        c_off.fill, c_off.alignment, c_off.protection = fill_yellow, align_left, protect_unlocked

        c_price = ws.cell(row=r_item, column=9, value=None)
        c_price.fill, c_price.alignment, c_price.number_format, c_price.protection = fill_yellow, align_right, "#,##0.00", protect_unlocked

        c_vat = ws.cell(row=r_item, column=10, value="Без НДС")
        c_vat.fill, c_vat.alignment, c_vat.protection = fill_yellow, align_center, protect_unlocked

        c_cost = ws.cell(row=r_item, column=11, value=f"=ROUND(F{r_item}*I{r_item}, 2)")
        c_cost.alignment, c_cost.number_format, c_cost.protection = align_right, "#,##0.00", protect_locked

        # Скрытый технический JSON в колонке L (12) и эталон модели в колонке M (13)
        meta_item = {"row_type": "item", "item_idx": idx, "item_id": item_id, "name": name, "ref_model": ref_model, "unit": unit, "quantity": qty, "characteristics": chars}
        c_meta = ws.cell(row=r_item, column=12, value=json.dumps(meta_item, ensure_ascii=False))
        c_meta.protection = protect_locked
        c_ref_m = ws.cell(row=r_item, column=13, value=ref_model)
        c_ref_m.protection = protect_locked

        for c in range(1, 12):
            cell = ws.cell(row=r_item, column=c)
            cell.font, cell.border = font_regular, thin_border
            if c not in (7, 8, 9, 10):
                cell.protection = protect_locked

        curr_row += 1

        # Подстроки для каждой характеристики товара
        for c_idx, char in enumerate(chars):
            r_char = curr_row

            ws.cell(row=r_char, column=1, value=f"{idx + 1}.{c_idx + 1}").alignment = align_center
            ws.cell(row=r_char, column=2, value=item_id).alignment = align_center
            ws.cell(row=r_char, column=3, value=f"  • {char.get('name', '')}").alignment = align_left
            ws.cell(row=r_char, column=4, value=char.get("req_value", "")).alignment = align_left
            ws.cell(row=r_char, column=5, value=char.get("unit", "")).alignment = align_center
            ws.cell(row=r_char, column=6, value="")

            c_type_ch = ws.cell(row=r_char, column=7, value="Точный показатель*")
            c_type_ch.alignment, c_type_ch.font = align_center, font_sub

            # Жёлтая ячейка для ввода точного значения характеристики участником
            req_v = str(char.get("req_value", "")).strip()
            ref_v = str(char.get("ref_value") or extract_default_exact_value(req_v)).strip()
            if "offered_value" in char:
                init_off_val = str(char.get("offered_value") or "")
                c_off_ch = ws.cell(row=r_char, column=8, value=init_off_val)
            else:
                init_off_val = ref_v
                c_off_ch = ws.cell(row=r_char, column=8, value=f'=IF(ISNUMBER(SEARCH("Заказчика", $G${r_item})), M{r_char}, "")')
            c_off_ch.fill, c_off_ch.alignment, c_off_ch.protection = fill_yellow, align_left, protect_unlocked
            ws.row_dimensions[r_char].height = _calc_row_height(
                [(char.get("name", ""), 36), (req_v, 40), (init_off_val, 42)],
                min_h=24.0,
                line_h=13.0,
                pad=6.0,
            )

            # Колонки I, J, K пустые для характеристик
            ws.cell(row=r_char, column=9, value="")
            ws.cell(row=r_char, column=10, value="")
            ws.cell(row=r_char, column=11, value="")

            meta_char = {"row_type": "char", "item_idx": idx, "item_id": item_id, "char_idx": c_idx, "name": char.get("name", ""), "req_value": req_v, "ref_value": ref_v, "unit": char.get("unit", "")}
            ws.cell(row=r_char, column=12, value=json.dumps(meta_char, ensure_ascii=False)).protection = protect_locked
            c_ref_ch = ws.cell(row=r_char, column=13, value=ref_v)
            c_ref_ch.protection = protect_locked

            for c in range(1, 12):
                cell = ws.cell(row=r_char, column=c)
                cell.font = font_sub if c != 8 else font_regular
                cell.border = thin_border
                if c != 8:
                    cell.fill = fill_sub
                    cell.protection = protect_locked

            curr_row += 1

    # Валидация выпадающих списков только для строк товаров
    if item_rows_indices:
        dv_offer = DataValidation(type="list", formula1='"Предоставляю модель Заказчика (по ТЗ),Эквивалент (аналог)"', allow_blank=True)
        ws.add_data_validation(dv_offer)
        dv_item_vat = DataValidation(type="list", formula1='"Без НДС,в т.ч. НДС 20%,в т.ч. НДС 22%,в т.ч. НДС 10%,в т.ч. НДС 5%,в т.ч. НДС 7%"', allow_blank=True)
        ws.add_data_validation(dv_item_vat)
        for r_i in item_rows_indices:
            dv_offer.add(f"G{r_i}")
            dv_item_vat.add(f"J{r_i}")

    # Строка ИТОГО
    r_total = curr_row
    ws.row_dimensions[r_total].height = 26
    ws.merge_cells(start_row=r_total, start_column=1, end_row=r_total, end_column=10)
    c_tot_label = ws.cell(row=r_total, column=1, value="ИТОГО по технико-коммерческому предложению, руб.:")
    c_tot_label.font, c_tot_label.alignment = font_bold, align_right

    for c in range(1, 11):
        ws.cell(row=r_total, column=c).border = thin_border

    c_tot_sum = ws.cell(row=r_total, column=11, value=f"=SUM(K13:K{r_total - 1})" if item_rows_indices else 0)
    c_tot_sum.font, c_tot_sum.border, c_tot_sum.alignment, c_tot_sum.number_format = font_bold, thin_border, align_right, "#,##0.00"

    # Памятка участнику
    r_memo = r_total + 2
    memo_lines = [
        "* Внимание! Участник заполняет ячейки со светло-жёлтым фоном (реквизиты в строках 4–10, марку/модель/цену товара и значения характеристик в графе 8).",
        "* Для каждой позиции товара под основной строкой выделены отдельные строки для всех характеристик ТЗ. При предложении эквивалента укажите конкретные значения в каждой строке.",
        "* Цену за ед. укажите в графе 9. Ставку НДС выберите в графе 10. Сумма рассчитывается автоматически.",
        "* Заполненный файл .xlsx вместе со скан-копией .pdf прикрепите в составе заявки на электронной площадке.",
    ]
    for i, line in enumerate(memo_lines):
        r_m = r_memo + i
        ws.merge_cells(start_row=r_m, start_column=1, end_row=r_m, end_column=11)
        cell = ws.cell(row=r_m, column=1, value=line)
        cell.font, cell.alignment = font_hint, align_left

    col_widths = {
        "A": 10, "B": 18, "C": 36, "D": 40, "E": 10, "F": 10,
        "G": 22, "H": 42, "I": 16, "J": 16, "K": 18,
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Скрываем колонку L с JSON и колонку M с эталонными значениями
    ws.column_dimensions["L"].hidden = True
    ws.column_dimensions["M"].hidden = True

    # Защита листа
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

        chars = extract_item_structured_chars(item, raw.get("description", ""))

        rows.append({
            "item_id": getattr(item, "id", None),
            "okpd2": "",
            "name": raw["name"],
            "quantity": raw["quantity"],
            "unit": raw["unit"],
            "unit_price": raw["unit_price"],
            "description": raw["description"],
            "characteristics": chars,
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
