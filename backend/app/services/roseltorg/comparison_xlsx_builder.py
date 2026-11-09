"""Построитель сводной таблицы сравнения предложений всех участников (ТКП).

ПРАВИЛО №5: компактный модуль (< 350 строк).
ПРАВИЛО №6: единый источник строк ТЗ load_standardized_tkp_rows.
"""
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_publication import PlatformPublication
from app.services.documents.tkp_form_xlsx import load_standardized_tkp_rows
from app.services.roseltorg.analog_matcher import clean_str, extract_default_exact_value, parse_num


def build_comparison_matrix_xlsx(
    purchase_subject: str,
    customer_name: str,
    nmck: float,
    tz_rows: List[Dict[str, Any]],
    applications: List[Dict[str, Any]],
    purchase_id: Optional[int] = None,
) -> bytes:
    """Формирует книгу Excel «Сводная таблица ТКП» со сопоставлением предложений всех участников."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сводная таблица ТКП"
    ws.views.sheetView[0].showGridLines = True

    font_title, font_bold, font_regular, font_sub = Font(name="Calibri", size=13, bold=True, color="1565C0"), Font(name="Calibri", size=10, bold=True), Font(name="Calibri", size=10), Font(name="Calibri", size=9, color="555555")
    font_warn_banner = Font(name="Calibri", size=10, bold=True, color="BF360C")
    font_ok, font_warn, font_alt, font_rej = Font(name="Calibri", size=9, bold=True, color="2E7D32"), Font(name="Calibri", size=9, bold=True, color="E65100"), Font(name="Calibri", size=9, bold=True, color="0277BD"), Font(name="Calibri", size=9, bold=True, color="C62828")

    fill_header, fill_tz, fill_ok = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid"), PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid"), PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
    fill_warn, fill_alt, fill_rej, fill_warn_banner = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid"), PatternFill(start_color="E1F5FE", end_color="E1F5FE", fill_type="solid"), PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid"), PatternFill(start_color="FFE0B2", end_color="FFE0B2", fill_type="solid")

    thin_border_side = Side(style="thin", color="CCCCCC")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="center", wrap_text=True)

    def _calc_row_h(texts: List[str], col_ws: List[int], min_h: float = 24.0, line_h: float = 13.5, pad: float = 7.0) -> float:
        max_lines = 1
        for t, w in zip(texts, col_ws):
            s = clean_str(t)
            if not s:
                continue
            for line in s.split("\n"):
                eff = max(int(w * 0.85), 6)
                lines = max(1, (len(line) + eff - 1) // eff)
                if lines > max_lines:
                    max_lines = lines
        return max(min_h, round(max_lines * line_h + pad, 1))

    # Шапка документа
    ws.cell(1, 1, "СВОДНАЯ ТАБЛИЦА СРАВНЕНИЯ ПРЕДЛОЖЕНИЙ УЧАСТНИКОВ (ТКП)").font = font_title
    ws.row_dimensions[1].height = 24
    ws.cell(2, 1, f"Закупка: {purchase_subject or (f'#{purchase_id}' if purchase_id else '')}").font = font_bold
    ws.row_dimensions[2].height = 20
    ws.cell(3, 1, f"Заказчик: {customer_name or 'ВСКС'} | НМЦК: {nmck:,.2f} руб.").font = font_regular
    ws.row_dimensions[3].height = 20

    curr_row = 5
    has_any_tz_corr = any(
        app.get("has_tz_correction")
        or any(p.get("has_tz_correction") for p in app.get("positions", []))
        for app in applications
    )
    if has_any_tz_corr:
        ws.merge_cells(start_row=curr_row, start_column=1, end_row=curr_row, end_column=max(6 + len(applications) * 2, 8))
        banner_c = ws.cell(curr_row, 1, "⚠️ ВНИМАНИЕ ЗАКАЗЧИКУ: Участник(и) указали на возможную неточность в характеристиках ТЗ при поставке запрашиваемой модели (выделено оранжевым цветом в таблице ниже)!")
        banner_c.font, banner_c.fill, banner_c.alignment = font_warn_banner, fill_warn_banner, align_left
        ws.row_dimensions[curr_row].height = 28
        curr_row += 2

    # Шапка таблицы (2 строки: строка заголовков заказчика и участников)
    hdr_row = curr_row
    ws.row_dimensions[hdr_row].height = 42

    tz_headers = [
        (1, "№ п/п"), (2, "Наименование товара / характеристики"),
        (3, "Требования Заказчика (ТЗ)"), (4, "Эталон модели ТЗ"),
        (5, "Ед. изм."), (6, "Кол-во"),
    ]
    for c_idx, h_text in tz_headers:
        c = ws.cell(hdr_row, c_idx, h_text)
        c.font, c.fill, c.border, c.alignment = font_bold, fill_header, thin_border, align_center

    app_col_widths = []
    for app_idx, app in enumerate(applications):
        c_m = 7 + app_idx * 2
        c_s = c_m + 1
        s_name = app.get("supplier_name") or f"Участник {app_idx + 1}"
        cm_cell = ws.cell(hdr_row, c_m, f"Участник № {app_idx + 1}:\n{s_name}\n(Предложенная модель)")
        cm_cell.font, cm_cell.fill, cm_cell.border, cm_cell.alignment = font_bold, fill_header, thin_border, align_center
        cs_cell = ws.cell(hdr_row, c_s, f"Участник № {app_idx + 1}:\nСтатус проверки / Цена")
        cs_cell.font, cs_cell.fill, cs_cell.border, cs_cell.alignment = font_bold, fill_header, thin_border, align_center
        app_col_widths.extend([32, 28])

    curr_row += 1

    # Строки товаров и характеристик
    for idx, row in enumerate(tz_rows):
        r_item = curr_row
        item_num = idx + 1
        name = clean_str(row.get("name"))
        desc = clean_str(row.get("description"))
        unit = clean_str(row.get("unit")) or "шт."
        qty = parse_num(row.get("quantity"))
        chars = row.get("characteristics") or []
        ref_model = clean_str(row.get("ref_model") or row.get("offered_model") or name)

        ws.cell(r_item, 1, item_num).alignment = align_center
        ws.cell(r_item, 2, name).alignment = align_left
        ws.cell(r_item, 3, desc).alignment = align_left
        ws.cell(r_item, 4, ref_model).alignment = align_left
        ws.cell(r_item, 5, unit).alignment = align_center
        c_q = ws.cell(r_item, 6, qty)
        c_q.alignment, c_q.number_format = align_right, "#,##0.00"

        for c in range(1, 7):
            cell = ws.cell(r_item, c)
            cell.font, cell.fill, cell.border = font_bold, fill_tz, thin_border

        texts_for_h = [name, desc, ref_model]
        widths_for_h = [36, 38, 22]

        for app_idx, app in enumerate(applications):
            c_m = 7 + app_idx * 2
            c_s = c_m + 1
            pos = next((p for p in (app.get("positions") or []) if p.get("item_num") == item_num or p.get("purchase_item_id") == row.get("item_id")), None)
            if not pos and app_idx < len(app.get("positions") or []):
                pos = (app.get("positions") or [])[idx] if idx < len(app.get("positions") or []) else None

            if pos:
                off_m = clean_str(pos.get("offered_name") or pos.get("offered_specs") or "")
                is_exact = pos.get("is_exact_model_offer", not pos.get("is_alternative", False))
                type_lbl = "Модель Заказчика" if is_exact else "Эквивалент (аналог)"
                u_p = parse_num(pos.get("unit_price"))
                t_p = parse_num(pos.get("total_price"))
                vat_r = clean_str(pos.get("vat_rate") or "Без НДС")
                c1_txt = f"{off_m}\n({type_lbl})" if off_m else type_lbl
                c2_txt = f"Цена: {u_p:,.2f} руб.\nСумма: {t_p:,.2f} руб.\n{vat_r}"
                status_fill = fill_ok if is_exact else fill_alt
            else:
                c1_txt, c2_txt, status_fill = "—", "—", fill_tz

            cm_c = ws.cell(r_item, c_m, c1_txt)
            cm_c.font, cm_c.fill, cm_c.border, cm_c.alignment = font_bold, status_fill, thin_border, align_left
            cs_c = ws.cell(r_item, c_s, c2_txt)
            cs_c.font, cs_c.fill, cs_c.border, cs_c.alignment = font_regular, status_fill, thin_border, align_right

            texts_for_h.extend([c1_txt, c2_txt])
            widths_for_h.extend([32, 28])

        ws.row_dimensions[r_item].height = _calc_row_h(texts_for_h, widths_for_h, min_h=34.0)
        curr_row += 1

        # Подстроки характеристик
        for c_idx, char in enumerate(chars):
            r_char = curr_row
            ch_num = f"{item_num}.{c_idx + 1}"
            ch_name = clean_str(char.get("name"))
            ch_req = clean_str(char.get("req_value"))
            ch_ref = clean_str(char.get("ref_value") or extract_default_exact_value(ch_req))
            ch_unit = clean_str(char.get("unit"))

            ws.cell(r_char, 1, ch_num).alignment = align_center
            ws.cell(r_char, 2, f"  • {ch_name}").alignment = align_left
            ws.cell(r_char, 3, ch_req).alignment = align_left
            ws.cell(r_char, 4, ch_ref).alignment = align_left
            ws.cell(r_char, 5, ch_unit).alignment = align_center
            ws.cell(r_char, 6, "—").alignment = align_center

            for c in range(1, 7):
                cell = ws.cell(r_char, c)
                cell.font, cell.border = font_sub, thin_border

            ch_texts_h = [ch_name, ch_req, ch_ref]
            ch_widths_h = [36, 38, 22]

            for app_idx, app in enumerate(applications):
                c_m = 7 + app_idx * 2
                c_s = c_m + 1
                pos = next((p for p in (app.get("positions") or []) if p.get("item_num") == item_num or p.get("purchase_item_id") == row.get("item_id")), None)
                if not pos and idx < len(app.get("positions") or []):
                    pos = (app.get("positions") or [])[idx]

                p_chars = pos.get("characteristics") or [] if pos else []
                ch_eval = next((c for c in p_chars if clean_str(c.get("name")).lower() == ch_name.lower() or c.get("param_idx") == c_idx + 1), None)

                if ch_eval:
                    off_v = clean_str(ch_eval.get("offered_value") or ch_eval.get("value"))
                    u_sfx = f" {ch_unit}".rstrip() if ch_unit else ""
                    val_str = f"{off_v}{u_sfx}" if off_v else "—"

                    is_corr = ch_eval.get("tz_corrected_by_supplier") or ch_eval.get("has_tz_correction")
                    is_ok = ch_eval.get("compliant", True)
                    is_alt = pos.get("is_alternative", False) if pos else False

                    if is_corr:
                        status_txt = f"⚠️ Скорректировано участником (было: {ch_req}) — проверьте ТЗ!"
                        ch_fill, ch_font = fill_warn, font_warn
                    elif not is_ok:
                        note = clean_str(ch_eval.get("note")) or f"требуется {ch_req}"
                        status_txt = f"✗ Не соответствует ТЗ ({note})"
                        ch_fill, ch_font = fill_rej, font_rej
                    elif is_alt:
                        status_txt = f"✓ Аналог: {val_str} (соответствует ТЗ)"
                        ch_fill, ch_font = fill_alt, font_alt
                    else:
                        status_txt = "✓ Соответствует ТЗ"
                        ch_fill, ch_font = fill_ok, font_ok
                else:
                    val_str, status_txt, ch_fill, ch_font = "—", "—", fill_tz, font_sub

                c_m_cell = ws.cell(r_char, c_m, val_str)
                c_m_cell.font, c_m_cell.fill, c_m_cell.border, c_m_cell.alignment = ch_font, ch_fill, thin_border, align_center
                c_s_cell = ws.cell(r_char, c_s, status_txt)
                c_s_cell.font, c_s_cell.fill, c_s_cell.border, c_s_cell.alignment = ch_font, ch_fill, thin_border, align_left

                ch_texts_h.extend([val_str, status_txt])
                ch_widths_h.extend([32, 28])

            ws.row_dimensions[r_char].height = _calc_row_h(ch_texts_h, ch_widths_h, min_h=22.0)
            curr_row += 1

    # Итоговые строки
    total_cols_count = 6 + len(applications) * 2

    def _add_summary_row(label: str, values: List[Tuple[str, PatternFill, Font, str]], height: float = 24.0):
        nonlocal curr_row
        r_sum = curr_row
        ws.row_dimensions[r_sum].height = height
        ws.merge_cells(start_row=r_sum, start_column=1, end_row=r_sum, end_column=6)
        lbl_c = ws.cell(r_sum, 1, label)
        lbl_c.font, lbl_c.fill, lbl_c.alignment = font_bold, fill_header, align_right
        for c in range(1, 7):
            ws.cell(r_sum, c).border = thin_border

        for app_idx, (val_str, fill_val, font_val, num_fmt) in enumerate(values):
            c_m = 7 + app_idx * 2
            c_s = c_m + 1
            ws.merge_cells(start_row=r_sum, start_column=c_m, end_row=r_sum, end_column=c_s)
            val_c = ws.cell(r_sum, c_m, val_str)
            val_c.font, val_c.fill, val_c.border, val_c.alignment = font_val, fill_val, thin_border, align_center
            ws.cell(r_sum, c_s).border = thin_border
            if num_fmt:
                val_c.number_format = num_fmt
        curr_row += 1

    # 1. Итоговая стоимость
    price_vals = []
    for app in applications:
        p = parse_num(app.get("price") or app.get("price_with_vat") or app.get("total_price"))
        price_vals.append((f"{p:,.2f} руб.", fill_tz, font_bold, None))
    _add_summary_row("ИТОГО стоимость предложения, руб.:", price_vals, height=26.0)

    # 2. Снижение от НМЦК
    drop_vals = []
    for app in applications:
        p = parse_num(app.get("price") or app.get("price_with_vat") or app.get("total_price"))
        if nmck > 0 and p > 0:
            diff_pct = (nmck - p) / nmck * 100.0
            drop_vals.append((f"-{diff_pct:.1f}%" if diff_pct > 0 else f"+{abs(diff_pct):.1f}%", fill_tz, font_bold, None))
        else:
            drop_vals.append(("0.0%", fill_tz, font_regular, None))
    _add_summary_row("Снижение от НМЦК, %:", drop_vals, height=22.0)

    # 3. Решение комиссии
    dec_vals = []
    for app in applications:
        adm = app.get("admitted", True)
        has_tz_corr = app.get("has_tz_correction", False)
        if not adm:
            dec_vals.append(("Отклонён (несоответствие ТЗ)", fill_rej, font_rej, None))
        elif has_tz_corr:
            dec_vals.append(("⚠️ Требует решения Заказчика (корректировка ТЗ)", fill_warn, font_warn, None))
        else:
            dec_vals.append(("Допущен (соответствует ТЗ)", fill_ok, font_ok, None))
    _add_summary_row("Решение комиссии / Допуск:", dec_vals, height=24.0)

    # 4. Итоговое место
    place_vals = []
    for app in applications:
        pl = app.get("place")
        txt = f"{pl}-е место" if pl else "—"
        fnt = font_bold if pl == 1 else font_regular
        place_vals.append((txt, fill_tz, fnt, None))
    _add_summary_row("Итоговое место:", place_vals, height=22.0)

    # Ширины столбцов
    col_widths = {"A": 8, "B": 36, "C": 38, "D": 22, "E": 10, "F": 14}
    for c_letter, w in col_widths.items():
        ws.column_dimensions[c_letter].width = w

    for col_idx in range(7, total_cols_count + 1):
        c_letter = get_column_letter(col_idx)
        ws.column_dimensions[c_letter].width = 30 if col_idx % 2 == 1 else 28

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def build_comparison_matrix_for_publication(
    db: AsyncSession,
    pub_id: int,
) -> Tuple[Optional[bytes], str, List[str]]:
    """Загружает данные закупки и протокола и формирует сводную матрицу сравнения."""
    res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
    pub = res.scalar_one_or_none()
    if not pub:
        return None, "", [f"Публикация {pub_id} не найдена"]

    purchase_id = getattr(pub, "purchase_id", None)
    if not purchase_id:
        return None, "", [f"У публикации {pub_id} не указана закупка"]

    p, tz_rows, errors = await load_standardized_tkp_rows(db, purchase_id)
    if not p:
        return None, "", errors or [f"Закупка {purchase_id} не найдена"]

    results_data = getattr(pub, "results_data", None) or {}
    applications = results_data.get("applications") or []
    if not applications and results_data.get("application"):
        applications = [results_data["application"]]

    subject = str(getattr(p, "subject", "") or getattr(p, "registry_number", "") or f"Закупка #{p.id}")
    nmck = float(getattr(p, "initial_price", 0.0) or 0.0)

    xlsx_bytes = build_comparison_matrix_xlsx(
        purchase_subject=subject,
        customer_name="ВОМО «ВСКС»",
        nmck=nmck,
        tz_rows=tz_rows,
        applications=applications,
        purchase_id=p.id,
    )
    filename = f"Сводная_таблица_ТКП_{pub.registry_number or pub.id}.xlsx"
    return xlsx_bytes, filename, errors
