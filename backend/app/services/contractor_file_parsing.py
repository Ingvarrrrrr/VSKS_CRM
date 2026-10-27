"""Разбор файлов карточек контрагента (xlsx/xls/docx/doc/pdf) в строки.

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Чистая логика без
HTTP-зависимостей (кроме HTTPException — используется как сигнал ошибки
разбора файла, как и в исходном роутере) — переиспользуется тремя
эндпоинтами contractors_import.py: /parse-file, /import/preview,
/import/mapped. Второго механизма парсинга контрагентских файлов заводить
не нужно — только этот.
"""
from io import BytesIO

from fastapi import HTTPException

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    import pdfplumber as _pdfplumber
except ImportError:
    _pdfplumber = None


def _ocr_pdf_to_rows(content: bytes) -> tuple[list, str | None]:
    """Fallback: convert scanned PDF pages to images, run OCR, parse lines.
    Returns (rows, error_message). error_message is None on success."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return [], "OCR-библиотеки не установлены (pdf2image, pytesseract). Обратитесь к администратору."
    try:
        images = convert_from_bytes(content, dpi=300)
    except Exception as e:
        return [], f"Не удалось преобразовать PDF в изображения для OCR: {e}"
    if not images:
        return [], "PDF не содержит страниц для распознавания."
    import re
    all_rows = []
    for img in images:
        try:
            text = pytesseract.image_to_string(img, lang='rus+eng')
        except Exception as e:
            return [], f"Ошибка OCR-распознавания: {e}"
        if not text:
            continue
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            cells = re.split(r'\t|  {2,}', line)
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                all_rows.append(cells)
    if not all_rows:
        return [], "OCR не нашёл текст на страницах. Возможно, качество скана слишком низкое."
    return all_rows, None


# ---------------------------------------------------------------------------
# Shared file parsing helpers
# ---------------------------------------------------------------------------

_CONTRACTOR_HINTS = (
    'назван', 'наимен', 'инн', 'inn', 'кпп', 'огрн', 'адрес',
    'email', 'телефон', 'банк', 'бик', 'контакт', 'подписант',
)


def _detect_hdr(rows):
    """Return index of the row most likely to be a header row."""
    best_score, best_idx = 0, 0
    for ri, row in enumerate(rows):
        norm = [str(h).strip().lower() if h is not None else "" for h in row]
        score = sum(1 for h in norm if h and any(x in h for x in _CONTRACTOR_HINTS))
        if score > best_score:
            best_score = score
            best_idx = ri
    return best_idx


# Словарь распознавания карточки «ключ/значение» и сам разбор —
# app/services/contractor_card_kv_parsing.py (Правило №5, вынесено
# 27.10.2026). _map_kv_key/_KV_LABEL_TO_FIELD переэкспортируются отсюда —
# app/routers/contractors_import.py переиспользует их (ПРАВИЛО №6,
# второго словаря распознавания заголовков карточки не заводим).
from app.services.contractor_card_kv_parsing import (  # noqa: E402
    _map_kv_key, _KV_LABEL_TO_FIELD, _FIELD_TO_HEADER, _try_parse_kv_docx,
)


def _try_parse_paragraphs_docx(doc) -> tuple[list, int] | None:
    """Parse plain-paragraph requisites card (no tables).

    Scans paragraph text via regex patterns for ИНН, КПП, ОГРН, БИК,
    р/с, к/с, name, address, email, phone, signatory.
    Returns (all_rows, 0) — header row + value row — or None if too few fields found.
    """
    import re as _re
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        return None
    # Also scan paragraphs inside tables (some docs use 1-cell layout-tables)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    t = p.text.strip()
                    if t:
                        paragraphs.append(t)
    full_text = "\n".join(paragraphs)

    fields: dict[str, str] = {}

    def _digits(s: str) -> str:
        return _re.sub(r'\D', '', s)

    # Compact "ИНН/КПП:" combo (e.g. "ИНН/КПП: 7731178803/772901001")
    m = _re.search(r'ИНН\s*/?\s*КПП\s*[:№]?\s*(\d{10,12})\s*/\s*(\d{9})', full_text, _re.IGNORECASE)
    if m:
        fields['inn'] = m.group(1)
        fields['kpp'] = m.group(2)

    # Individual labelled fields
    PATTERNS = [
        ('inn',    r'ИНН[\s:№]+(\d{10,12})\b'),
        ('kpp',    r'КПП[\s:№]+(\d{9})\b'),
        ('ogrn',   r'ОГРН(?:ИП)?[\s:№]+(\d{13,15})\b'),
        ('bik',    r'БИК[\s:№]+(\d{9})\b'),
    ]
    for field, pat in PATTERNS:
        if field in fields:
            continue
        m = _re.search(pat, full_text, _re.IGNORECASE)
        if m:
            fields[field] = m.group(1)

    # Bank accounts: collect ALL 20-digit numbers, classify by prefix.
    # 30101... → correspondent (к/с), 4xxxxx → settlement (р/с).
    # This is more robust than label-matching ("р/счёт", "р/с", "расч/сч." etc).
    accounts_seen: set[str] = set()
    for m in _re.finditer(r'\b(\d{20})\b', full_text):
        acc = m.group(1)
        if acc in accounts_seen:
            continue
        accounts_seen.add(acc)
        if acc.startswith('30101') and 'correspondent_account' not in fields:
            fields['correspondent_account'] = acc
        elif acc.startswith('4') and 'settlement_account' not in fields:
            fields['settlement_account'] = acc

    # Name — first quoted phrase or first paragraph if it looks like an org name
    m = _re.search(r'((?:ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|ОООО|АНО)\s*["«»]?[^"\n«»]+["»]?)', full_text)
    if m:
        fields['name'] = m.group(1).strip().strip(',').strip()
    elif paragraphs:
        # First non-trivial paragraph as name
        for p in paragraphs:
            if len(p) >= 5 and not _re.fullmatch(r'[\d\s\-+\(\)]+', p):
                fields['name'] = p.strip()
                break

    # Email
    m = _re.search(r'\b([\w.+-]+@[\w-]+\.[\w.-]+)\b', full_text)
    if m:
        fields['email'] = m.group(1)

    # Phone
    m = _re.search(r'(\+?7?\s*\(?\d{3,4}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2})', full_text)
    if m:
        fields['phone'] = m.group(1).strip()

    # Address — line containing "г. " or 6-digit postal code + comma
    for p in paragraphs:
        clean = _re.sub(r'^(?:Юр\.?\s*адрес|Адрес|Юридический\s+адрес|Фактический\s+адрес|Местонахождение)[\s:]+', '', p, flags=_re.IGNORECASE)
        if _re.search(r'\b\d{6}\b', clean) or _re.search(r'\bг\.\s', clean):
            if 10 < len(clean) < 250 and 'address' not in fields:
                fields['address'] = clean.strip()
                break

    # Bank name — line starting with "Банк:" / "в банке" etc, or following BIK
    m = _re.search(r'(?:Банк|в\s+банке)[\s:]+([^\n]+?)(?=\s*БИК|\s*к/?с|\s*$|\n)', full_text, _re.IGNORECASE)
    if m:
        fields['bank_name'] = m.group(1).strip().strip(',').strip()

    # Signatory — "Подписант: ..." or "Генеральный директор ФИО"
    m = _re.search(r'(?:Подписант|Уполномоченное\s+лицо|Представитель)[\s:]+([^\n]+)', full_text, _re.IGNORECASE)
    if m:
        fields['signatory'] = m.group(1).strip()
    else:
        m = _re.search(r'((?:Генеральный\s+директор|Директор|Председатель|Президент|Главный\s+бухгалтер|Управляющий)\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.?\s*[А-ЯЁ]\.?)', full_text)
        if m:
            fields['signatory'] = m.group(1).strip()

    if len(fields) < 2:
        return None  # too little extracted — not a requisites card

    # Build header/value rows in stable order
    order = ['name', 'inn', 'kpp', 'ogrn', 'address', 'phone', 'email',
             'settlement_account', 'correspondent_account', 'bik', 'bank_name', 'signatory',
             'okpo', 'okved', 'treasury_account', 'single_treasury_account',
             'signatory_position', 'website', 'registration_date']
    headers = [_FIELD_TO_HEADER.get(f, f) for f in order if f in fields]
    values = [fields[f] for f in order if f in fields]
    return [headers, values], 0


def _parse_file_to_rows(fname: str, content: bytes):
    """Parse xlsx/xls/docx/doc/pdf and return (all_rows, hdr_idx)."""
    fname = fname.lower()

    if fname.endswith('.xls') and not fname.endswith('.xlsx'):
        try:
            import xlrd as _xlrd_mod
        except ImportError:
            raise HTTPException(500, "xlrd не установлен")
        try:
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xls файл: {e}")
        ws_xls = wb_xls.sheet_by_index(0)
        all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]

    elif fname.endswith('.xlsx'):
        if not load_workbook:
            raise HTTPException(500, "openpyxl не установлен")
        try:
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .xlsx файл: {e}")
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

    elif fname.endswith(('.docx', '.doc')):
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(500, "python-docx не установлен")
        try:
            doc = Document(BytesIO(content))
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать .docx файл: {e}")

        # Try key-value card format from tables (карточка реквизитов в таблице)
        if doc.tables:
            kv_result = _try_parse_kv_docx(doc)
            if kv_result is not None:
                return kv_result

        # Fallback: parse paragraphs via regex (карточка-абзацы без таблиц)
        para_result = _try_parse_paragraphs_docx(doc)
        if para_result is not None:
            return para_result

        if not doc.tables:
            raise HTTPException(
                400,
                "В документе .docx не найдено ни таблиц, ни узнаваемых полей "
                "(ИНН/КПП/ОГРН/название). Проверьте что документ содержит реквизиты."
            )

        tbl = doc.tables[0]
        all_rows = [[cell.text.strip() for cell in row.cells] for row in tbl.rows]

    elif fname.endswith('.pdf'):
        if not _pdfplumber:
            raise HTTPException(500, "pdfplumber не установлен")
        has_text = False
        try:
            with _pdfplumber.open(BytesIO(content)) as pdf:
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for tbl in tables:
                            all_rows.extend([r for r in tbl if r])
                if not all_rows:
                    for page in _pdfplumber.open(BytesIO(content)).pages:
                        text = page.extract_text()
                        if text:
                            has_text = True
                            for line in text.strip().split('\n'):
                                cells = [c.strip() for c in line.split('\t')]
                                if len(cells) < 2:
                                    cells = [c.strip() for c in line.split('  ') if c.strip()]
                                if cells:
                                    all_rows.append(cells)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать PDF-файл: {e}")
        if not all_rows:
            if not has_text:
                # Scanned PDF — try OCR
                all_rows, ocr_error = _ocr_pdf_to_rows(content)
                if not all_rows:
                    detail = ocr_error or "OCR не смог распознать таблицу."
                    raise HTTPException(
                        400,
                        f"Этот PDF — скан (изображение). {detail} "
                        "Попробуйте сохранить данные в Excel (.xlsx) или Word (.docx)."
                    )
            else:
                raise HTTPException(
                    400,
                    "В PDF найден текст, но не удалось распознать таблицу. "
                    "Попробуйте сохранить данные в Excel (.xlsx) и загрузить его."
                )

    else:
        raise HTTPException(400, "Неподдерживаемый формат файла. Используйте .xlsx, .xls, .docx, .doc или .pdf")

    if not all_rows:
        raise HTTPException(400, "Файл пустой или не содержит данных")

    hdr_idx = _detect_hdr(all_rows)
    return all_rows, hdr_idx
