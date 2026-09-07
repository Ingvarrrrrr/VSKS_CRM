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


def _map_kv_key(key: str) -> str | None:
    """Map a key-value card label to a contractor field name.
    Returns the field name string or None if the key is not recognised."""
    k = key.strip().lower()
    if not k:
        return None
    # Order matters — more specific checks first
    if 'инн' in k or 'inn' in k:
        return 'инн'
    if 'кпп' in k or 'kpp' in k:
        return 'кпп'
    if 'огрн' in k:
        return 'огрн'
    if 'бик' in k or 'bik' in k:
        return 'бик'
    if 'расч' in k or 'р/с' in k:
        return 'расчётный счёт'
    if 'корр' in k or 'к/с' in k:
        return 'корр. счёт'
    if 'банк' in k and 'реквиз' not in k:
        return 'банк'
    if 'назван' in k or 'наимен' in k or 'учредит' in k:
        return 'наименование'
    if 'юридич' in k and 'адрес' in k:
        return 'адрес'
    if 'почтов' in k:
        return 'почтовый адрес'
    if 'телефон' in k or (k.startswith('тел') and len(k) < 10):
        return 'телефон'
    if 'email' in k or 'e-mail' in k:
        return 'email'
    if 'подписант' in k or 'уполномоч' in k or 'представит' in k:
        return 'подписант'
    if 'должност' in k:
        return 'должность'
    if 'сайт' in k or 'website' in k:
        return 'сайт'
    if 'окпо' in k:
        return 'окпо'
    if 'оквэд' in k:
        return 'оквэд'
    if 'единый' in k and 'казначейск' in k:
        return 'единый казначейский счёт'
    if 'казначейск' in k:
        return 'казначейский счёт'
    return None


# Mapping from Russian card labels to ContractorCreate field names
_KV_LABEL_TO_FIELD: dict[str, str] = {
    'инн': 'inn',
    'кпп': 'kpp',
    'огрн': 'ogrn',
    'бик': 'bik',
    'расчётный счёт': 'settlement_account',
    'корр. счёт': 'correspondent_account',
    'банк': 'bank_name',
    'наименование': 'name',
    'адрес': 'address',
    'почтовый адрес': 'postal_address',
    'телефон': 'phone',
    'email': 'email',
    'подписант': 'signatory',
    'должность': 'signatory_position',
    'сайт': 'website',
    'окпо': 'okpo',
    'оквэд': 'okved',
    'казначейский счёт': 'treasury_account',
    'единый казначейский счёт': 'single_treasury_account',
}

# Human-readable column header for each field used in preview response
_FIELD_TO_HEADER: dict[str, str] = {
    'inn': 'ИНН',
    'kpp': 'КПП',
    'ogrn': 'ОГРН',
    'bik': 'БИК',
    'settlement_account': 'Расчётный счёт',
    'correspondent_account': 'Корр. счёт',
    'bank_name': 'Банк',
    'name': 'Наименование',
    'address': 'Адрес',
    'postal_address': 'Почтовый адрес',
    'phone': 'Телефон',
    'email': 'Email',
    'signatory': 'Подписант',
    'website': 'Сайт',
    'registration_date': 'Дата регистрации',
    'okpo': 'ОКПО',
    'okved': 'ОКВЭД',
    'treasury_account': 'Казначейский счёт',
    'single_treasury_account': 'Единый казначейский счёт',
    'signatory_position': 'Должность',
}


def _try_parse_kv_docx(doc) -> tuple[list, int] | None:
    """Try to parse a DOCX document as a key-value requisites card.

    Returns (all_rows, hdr_idx) where all_rows = [header_row, value_row]
    with hdr_idx = 0, ready to be returned from _parse_file_to_rows.

    Returns None if the document does not look like a key-value card
    (e.g. it is a proper table with data in multiple data rows).
    """
    # Collect all key→value pairs from every table in the document
    kv_pairs: list[tuple[str, str]] = []
    two_col_count = 0
    total_rows = 0

    for tbl in doc.tables:
        for row in tbl.rows:
            cells = [c.text.strip() for c in row.cells]
            # Remove duplicate adjacent cells (merged cells repeat in python-docx)
            deduped = []
            for c in cells:
                if not deduped or c != deduped[-1]:
                    deduped.append(c)
            non_empty = [c for c in deduped if c]
            total_rows += 1
            if len(non_empty) == 2:
                two_col_count += 1
                kv_pairs.append((non_empty[0], non_empty[1]))
            elif len(non_empty) == 1:
                # Single-cell rows are OK (section headers) — do not disqualify
                pass
            # Rows with 3+ distinct non-empty cells suggest a real data table
            elif len(non_empty) >= 3:
                return None  # Looks like a multi-column table — not a card

    if total_rows == 0:
        return None

    # If fewer than half the rows are 2-column key-value rows, it's not a card
    if two_col_count < max(2, total_rows * 0.4):
        return None

    # Also check that the keys look like field labels (not values)
    recognised = sum(1 for k, _ in kv_pairs if _map_kv_key(k) is not None)
    if recognised < 2:
        return None  # Too few recognisable field labels — not a requisites card

    # Build a synthetic header row + single data row
    # Use only the first match for each field to avoid duplicates
    headers: list[str] = []
    values: list[str] = []
    seen_fields: set[str] = set()

    for raw_key, raw_val in kv_pairs:
        label = _map_kv_key(raw_key)
        if label is None:
            continue
        field = _KV_LABEL_TO_FIELD.get(label)
        if field is None:
            continue
        if field in seen_fields:
            continue  # Take first match only
        seen_fields.add(field)
        headers.append(_FIELD_TO_HEADER.get(field, field))
        values.append(raw_val)

    # Post-process: if ОГРН value contains a dd.mm.yyyy date (e.g. "1239500010639, 11.12.2023"),
    # split it — keep digits as ОГРН and extract registration_date if not already captured.
    try:
        import re as _re_kv
        ogrn_header = _FIELD_TO_HEADER.get('ogrn', 'ОГРН')
        if ogrn_header in headers:
            idx = headers.index(ogrn_header)
            ogrn_val = values[idx]
            dm = _re_kv.search(r'(\d{2}\.\d{2}\.\d{4})', ogrn_val)
            if dm:
                # Keep only digits for ОГРН
                values[idx] = _re_kv.sub(r'\D', '', ogrn_val.split(',')[0])
                if 'registration_date' not in seen_fields:
                    headers.append(_FIELD_TO_HEADER.get('registration_date', 'Дата регистрации'))
                    values.append(dm.group(1))
                    seen_fields.add('registration_date')
    except Exception:
        pass  # defensive — don't break existing parsing

    # Fallback: if name not found, scan paragraphs
    if 'name' not in seen_fields:
        for para in doc.paragraphs:
            text = para.text.strip()
            if len(text) > 5:
                headers.insert(0, _FIELD_TO_HEADER['name'])
                values.insert(0, text)
                break

    if not headers:
        return None

    all_rows = [headers, values]
    return all_rows, 0  # hdr_idx = 0


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
