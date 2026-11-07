"""Вспомогательные утилиты стилизации и форматирования docx-таблиц для протоколов ВСКС.

ПРАВИЛО №5: файл строго модульный (< 500 строк).
ПРАВИЛО №6: единый источник формирования разметки docxtpl-шаблона протокола.
"""
from datetime import date, datetime
import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Cm, Pt

logger = logging.getLogger(__name__)

RU_MONTHS_GEN = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

CANDIDATE_HEADER_TEMPLATES = [
    "procurement_protocol.docx",
    "order_purchase.docx",
    "contract_goods_single.docx",
    "contract_services.docx",
    "contract.docx",
    "fabrikant_documentation.docx",
    "approval_sheet.docx",
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


def _extract_org_header_from_contract_doc(doc: docx.Document) -> Dict[str, str]:
    """Извлекает наименование организации, краткое наименование и город из договора."""
    info = {"customer_name": "", "customer_short_name": "", "city": ""}
    full_text = " ".join([p.text for p in doc.paragraphs[:25]])
    for table in doc.tables[:1]:
        for row in table.rows:
            full_text += " " + " ".join([c.text for c in row.cells])
    m_city = re.search(r"г\.\s*([А-Яа-яA-Za-z\-]+)", full_text)
    if m_city:
        info["city"] = m_city.group(1).strip()
    m_org = re.search(r"(ВСЕРОССИЙСКАЯ[^\n,]+|ВОМО[^\n,]+|ОБЩЕРОССИЙСКАЯ[^\n,]+|[А-ЯA-Z]{3,}\s*«[^»]+»)", full_text)
    if m_org:
        info["customer_name"] = m_org.group(1).strip()
    m_short = re.search(r"«([^»]+)»", info.get("customer_name") or full_text)
    if m_short:
        info["customer_short_name"] = f"«{m_short.group(1).strip()}»"
    return info


def is_valid_full_protocol_template(doc_or_path: Any) -> bool:
    """Проверяет, содержит ли docx шаблон протокола полную разметку (3 таблицы и ключевые разделы)."""
    try:
        if isinstance(doc_or_path, str):
            if not os.path.exists(doc_or_path):
                return False
            d = docx.Document(doc_or_path)
        else:
            d = doc_or_path
        if len(d.tables) < 3:
            return False
        all_text = " ".join([p.text for p in d.paragraphs]).upper()
        required_markers = [
            "РАБОТЫ КОМИССИИ",
            "РАССМОТРЕНИЕ ЗАЯВОК",
            "РЕШЕНИЯ, ПРИНЯТЫЕ КОМИССИЕЙ",
        ]
        return all(m in all_text for m in required_markers)
    except Exception:
        return False


def populate_protocol_template_body(doc: docx.Document, org_info: Optional[Dict[str, str]] = None) -> None:
    """Заполняет тело docx-документа полной docxtpl-разметкой протокола ВСКС (6 разделов, 3 таблицы, подписи)."""
    default_customer = (org_info and org_info.get("customer_name")) or "____________________"
    default_short = (org_info and org_info.get("customer_short_name")) or "Заказчика"
    default_city = (org_info and org_info.get("city")) or "Москва"

    # Шапка протокола
    add_styled_p(doc, "ПРОТОКОЛ ________", font_name="Times New Roman", size_pt=14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_styled_p(doc, "РАБОТЫ КОМИССИИ", font_name="Times New Roman", size_pt=14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_styled_p(
        doc,
        "(Извещение № {{ publication_number|default(purchase_number|default('__________')) }} "
        "от {{ publication_date|default('«__» _________ 202_ г.') }})",
        font_name="Times New Roman",
        size_pt=11,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=12,
    )

    add_styled_p(
        doc,
        f"г. {{{{ city|default('{default_city}') }}}}\t\t\t\t\t\t\t\t\t{{{{ protocol_date_formatted|default('«__» _________ 202_ г.') }}}}",
        font_name="Times New Roman",
        size_pt=11,
        bold=True,
        space_after=10,
    )

    preamble_lines = [
        f"\tЗаказчик: {{{{ customer_name|default('{default_customer}') }}}}",
        f"\tОрганизатор закупки: {{{{ customer_name|default('{default_customer}') }}}}",
        "\tСпособ закупки: {{ procurement_method|default('запрос предложений') }}",
        "\tПредмет закупки: {{ purchase_name|default(name|default('____________________')) }}",
        "\tНачальная (максимальная) цена договора: {{ nmck_formatted|default('не установлена') }}",
        "\tМесто и время проведения заседания Комиссии: {{ meeting_place_and_time|default('119454, город Москва, пр-кт Вернадского, д. 78 строен 8, эт/пом/ком цок/I/4 в 16:30 (время московское)') }}",
    ]
    for pl in preamble_lines:
        add_styled_p(doc, pl, font_name="Times New Roman", size_pt=10.5, space_after=3)

    # 1. Общая информация
    add_styled_p(doc, "1. Общая информация", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    sec1_lines = [
        "\t1.1. Извещение о запросе № {{ publication_number|default(purchase_number|default('__________')) }} было размещено {{ publication_date|default('__') }}, на сайте электронной торговой площадки (далее – ЭТП) в информационно-коммуникационной сети интернет по адресу: {{ etp_url|default('https://www.fabrikant.ru/') }}",
        "\t1.2. Срок окончания подачи заявок на участие в закупке {{ submission_deadline|default('12:00 (время московское) «__» _________ 202_ года') }}.",
        f"\t1.3. Рассмотрение заявок проводилось комиссией по проведению закупки (далее – Комиссия). Состав Комиссии утвержден приказом {{{{ customer_short_name|default('{default_short}') }}}} №{{{{ commission_order_number|default('__') }}}} от {{{{ commission_order_date|default('«__» _________ 202_ г.') }}}} в составе {{{{ commission_total_count|default('__') }}}} человек.",
        "\t1.4. Заседание проводится очно (по видеоконференцсвязи), в присутствии:",
    ]
    for s1 in sec1_lines:
        add_styled_p(doc, s1, font_name="Times New Roman", size_pt=10.5, space_after=3)

    # Таблица 1: Состав комиссии
    t1 = doc.add_table(rows=4, cols=2)
    t1.rows[0].cells[0].text = "ФИО, должность"
    t1.rows[0].cells[1].text = "Роль в Комиссии"
    t1.rows[1].cells[0].text = "{%tr for m in commission_members %}"
    t1.rows[1].cells[1].text = ""
    t1.rows[2].cells[0].text = "{{ m.full_name }}{% if m.position %}, {{ m.position }}{% endif %}"
    t1.rows[2].cells[1].text = "{{ m.role }}{% if not m.present %} (отсутствовал(а)){% endif %}"
    t1.rows[3].cells[0].text = "{%tr endfor %}"
    t1.rows[3].cells[1].text = ""
    style_table(t1, [Cm(10.5), Cm(6.0)])

    add_styled_p(doc, "1.5. Кворум имеется, Комиссия правомочна.", font_name="Times New Roman", size_pt=10.5, space_before=6, space_after=8)

    # 2. Рассмотрение заявок
    add_styled_p(doc, "2. Рассмотрение заявок", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    add_styled_p(doc, "\t2.1. Комиссия рассматривает поступившие заявки участников закупки на соответствие требованиям закупочной документации.", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t2.2. Количество поданных на ЭТП заявок на участие в закупке: {{ applications_count|default('0') }}", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t2.3. Комиссия рассмотрела поступившие заявки и приняла следующие решения:", font_name="Times New Roman", size_pt=10.5, space_after=4)

    # Таблица 2: Рассмотрение заявок
    t2 = doc.add_table(rows=4, cols=4)
    t2.rows[0].cells[0].text = "№ заявки"
    t2.rows[0].cells[1].text = "Наименование организации (для юридических лиц); Фамилия Имя Отчество  (для физических лиц);"
    t2.rows[0].cells[2].text = "Дата и время подачи заявки, цена предложения"
    t2.rows[0].cells[3].text = "Принятое решение"
    t2.rows[1].cells[0].text = "{%tr for app in applications %}"
    t2.rows[1].cells[1].text = ""
    t2.rows[1].cells[2].text = ""
    t2.rows[1].cells[3].text = ""
    t2.rows[2].cells[0].text = "{{ app.app_number }}."
    t2.rows[2].cells[1].text = "{{ app.contractor_name }}{% if app.contractor_inn %}\nИНН / КПП {{ app.contractor_inn }}{% if app.contractor_kpp %} / {{ app.contractor_kpp }}{% endif %}{% endif %}"
    t2.rows[2].cells[2].text = "{{ app.submitted_at_formatted|default('') }} {{ app.offer_price_formatted|default('') }}"
    t2.rows[2].cells[3].text = "{{ app.decision_text|default(app.rejection_reason|default('Признать соответствующей требованиям закупочной документации.')) }}"
    t2.rows[3].cells[0].text = "{%tr endfor %}"
    t2.rows[3].cells[1].text = ""
    t2.rows[3].cells[2].text = ""
    t2.rows[3].cells[3].text = ""
    style_table(t2, [Cm(1.8), Cm(6.0), Cm(4.5), Cm(4.2)])

    add_styled_p(doc, "\t2.4. Количество отклоненных заявок участников: {{ rejected_applications_count|default('0') }}", font_name="Times New Roman", size_pt=10.5, space_before=4, space_after=3)
    add_styled_p(doc, "\t2.5. Количество заявок участников, признанных соответствующими требованиям закупочной документации: {{ admitted_applications_count|default('0') }}", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t2.6. {{ note_on_single_application|default('Закупка может быть признана несоответствующей по причине наличия только одной заявки.') }}", font_name="Times New Roman", size_pt=10.5, space_after=6)

    # 3. Оценка заявок
    add_styled_p(doc, "3. Оценка заявок", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    add_styled_p(doc, "\t3.1. Порядок оценки и сопоставления заявок участников закупки установлен в закупочной документации.", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t3.2. Лучшим предложением по цене товара (работы, услуги) является предложение с наименьшей ценой исполнения договора.", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t3.3. Предложения поступившие от участников закупки:", font_name="Times New Roman", size_pt=10.5, space_after=6)

    # 4. Сопоставление и ранжирование
    add_styled_p(doc, "4. Сопоставление и ранжирование по результатам оценки заявок", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    add_styled_p(doc, "\t4.1. Порядок оценки и сопоставления заявок участников закупки установлен в закупочной документации.", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t4.2. {{ ranking_method_text|default('Комиссия ранжирует заявки по предложенной цене.') }}", font_name="Times New Roman", size_pt=10.5, space_after=4)

    # Таблица 3: Ранжирование
    t3 = doc.add_table(rows=4, cols=4)
    t3.rows[0].cells[0].text = "№ заявки"
    t3.rows[0].cells[1].text = "Наименование организации (для юридических лиц); Фамилия Имя Отчество (для физических лиц);"
    t3.rows[0].cells[2].text = "Цена исполнения договора"
    t3.rows[0].cells[3].text = "Присвоенное место"
    t3.rows[1].cells[0].text = "{%tr for app in ranked_applications %}"
    t3.rows[1].cells[1].text = ""
    t3.rows[1].cells[2].text = ""
    t3.rows[1].cells[3].text = ""
    t3.rows[2].cells[0].text = "{{ app.app_number }}."
    t3.rows[2].cells[1].text = "{{ app.contractor_name }}{% if app.contractor_inn %}\nИНН / КПП {{ app.contractor_inn }}{% if app.contractor_kpp %} / {{ app.contractor_kpp }}{% endif %}{% endif %}"
    t3.rows[2].cells[2].text = "{{ app.offer_price_formatted|default('') }}"
    t3.rows[2].cells[3].text = "{{ app.rank|default(loop.index) }}"
    t3.rows[3].cells[0].text = "{%tr endfor %}"
    t3.rows[3].cells[1].text = ""
    t3.rows[3].cells[2].text = ""
    t3.rows[3].cells[3].text = ""
    style_table(t3, [Cm(1.8), Cm(7.0), Cm(4.5), Cm(3.2)])

    # 5. Решения, принятые Комиссией
    add_styled_p(doc, "5. Решения, принятые Комиссией", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    add_styled_p(doc, "\t5.1. {{ decision_status_text|default('В соответствии с положением о закупках признать закупку состоявшейся.') }}", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t5.2. Признать победителем закупки {{ winner_name|default('________________________') }} по цене {{ winner_price_formatted|default('__') }}.", font_name="Times New Roman", size_pt=10.5, space_after=3)
    add_styled_p(doc, "\t5.3. Настоящий протокол подлежит хранению в течение трех лет от даты подведения итогов запроса.", font_name="Times New Roman", size_pt=10.5, space_after=6)

    # 6. Подписи
    add_styled_p(doc, "6. Подписи", font_name="Times New Roman", size_pt=11, bold=True, space_before=10, space_after=4)
    add_styled_p(doc, "Подписи членов Закупочной комиссии:", font_name="Times New Roman", size_pt=10.5, bold=True, space_after=6)
    add_styled_p(doc, "{%p for m in commission_members %}", font_name="Times New Roman", size_pt=10.5)
    add_styled_p(doc, "{{ m.role }}:\t\t\t____________________ / {{ m.full_name }} /", font_name="Times New Roman", size_pt=10.5, space_after=4)
    add_styled_p(doc, "{%p endfor %}", font_name="Times New Roman", size_pt=10.5)


def _find_subsidy_dir(subsidy_id: Any) -> Optional[str]:
    if not subsidy_id:
        return None
    try:
        sid_int = int(subsidy_id)
    except (ValueError, TypeError):
        return None
    candidates = [
        f"/app/uploads/templates/subsidies/{sid_int}",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "templates", "subsidies", str(sid_int))),
        os.path.abspath(os.path.join("backend", "uploads", "templates", "subsidies", str(sid_int))),
        os.path.abspath(os.path.join("uploads", "templates", "subsidies", str(sid_int))),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def resolve_or_build_subsidy_protocol_base_doc(
    subsidy_id: Optional[int],
    custom_dir: Optional[str] = None,
    for_rendering: bool = False,
) -> docx.Document:
    """Возвращает docx.Document для протокола субсидии.

    1) При `for_rendering=False` гарантирует наличие на диске полного валидного шаблона
       `procurement_protocol.docx` (с 6 разделами, 3 таблицами docxtpl) и возвращает его.
    2) При `for_rendering=True` возвращает документ с сохранёнными колонтитулами
       организации и очищенным телом для программного наполнения через python-docx.
    """
    subsidy_dir = custom_dir or _find_subsidy_dir(subsidy_id)

    if subsidy_dir:
        proto_path = os.path.join(subsidy_dir, "procurement_protocol.docx")
        # Проверяем, существует ли уже валидный полный шаблон на диске
        if os.path.isfile(proto_path) and is_valid_full_protocol_template(proto_path):
            doc = docx.Document(proto_path)
            if for_rendering:
                preserve_tbl = _should_preserve_first_table(doc)
                _clear_doc_body_paragraphs(doc, preserve_first_table=preserve_tbl)
            return doc

        # Если файла нет или он без разметки — строим полный шаблон с шапкой организации
        org_doc = None
        org_info: Dict[str, str] = {}
        for cand in CANDIDATE_HEADER_TEMPLATES:
            cand_path = os.path.join(subsidy_dir, cand)
            if os.path.isfile(cand_path):
                try:
                    org_doc = docx.Document(cand_path)
                    org_info = _extract_org_header_from_contract_doc(org_doc)
                    preserve_tbl = _should_preserve_first_table(org_doc)
                    _clear_doc_body_paragraphs(org_doc, preserve_first_table=preserve_tbl)
                    break
                except Exception as e:
                    logger.debug("Failed opening candidate template %s: %s", cand_path, e)

        if org_doc is None:
            org_doc = docx.Document()
            for sec in org_doc.sections:
                sec.top_margin = Cm(1.5)
                sec.bottom_margin = Cm(1.5)
                sec.left_margin = Cm(2.0)
                sec.right_margin = Cm(1.5)

        populate_protocol_template_body(org_doc, org_info)
        saved_ok = False
        try:
            os.makedirs(subsidy_dir, exist_ok=True)
            org_doc.save(proto_path)
            saved_ok = True
        except Exception as se:
            logger.debug("Could not save populated protocol template %s: %s", proto_path, se)

        if for_rendering:
            if saved_ok and os.path.isfile(proto_path):
                try:
                    doc_render = docx.Document(proto_path)
                    preserve_tbl = _should_preserve_first_table(doc_render)
                    _clear_doc_body_paragraphs(doc_render, preserve_first_table=preserve_tbl)
                    return doc_render
                except Exception:
                    pass
            preserve_tbl = _should_preserve_first_table(org_doc)
            _clear_doc_body_paragraphs(org_doc, preserve_first_table=preserve_tbl)
            return org_doc
        return org_doc

    # Глобальный базовый шаблон
    global_paths = [
        "/app/templates/procurement_protocol.docx",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates", "procurement_protocol.docx")),
        os.path.abspath(os.path.join("backend", "templates", "procurement_protocol.docx")),
        os.path.abspath(os.path.join("templates", "procurement_protocol.docx")),
    ]
    for gp in global_paths:
        if os.path.isfile(gp) and is_valid_full_protocol_template(gp):
            doc = docx.Document(gp)
            if for_rendering:
                preserve_tbl = _should_preserve_first_table(doc)
                _clear_doc_body_paragraphs(doc, preserve_first_table=preserve_tbl)
            return doc

    # Создаём дефолтный полный документ
    doc = docx.Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(2.0)
        sec.right_margin = Cm(1.5)
    populate_protocol_template_body(doc)
    if for_rendering:
        _clear_doc_body_paragraphs(doc)
    return doc


def ensure_subsidy_protocol_templates_from_contracts() -> list[str]:
    """Сканирует папки шаблонов всех субсидий и создаёт валидный procurement_protocol.docx."""
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
                    if not os.path.exists(proto_file) or not is_valid_full_protocol_template(proto_file):
                        try:
                            sid = int(entry) if entry.isdigit() else None
                            doc = resolve_or_build_subsidy_protocol_base_doc(sid, custom_dir=sub_dir, for_rendering=False)
                            if doc and os.path.exists(proto_file):
                                created.append(proto_file)
                        except Exception as e:
                            logger.debug("Failed auto-creation for %s: %s", sub_dir, e)
    return created
