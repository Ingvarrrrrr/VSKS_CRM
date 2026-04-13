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

    # If PDF returned empty text, try OCR fallback
    if not text.strip() and ext == "pdf":
        logger.info("markitdown returned empty for PDF, trying OCR fallback")
        text = _ocr_pdf_to_markdown(content)

    return text


def _ocr_pdf_to_markdown(content: bytes) -> str:
    """Fallback: convert scanned PDF to markdown via OCR."""
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
