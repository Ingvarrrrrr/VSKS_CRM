"""generate_document: post-render fixups (approvers table rebuild/patch,
receipts-table marker insertion) and the friendly TEMPLATE_RENDER_ERROR
translation for whatever goes wrong while producing the final buffer.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
import os
import re as _re
import logging
from io import BytesIO

from fastapi import HTTPException
from docxtpl import DocxTemplate

from app.services.documents.doc_types import SUBSIDY_TEMPLATES_DIR
from app.services.documents.templates import _insert_receipts_table_if_marker

logger = logging.getLogger(__name__)


def _rebuild_or_patch_approvers_table(tpl: DocxTemplate, approvers_list: list, receipt_png_paths: list) -> BytesIO:
    """Post-process: fix approvers table if docxtpl loop didn't render all rows."""
    from docx import Document as _DocxDoc
    from copy import deepcopy
    from lxml import etree

    _buf = BytesIO()
    tpl.save(_buf)
    _buf.seek(0)
    _doc = _DocxDoc(_buf)

    # Find the approvers table (has header row with "Должность" or "ФИО")
    target_table = None
    for _t in _doc.tables:
        hdr = " ".join(c.text.strip() for c in _t.rows[0].cells)
        if "Должность" in hdr or "ФИО" in hdr:
            target_table = _t
            break

    if target_table:
        # Count current data rows (skip header)
        current_data_rows = len(target_table.rows) - 1
        needed = len(approvers_list)

        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

        def _set_cell_text(cell_el, text):
            """Replace all cell content with plain text."""
            for p_el in list(cell_el.findall(f'{ns}p')):
                cell_el.remove(p_el)
            p = etree.SubElement(cell_el, f'{ns}p')
            r = etree.SubElement(p, f'{ns}r')
            t = etree.SubElement(r, f'{ns}t')
            t.text = text or ""

        def _set_cell_two_lines(cell_el, line1, line2):
            """Replace cell content with two paragraphs."""
            for p_el in list(cell_el.findall(f'{ns}p')):
                cell_el.remove(p_el)
            p1 = etree.SubElement(cell_el, f'{ns}p')
            r1 = etree.SubElement(p1, f'{ns}r')
            t1 = etree.SubElement(r1, f'{ns}t')
            t1.text = line1 or ""
            p2 = etree.SubElement(cell_el, f'{ns}p')
            r2 = etree.SubElement(p2, f'{ns}r')
            t2 = etree.SubElement(r2, f'{ns}t')
            t2.text = line2 or ""

        if current_data_rows < needed:
            # Rebuild table: template loop didn't render all rows
            template_row_el = target_table.rows[1]._tr
            for row in list(target_table.rows[1:]):
                target_table._tbl.remove(row._tr)
            for a in approvers_list:
                new_tr = deepcopy(template_row_el)
                cells = new_tr.findall(f'.//{ns}tc')
                if len(cells) >= 4:
                    _set_cell_text(cells[0], str(a.get("num", "")))
                    _set_cell_two_lines(cells[1], a.get("role_name", ""), a.get("full_name", ""))
                    _set_cell_text(cells[2], "")
                    _set_cell_text(cells[3], a.get("note", ""))
                target_table._tbl.append(new_tr)
        else:
            # Rows match — patch note/FEO into last column of each data row
            for idx, a in enumerate(approvers_list):
                row_idx = idx + 1  # skip header
                if row_idx >= len(target_table.rows):
                    break
                row_el = target_table.rows[row_idx]._tr
                cells = row_el.findall(f'.//{ns}tc')
                note_val = a.get("note", "")
                if note_val and len(cells) >= 4:
                    _set_cell_text(cells[-1], note_val)

        # Phase 26-ggg: receipts table (no-op если маркер отсутствует)
        _insert_receipts_table_if_marker(_doc, receipt_png_paths)
        buf = BytesIO()
        _doc.save(buf)
        buf.seek(0)
    else:
        _insert_receipts_table_if_marker(tpl.docx, receipt_png_paths)
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    return buf


def _build_template_render_error(e: Exception, pid: int, doc_type: str, template_path: str) -> HTTPException:
    """Phase 23.2: human-friendly error explanations for Jinja/docxtpl errors."""
    err_class = type(e).__name__
    err_msg = str(e)
    template_name = os.path.basename(template_path) if template_path else f"{doc_type}.docx"
    is_custom = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))

    detail = {
        "code": "TEMPLATE_RENDER_ERROR",
        "message": f"Не удалось сгенерировать «{template_name}»",
        "template": template_name,
        "template_source": "Шаблон субсидии (загруженный пользователем)" if is_custom else "Глобальный шаблон",
        "error_class": err_class,
        "error_raw": err_msg,
        "hint": None,
    }

    # Pattern: Jinja2 UndefinedError ('X' is undefined)
    m = _re.match(r"'([a-zA-Z_][a-zA-Z0-9_]*)' is undefined", err_msg)
    if m:
        var_name = m.group(1)
        detail["message"] = f"В шаблоне «{template_name}» используется переменная {{{{{var_name}.…}}}} вне цикла"
        loop_hints = {
            "a": "{% tr for a in approvers %}…{{a.full_name}}…{% tr endfor %}  — переменная для согласующих (approval_sheet, лист согласования)",
            "item": "{% tr for item in items %}…{{item.name}}…{% tr endfor %}  — переменная для позиций закупки",
        }
        if var_name in loop_hints:
            detail["hint"] = (
                f"Переменная «{var_name}» доступна только внутри цикла. "
                f"Оберните строки/ячейки таблицы в:\n  {loop_hints[var_name]}\n\n"
                f"Либо удалите кастомный шаблон в UI «Субсидии → Шаблоны → {template_name} → 🗑» и используйте глобальный."
            )
        else:
            detail["hint"] = (
                f"В словаре переменных нет «{var_name}». Возможно, переменная переименована или удалена. "
                f"См. справочник «Руководство по переменным» в Subsidies → Шаблоны."
            )

    # Pattern: 'X' has no attribute 'Y'
    m2 = _re.match(r"'(\w+)' (?:object )?has no attribute '(\w+)'", err_msg)
    if not m and m2:
        obj_name = m2.group(1)
        attr = m2.group(2)
        detail["message"] = f"В шаблоне «{template_name}» используется {{{{{obj_name}.{attr}}}}} но поле «{attr}» отсутствует"
        detail["hint"] = (
            f"Возможные причины:\n"
            f"• опечатка в имени переменной — см. «Руководство по переменным»\n"
            f"• данные ещё не заполнены в закупке (например, попытка использовать {{{{{obj_name}.{attr}}}}} когда поле пустое)"
        )

    # Pattern: TemplateSyntaxError
    if err_class == "TemplateSyntaxError":
        detail["message"] = f"Синтаксическая ошибка в шаблоне «{template_name}»: {err_msg}"
        detail["hint"] = (
            "Проверьте парные теги в Word: `{% if ... %}` ↔ `{% endif %}`, "
            "`{% for ... %}` ↔ `{% endfor %}`. Откройте шаблон в Word и убедитесь, "
            "что все условные блоки закрыты."
        )

    # Pattern: file not found / permission
    if isinstance(e, FileNotFoundError) or "no such file" in err_msg.lower():
        detail["message"] = f"Файл шаблона не найден: {template_name}"
        detail["hint"] = "Загрузите шаблон через UI «Субсидии → Шаблоны → Загрузить свой шаблон»."

    return HTTPException(500, detail=detail)


def build_final_buffer(tpl: DocxTemplate, doc_type: str, approvers_list: list,
                        receipt_png_paths: list, pid: int, template_path: str) -> BytesIO:
    try:
        if doc_type == "approval_sheet" and len(approvers_list) > 0:
            buf = _rebuild_or_patch_approvers_table(tpl, approvers_list, receipt_png_paths)
        else:
            _insert_receipts_table_if_marker(tpl.docx, receipt_png_paths)
            buf = BytesIO()
            tpl.save(buf)
            buf.seek(0)
    except Exception as e:
        logger.exception("Document generation error for purchase %s, doc_type=%s, template=%s", pid, doc_type, template_path)
        raise _build_template_render_error(e, pid, doc_type, template_path)

    return buf
