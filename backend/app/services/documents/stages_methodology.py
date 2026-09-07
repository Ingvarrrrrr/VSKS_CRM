"""generate_document: attach методичка (large/small) to a rendered contract
via docxcompose.Composer.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
import os
import logging
from io import BytesIO

from fastapi import HTTPException

from app.services.documents.doc_types import DOC_TYPES, CONTRACT_TYPED_FORM_DOC_TYPES
from app.services.documents.templates import _resolve_doc_template_path

logger = logging.getLogger(__name__)


def attach_methodology(buf: BytesIO, doc_type: str, p, pid: int) -> BytesIO:
    # ── Methodology attach: приклеиваем методичку к готовому договору ──────
    # Владелец: методичка (большая/малая) — отдельный документ, физически
    # отсутствующий во всех семи шаблонах договора (см. test_contract_templates.py,
    # _METHODOLOGY_MARKERS). Она приклеивается ПОСЛЕ рендера договора через
    # docxcompose.Composer — итоговый файл содержит и договор, и методичку.
    if doc_type in CONTRACT_TYPED_FORM_DOC_TYPES:
        methodology = getattr(p, "methodology", None)
        if methodology in ("large", "small"):
            methodology_doc_type = f"methodology_{methodology}"
            meth_label = "большие" if methodology == "large" else "малые"
            meth_path, _meth_file, _meth_base = _resolve_doc_template_path(
                methodology_doc_type, p.subsidy_id
            )
            if not os.path.exists(meth_path):
                raise HTTPException(
                    422,
                    detail={
                        "code": "METHODOLOGY_TEMPLATE_MISSING",
                        "message": f"Не найден файл методических рекомендаций ({meth_label})",
                        "hint": (
                            f"В закупке выбрана методичка «{meth_label}», но соответствующий "
                            f"файл шаблона ({DOC_TYPES[methodology_doc_type][0]}) не загружен "
                            "ни на субсидию, ни глобально. Загрузите файл в «Шаблоны документов» "
                            "субсидии или положите его в backend/templates/, либо снимите выбор "
                            "методички в закупке."
                        ),
                        "doc_type": doc_type,
                        "methodology": methodology,
                    },
                )
            try:
                from docxcompose.composer import Composer as _Composer
                from docx import Document as _ComposeDoc

                buf.seek(0)
                _master = _ComposeDoc(buf)
                _composer = _Composer(_master)
                _composer.append(_ComposeDoc(meth_path))
                _composed_buf = BytesIO()
                _composer.save(_composed_buf)
                _composed_buf.seek(0)
                buf = _composed_buf
            except HTTPException:
                raise
            except Exception as meth_err:
                logger.exception(
                    "Methodology attach error for purchase %s, doc_type=%s, methodology=%s",
                    pid, doc_type, methodology,
                )
                raise HTTPException(
                    422,
                    detail={
                        "code": "METHODOLOGY_ATTACH_FAILED",
                        "message": "Не удалось приклеить методические рекомендации к договору",
                        "hint": f"{type(meth_err).__name__}: {meth_err}",
                        "doc_type": doc_type,
                        "methodology": methodology,
                    },
                )

    return buf
