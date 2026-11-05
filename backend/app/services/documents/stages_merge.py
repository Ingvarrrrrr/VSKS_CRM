"""generate_document: Phase 19.06 ?merge=<doc_type> secondary-document merge.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Failure here is non-fatal by design (original just logs and returns buf
unchanged) — preserved exactly.
"""
import os
from io import BytesIO

from app.services.documents.doc_types import DOC_TYPES
from app.services.documents.templates import _resolve_doc_template_path
from app.services.documents.blank_placeholders import render_docx


def _rebind_inline_images_for_tpl(context: dict, target_tpl) -> dict:
    """Перепривязывает объекты docxtpl.InlineImage в копии context к target_tpl.

    InlineImage хранит ссылку на родительский DocxTemplate (self.tpl) и при
    рендере регистрирует картинку и rId в self.tpl.current_rendering_part.
    Если рендерить вторичный шаблон (sec_tpl) со старыми InlineImage от
    основного шаблона (tpl), rId запишется в основной шаблон, а в sec_tpl
    останется битая ссылка r:embed («Не удаётся отобразить рисунок»).
    """
    try:
        from docxtpl import InlineImage as _InlineImage
    except ImportError:
        return context

    def _clone_val(v):
        if isinstance(v, _InlineImage):
            desc = v.image_descriptor
            if hasattr(desc, "seek"):
                try:
                    desc.seek(0)
                except Exception:
                    pass
            return _InlineImage(
                target_tpl,
                desc,
                width=v.width,
                height=v.height,
                anchor=v.anchor,
            )
        if isinstance(v, dict):
            return {k: _clone_val(sub_v) for k, sub_v in v.items()}
        if isinstance(v, list):
            return [_clone_val(item) for item in v]
        return v

    return {k: _clone_val(v) for k, v in context.items()}


def _ensure_explicit_table_borders(doc) -> None:
    """Проставляет явные чёрные границы (<w:tblBorders>) таблицам документа,
    у которых задан сеточный стиль (TableGrid / Table Grid).
    Это защищает таблицы ТЗ от потери рамок при склейке с договором,
    в чьём styles.xml стиль TableGrid имеет другой внутренний styleId (например, a9).
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    for tbl in getattr(doc, "tables", ()):
        tblPr = tbl._tbl.tblPr
        if tblPr is None:
            continue
        if tblPr.find(qn("w:tblBorders")) is not None:
            continue
        tblStyle = tblPr.find(qn("w:tblStyle"))
        style_val = (tblStyle.get(qn("w:val")) if tblStyle is not None else "") or ""
        style_name = (getattr(getattr(tbl, "style", None), "name", "") or "")
        if "grid" not in style_val.lower() and "grid" not in style_name.lower() and style_val not in ("a9", " сетка"):
            continue
        tblBorders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
            tblBorders.append(el)
        tblPr.append(tblBorders)


def merge_secondary_doc(buf: BytesIO, merge, doc_type: str, context: dict, p, filename_base: str):
    """Returns (buf, filename_base) — both updated when the merge succeeds."""
    # ── Phase 19.06: merge with secondary doc ──────────────────────────────
    # When ?merge=<doc_type> is passed, render the secondary template against
    # the same context and append its paragraphs/tables after a page break.
    if merge and merge in DOC_TYPES and merge != doc_type:
        try:
            from docxtpl import DocxTemplate as _Tpl
            from docx import Document as _Docx

            secondary_path, _secondary_file, secondary_base = _resolve_doc_template_path(merge, p.subsidy_id)

            if os.path.exists(secondary_path):
                from app.services.documents.stages_template_engine import build_docx_template
                sec_tpl = build_docx_template(secondary_path, getattr(p, "id", 0), merge)
                sec_context = _rebind_inline_images_for_tpl(context, sec_tpl)
                render_docx(sec_tpl, sec_context)
                _ensure_explicit_table_borders(sec_tpl.docx)
                sec_buf = BytesIO()
                sec_tpl.save(sec_buf)
                sec_buf.seek(0)

                # Append secondary into primary via docxcompose.Composer so media
                # relationships (InlineImage photos) and styles are preserved.
                buf.seek(0)
                main_doc = _Docx(buf)
                main_doc.add_page_break()
                sec_doc = _Docx(sec_buf)

                merged_buf = BytesIO()
                try:
                    from docxcompose.composer import Composer as _Composer
                    composer = _Composer(main_doc)
                    composer.append(sec_doc)
                    composer.save(merged_buf)
                except ImportError:
                    from copy import deepcopy
                    from docx.oxml.ns import qn as _qn
                    rel_map = {}
                    for r_id, rel in sec_doc.part.rels.items():
                        if "image" in rel.reltype and not rel.is_external:
                            rel_map[r_id] = main_doc.part.relate_to(rel.target_part, rel.reltype)
                    for element in sec_doc.element.body:
                        if element.tag.endswith("sectPr"):
                            continue
                        el_copy = deepcopy(element)
                        for blip in el_copy.iter(_qn("a:blip")):
                            old_r = blip.get(_qn("r:embed"))
                            if old_r and old_r in rel_map:
                                blip.set(_qn("r:embed"), rel_map[old_r])
                        main_doc.element.body.append(el_copy)
                    main_doc.save(merged_buf)

                merged_buf.seek(0)
                buf = merged_buf
                # Update filename to reflect merge
                filename_base = f"{filename_base}_и_{secondary_base}"
        except Exception as merge_err:
            import traceback
            print(f"Doc merge error ({doc_type} + {merge}): {merge_err}\n{traceback.format_exc()}")

    return buf, filename_base
