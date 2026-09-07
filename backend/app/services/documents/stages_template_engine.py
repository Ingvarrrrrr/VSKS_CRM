"""generate_document: DocxTemplate loading (with lazy legacy-template normalize)
and the two InlineImage-producing helpers (product photo / base64 signature).

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
import os
import logging

from fastapi import HTTPException
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm as _Cm

logger = logging.getLogger(__name__)


def build_docx_template(template_path: str, pid: int, doc_type: str) -> DocxTemplate:
    """Load DocxTemplate, lazily normalizing legacy-uploaded templates first."""
    try:
        # Templates are normalized at upload time (subsidies.py
        # _normalize_docx_template). For files uploaded BEFORE that fix
        # landed we lazily rewrite them on first render: scan + replace +
        # atomic rename, so subsequent renders hit the fast path with no
        # extra IO and InlineImage placeholders sit in a single contiguous
        # run (required for the drawing element to be inserted).
        try:
            import zipfile as _zf
            needs_norm = False
            with _zf.ZipFile(template_path, 'r') as _zin:
                for _name in _zin.namelist():
                    if _name == 'word/document.xml' or _name.startswith('word/header') or _name.startswith('word/footer'):
                        _bytes = _zin.read(_name)
                        if b'<w:proofErr' in _bytes or b'<w:bookmark' in _bytes or b'<w:commentRange' in _bytes or b'<w:lastRenderedPageBreak' in _bytes:
                            needs_norm = True
                            break
            if needs_norm:
                from app.routers.subsidies import _normalize_docx_template as _norm
                _stats = _norm(template_path)
                logger.info("lazy normalize on render %s: %s", template_path, _stats)
        except Exception as _scan_e:
            logger.warning("lazy normalize scan failed for %s: %s", template_path, _scan_e)

        tpl = DocxTemplate(template_path)
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        logger.exception("Document template load failed for purchase %s, doc_type=%s", pid, doc_type)
        raise HTTPException(500, detail={
            "code": "DOCUMENT_GENERATION_FAILED",
            "message": f"Не удалось загрузить шаблон «{doc_type}»: {type(e).__name__}",
            "doc_type": doc_type,
            "purchase_id": pid,
            "error_class": type(e).__name__,
            "error_raw": str(e),
            "traceback": "".join(_tb.format_exception(type(e), e, e.__traceback__))[:4000],
            "hint": (
                "Ошибка при загрузке файла шаблона docxtpl. "
                "Возможные причины: повреждённый .docx файл шаблона, "
                "отсутствие библиотеки docxtpl/python-docx. "
                "Передайте администратору error_class + traceback."
            ),
        })
    return tpl


UPLOADS_DIR = "/app/uploads/products"


def make_photo_resolver(tpl: DocxTemplate, uploads_dir: str = UPLOADS_DIR):
    """Factory: returns a resolve_photo(photo_url) closure bound to `tpl`."""

    def _resolve_photo(photo_url):
        """Return InlineImage or empty string."""
        import tempfile, urllib.request as _ur
        if not photo_url:
            return ""
        url = str(photo_url).strip()
        local_path = None

        if url.startswith("/api/products/photos/"):
            fname = url.split("/")[-1]
            local_path = f"{uploads_dir}/{fname}"
        elif url.isdigit():
            for ext in ("jpg", "jpeg", "png"):
                pth = f"{uploads_dir}/product_{url}.{ext}"
                if os.path.exists(pth):
                    local_path = pth
                    break
        elif url.startswith("http://") or url.startswith("https://"):
            # Download external image; convert webp via Pillow if available
            try:
                with _ur.urlopen(url, timeout=5) as r:
                    ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    raw = r.read()
                is_webp = "webp" in ct or url.lower().endswith(".webp")
                if is_webp:
                    try:
                        from PIL import Image as _Img
                        import io as _io
                        img = _Img.open(_io.BytesIO(raw)).convert("RGB")
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        img.save(tmp, format="JPEG", quality=85)
                        tmp.close()
                        local_path = tmp.name
                    except Exception:
                        return ""  # Pillow not available or conversion failed
                else:
                    ext_map = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                               "image/gif": ".gif", "image/bmp": ".bmp", "image/tiff": ".tiff"}
                    suffix = ext_map.get(ct, ".jpg")
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tmp.write(raw)
                    tmp.close()
                    local_path = tmp.name
            except Exception:
                return ""

        if not local_path or not os.path.exists(local_path):
            return ""
        try:
            return InlineImage(tpl, local_path, width=_Cm(2.5))
        except Exception:
            return ""

    return _resolve_photo


def make_base64_to_inline(tpl: DocxTemplate):
    """Factory: returns a base64_to_inline(tpl_obj, b64_data) closure.

    Kept as a 2-arg callable (tpl_obj, b64_data) to match the original
    call site `_base64_to_inline(tpl, pa.signature_data)` byte-for-byte —
    tpl_obj is accepted but the outer `tpl` bound at factory time is what
    actually gets used, exactly as before (both are always the same object).
    """

    def _base64_to_inline(tpl_obj, b64_data: str):
        """Convert base64 PNG data URL to docxtpl InlineImage."""
        import tempfile, base64, re as _re
        try:
            from docxtpl import InlineImage
            from docx.shared import Cm as _Cm
            m = _re.match(r"data:image/\w+;base64,(.+)", b64_data, _re.DOTALL)
            if not m:
                return ""
            raw = base64.b64decode(m.group(1))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(raw)
            tmp.close()
            return InlineImage(tpl_obj, tmp.name, width=_Cm(3.0))
        except Exception:
            return ""

    return _base64_to_inline
