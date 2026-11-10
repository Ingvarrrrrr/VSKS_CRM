"""generate_document: render_docx() with custom-template auto-fallback.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
import os
import logging

from docxtpl import DocxTemplate

from app.services.documents.doc_types import TEMPLATES_DIR, SUBSIDY_TEMPLATES_DIR
from app.services.documents.blank_placeholders import render_docx
from app.services.documents.templates import _resolve_doc_template_path

from typing import Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def render_template(tpl: DocxTemplate, context: dict, template_path: str, doc_type: str, pid: Optional[int] = None):
    """Returns (tpl, template_path, fallback_info) — fallback_info is None
    unless a broken custom template silently fell back to the base one."""
    _fallback_info = None  # phase31-02: track silent fallback for response header
    try:
        render_docx(tpl, context)
    except Exception as render_err:
        if isinstance(render_err, HTTPException):
            raise
        # phase26-nn: auto-fallback на базовый шаблон если кастомный из БД сломан.
        # Lessons.md (2026-05-15): кастомные шаблоны с {% tr %} вне таблицы или
        # повреждённой структурой валят TemplateSyntaxError → user видит белый экран.
        # Безопаснее упасть на базовый из репо и предупредить.
        from app.services.documents.stages_postprocess import _build_template_render_error

        is_custom_template = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))
        if is_custom_template:
            base_path, _, _ = _resolve_doc_template_path(doc_type, None)
            if os.path.exists(base_path) and base_path != template_path:
                _fallback_reason = f"{type(render_err).__name__}: {str(render_err)[:300]}"
                logging.getLogger(__name__).warning(
                    f"Custom template {template_path} render failed ({_fallback_reason}). "
                    f"Falling back to base template {base_path}."
                )
                _fallback_info = {
                    "original": os.path.basename(template_path),
                    "fallback": os.path.basename(base_path),
                    "reason": _fallback_reason,
                }
                tpl = DocxTemplate(base_path)
                template_path = base_path
                try:
                    render_docx(tpl, context)
                except Exception as fallback_render_err:
                    if isinstance(fallback_render_err, HTTPException):
                        raise
                    raise _build_template_render_error(fallback_render_err, pid or 0, doc_type, template_path) from fallback_render_err
            else:
                raise _build_template_render_error(render_err, pid or 0, doc_type, template_path) from render_err
        else:
            raise _build_template_render_error(render_err, pid or 0, doc_type, template_path) from render_err

    return tpl, template_path, _fallback_info
