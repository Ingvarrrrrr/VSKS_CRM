"""
Unified document-to-markdown conversion.

Supported formats: PDF, DOCX, XLSX, XLS
Pipeline: file bytes → markitdown → markdown string → parsed tables

For scanned PDFs (no text layer), falls back to pytesseract OCR.
"""
import io
import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def file_to_markdown(content: bytes, filename: str) -> str:
    """Convert file bytes to markdown string using markitdown."""
    from markitdown import MarkItDown

    md = MarkItDown()
    # markitdown works with file-like objects
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    suffix = f".{ext}" if ext else ""

    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = md.convert(tmp_path)
        text = result.text_content or ""
    finally:
        os.unlink(tmp_path)

    # Route the PDF branch through pdf-inspector classification when available;
    # falls back to the legacy "empty text → OCR" rule when it isn't.
    if ext == "pdf":
        text = _route_pdf_markdown(content, text)

    return text


def _route_pdf_markdown(content: bytes, markitdown_text: str) -> str:
    """Decide how to turn a PDF into markdown, using pdf-inspector classification.

    - inspect_pdf unavailable or insp.ok is False: EXACT legacy behavior —
      OCR only when markitdown's own text is empty.
    - insp.ok and needs_ocr(insp) (scanned/image/mixed pdf_type, OR a broken
      text-layer encoding, OR specific pages flagged): always OCR, even if
      markitdown_text is non-empty. A scan with a garbage text layer (a stamp,
      a header fragment) can make `text.strip()` truthy while the document is
      still effectively an image — that's exactly the case the old
      `if not text.strip()` check missed.
    - insp.ok, pdf_type == "text", no encoding issues: prefer pdf-inspector's
      own markdown when it produced one (it preserves tables and multi-column
      reading order, which markitdown does not) — otherwise keep markitdown's
      text.
    - Anything else classified successfully but not matching the above
      (e.g. pdf_type == "unknown" with no OCR pages and no encoding issues):
      keep the legacy empty-text-triggers-OCR fallback as a safety net.

    Never raises — any failure here degrades to the legacy behavior.
    """
    try:
        from app.utils.pdf_classify import inspect_pdf, needs_ocr
    except Exception as e:
        logger.warning("document_to_markdown: pdf_classify unavailable, using legacy OCR fallback: %s", e)
        return _legacy_pdf_ocr_fallback(content, markitdown_text)

    try:
        insp = inspect_pdf(content)
    except Exception as e:
        logger.warning("document_to_markdown: inspect_pdf raised unexpectedly: %s", e)
        return _legacy_pdf_ocr_fallback(content, markitdown_text)

    if not insp.ok:
        return _legacy_pdf_ocr_fallback(content, markitdown_text)

    try:
        route_needs_ocr = needs_ocr(insp)
    except Exception as e:
        logger.warning("document_to_markdown: needs_ocr() raised unexpectedly: %s", e)
        return _legacy_pdf_ocr_fallback(content, markitdown_text)

    if route_needs_ocr:
        logger.info(
            "document_to_markdown: pdf_classify routed to OCR (pdf_type=%s, "
            "has_encoding_issues=%s, ocr_pages=%s)",
            insp.pdf_type, insp.has_encoding_issues, insp.ocr_pages,
        )
        pages = insp.ocr_pages or None
        try:
            ocr_markdown = _ocr_pdf_to_markdown_tables(content, pages)
        except Exception as e:
            logger.warning("document_to_markdown: OCR table pipeline failed, using legacy OCR: %s", e)
            ocr_markdown = ""
        if ocr_markdown.strip():
            return ocr_markdown
        # OCR table pipeline found nothing usable — fall back to the proven
        # plain-text OCR path rather than returning empty.
        return _ocr_pdf_to_markdown(content)

    if insp.pdf_type == "text" and not insp.has_encoding_issues:
        if insp.markdown and insp.markdown.strip():
            logger.info("document_to_markdown: using pdf-inspector markdown (text PDF, tables preserved)")
            return insp.markdown
        return markitdown_text

    # Classified successfully but not confidently "text" or "needs OCR"
    # (e.g. pdf_type == "unknown") — keep the legacy safety net.
    return _legacy_pdf_ocr_fallback(content, markitdown_text)


def _legacy_pdf_ocr_fallback(content: bytes, markitdown_text: str) -> str:
    """Exact pre-classification behavior: OCR only if markitdown text is empty."""
    if not markitdown_text.strip():
        logger.info("markitdown returned empty for PDF, trying OCR fallback")
        return _ocr_pdf_to_markdown(content)
    return markitdown_text


def _ocr_pdf_to_markdown_tables(content: bytes, pages: list[int] | None) -> str:
    """OCR a PDF into markdown TABLES (not flat text), so parse_markdown_tables
    can actually find something. Built entirely on top of the existing OCR
    helpers in app.utils.pdf_ocr — no new recognition logic added here.

    Order: ocrmypdf_then_extract_tables (adds an OCR text layer, then lets
    pdfplumber's native table detection run on it) → if that yields nothing,
    ocr_pdf_to_rows_enhanced (preprocessing + per-page PSM auto-selection,
    treated as a single table). Returns "" if neither pipeline finds rows.
    """
    from app.utils.pdf_ocr import ocrmypdf_then_extract_tables, ocr_pdf_to_rows_enhanced

    try:
        tables = ocrmypdf_then_extract_tables(content)
    except Exception as e:
        logger.warning("_ocr_pdf_to_markdown_tables: ocrmypdf_then_extract_tables failed: %s", e)
        tables = []

    if not tables:
        try:
            rows, error = ocr_pdf_to_rows_enhanced(content, pages=pages)
        except Exception as e:
            logger.warning("_ocr_pdf_to_markdown_tables: ocr_pdf_to_rows_enhanced failed: %s", e)
            rows, error = [], str(e)
        if rows:
            tables = [rows]
        else:
            logger.warning("_ocr_pdf_to_markdown_tables: no rows found (%s)", error)
            return ""

    rendered = [rows_to_markdown_table(t) for t in tables if t]
    return "\n\n".join(r for r in rendered if r)


def rows_to_markdown_table(rows: list) -> str:
    """Render rows (list[list[str]]) as a GitHub-style markdown table string.

    Produces `| a | b |` rows plus a `|---|---|` separator after the first
    row, so parse_markdown_tables (which looks for lines wrapped in `|` and
    discards the `|---|` separator) recognizes it. Cells: `|` is escaped to
    `\\|` and newlines are collapsed to spaces so a cell can never break the
    row out of its `|...|` line. Rows that are empty/all-blank are dropped;
    returns "" if nothing is left after that.
    """
    def _escape_cell(cell) -> str:
        text = "" if cell is None else str(cell)
        text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        text = text.replace("|", "\\|")
        return text.strip()

    clean_rows = [r for r in (rows or []) if r and any(str(c).strip() for c in r if c is not None)]
    if not clean_rows:
        return ""

    ncols = max(len(r) for r in clean_rows)
    lines: list[str] = []
    for ri, row in enumerate(clean_rows):
        padded_cells = list(row) + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(_escape_cell(c) for c in padded_cells) + " |")
        if ri == 0:
            lines.append("|" + "|".join(["---"] * ncols) + "|")
    return "\n".join(lines)


def _ocr_pdf_to_markdown(content: bytes) -> str:
    """Fallback: convert scanned PDF to markdown via OCR (flat text, no tables).

    Kept verbatim as the last-resort fallback for the insp.ok is False legacy
    path and for cases where the table-producing OCR pipeline above finds
    nothing — plain text is still better than an empty result.
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return ""

    try:
        images = convert_from_bytes(content, dpi=300)
    except Exception as e:
        logger.warning("pdf2image failed: %s", e)
        return ""

    lines = []
    for img in images:
        text = pytesseract.image_to_string(img, lang="rus+eng")
        lines.append(text)

    return "\n\n".join(lines)


def parse_markdown_tables(md_text: str) -> List[List[List[str]]]:
    """
    Extract all markdown tables from text.
    Returns list of tables, each table is list of rows, each row is list of cells.

    Handles standard markdown table format:
    | Header1 | Header2 |
    |---------|---------|
    | cell1   | cell2   |
    """
    tables: List[List[List[str]]] = []
    current_table: List[List[str]] = []
    in_table = False

    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Check if separator row (|---|---|)
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue  # skip separator
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            current_table.append(cells)
            in_table = True
        else:
            if in_table and current_table:
                tables.append(current_table)
                current_table = []
            in_table = False

    # Flush last table
    if current_table:
        tables.append(current_table)

    return tables


def pick_best_table(
    tables: List[List[List[str]]],
) -> Optional[Tuple[List[List[str]], int]]:
    """
    Pick the table most likely to contain purchase items.
    Returns (table_rows, header_row_index) or None.
    """
    _NAME_HINTS = {"наименован", "назван", "товар", "предмет", "описан", "услуг", "name", "продукц"}
    _PRICE_HINTS = {"цена", "стоимость", "сумма", "итог", "price", "amount", "total"}
    _QTY_HINTS = {"кол", "количеств", "qty", "quantity"}

    best_table = None
    best_score = 0
    best_hdr = 0

    for table in tables:
        if len(table) < 2:
            continue
        # Check first 3 rows as potential headers
        for hdr_idx in range(min(3, len(table))):
            row_text = " ".join(c.lower() for c in table[hdr_idx])
            score = 0
            has_name = False
            for hint in _NAME_HINTS:
                if hint in row_text:
                    score += 3
                    has_name = True
                    break
            for hint in _PRICE_HINTS:
                if hint in row_text:
                    score += 2
                    break
            for hint in _QTY_HINTS:
                if hint in row_text:
                    score += 1
                    break
            if has_name and score > best_score:
                best_score = score
                best_table = table
                best_hdr = hdr_idx

    if best_table is None:
        return None
    return best_table, best_hdr


def detect_columns(header_row: List[str]) -> dict:
    """Map column indices from header row text."""
    _COL_MAP = {
        "item_name": ["наименован", "назван", "name", "товар", "предмет", "описан", "услуг", "продукц"],
        "item_type": ["тип", "type", "вид"],
        "quantity": ["кол", "количеств", "qty", "quantity"],
        "unit": ["ед.", "единиц", "unit", "изм"],
        "unit_price": ["цена ед", "цена за", "стоимость ед", "price"],
        "total_price": ["сумма", "итог", "total", "amount", "всего", "стоимость"],
    }

    mapping: dict = {}
    for idx, cell in enumerate(header_row):
        cell_lower = cell.lower().strip()
        if not cell_lower:
            continue
        for col_name, hints in _COL_MAP.items():
            if col_name in mapping:
                continue
            for hint in hints:
                if hint in cell_lower:
                    mapping[col_name] = idx
                    break

    return mapping
