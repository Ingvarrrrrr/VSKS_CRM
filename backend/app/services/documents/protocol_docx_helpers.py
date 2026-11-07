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


import os
import shutil
import logging
import docx

logger = logging.getLogger(__name__)

CANDIDATE_HEADER_TEMPLATES = [
    "procurement_protocol.docx",
    "order_purchase.docx",
    "contract_goods_single.docx",
    "contract_services.docx",
    "contract.docx",
    "fabrikant_documentation.docx",
    "approval_sheet.docx",
]


def _clear_doc_body_paragraphs(doc: docx.Document, preserve_first_table: bool = False):
    """Очищает тело документа (параграфы и таблицы), сохраняя колонтитулы (header/footer) и sectPr."""
    body = doc.element.body
    first_tbl_seen = False
    for child in list(body):
        if child.tag.endswith("sectPr"):
            continue
        if child.tag.endswith("tbl") and preserve_first_table and not first_tbl_seen:
            first_tbl_seen = True
            continue
        body.remove(child)


def _should_preserve_first_table(doc: docx.Document) -> bool:
    """Проверяет, есть ли таблица-шапка организации в самом верху тела документа (до названия договора/приказа)."""
    if not doc.tables:
        return False
    first_tbl = doc.tables[0]._tbl
    body = doc.element.body
    for child in body:
        if child == first_tbl:
            return True
        if child.tag.endswith("p"):
            txt = "".join(child.itertext()).strip().upper()
            if "ДОГОВОР" in txt or "ПРИКАЗ" in txt or "ПРОТОКОЛ" in txt:
                return False
    return True


def _find_subsidy_dir(subsidy_id: Optional[int]) -> Optional[str]:
    if not subsidy_id:
        return None
    candidates = [
        f"/app/uploads/templates/subsidies/{subsidy_id}",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "templates", "subsidies", str(subsidy_id))),
        os.path.abspath(os.path.join("backend", "uploads", "templates", "subsidies", str(subsidy_id))),
        os.path.abspath(os.path.join("uploads", "templates", "subsidies", str(subsidy_id))),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def resolve_or_build_subsidy_protocol_base_doc(
    subsidy_id: Optional[int],
    custom_dir: Optional[str] = None,
) -> docx.Document:
    """Возвращает базовый docx.Document для протокола субсидии.

    1) Если уже есть `procurement_protocol.docx` в папке субсидии — открывает его,
       очищает тело (сохраняя колонтитулы header/first_page_header с логотипами и шапкой).
    2) Если `procurement_protocol.docx` ещё нет, но есть шаблон договора или приказа
       (contract_goods_single, contract_services, order_purchase, etc.) в папке субсидии —
       берёт его колонтитулы/шапку, сохраняет как готовый `procurement_protocol.docx`
       и возвращает очищенный документ.
    3) Если шаблонов субсидии нет — открывает глобальный `backend/templates/procurement_protocol.docx`
       (или создаёт новый чистый документ с полями A4).
    """
    subsidy_dir = custom_dir or _find_subsidy_dir(subsidy_id)

    # 1. Если уже есть собственный procurement_protocol.docx у субсидии
    if subsidy_dir and os.path.exists(subsidy_dir):
        proto_path = os.path.join(subsidy_dir, "procurement_protocol.docx")
        if os.path.isfile(proto_path):
            try:
                doc = docx.Document(proto_path)
                preserve_tbl = _should_preserve_first_table(doc)
                _clear_doc_body_paragraphs(doc, preserve_first_table=preserve_tbl)
                return doc
            except Exception as e:
                logger.debug("Failed to open existing subsidy protocol template %s: %s", proto_path, e)

        # 2. Ищем шаблон договора/приказа в папке субсидии для копирования шапки/колонтитулов
        for cand in CANDIDATE_HEADER_TEMPLATES:
            cand_path = os.path.join(subsidy_dir, cand)
            if os.path.isfile(cand_path):
                try:
                    doc = docx.Document(cand_path)
                    preserve_tbl = _should_preserve_first_table(doc)
                    _clear_doc_body_paragraphs(doc, preserve_first_table=preserve_tbl)
                    try:
                        os.makedirs(subsidy_dir, exist_ok=True)
                        doc.save(proto_path)
                    except Exception as se:
                        logger.debug("Could not save auto-generated protocol template %s: %s", proto_path, se)
                    return doc
                except Exception as e:
                    logger.debug("Failed to extract header from candidate %s: %s", cand_path, e)

    # 3. Глобальный базовый шаблон
    global_paths = [
        "/app/templates/procurement_protocol.docx",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates", "procurement_protocol.docx")),
        os.path.abspath(os.path.join("backend", "templates", "procurement_protocol.docx")),
        os.path.abspath(os.path.join("templates", "procurement_protocol.docx")),
    ]
    for gp in global_paths:
        if os.path.isfile(gp):
            try:
                doc = docx.Document(gp)
                preserve_tbl = _should_preserve_first_table(doc)
                _clear_doc_body_paragraphs(doc, preserve_first_table=preserve_tbl)
                return doc
            except Exception:
                pass

    # Fallback: пустой документ
    doc = docx.Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(2.0)
        sec.right_margin = Cm(1.5)
    return doc


def ensure_subsidy_protocol_templates_from_contracts() -> list[str]:
    """Сканирует папки шаблонов всех субсидий и создаёт procurement_protocol.docx при наличии шаблонов договоров."""
    created = []
    base_dirs = [
        "/app/uploads/templates/subsidies",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "templates", "subsidies")),
        os.path.abspath(os.path.join("backend", "uploads", "templates", "subsidies")),
    ]
    for b in base_dirs:
        if os.path.isdir(b):
            for entry in os.listdir(b):
                sub_dir = os.path.join(b, entry)
                if os.path.isdir(sub_dir):
                    proto_file = os.path.join(sub_dir, "procurement_protocol.docx")
                    if not os.path.exists(proto_file):
                        try:
                            sid = int(entry) if entry.isdigit() else None
                            doc = resolve_or_build_subsidy_protocol_base_doc(sid, custom_dir=sub_dir)
                            if doc and os.path.exists(proto_file):
                                created.append(proto_file)
                        except Exception as e:
                            logger.debug("Failed auto-creation for %s: %s", sub_dir, e)
    return created
