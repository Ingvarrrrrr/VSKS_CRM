# -*- coding: utf-8 -*-
"""Генератор Дополнительных соглашений (ДС №1..N) к договору (Волна 4c).

ПРАВИЛО №5: < 500 строк.
ПРАВИЛО №6: Единый источник истины (склонение подписантов через
contexts_signatory_cases.py, форматирование через formatting.py).
НИКОГДА не использует {% tr %} / {% tc %} в .docx шаблонах!
"""
import io
import os
from datetime import date
from typing import Any, Dict, List, Optional

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt
from docxtpl import DocxTemplate

from app.services.documents.contexts_signatory_cases import enrich_document_signatories_and_orders
from app.services.documents.formatting import (
    _fmt_date,
    _fmt_money,
    _fmt_quantity,
    _rubles_to_words,
)

RU_MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_ru_date_parts(d: Any) -> tuple[str, str, str]:
    """Возвращает (день '05', месяц 'ноября', год '2026')."""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d.split("T")[0])
        except Exception:
            d = date.today()
    elif not isinstance(d, date):
        d = date.today()

    day = f"{d.day:02d}"
    month = RU_MONTHS_GEN[d.month - 1]
    year = str(d.year)
    return day, month, year


def build_amendment_clauses(
    price_change: Optional[Dict[str, Any]] = None,
    term_change: Optional[Dict[str, Any]] = None,
    has_spec_change: bool = False,
    custom_clauses: Optional[List[str]] = None,
) -> str:
    """Формирует юридически выверенные пункты Дополнительного соглашения с авто-нумерацией."""
    clauses: List[str] = []
    num = 1

    # 1. Изменение цены договора с НДС
    if price_change and price_change.get("new_price") is not None:
        new_price = float(price_change["new_price"])
        clause_ref = price_change.get("clause_ref", "3.1")
        price_rub = _fmt_money(new_price)
        price_words = _rubles_to_words(new_price)

        vat_rate = price_change.get("vat_rate")
        vat_applicable = price_change.get("vat_applicable", True)

        if vat_applicable and vat_rate is not None and float(vat_rate) > 0:
            rate_val = float(vat_rate)
            vat_amount = round(new_price * rate_val / (100 + rate_val), 2)
            vat_rub = _fmt_money(vat_amount)
            vat_words = _rubles_to_words(vat_amount)
            vat_text = f"в том числе НДС {int(rate_val)}% в размере {vat_rub} ({vat_words})"
        else:
            vat_text = "НДС не облагается"

        clauses.append(
            f"{num}. Изложить пункт {clause_ref} Договора в следующей редакции:\n"
            f"   «Цена Договора составляет {price_rub} руб. ({price_words}), {vat_text}»."
        )
        num += 1

    # 2. Изменение срока поставки / действия договора
    if term_change and term_change.get("new_date"):
        new_date_val = term_change["new_date"]
        clause_ref = term_change.get("clause_ref", "4.1")
        day_str, month_str, year_str = format_ru_date_parts(new_date_val)
        date_formatted = f"«{day_str}» {month_str} {year_str} года"

        clauses.append(
            f"{num}. Изложить пункт {clause_ref} Договора в следующей редакции:\n"
            f"   «Срок действия Договора (поставки товаров / оказания услуг) продлевается до {date_formatted}»."
        )
        num += 1

    # 3. Изменение спецификации позиций
    if has_spec_change:
        clauses.append(
            f"{num}. Изложить Спецификацию (Приложение к Договору) в новой редакции согласно "
            f"Приложению № 1 к настоящему Дополнительному соглашению."
        )
        num += 1

    # 4. Дополнительные пользовательские пункты (если переданы)
    if custom_clauses:
        for c in custom_clauses:
            if c and c.strip():
                clauses.append(f"{num}. {c.strip()}")
                num += 1

    # 5. Заключительные стандартные пункты
    clauses.append(
        f"{num}. Настоящее Дополнительное соглашение вступает в силу с момента его подписания "
        f"обеими Сторонами и является неотъемлемой частью Договора."
    )
    num += 1
    clauses.append(
        f"{num}. Все остальные условия Договора, не затронутые настоящим Дополнительным "
        f"соглашением, остаются без изменений."
    )
    num += 1
    clauses.append(
        f"{num}. Настоящее Дополнительное соглашение составлено в двух подлинных экземплярах, "
        f"имеющих одинаковую юридическую силу, по одному для каждой из Сторон."
    )

    return "\n\n".join(clauses)


def build_amendment_context(
    contract_data: Dict[str, Any],
    amendment_data: Dict[str, Any],
    customer_data: Optional[Dict[str, Any]] = None,
    contractor_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Формирует полный docxtpl-контекст для шаблона contract_amendment.docx."""
    ctx: Dict[str, Any] = {}

    # Реквизиты ДС
    num = str(amendment_data.get("amendment_number") or "1")
    ctx["amendment_number"] = num
    am_date = amendment_data.get("amendment_date") or date.today()
    ctx["amendment_date"] = _fmt_date(am_date)
    day, month, year = format_ru_date_parts(am_date)
    ctx["amendment_day"] = day
    ctx["amendment_month"] = month
    ctx["amendment_year"] = year

    # Договор-основание
    ctx["contract_number"] = str(contract_data.get("number") or "—")
    ctx["contract_date"] = _fmt_date(contract_data.get("date"))
    ctx["contract_city"] = contract_data.get("city") or "Москва"

    # Заказчик
    cust = customer_data or {}
    ctx["customer_full_name"] = cust.get("full_name") or cust.get("name") or "Заказчик"
    ctx["customer_short_name"] = cust.get("short_name") or cust.get("name") or "Заказчик"
    ctx["customer_address"] = cust.get("address") or "—"
    ctx["customer_inn"] = cust.get("inn") or "—"
    ctx["customer_kpp"] = cust.get("kpp") or "—"
    ctx["customer_ogrn"] = cust.get("ogrn") or "—"
    ctx["customer_settlement_account"] = cust.get("settlement_account") or "—"
    ctx["customer_bank_name"] = cust.get("bank_name") or "—"
    ctx["customer_bik"] = cust.get("bik") or "—"
    ctx["customer_correspondent_account"] = cust.get("correspondent_account") or "—"
    ctx["customer_signatory"] = cust.get("signatory") or ""
    ctx["customer_signatory_name"] = cust.get("signatory_name") or ""
    ctx["customer_signatory_position"] = cust.get("signatory_position") or "Руководитель"
    ctx["customer_signatory_name_initials"] = cust.get("signatory_name_initials") or cust.get("signatory_name") or ""
    ctx["customer_signatory_basis"] = cust.get("signatory_basis") or "Устава"

    # Подрядчик
    ctr = contractor_data or {}
    ctx["contractor_full_name"] = ctr.get("full_name") or ctr.get("name") or "Подрядчик"
    ctx["contractor_short_name"] = ctr.get("short_name") or ctr.get("name") or "Подрядчик"
    ctx["contractor_address"] = ctr.get("address") or "—"
    ctx["contractor_inn"] = ctr.get("inn") or "—"
    ctx["contractor_kpp"] = ctr.get("kpp") or "—"
    ctx["contractor_ogrn"] = ctr.get("ogrn") or "—"
    ctx["contractor_settlement_account"] = ctr.get("settlement_account") or "—"
    ctx["contractor_bank_name"] = ctr.get("bank_name") or "—"
    ctx["contractor_bik"] = ctr.get("bik") or "—"
    ctx["contractor_correspondent_account"] = ctr.get("correspondent_account") or "—"
    ctx["contractor_signatory"] = ctr.get("signatory") or ""
    ctx["contractor_signatory_name"] = ctr.get("signatory_name") or ""
    ctx["contractor_signatory_position"] = ctr.get("signatory_position") or "Директор"
    ctx["contractor_signatory_name_initials"] = ctr.get("signatory_name_initials") or ctr.get("signatory_name") or ""
    ctx["contractor_signatory_basis"] = ctr.get("signatory_basis") or "Устава"

    # Обогащаем падежами подписантов через ЕДИНЫЙ источник (Правило №6)
    enrich_document_signatories_and_orders(ctx)

    # Пункты ДС
    price_change = amendment_data.get("price_change")
    term_change = amendment_data.get("term_change")
    spec_items = amendment_data.get("specification_items")
    has_spec = bool(spec_items and len(spec_items) > 0)
    custom_cl = amendment_data.get("custom_clauses")

    ctx["clauses_text"] = build_amendment_clauses(
        price_change=price_change,
        term_change=term_change,
        has_spec_change=has_spec,
        custom_clauses=custom_cl,
    )

    if price_change and price_change.get("new_price") is not None:
        ctx["new_contract_price"] = f"{_fmt_money(price_change['new_price'])} ₽"
    if term_change and term_change.get("new_date"):
        ctx["new_delivery_term"] = _fmt_date(term_change["new_date"])

    return ctx


def append_specification_table(
    doc: docx.Document,
    items: List[Dict[str, Any]],
    amendment_number: str,
    contract_number: str,
    contract_date_str: str,
) -> None:
    """Безопасно строит таблицу Спецификации позиций через python-docx без {% tr %}."""
    doc.add_page_break()

    p_annex = doc.add_paragraph()
    p_annex.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_annex = p_annex.add_run(
        f"Приложение № 1\nк Дополнительному соглашению № {amendment_number}\n"
        f"к Договору № {contract_number} от {contract_date_str} г."
    )
    r_annex.font.name = "Times New Roman"
    r_annex.font.size = Pt(10)
    r_annex.italic = True

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run("СПЕЦИФИКАЦИЯ ТОВАРОВ / УСЛУГ (в новой редакции)")
    r_title.bold = True
    r_title.font.name = "Times New Roman"
    r_title.font.size = Pt(12)

    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Заголовок таблицы
    headers = [
        ("№ п/п", Inches(0.6)),
        ("Наименование товара (услуги)", Inches(3.2)),
        ("Ед. изм.", Inches(0.8)),
        ("Кол-во", Inches(0.8)),
        ("Цена с НДС, руб.", Inches(1.1)),
        ("Сумма с НДС, руб.", Inches(1.2)),
    ]
    hdr_cells = table.rows[0].cells
    for i, (title, width) in enumerate(headers):
        hdr_cells[i].width = width
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(9.5)

    # Строки позиций
    total_sum = 0.0
    for idx, item in enumerate(items, start=1):
        row = table.add_row()
        name = str(item.get("name") or "Товар")
        unit = str(item.get("unit") or "шт.")
        qty = float(item.get("quantity") or 1.0)
        price = float(item.get("unit_price") or 0.0)
        total = float(item.get("total") if item.get("total") is not None else (qty * price))
        total_sum += total

        vals = [
            (str(idx), WD_ALIGN_PARAGRAPH.CENTER),
            (name, WD_ALIGN_PARAGRAPH.LEFT),
            (unit, WD_ALIGN_PARAGRAPH.CENTER),
            (_fmt_quantity(qty), WD_ALIGN_PARAGRAPH.RIGHT),
            (_fmt_money(price), WD_ALIGN_PARAGRAPH.RIGHT),
            (_fmt_money(total), WD_ALIGN_PARAGRAPH.RIGHT),
        ]
        for col_idx, (text_val, align) in enumerate(vals):
            c = row.cells[col_idx]
            c.width = headers[col_idx][1]
            p = c.paragraphs[0]
            p.alignment = align
            r = p.add_run(text_val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(9)

    # Итоговая строка
    tot_row = table.add_row()
    c_tot_lbl = tot_row.cells[1]
    p_lbl = c_tot_lbl.paragraphs[0]
    p_lbl.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_lbl = p_lbl.add_run("ИТОГО:")
    r_lbl.bold = True
    r_lbl.font.name = "Times New Roman"
    r_lbl.font.size = Pt(9.5)

    c_tot_val = tot_row.cells[5]
    p_val = c_tot_val.paragraphs[0]
    p_val.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_val = p_val.add_run(_fmt_money(total_sum))
    r_val.bold = True
    r_val.font.name = "Times New Roman"
    r_val.font.size = Pt(9.5)

    # Накладываем границы таблицы через XML
    tblPr = table._tbl.tblPr
    borders_xml = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>\n'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'  <w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>\n'
        f'</w:tblBorders>'
    )
    tblPr.append(borders_xml)


def generate_contract_amendment_docx(
    contract_data: Dict[str, Any],
    amendment_data: Dict[str, Any],
    customer_data: Optional[Dict[str, Any]] = None,
    contractor_data: Optional[Dict[str, Any]] = None,
    template_path: Optional[str] = None,
) -> bytes:
    """Генерирует готовый .docx файл Дополнительного соглашения к договору."""
    if not template_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        template_path = os.path.join(base_dir, "templates", "contract_amendment.docx")

    ctx = build_amendment_context(
        contract_data=contract_data,
        amendment_data=amendment_data,
        customer_data=customer_data,
        contractor_data=contractor_data,
    )

    tpl = DocxTemplate(template_path)
    tpl.render(ctx)

    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)

    # Если есть обновлённая спецификация позиций — добавляем таблицу через python-docx
    spec_items = amendment_data.get("specification_items")
    if spec_items and len(spec_items) > 0:
        doc = docx.Document(buf)
        append_specification_table(
            doc=doc,
            items=spec_items,
            amendment_number=str(ctx.get("amendment_number") or "1"),
            contract_number=str(ctx.get("contract_number") or "—"),
            contract_date_str=str(ctx.get("contract_date") or ""),
        )
        final_buf = io.BytesIO()
        doc.save(final_buf)
        final_buf.seek(0)
        return final_buf.getvalue()

    return buf.getvalue()
