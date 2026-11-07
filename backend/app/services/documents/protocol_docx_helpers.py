"""Вспомогательные утилиты стилизации и форматирования docx-таблиц для протоколов ВСКС."""
from datetime import date, datetime
from typing import Any, List, Optional

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Cm, Pt

RU_MONTHS_GEN = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def quote_ru_date(d: Any) -> str:
    """Форматирует дату в «17» февраля 2026 г."""
    if not d:
        return "«__» _________ 202_ г."
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except Exception:
            return str(d)
    if isinstance(d, (date, datetime)):
        m_name = RU_MONTHS_GEN[d.month] if 1 <= d.month <= 12 else ""
        return f"«{d.day:02d}» {m_name} {d.year} г."
    return str(d)


def style_run(run, font_name="Times New Roman", size_pt=10.5, bold=False, italic=False):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic


def add_styled_p(
    doc,
    text: str = "",
    font_name="Times New Roman",
    size_pt=10.5,
    bold=False,
    italic=False,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    space_after=0,
    space_before=0,
    line_spacing=1.0,
):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.line_spacing = line_spacing
    if text:
        r = p.add_run(text)
        style_run(r, font_name, size_pt, bold, italic)
    return p


def style_table(table, col_widths: Optional[List[Cm]] = None):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        r'<w:tblBorders %s>'
        r'  <w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'  <w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'  <w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        r'</w:tblBorders>' % nsdecls("w")
    )
    tblPr.append(borders)
    for row in table.rows:
        for c_idx, cell in enumerate(row.cells):
            tcPr = cell._tc.get_or_add_tcPr()
            tcMar = parse_xml(
                r'<w:tcMar %s>'
                r'  <w:top w:w="120" w:type="dxa"/>'
                r'  <w:bottom w:w="120" w:type="dxa"/>'
                r'  <w:left w:w="160" w:type="dxa"/>'
                r'  <w:right w:w="160" w:type="dxa"/>'
                r'</w:tcMar>' % nsdecls("w")
            )
            tcPr.append(tcMar)
            if col_widths and c_idx < len(col_widths):
                cell.width = col_widths[c_idx]
