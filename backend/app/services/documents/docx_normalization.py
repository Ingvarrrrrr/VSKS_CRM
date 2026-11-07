"""Утилиты нормализации и исправления .docx шаблонов (Jinja2 / Word markers).

Вынесено из app/routers/subsidy_templates.py для соблюдения ПРАВИЛА №5 (< 500 строк).
ПРАВИЛО №6: единое место для нормализации docx байтов.
"""
import io
import os
import re
import zipfile
import logging
import tempfile
from typing import Tuple

from fastapi import HTTPException

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

logger = logging.getLogger(__name__)


def _normalize_docx_bytes(data: bytes) -> Tuple[bytes, dict]:
    """Pure, in-memory transform: strip Word-internal markers that split
    jinja-placeholders across runs. No disk I/O — takes the raw .docx bytes
    of a zip package and returns (cleaned_bytes, stats).
    """
    JINJA_BEARING = ('word/document.xml',)
    JINJA_BEARING_PREFIXES = ('word/header', 'word/footer')
    JINJA_BEARING_SUFFIXES = ('word/footnotes.xml', 'word/endnotes.xml')

    def _is_jinja_bearing(name: str) -> bool:
        if name in JINJA_BEARING or name in JINJA_BEARING_SUFFIXES:
            return True
        return any(name.startswith(p) and name.endswith('.xml') for p in JINJA_BEARING_PREFIXES)

    stats = {"proofErr": 0, "bookmark": 0, "comment": 0, "pageBreak": 0}
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), 'r') as zin:
        with zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                part = zin.read(item.filename)
                if _is_jinja_bearing(item.filename):
                    xml = part.decode('utf-8', errors='replace')
                    before_proof = xml.count('<w:proofErr')
                    xml = re.sub(r'<w:proofErr\s[^/]*?/>', '', xml)
                    stats["proofErr"] += before_proof - xml.count('<w:proofErr')

                    before_bm = xml.count('<w:bookmark')
                    xml = re.sub(r'<w:bookmarkStart\s[^/]*?/>', '', xml)
                    xml = re.sub(r'<w:bookmarkEnd\s[^/]*?/>', '', xml)
                    stats["bookmark"] += before_bm - xml.count('<w:bookmark')

                    before_cm = xml.count('<w:comment')
                    xml = re.sub(r'<w:commentRangeStart\s[^/]*?/>', '', xml)
                    xml = re.sub(r'<w:commentRangeEnd\s[^/]*?/>', '', xml)
                    xml = re.sub(r'<w:commentReference\s[^/]*?/>', '', xml)
                    stats["comment"] += before_cm - xml.count('<w:comment')

                    before_pb = xml.count('<w:lastRenderedPageBreak')
                    xml = re.sub(r'<w:lastRenderedPageBreak\s*/>', '', xml)
                    stats["pageBreak"] += before_pb - xml.count('<w:lastRenderedPageBreak')

                    part = xml.encode('utf-8')
                zout.writestr(item, part)
    return out_buf.getvalue(), stats


def _normalize_docx_template(path: str) -> dict:
    """Disk-writing wrapper around `_normalize_docx_bytes`."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=os.path.dirname(path) or None)
    os.close(tmp_fd)
    stats = {"proofErr": 0, "bookmark": 0, "comment": 0, "pageBreak": 0}
    try:
        with open(path, 'rb') as f:
            data = f.read()
        cleaned, stats = _normalize_docx_bytes(data)
        with open(tmp_path, 'wb') as f:
            f.write(cleaned)
        os.replace(tmp_path, path)
        logger.info("docx normalize %s: %s", path, stats)
    except Exception as e:
        logger.warning("docx normalize failed for %s: %s", path, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return stats


def _peek_normalize_stats(path: str) -> dict:
    """Informational-only: сколько маркеров вычистил бы _normalize_docx_bytes."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        _cleaned, stats = _normalize_docx_bytes(data)
        return stats
    except Exception as e:
        logger.warning("docx normalize peek failed for %s: %s", path, e)
        return {"proofErr": 0, "bookmark": 0, "comment": 0, "pageBreak": 0}


def _validate_renders_in_memory(path: str, doc_type: str) -> None:
    """Trial-render check for upload endpoints with in-memory copy."""
    if DocxTemplate is None:
        return
    try:
        with open(path, 'rb') as f:
            data = f.read()
        normalized, _stats = _normalize_docx_bytes(data)
        tpl = DocxTemplate(io.BytesIO(normalized))
        tpl.render({})
    except Exception as e:
        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"Шаблон некорректен: {type(e).__name__}: {str(e)[:200]}"
        )


def _repair_docx_template(path: str) -> list[str]:
    """Fix common Jinja2 errors in uploaded .docx templates."""
    fixes = []
    try:
        from docx import Document
        doc = Document(path)

        def _fix_paragraph(para):
            if not para.runs:
                return False
            full = "".join(r.text for r in para.runs)
            if "{{" not in full and "{%" not in full:
                return False

            original = full

            def _clean_tag(m):
                inner = m.group(1)
                parts = inner.strip().split()
                if len(parts) <= 1:
                    return m.group(0)
                var_name = parts[0]
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', var_name):
                    return m.group(0)
                rest = " ".join(parts[1:])
                if any(ord(c) > 127 for c in rest):
                    return "{{ " + var_name + " }} " + rest
                return m.group(0)

            fixed = re.sub(r'\{\{([^}]+)\}\}', _clean_tag, full)

            def _strip_if_all_non_ascii(m):
                inner = m.group(1).strip()
                if not inner:
                    return m.group(0)
                if not re.search(r'[a-zA-Z_]', inner):
                    return inner
                return m.group(0)
            fixed = re.sub(r'\{\{([^}]+)\}\}', _strip_if_all_non_ascii, fixed)

            _JINJA_KEYWORDS = {
                'if', 'else', 'elif', 'endif', 'for', 'endfor', 'set',
                'with', 'endwith', 'tr', 'block', 'endblock', 'macro',
                'endmacro', 'include', 'extends', 'import', 'from',
                'do', 'raw', 'endraw', 'call', 'endcall', 'filter',
                'endfilter', 'autoescape', 'endautoescape',
            }
            def _strip_pct_if_no_keyword(m):
                inner = m.group(1).strip().lstrip('-').rstrip('-').strip()
                if not inner:
                    return m.group(0)
                first = inner.split()[0].lower() if inner.split() else ''
                if first not in _JINJA_KEYWORDS and not re.match(r'^[a-zA-Z_]', first):
                    return inner
                return m.group(0)
            fixed = re.sub(r'\{%([^%]+)%\}', _strip_pct_if_no_keyword, fixed)

            fixed = re.sub(r'(\b\w+\.)\s+\1', r'\1', fixed)

            if fixed == original:
                return False
            para.runs[0].text = fixed
            for r in para.runs[1:]:
                r.text = ""
            return True

        count = 0
        for para in doc.paragraphs:
            if _fix_paragraph(para):
                count += 1
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if _fix_paragraph(para):
                            count += 1

        if count:
            doc.save(path)
            fixes.append(f"Исправлено {count} Jinja-тегов")

        tpl = DocxTemplate(path)
        tpl.get_undeclared_template_variables()

    except Exception as e:
        logger.warning("Template repair/validation warning for %s: %s", path, e)
        fixes.append(f"Предупреждение: {e}")

    return fixes
