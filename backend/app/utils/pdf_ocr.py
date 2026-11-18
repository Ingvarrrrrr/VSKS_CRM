"""Unified home for PDF OCR logic.

`ocr_pdf_to_rows` and `ocrmypdf_then_extract_tables` are moved here verbatim
from app/routers/purchase_items_import.py (only renamed, no logic changes) so
that OCR code lives in one place instead of being duplicated across the
router and app/utils/document_to_markdown.py. `ocr_pdf_to_rows` remains as a
proven fallback; `ocr_pdf_to_rows_enhanced` adds image preprocessing and
per-page PSM selection on top of the same row-grouping logic.
"""
import logging
import math
import threading

logger = logging.getLogger(__name__)

# Строго поочерёдная обработка тяжёлых страниц/изображений (защита от OOM при сотнях пользователей)
HEAVY_VISION_SEMAPHORE = threading.BoundedSemaphore(1)


def iter_pdf_page_images(
    content: bytes,
    dpi: int = 200,
    max_pages: int = 25,
    pages: list[int] | None = None,
):
    """Unified generator for page-by-page PDF rendering under HEAVY_VISION_SEMAPHORE.

    Renders one page at a time with first_page=page_num, last_page=page_num,
    yielding PIL Image and closing it in finally so uncompressed bitmaps
    do not accumulate in RAM across pages or concurrent requests.
    """
    if not content:
        return

    try:
        from pdf2image import convert_from_bytes
        from pdf2image.exceptions import PDFPageCountError
    except ImportError:
        logger.warning("iter_pdf_page_images: pdf2image is not installed")
        return

    if pages is not None:
        page_nums = sorted({p for p in pages if isinstance(p, int) and p > 0})[:max_pages]
    else:
        page_nums = list(range(1, max_pages + 1))

    for page_num in page_nums:
        img = None
        try:
            with HEAVY_VISION_SEMAPHORE:
                try:
                    imgs = convert_from_bytes(
                        content, dpi=dpi, first_page=page_num, last_page=page_num
                    )
                except PDFPageCountError:
                    break
                except Exception as e:
                    logger.warning("iter_pdf_page_images: page %s render error: %s", page_num, e)
                    break

            if not imgs:
                break
            img = imgs[0]
            yield img
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass


def ocr_pdf_to_simple_rows(content: bytes, dpi: int = 200) -> tuple[list, str | None]:
    """Lightweight line-by-line OCR for tabular PDF scans (contracts, contractor cards).

    Iterates page-by-page via iter_pdf_page_images, calls pytesseract.image_to_string
    under HEAVY_VISION_SEMAPHORE, and splits lines by tab or multiple spaces.
    Returns (all_rows, error_message).
    """
    if not content:
        return [], "PDF пуст или не содержит данных."

    try:
        import pdf2image  # noqa: F401
        import pytesseract
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."

    import re
    all_rows = []
    had_pages = False

    for img in iter_pdf_page_images(content, dpi=dpi):
        had_pages = True
        try:
            with HEAVY_VISION_SEMAPHORE:
                text = pytesseract.image_to_string(img, lang="rus+eng")
        except Exception as e:
            return [], f"Ошибка OCR-распознавания: {e}"

        if not text:
            continue
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            cells = re.split(r"\t|  {2,}", line)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)

    if not had_pages:
        return [], "PDF не содержит страниц для распознавания."
    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None


try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


def ocr_pdf_to_rows(content: bytes, dpi: int = 250) -> tuple[list, str | None]:
    """Convert scanned PDF to rows via OCR with layout awareness.
    Uses pytesseract image_to_data (TSV) — gives bounding boxes per word.
    Group words into rows by y-coordinate, then split into columns by
    x-gaps within each row. Returns (rows, error_message).
    """
    if not content:
        return [], "PDF пуст или не содержит данных."

    try:
        import pdf2image  # noqa: F401
        import pytesseract
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."

    all_rows: list[list[str]] = []
    had_pages = False
    for img in iter_pdf_page_images(content, dpi=dpi):
        had_pages = True
        try:
            with HEAVY_VISION_SEMAPHORE:
                # PSM 6 = "Assume a single uniform block of text" — best for tables/lists
                data = pytesseract.image_to_data(
                    img, lang='rus+eng', config='--psm 6',
                    output_type=pytesseract.Output.DICT,
                )
        except Exception as e:
            return [], f"Ошибка OCR-распознавания (tesseract установлен?): {e}"

        # Group words by (block_num, par_num, line_num) → one OCR line each
        n = len(data.get('text', []))
        line_buckets: dict[tuple, list] = {}
        for i in range(n):
            word = (data['text'][i] or '').strip()
            if not word:
                continue
            try:
                conf = int(data['conf'][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            line_buckets.setdefault(key, []).append({
                'text': word,
                'left': int(data['left'][i]),
                'right': int(data['left'][i]) + int(data['width'][i]),
                'top': int(data['top'][i]),
            })

        # Sort lines top-to-bottom by mean y-coord of their words
        sorted_lines = sorted(
            line_buckets.values(),
            key=lambda ws: sum(w['top'] for w in ws) / len(ws),
        )

        for words in sorted_lines:
            words.sort(key=lambda w: w['left'])
            # Split into cells: gap > 40px between adjacent words = new column
            GAP_PX = 40
            cells: list[str] = []
            current = words[0]['text']
            prev_right = words[0]['right']
            for w in words[1:]:
                if w['left'] - prev_right > GAP_PX:
                    cells.append(current)
                    current = w['text']
                else:
                    current += ' ' + w['text']
                prev_right = w['right']
            cells.append(current)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)

    if not had_pages:
        return [], "PDF не содержит страниц для распознавания."
    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None


def ocrmypdf_then_extract_tables(content: bytes) -> list[list[list[str]]]:
    """Run ocrmypdf on scanned PDF (adds invisible OCR text layer),
    then extract tables via pdfplumber from the OCR'd PDF.
    Returns list of tables (each = list of rows). Empty list on failure.
    """
    try:
        import ocrmypdf
        import pdfplumber as _pp
    except ImportError as e:
        logger.warning("ocrmypdf or pdfplumber not installed: %s", e)
        return []
    import tempfile, os
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fin:
            fin.write(content)
            in_path = fin.name
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fout:
            out_path = fout.name
        # force_ocr=True even if pdf has some text — scans often have garbage text layer
        # skip_text=False ensures all pages get OCR'd
        try:
            ocrmypdf.ocr(
                in_path, out_path,
                language='rus+eng',
                force_ocr=True,
                deskew=True,
                clean=True,
                progress_bar=False,
                output_type='pdf',
            )
        except Exception as e:
            logger.warning("ocrmypdf failed: %s", e)
            return []
        # Now extract tables from the OCR'd PDF
        tables_out: list[list[list[str]]] = []
        try:
            with _pp.open(out_path) as pdf:
                for page in pdf.pages:
                    for tbl in (page.extract_tables() or []):
                        if tbl:
                            cleaned = [[str(c).strip() if c else "" for c in row] for row in tbl]
                            if any(any(c for c in row) for row in cleaned):
                                tables_out.append(cleaned)
                    # If no tables detected, fall back to text lines as virtual table
                    if not tables_out:
                        text = page.extract_text() or ""
                        if text.strip():
                            import re
                            rows = []
                            for line in text.split('\n'):
                                line = line.strip()
                                if not line:
                                    continue
                                cells = re.split(r'  {2,}|\t', line)
                                cells = [c.strip() for c in cells if c.strip()]
                                if cells:
                                    rows.append(cells)
                            if rows:
                                tables_out.append(rows)
        except Exception as e:
            logger.warning("pdfplumber on OCR'd PDF failed: %s", e)
            return []
        return tables_out
    finally:
        for p in (in_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def preprocess_for_ocr(pil_image):
    """Deskew + denoise + adaptively binarize a page image before tesseract.

    Pipeline: PIL → numpy grayscale → deskew (via cv2.minAreaRect on the
    inverted-mask nonzero pixels, only for angles between 0.3° and 15° to
    avoid rotating already-straight scans) → median blur denoise → adaptive
    gaussian threshold → back to PIL. Any failing step falls back to
    returning the input image unchanged rather than raising.
    """
    if cv2 is None or np is None:
        logger.warning("preprocess_for_ocr: cv2/numpy not installed, skipping preprocessing")
        return pil_image

    try:
        from PIL import Image
    except ImportError:
        return pil_image

    try:
        img = np.array(pil_image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    except Exception as e:
        logger.warning("preprocess_for_ocr: grayscale conversion failed: %s", e)
        return pil_image

    # Deskew
    try:
        inverted = cv2.bitwise_not(gray)
        # Threshold to get a clean mask of "ink" pixels for angle estimation
        _, mask = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        coords = cv2.findNonZero(mask)
        if coords is not None and len(coords) > 0:
            rect_angle = cv2.minAreaRect(coords)[-1]
            angle = rect_angle
            # cv2.minAreaRect angle convention: normalize to [-45, 45]
            if angle < -45:
                angle = 90 + angle
            if 0.3 <= abs(angle) <= 15:
                (h, w) = gray.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(
                    gray, M, (w, h),
                    flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
                )
    except Exception as e:
        logger.warning("preprocess_for_ocr: deskew failed, continuing without it: %s", e)

    # Denoise
    try:
        gray = cv2.medianBlur(gray, 3)
    except Exception as e:
        logger.warning("preprocess_for_ocr: median blur failed: %s", e)

    # Adaptive binarization
    try:
        binarized = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            31, 11,
        )
    except Exception as e:
        logger.warning("preprocess_for_ocr: adaptive threshold failed: %s", e)
        binarized = gray

    try:
        return Image.fromarray(binarized)
    except Exception as e:
        logger.warning("preprocess_for_ocr: could not convert back to PIL, returning original: %s", e)
        return pil_image


def best_psm_data(pil_image, lang: str = 'rus+eng', psm_candidates: tuple = (6, 4, 11)) -> tuple[dict, int, float]:
    """Run pytesseract image_to_data for several PSM modes and pick the best.

    Quality score = mean confidence of words with conf >= 0, weighted by
    log1p(word_count) so a mode that finds more words isn't unfairly
    penalized by a slightly lower mean confidence. Returns
    (best_data_dict, best_psm, best_score); ({}, psm_candidates[0], 0.0) if
    every candidate raised.
    """
    try:
        import pytesseract
    except ImportError:
        return {}, (psm_candidates[0] if psm_candidates else 6), 0.0

    best_data: dict = {}
    best_psm = psm_candidates[0] if psm_candidates else 6
    best_score = -1.0

    for psm in psm_candidates:
        try:
            data = pytesseract.image_to_data(
                pil_image, lang=lang, config=f'--psm {psm}',
                output_type=pytesseract.Output.DICT,
            )
        except Exception as e:
            logger.warning("best_psm_data: psm=%s failed: %s", psm, e)
            continue

        confs = []
        n = len(data.get('text', []))
        for i in range(n):
            word = (data['text'][i] or '').strip()
            if not word:
                continue
            try:
                conf = int(data['conf'][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            confs.append(conf)

        if confs:
            mean_conf = sum(confs) / len(confs)
            score = mean_conf * math.log1p(len(confs))
        else:
            score = 0.0

        if score > best_score:
            best_score = score
            best_data = data
            best_psm = psm

    if best_score < 0:
        return {}, (psm_candidates[0] if psm_candidates else 6), 0.0

    return best_data, best_psm, best_score


def ocr_pdf_to_rows_enhanced(content: bytes, dpi: int = 250, pages: list[int] | None = None) -> tuple[list, str | None]:
    """Enhanced version of ocr_pdf_to_rows: preprocessing + PSM auto-selection.

    Same contract as ocr_pdf_to_rows: returns (rows, error_message). Applies
    preprocess_for_ocr to each page image, picks the best PSM per page via
    best_psm_data, optionally restricts to a 1-based `pages` subset, and
    reuses the exact same word→line→cell grouping logic as the original.
    """
    if not content:
        return [], "PDF пуст или не содержит данных."

    try:
        import pdf2image  # noqa: F401
        import pytesseract  # noqa: F401
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."

    all_rows: list[list[str]] = []
    had_pages = False
    for img in iter_pdf_page_images(content, dpi=dpi, pages=pages):
        had_pages = True
        processed = img
        try:
            with HEAVY_VISION_SEMAPHORE:
                processed = preprocess_for_ocr(img)
        except Exception as e:
            logger.warning("ocr_pdf_to_rows_enhanced: preprocessing failed, using original image: %s", e)
            processed = img

        with HEAVY_VISION_SEMAPHORE:
            data, _psm, _score = best_psm_data(processed, lang='rus+eng')
        if processed is not img:
            try:
                processed.close()
            except Exception:
                pass
        if not data:
            continue
        # Group words by (block_num, par_num, line_num) → one OCR line each
        n = len(data.get('text', []))
        line_buckets: dict[tuple, list] = {}
        for i in range(n):
            word = (data['text'][i] or '').strip()
            if not word:
                continue
            try:
                conf = int(data['conf'][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            left, width, top = int(data['left'][i]), int(data['width'][i]), int(data['top'][i])
            line_buckets.setdefault(key, []).append({'text': word, 'left': left, 'right': left + width, 'top': top})
        # Sort lines top-to-bottom by mean y-coord of their words
        sorted_lines = sorted(line_buckets.values(), key=lambda ws: sum(w['top'] for w in ws) / len(ws))
        for words in sorted_lines:
            words.sort(key=lambda w: w['left'])
            # Split into cells: gap > 40px between adjacent words = new column
            GAP_PX = 40
            cells: list[str] = []
            current = words[0]['text']
            prev_right = words[0]['right']
            for w in words[1:]:
                if w['left'] - prev_right > GAP_PX:
                    cells.append(current)
                    current = w['text']
                else:
                    current += ' ' + w['text']
                prev_right = w['right']
            cells.append(current)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)

    if not had_pages:
        return [], "PDF не содержит страниц для распознавания."
    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None
