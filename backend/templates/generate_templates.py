"""
Run inside backend container:
    docker exec vsks_crm-backend-1 sh -c 'cd /app && python templates/generate_templates.py'
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

TEMPLATES_DIR = os.path.dirname(os.path.abspath(__file__))


def set_cell_bg(cell, hex_color: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def page_margins(doc):
    for sec in doc.sections:
        sec.top_margin = Cm(2)
        sec.bottom_margin = Cm(2)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(1.5)


def add_label_value(doc, label, value, size=10):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(label + " ")
    r.bold = True
    r.font.size = Pt(size)
    r2 = p.add_run(value)
    r2.font.size = Pt(size)
    return p


def hline(doc):
    """Thin horizontal separator."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'CCCCCC')
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


# ── contract_tz.docx ─────────────────────────────────────────────────────────
# Items are rendered using {%p for %} paragraph-level loop.
# Each item gets 3 paragraphs: header, details, description.
# The loop start/end paragraphs are invisible (font size 1).
def make_contract_tz():
    doc = Document()
    page_margins(doc)

    # Title
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("ТЕХНИЧЕСКОЕ ЗАДАНИЕ")
    r.bold = True; r.font.size = Pt(14)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run("к договору № {{contract_number}} от {{contract_date}}").font.size = Pt(11)

    doc.add_paragraph()

    add_label_value(doc, "Субсидия:", "{{subsidy_name}} ({{subsidy_year}})")
    add_label_value(doc, "Реестровый номер:", "{{registry_number}}")
    add_label_value(doc, "Способ закупки:", "{{purchase_method}}")
    add_label_value(doc, "Контрагент:", "{{contractor_name}}, ИНН {{contractor_inn}} / КПП {{contractor_kpp}}")
    add_label_value(doc, "Адрес:", "{{contractor_address}}")
    add_label_value(doc, "Страна происхождения:", "{{country_origin}}")
    add_label_value(doc, "Срок исполнения:", "{{execution_term}}")

    doc.add_paragraph()
    hline(doc)

    # Section header
    hdr = doc.add_paragraph()
    r = hdr.add_run("1. Перечень поставляемых товаров (работ, услуг)")
    r.bold = True; r.font.size = Pt(11)

    doc.add_paragraph()

    # ── Items list using {%p for %} ───────────────────────────
    # Paragraph 1: loop start marker (invisible, size 1)
    p_for = doc.add_paragraph()
    p_for.paragraph_format.space_before = Pt(0)
    p_for.paragraph_format.space_after = Pt(0)
    rr = p_for.add_run("{%p for item in items %}")
    rr.font.size = Pt(1)
    rr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Paragraph 2: item name line (repeated per item)
    p_name = doc.add_paragraph()
    p_name.paragraph_format.space_before = Pt(4)
    p_name.paragraph_format.space_after = Pt(1)
    rn = p_name.add_run("{{item.num}}. {{item.name}}")
    rn.bold = True
    rn.font.size = Pt(10)

    # Paragraph 3: item details
    p_det = doc.add_paragraph()
    p_det.paragraph_format.space_before = Pt(0)
    p_det.paragraph_format.space_after = Pt(1)
    p_det.paragraph_format.left_indent = Cm(0.5)
    rd = p_det.add_run(
        "Тип: {{item.type}}  |  Кол-во: {{item.quantity}} {{item.unit}}"
        "  |  Цена ед.: {{item.unit_price}}  |  Сумма: {{item.total_price}}"
    )
    rd.font.size = Pt(9)
    rd.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    # Paragraph 4: description (shown even if empty, docxtpl will render empty string)
    p_desc = doc.add_paragraph()
    p_desc.paragraph_format.space_before = Pt(0)
    p_desc.paragraph_format.space_after = Pt(4)
    p_desc.paragraph_format.left_indent = Cm(0.5)
    rdesc = p_desc.add_run("{{item.description}}")
    rdesc.font.size = Pt(9)
    rdesc.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    # Paragraph 5: loop end marker (invisible, size 1)
    p_end = doc.add_paragraph()
    p_end.paragraph_format.space_before = Pt(0)
    p_end.paragraph_format.space_after = Pt(0)
    re = p_end.add_run("{%p endfor %}")
    re.font.size = Pt(1)
    re.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    # ── End items list ─────────────────────────────────────────

    hline(doc)
    doc.add_paragraph()

    # Total
    tot = doc.add_paragraph()
    tot.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r1 = tot.add_run("Итого НМЦК: ")
    r1.bold = True; r1.font.size = Pt(12)
    r2 = tot.add_run("{{total_nmck}}")
    r2.bold = True; r2.font.size = Pt(12)
    r2.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)

    doc.add_paragraph()
    add_label_value(doc, "Цена договора:", "{{contract_price}}")
    add_label_value(doc, "Экономия:", "{{economy}}")

    hline(doc)

    # Signatures
    hdr2 = doc.add_paragraph()
    r = hdr2.add_run("2. Подписи сторон")
    r.bold = True; r.font.size = Pt(11)

    sig = doc.add_table(rows=4, cols=2)
    sig.style = 'Table Grid'

    def sig_cell(row, col, text, bold=False):
        p = sig.rows[row].cells[col].paragraphs[0]
        run = p.add_run(text)
        run.bold = bold; run.font.size = Pt(9)

    sig_cell(0, 0, "Заказчик", bold=True)
    sig_cell(0, 1, "Исполнитель", bold=True)
    sig_cell(1, 0, "{{subsidy_name}}")
    sig_cell(1, 1, "{{contractor_name}}")
    sig_cell(2, 0, "Адрес: {{contractor_address}}")
    sig_cell(2, 1,
        "Адрес: {{contractor_postal_address}}\n"
        "ОГРН: {{contractor_ogrn}}\n"
        "р/с {{contractor_settlement_account}}\n"
        "{{contractor_bank_name}}\n"
        "БИК {{contractor_bik}} | к/с {{contractor_correspondent_account}}"
    )
    sig_cell(3, 0, "Подпись: _______________  /  М.П.")
    sig_cell(3, 1, "{{contractor_signatory}}, действует на основании {{contractor_signatory_basis}}\nПодпись: _______________ / М.П.")

    path = os.path.join(TEMPLATES_DIR, "contract_tz.docx")
    doc.save(path)
    print(f"[OK] {path}")


# ── service_note.docx ─────────────────────────────────────────────────────────
def make_service_note():
    doc = Document()
    page_margins(doc)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("СЛУЖЕБНАЯ ЗАПИСКА")
    r.bold = True; r.font.size = Pt(14)

    doc.add_paragraph()

    add_label_value(doc, "Дата:", "{{today}}")
    add_label_value(doc, "Субсидия:", "{{subsidy_name}} ({{subsidy_year}})")
    add_label_value(doc, "Реестровый номер:", "{{registry_number}}")
    add_label_value(doc, "Контрагент:", "{{contractor_name}}, ИНН {{contractor_inn}}")
    add_label_value(doc, "Способ закупки:", "{{purchase_method}}")
    add_label_value(doc, "НМЦК:", "{{total_nmck}}")
    add_label_value(doc, "Цена договора:", "{{contract_price}}")
    add_label_value(doc, "Экономия:", "{{economy}}")
    add_label_value(doc, "Страна происхождения:", "{{country_origin}}")
    add_label_value(doc, "Срок исполнения:", "{{execution_term}}")
    add_label_value(doc, "Договор:", "№{{contract_number}} от {{contract_date}}")

    doc.add_paragraph()

    body = doc.add_paragraph()
    body.add_run(
        "Прошу согласовать закупку №{{purchase_number}} (реестр {{registry_number}}) "
        "у контрагента {{contractor_name}} на сумму {{total_nmck}} "
        "в рамках субсидии «{{subsidy_name}}»."
    ).font.size = Pt(10)

    doc.add_paragraph()
    doc.add_paragraph()

    sig = doc.add_paragraph()
    sig.add_run("Исполнитель: _______________  /  ФИО  /  {{today}}").font.size = Pt(10)

    path = os.path.join(TEMPLATES_DIR, "service_note.docx")
    doc.save(path)
    print(f"[OK] {path}")


# ── approval_sheet.docx ───────────────────────────────────────────────────────
def make_approval_sheet():
    doc = Document()
    page_margins(doc)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("ЛИСТ СОГЛАСОВАНИЯ")
    r.bold = True; r.font.size = Pt(14)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run("Закупка №{{purchase_number}} / Реестр {{registry_number}}").font.size = Pt(11)

    doc.add_paragraph()

    add_label_value(doc, "Субсидия:", "{{subsidy_name}} ({{subsidy_year}})")
    add_label_value(doc, "Контрагент:", "{{contractor_name}}, ИНН {{contractor_inn}}")
    add_label_value(doc, "НМЦК:", "{{total_nmck}}")
    add_label_value(doc, "Цена договора:", "{{contract_price}}")
    add_label_value(doc, "Договор:", "№{{contract_number}} от {{contract_date}}")
    add_label_value(doc, "Срок исполнения:", "{{execution_term}}")

    doc.add_paragraph()

    tbl = doc.add_table(rows=5, cols=4)
    tbl.style = 'Table Grid'
    headers = ["№", "Должность", "ФИО", "Подпись / Дата"]
    for i, h in enumerate(headers):
        p = tbl.rows[0].cells[i].paragraphs[0]
        run = p.add_run(h)
        run.bold = True; run.font.size = Pt(9)
        set_cell_bg(tbl.rows[0].cells[i], "D6E4F7")

    roles = [
        ("1", "Ответственный исполнитель", ""),
        ("2", "Начальник отдела", ""),
        ("3", "Главный бухгалтер", ""),
        ("4", "Руководитель организации", ""),
    ]
    for ridx, (num, role, fio) in enumerate(roles, start=1):
        row = tbl.rows[ridx]
        for cidx, val in enumerate([num, role, fio, ""]):
            row.cells[cidx].paragraphs[0].add_run(val).font.size = Pt(9)

    path = os.path.join(TEMPLATES_DIR, "approval_sheet.docx")
    doc.save(path)
    print(f"[OK] {path}")


if __name__ == "__main__":
    make_contract_tz()
    make_service_note()
    make_approval_sheet()
    print("All templates generated.")
