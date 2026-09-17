"""generate_document: Phase 19.06 ?merge=<doc_type> secondary-document merge.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Failure here is non-fatal by design (original just logs and returns buf
unchanged) — preserved exactly.
"""
import os
from io import BytesIO

from app.services.documents.doc_types import DOC_TYPES
# Правило №6 — единственный резолвер пути к шаблону (субсидийный override →
# глобальный → DOC_TYPE_FALLBACK_FILES). Раньше здесь жила копия-дубль той же
# логики приоритета — эквивалентная по результату, но лишний источник
# расхождения при будущих правках резолвера (см. _resolve_doc_template_path
# docstring и жалобу владельца 2026-09-17 про service_note_advance).
from app.services.documents.templates import _resolve_doc_template_path


def merge_secondary_doc(buf: BytesIO, merge, doc_type: str, context: dict, p, filename_base: str):
    """Returns (buf, filename_base) — both updated when the merge succeeds."""
    # ── Phase 19.06: merge with secondary doc ──────────────────────────────
    # When ?merge=<doc_type> is passed, render the secondary template against
    # the same context and append its paragraphs/tables after a page break.
    if merge and merge in DOC_TYPES and merge != doc_type:
        try:
            from docxtpl import DocxTemplate as _Tpl
            from docx import Document as _Docx
            from copy import deepcopy

            secondary_path, _secondary_file, secondary_base = _resolve_doc_template_path(merge, p.subsidy_id)

            if os.path.exists(secondary_path):
                sec_tpl = _Tpl(secondary_path)
                sec_tpl.render(context)
                sec_buf = BytesIO()
                sec_tpl.save(sec_buf)
                sec_buf.seek(0)

                # Append secondary into primary
                buf.seek(0)
                main_doc = _Docx(buf)
                sec_doc = _Docx(sec_buf)

                main_doc.add_page_break()
                # Copy every top-level element (paragraphs, tables, etc.) from body
                for element in sec_doc.element.body:
                    main_doc.element.body.append(deepcopy(element))

                merged_buf = BytesIO()
                main_doc.save(merged_buf)
                merged_buf.seek(0)
                buf = merged_buf
                # Update filename to reflect merge
                filename_base = f"{filename_base}_и_{secondary_base}"
        except Exception as merge_err:
            import traceback
            print(f"Doc merge error ({doc_type} + {merge}): {merge_err}\n{traceback.format_exc()}")

    return buf, filename_base
