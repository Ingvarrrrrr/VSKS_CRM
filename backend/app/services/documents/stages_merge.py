"""generate_document: Phase 19.06 ?merge=<doc_type> secondary-document merge.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Failure here is non-fatal by design (original just logs and returns buf
unchanged) — preserved exactly.
"""
import os
from io import BytesIO

from app.services.documents.doc_types import TEMPLATES_DIR, SUBSIDY_TEMPLATES_DIR, DOC_TYPES, DOC_TYPE_FALLBACK_FILES


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

            secondary_file, secondary_base = DOC_TYPES[merge]
            secondary_path = os.path.join(TEMPLATES_DIR, secondary_file)
            # subsidy override for secondary
            if p.subsidy_id:
                sub_override = os.path.join(
                    SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{merge}.docx"
                )
                if os.path.exists(sub_override):
                    secondary_path = sub_override
            # fallback if the dedicated secondary file is missing
            if not os.path.exists(secondary_path):
                fb = DOC_TYPE_FALLBACK_FILES.get(merge)
                if fb:
                    fb_path = os.path.join(TEMPLATES_DIR, fb)
                    if os.path.exists(fb_path):
                        secondary_path = fb_path

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
