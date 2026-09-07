"""generate_document: strip Word review comments from the final bytes, build
the download filename and response headers.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
from io import BytesIO
from urllib.parse import quote

from app.services.documents.templates import _sanitize_subject
from app.services.documents.docx_post import _strip_word_comments

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def finalize_response(buf: BytesIO, p, pid: int, filename_base: str, fallback_info: dict | None):
    """Returns (buf, media_type, headers) ready for StreamingResponse."""
    # ── Strip Word review comments (template-author hints) from the final file ──
    # Templates carry Word comments explaining {{tags}} to whoever edits the
    # .docx TEMPLATE; docxtpl's render leaves them in place, so they must be
    # cut here before the file reaches the counterparty. Runs after render,
    # ТЗ append, methodology attach and merge, so it always sees the final bytes.
    buf.seek(0)
    buf = BytesIO(_strip_word_comments(buf.read()))

    _subj = _sanitize_subject(getattr(p, "subject", "") or "")
    if _subj:
        safe_name = f"{filename_base}_{_subj}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    else:
        safe_name = f"{filename_base}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    encoded_name = quote(safe_name, safe="-_.~")
    resp_headers: dict = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    # phase31-02: surface non-silent fallback via response headers
    if fallback_info:
        resp_headers["X-Template-Fallback"] = "1"
        resp_headers["X-Template-Fallback-Reason"] = quote(fallback_info["reason"][:200], safe="")
        resp_headers["X-Template-Fallback-Original"] = quote(fallback_info["original"], safe="")

    return buf, DOCX_MEDIA_TYPE, resp_headers
