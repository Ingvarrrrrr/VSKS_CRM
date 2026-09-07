"""generate_document: tpl.render() with custom-template auto-fallback.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
import os
import logging

from docxtpl import DocxTemplate

from app.services.documents.doc_types import TEMPLATES_DIR, SUBSIDY_TEMPLATES_DIR

logger = logging.getLogger(__name__)


def render_template(tpl: DocxTemplate, context: dict, template_path: str, doc_type: str):
    """Returns (tpl, template_path, fallback_info) — fallback_info is None
    unless a broken custom template silently fell back to the base one."""
    _fallback_info = None  # phase31-02: track silent fallback for response header
    try:
        tpl.render(context)
    except Exception as render_err:
        # phase26-nn: auto-fallback на базовый шаблон если кастомный из БД сломан.
        # Lessons.md (2026-05-15): кастомные шаблоны с {% tr %} вне таблицы или
        # повреждённой структурой валят TemplateSyntaxError → user видит белый экран.
        # Безопаснее упасть на базовый из репо и предупредить.
        is_custom_template = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))
        if is_custom_template:
            base_path = os.path.join(TEMPLATES_DIR, f"{doc_type}.docx")
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
                tpl.render(context)
            else:
                raise
        else:
            raise

    return tpl, template_path, _fallback_info
