# -*- coding: utf-8 -*-
"""Generate backend/templates/contract_amendment.docx template.

Uses pure python-docx without any {% tr %} or {% tc %} tags.
"""
import os
import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


def build_template():
    doc = docx.Document()

    for s in doc.sections:
        s.top_margin = Inches(0.79)
        s.bottom_margin = Inches(0.79)
        s.left_margin = Inches(0.79)
        s.right_margin = Inches(0.79)

    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № {{amendment_number}}")
    r_title.bold = True
    r_title.font.name = "Times New Roman"
    r_title.font.size = Pt(13)

    # Subtitle
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_sub = p_sub.add_run("к Договору № {{contract_number}} от {{contract_date}} г.")
    r_sub.bold = True
    r_sub.font.name = "Times New Roman"
    r_sub.font.size = Pt(12)

    # City & Date
    tbl_meta = doc.add_table(rows=1, cols=2)
    tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_city = tbl_meta.cell(0, 0)
    c_date = tbl_meta.cell(0, 1)

    p_city = c_city.paragraphs[0]
    p_city.paragraph_format.space_after = Pt(12)
    r_c = p_city.add_run("г. {{contract_city}}")
    r_c.font.name = "Times New Roman"
    r_c.font.size = Pt(11)

    p_date = c_date.paragraphs[0]
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_date.paragraph_format.space_after = Pt(12)
    r_d = p_date.add_run("«{{amendment_day}}» {{amendment_month}} {{amendment_year}} г.")
    r_d.font.name = "Times New Roman"
    r_d.font.size = Pt(11)

    # Preamble
    p_pre = doc.add_paragraph()
    p_pre.paragraph_format.line_spacing = 1.15
    p_pre.paragraph_format.space_after = Pt(8)
    p_pre.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    preamble_text = (
        "{{customer_full_name}}, именуемое в дальнейшем «Заказчик», в лице "
        "{{customer_signatory_genitive}}, действующего на основании "
        "{{customer_signatory_basis}}, с одной стороны, и {{contractor_full_name}}, "
        "именуемое в дальнейшем «Подрядчик», в лице {{contractor_signatory_genitive}}, "
        "действующего на основании {{contractor_signatory_basis}}, с другой стороны, "
        "совместно именуемые «Стороны», а по отдельности «Сторона», заключили настоящее "
        "Дополнительное соглашение к Договору № {{contract_number}} от {{contract_date}} г. "
        "о нижеследующем:"
    )
    r_pre = p_pre.add_run(preamble_text)
    r_pre.font.name = "Times New Roman"
    r_pre.font.size = Pt(11)

    # Clauses
    p_cl = doc.add_paragraph()
    p_cl.paragraph_format.line_spacing = 1.15
    p_cl.paragraph_format.space_after = Pt(14)
    p_cl.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r_cl = p_cl.add_run("{{clauses_text}}")
    r_cl.font.name = "Times New Roman"
    r_cl.font.size = Pt(11)

    # Signatures title
    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sig.paragraph_format.space_after = Pt(8)
    r_sig = p_sig.add_run("АДРЕСА, РЕКВИЗИТЫ И ПОДПИСИ СТОРОН")
    r_sig.bold = True
    r_sig.font.name = "Times New Roman"
    r_sig.font.size = Pt(11)

    # Table of signatories
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_l = tbl.cell(0, 0)
    c_r = tbl.cell(0, 1)

    p_l = c_l.paragraphs[0]
    p_l.paragraph_format.line_spacing = 1.15
    r_l = p_l.add_run(
        "ЗАКАЗЧИК:\n"
        "{{customer_short_name}}\n"
        "Адрес: {{customer_address}}\n"
        "ИНН: {{customer_inn}} / КПП: {{customer_kpp}}\n"
        "ОГРН: {{customer_ogrn}}\n"
        "Р/с: {{customer_settlement_account}}\n"
        "Банк: {{customer_bank_name}}\n"
        "БИК: {{customer_bik}}\n"
        "К/с: {{customer_correspondent_account}}\n\n"
        "{{customer_signatory_position}}\n\n"
        "_________________ / {{customer_signatory_name_initials}} /\n"
        "М.П."
    )
    r_l.font.name = "Times New Roman"
    r_l.font.size = Pt(9.5)

    p_r = c_r.paragraphs[0]
    p_r.paragraph_format.line_spacing = 1.15
    r_r = p_r.add_run(
        "ПОДРЯДЧИК:\n"
        "{{contractor_short_name}}\n"
        "Адрес: {{contractor_address}}\n"
        "ИНН: {{contractor_inn}} / КПП: {{contractor_kpp}}\n"
        "ОГРН: {{contractor_ogrn}}\n"
        "Р/с: {{contractor_settlement_account}}\n"
        "Банк: {{contractor_bank_name}}\n"
        "БИК: {{contractor_bik}}\n"
        "К/с: {{contractor_correspondent_account}}\n\n"
        "{{contractor_signatory_position}}\n\n"
        "_________________ / {{contractor_signatory_name_initials}} /\n"
        "М.П."
    )
    r_r.font.name = "Times New Roman"
    r_r.font.size = Pt(9.5)

    out_path = os.path.join("backend", "templates", "contract_amendment.docx")
    doc.save(out_path)
    print(f"Created template at {out_path}")


if __name__ == "__main__":
    build_template()
