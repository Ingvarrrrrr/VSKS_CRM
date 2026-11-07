"""Генератор интерактивного заполняемого PDF-бланка «Приложение_2_Форма_ТКП.pdf» (AcroForm).

ПРАВИЛО №5: компактный модуль (< 320 строк).
ПРАВИЛО №6: единый источник строк ТЗ load_standardized_tkp_rows.
"""
import json
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.documents.tkp_form_xlsx import load_standardized_tkp_rows

TKP_PDF_ZIP_FILE_NAME = "Приложение_2_Форма_ТКП.pdf"
TKP_PDF_MARKER = "GALA_TKP_PDF_V1"

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
]


def _get_font_path() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def build_standardized_tkp_pdf(
    rows: List[Dict[str, Any]],
    *,
    purchase_id: Optional[int] = None,
    purchase_subject: str = "",
    customer_name: str = "",
) -> bytes:
    """Создаёт интерактивный заполняемый PDF-файл «Приложение № 2 — Форма ТКП»."""
    doc = fitz.open()
    font_path = _get_font_path()

    page_width, page_height = 842.0, 595.0
    margin_x = 36.0
    col_widths = [24, 30, 106, 110, 34, 38, 84, 130, 64, 70, 80]
    col_x = [margin_x]
    for w in col_widths:
        col_x.append(col_x[-1] + w)

    headers = [
        "№ п/п",
        "ID поз.",
        "Название продукции (по ТЗ)",
        "Требования Заказчика к ТЗ",
        "Ед. изм.",
        "Кол-во",
        "Тип предложения*",
        "Предложение участника (марка, модель)",
        "Ставка НДС*",
        "Цена за ед., руб.*",
        "Стоимость, руб.",
    ]

    def _setup_page(pg: fitz.Page, is_first: bool) -> float:
        if font_path:
            pg.insert_font(fontname="f0", fontfile=font_path)
            bold_p = font_path.replace("arial.ttf", "arialbd.ttf").replace("Sans.ttf", "Sans-Bold.ttf")
            if os.path.exists(bold_p):
                pg.insert_font(fontname="f0b", fontfile=bold_p)
            else:
                pg.insert_font(fontname="f0b", fontfile=font_path)
        else:
            pg.insert_font(fontname="f0", fontname_builtin="helv")
            pg.insert_font(fontname="f0b", fontname_builtin="helv-bold")

        if is_first:
            # Заголовок и маркер
            pg.insert_text(fitz.Point(margin_x, 26), "ПРИЛОЖЕНИЕ № 2 — ФОРМА ТЕХНИКО-КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ (ТКП)", fontname="f0b", fontsize=11)
            pg.insert_text(fitz.Point(700, 26), TKP_PDF_MARKER, fontname="f0", fontsize=8, color=(0.5, 0.5, 0.5))

            subj = purchase_subject or (f"Закупка #{purchase_id}" if purchase_id else "")
            pg.insert_text(fitz.Point(margin_x, 40), f"Закупка: {subj}", fontname="f0", fontsize=8.5)
            pg.insert_text(fitz.Point(margin_x, 52), f"Заказчик: {customer_name or 'ВСКС'}", fontname="f0", fontsize=8.5)

            # Реквизиты
            def _add_field(name: str, label: str, rect: fitz.Rect, def_val: str = "", choices: Optional[List[str]] = None):
                pg.insert_text(fitz.Point(rect.x0 - 180 if rect.x0 > 200 else margin_x, rect.y0 + 12), label, fontname="f0b", fontsize=8)
                pg.draw_rect(rect, color=(0.8, 0.8, 0.8), fill=(1.0, 0.99, 0.91))
                w = fitz.Widget()
                w.field_name = name
                w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX if choices else fitz.PDF_WIDGET_TYPE_TEXT
                if choices:
                    w.choice_values = choices
                w.field_value = def_val
                w.rect = rect
                w.text_fontsize = 8
                pg.add_widget(w)

            _add_field("supplier_name", "Наименование участника*:", fitz.Rect(210, 64, 520, 80))
            _add_field("inn", "ИНН участника*:", fitz.Rect(210, 84, 350, 100))
            _add_field("kpp", "КПП участника:", fitz.Rect(440, 84, 560, 100))
            _add_field("contacts", "Телефон и E-mail:", fitz.Rect(210, 104, 520, 120))
            _add_field(
                "vat_rate",
                "Ставка НДС*:",
                fitz.Rect(630, 104, 760, 120),
                def_val="Без НДС",
                choices=["Без НДС", "в т.ч. НДС 20%", "в т.ч. НДС 22%", "в т.ч. НДС 10%", "в т.ч. НДС 5%", "в т.ч. НДС 7%"],
            )
            _add_field("validity_days", "Срок действия ТКП (дн.)*:", fitz.Rect(210, 124, 290, 140), def_val="30")
            _add_field("outgoing_ref", "Исх. № и дата ТКП:", fitz.Rect(440, 124, 760, 140))

            start_table_y = 152.0
        else:
            start_table_y = 30.0

        # Шапка таблицы
        hdr_h = 24.0
        for i, h in enumerate(headers):
            r = fitz.Rect(col_x[i], start_table_y, col_x[i + 1], start_table_y + hdr_h)
            pg.draw_rect(r, color=(0.7, 0.7, 0.7), fill=(0.9, 0.94, 0.98))
            pg.insert_textbox(fitz.Rect(r.x0 + 2, r.y0 + 2, r.x1 - 2, r.y1 - 2), h, fontname="f0b", fontsize=7.5, align=fitz.TEXT_ALIGN_CENTER)
        return start_table_y + hdr_h

    current_page = doc.new_page(width=page_width, height=page_height)
    curr_y = _setup_page(current_page, is_first=True)
    row_h = 28.0

    for idx, row in enumerate(rows):
        if curr_y + row_h > 530.0:
            current_page = doc.new_page(width=page_width, height=page_height)
            curr_y = _setup_page(current_page, is_first=False)

        item_id = row.get("item_id") or (idx + 1)
        name = str(row.get("name") or "").strip()
        desc = str(row.get("description") or "").strip()
        unit = str(row.get("unit") or "").strip() or "шт."
        qty = 0.0
        try:
            qty = float(row.get("quantity") or 0.0)
        except (ValueError, TypeError):
            qty = 0.0

        # Метаданные строки в скрытом/readonly виджете
        meta_val = json.dumps({"item_id": item_id, "name": name, "description": desc, "unit": unit, "quantity": qty}, ensure_ascii=False)
        w_meta = fitz.Widget()
        w_meta.field_name = f"item_{idx}_meta"
        w_meta.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w_meta.field_value = meta_val
        w_meta.rect = fitz.Rect(0, 0, 1, 1)
        w_meta.field_flags = fitz.PDF_FIELD_IS_READ_ONLY
        current_page.add_widget(w_meta)

        # Отрисовка колонок 0-5 (неизменяемые)
        r0 = fitz.Rect(col_x[0], curr_y, col_x[1], curr_y + row_h)
        current_page.draw_rect(r0, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r0.x0 + 1, r0.y0 + 6, r0.x1 - 1, r0.y1 - 2), str(idx + 1), fontname="f0", fontsize=7.5, align=fitz.TEXT_ALIGN_CENTER)

        r1 = fitz.Rect(col_x[1], curr_y, col_x[2], curr_y + row_h)
        current_page.draw_rect(r1, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r1.x0 + 1, r1.y0 + 6, r1.x1 - 1, r1.y1 - 2), str(item_id), fontname="f0", fontsize=7.5, align=fitz.TEXT_ALIGN_CENTER)

        r2 = fitz.Rect(col_x[2], curr_y, col_x[3], curr_y + row_h)
        current_page.draw_rect(r2, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r2.x0 + 2, r2.y0 + 2, r2.x1 - 2, r2.y1 - 2), name, fontname="f0", fontsize=7)

        r3 = fitz.Rect(col_x[3], curr_y, col_x[4], curr_y + row_h)
        current_page.draw_rect(r3, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r3.x0 + 2, r3.y0 + 2, r3.x1 - 2, r3.y1 - 2), desc, fontname="f0", fontsize=6.5)

        r4 = fitz.Rect(col_x[4], curr_y, col_x[5], curr_y + row_h)
        current_page.draw_rect(r4, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r4.x0 + 1, r4.y0 + 6, r4.x1 - 1, r4.y1 - 2), unit, fontname="f0", fontsize=7.5, align=fitz.TEXT_ALIGN_CENTER)

        r5 = fitz.Rect(col_x[5], curr_y, col_x[6], curr_y + row_h)
        current_page.draw_rect(r5, color=(0.8, 0.8, 0.8))
        current_page.insert_textbox(fitz.Rect(r5.x0 + 1, r5.y0 + 6, r5.x1 - 2, r5.y1 - 2), f"{qty:g}", fontname="f0", fontsize=7.5, align=fitz.TEXT_ALIGN_RIGHT)

        # Интерактивные виджеты участника (колонки 6-9, жёлтый фон)
        def _add_cell_widget(col_idx: int, field_name: str, def_val: str = "", choices: Optional[List[str]] = None):
            rect = fitz.Rect(col_x[col_idx], curr_y, col_x[col_idx + 1], curr_y + row_h)
            current_page.draw_rect(rect, color=(0.8, 0.8, 0.8), fill=(1.0, 0.99, 0.91))
            w = fitz.Widget()
            w.field_name = field_name
            w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX if choices else fitz.PDF_WIDGET_TYPE_TEXT
            if choices:
                w.choice_values = choices
            w.field_value = def_val
            w.rect = fitz.Rect(rect.x0 + 1, rect.y0 + 1, rect.x1 - 1, rect.y1 - 1)
            w.text_fontsize = 7.5
            current_page.add_widget(w)

        _add_cell_widget(6, f"item_{idx}_offer_type", def_val="По ТЗ Заказчика", choices=["По ТЗ Заказчика", "Эквивалент (аналог)"])
        _add_cell_widget(7, f"item_{idx}_offered_specs", def_val="")
        _add_cell_widget(8, f"item_{idx}_vat_rate", def_val="Без НДС", choices=["Без НДС", "20%", "22%", "10%", "5%", "7%"])
        _add_cell_widget(9, f"item_{idx}_unit_price", def_val="")
        _add_cell_widget(10, f"item_{idx}_total_price", def_val="")

        curr_y += row_h

    # Строка ИТОГО
    r_tot_lbl = fitz.Rect(col_x[0], curr_y, col_x[10], curr_y + 20)
    current_page.draw_rect(r_tot_lbl, color=(0.8, 0.8, 0.8))
    current_page.insert_text(fitz.Point(col_x[10] - 250, curr_y + 14), "ИТОГО по предложению, руб.:", fontname="f0b", fontsize=8.5)

    r_tot_val = fitz.Rect(col_x[10], curr_y, col_x[11], curr_y + 20)
    current_page.draw_rect(r_tot_val, color=(0.8, 0.8, 0.8))
    w_total = fitz.Widget()
    w_total.field_name = "grand_total_price"
    w_total.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w_total.field_value = ""
    w_total.rect = fitz.Rect(r_tot_val.x0 + 1, r_tot_val.y0 + 1, r_tot_val.x1 - 1, r_tot_val.y1 - 1)
    w_total.text_fontsize = 8
    current_page.add_widget(w_total)
    curr_y += 24.0

    # Памятка участнику
    memo = (
        "* Внимание! Заполните поля со светло-жёлтым фоном (реквизиты и предложение участника).\n"
        "* При предложении эквивалента выберите «Эквивалент (аналог)» в графе 7 и укажите точные характеристики в графе 8.\n"
        "* Заполненный PDF-бланк (или подписанную скан-копию) прикрепите в составе заявки на торговой площадке."
    )
    current_page.insert_textbox(fitz.Rect(margin_x, curr_y, margin_x + 750, curr_y + 36), memo, fontname="f0", fontsize=7, color=(0.4, 0.4, 0.4))

    return doc.tobytes()


async def render_standardized_tkp_pdf(
    db: AsyncSession,
    purchase_id: int,
) -> Tuple[Optional[bytes], List[str]]:
    """Собирает стандартизированный файл интерактивного бланка ТКП в формате PDF."""
    p, rows, errors = await load_standardized_tkp_rows(db, purchase_id)
    if not p:
        return None, errors or [f"Закупка {purchase_id} не найдена"]
    if not rows:
        return None, errors or [f"У закупки {purchase_id} нет позиций для бланка ТКП"]

    subject = str(getattr(p, "subject", "") or getattr(p, "registry_number", "") or f"Закупка #{p.id}")
    pdf_bytes = build_standardized_tkp_pdf(
        rows,
        purchase_id=p.id,
        purchase_subject=subject,
        customer_name="ВСКС",
    )
    return pdf_bytes, errors
