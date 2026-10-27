"""Разбор карточки-реквизитов контрагента в формате «ключ / значение»
(таблица Word из двух столбцов — ровно то, во что оформлены карточки
казначейства) в структурированные поля ContractorCreate.

ВЫРЕЗАНО (Правило №5, 27.10.2026) из app/services/contractor_file_parsing.py —
тот модуль разросся за счёт расширения словаря под карточки казначейства
(полное наименование, сайт/ОКПО/ОКВЭД/дата регистрации, казначейские счета,
лицевой счёт, ФИО руководителя по частям, «действует на основании»,
телефон/e-mail организации). Используется ИСКЛЮЧИТЕЛЬНО через
_try_parse_kv_docx, вызываемую из contractor_file_parsing._parse_file_to_rows
(единственный парсер карточек контрагента — второго не заводим, см. докстринг
там). _map_kv_key/_KV_LABEL_TO_FIELD переиспользуются также
app/routers/contractors_import.py::parse_contractor_file — там НЕ заводится
второй словарь распознавания заголовков карточки (ПРАВИЛО №6).
"""


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
    # «Полное наименование организации» (карточка казначейства) — ОТДЕЛЬНО от
    # «краткого» наименования: модель контрагента хранит оба (full_name/name),
    # проверять ДО общего 'наимен', иначе полное наименование попадало бы в
    # 'наименование' (краткое) как раньше. Короткого названия в карточках
    # казначейства нет — post-process ниже копирует full_name → name, если
    # name не задано отдельной строкой.
    if 'полн' in k and ('наимен' in k or 'назван' in k):
        return 'полное наименование'
    if 'назван' in k or 'наимен' in k or 'учредит' in k:
        return 'наименование'
    if 'юридич' in k and 'адрес' in k:
        return 'адрес'
    if 'почтов' in k:
        return 'почтовый адрес'
    # Телефон/E-mail ОРГАНИЗАЦИИ (карточка казначейства — других нет в
    # карточке) — отдельные поля модели (org_phone/org_email), не
    # «контактное лицо» (phone/email). Проверяем «организац»/«факс» ДО
    # общего телефона/почты, иначе ушло бы в контактное лицо.
    if ('телефон' in k or k.startswith('тел') or 'факс' in k) and ('организац' in k or 'факс' in k):
        return 'телефон организации'
    if 'телефон' in k or (k.startswith('тел') and len(k) < 10):
        return 'телефон'
    if ('email' in k or 'e-mail' in k) and 'организац' in k:
        return 'email организации'
    if 'email' in k or 'e-mail' in k:
        return 'email'
    # «Руководитель организации» (карточка казначейства) — тот же подписант,
    # что и «Подписант»/«Уполномоченное лицо»/«Представитель» — одно поле.
    if 'подписант' in k or 'уполномоч' in k or 'представит' in k or 'руководит' in k:
        return 'подписант'
    if 'должност' in k:
        return 'должность'
    # «Действует на основании» / «На основании чего действует» — то же поле,
    # что и короткое «Основание» (используется ContractorEditDialog.vue).
    if 'основан' in k or 'действует' in k:
        return 'основание'
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
    # «Лицевой счёт» отдельной строкой (карточка ДНР) — в карточке ЗО тот же
    # показатель сидит внутри строки банка, см. post-process в
    # _try_parse_kv_docx ниже (ПРАВИЛО №6: один показатель contractor.
    # personal_account, два пути извлечения из разных форматов карточки, а
    # не два разных поля).
    if 'лицевой' in k:
        return 'лицевой счёт'
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
    'полное наименование': 'full_name',
    'наименование': 'name',
    'адрес': 'address',
    'почтовый адрес': 'postal_address',
    'телефон': 'phone',
    'телефон организации': 'org_phone',
    'email': 'email',
    'email организации': 'org_email',
    'подписант': 'signatory',
    'должность': 'signatory_position',
    'основание': 'signatory_basis',
    'сайт': 'website',
    'окпо': 'okpo',
    'оквэд': 'okved',
    'казначейский счёт': 'treasury_account',
    'единый казначейский счёт': 'single_treasury_account',
    'лицевой счёт': 'personal_account',
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
    'full_name': 'Полное наименование',
    'name': 'Наименование',
    'address': 'Адрес',
    'postal_address': 'Почтовый адрес',
    'phone': 'Телефон',
    'org_phone': 'Телефон организации',
    'email': 'Email',
    'org_email': 'Email организации',
    'signatory': 'Подписант',
    'website': 'Сайт',
    'registration_date': 'Дата регистрации',
    'okpo': 'ОКПО',
    'okved': 'ОКВЭД',
    'treasury_account': 'Казначейский счёт',
    'single_treasury_account': 'Единый казначейский счёт',
    'personal_account': 'Лицевой счёт',
    'signatory_position': 'Должность',
    'signatory_basis': 'Основание',
    'signatory_last_name': 'Фамилия подписанта',
    'signatory_first_name': 'Имя подписанта',
    'signatory_middle_name': 'Отчество подписанта',
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
                key_cell, val_cell = non_empty
                # Карточка ДНР: две пары «ключ/значение» слиты в одну строку
                # таблицы одной ячейкой на объединённое поле — «Казначейский
                # счет\n\nОКВЭД 2» / «03225643210000008201\n\n     94.99».
                # Если в обеих ячейках одинаковое число непустых строк (>1) —
                # это несколько пар, разбираем по строкам внутри ячейки, а не
                # одна пара со слипшимся многострочным значением.
                key_lines = [l.strip() for l in key_cell.split('\n') if l.strip()]
                val_lines = [l.strip() for l in val_cell.split('\n') if l.strip()]
                if len(key_lines) > 1 and len(key_lines) == len(val_lines):
                    kv_pairs.extend(zip(key_lines, val_lines))
                else:
                    kv_pairs.append((key_cell, val_cell))
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

    # Поля-счета: в карточке казначейства номер может прийти с переносом
    # строки внутри ячейки («401028105453 70000097» — в реальности один
    # 20-значный счёт, разбитый переносом) — убираем внутренние пробелы.
    _ACCOUNT_FIELDS = {
        'treasury_account', 'single_treasury_account', 'personal_account',
        'settlement_account', 'correspondent_account',
    }

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
        val = raw_val
        if field in _ACCOUNT_FIELDS:
            val = "".join(val.split())
        values.append(val)

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

    # Карточка ЗО: лицевой счёт казначейства — не отдельной строкой, а внутри
    # строки банка: «ОКЦ № 6 ЮГУ Банка России//УФК по Запорожской области,
    # (л/сч 712ZUU57001)». ПРАВИЛО №6: тот же показатель contractor.
    # personal_account, что и отдельная строка «Лицевой счёт» в карточке ДНР
    # (см. _KV_LABEL_TO_FIELD['лицевой счёт'] выше) — здесь только второй
    # способ его извлечь из другого формата карточки, не второе поле.
    try:
        import re as _re_pa
        bank_header = _FIELD_TO_HEADER.get('bank_name', 'Банк')
        if bank_header in headers and 'personal_account' not in seen_fields:
            idx = headers.index(bank_header)
            bank_val = values[idx]
            pm = _re_pa.search(r'\(?\s*л/с[чт]?\.?\s*([A-ZА-Я0-9]+)\s*\)?', bank_val, _re_pa.IGNORECASE)
            if pm:
                values[idx] = _re_pa.sub(r',?\s*\(?\s*л/с[чт]?\.?\s*[A-ZА-Я0-9]+\s*\)?', '', bank_val, flags=_re_pa.IGNORECASE).strip().rstrip(',').strip()
                headers.append(_FIELD_TO_HEADER.get('personal_account', 'Лицевой счёт'))
                values.append(pm.group(1).strip())
                seen_fields.add('personal_account')
    except Exception:
        pass  # defensive — don't break existing parsing

    # Карточка казначейства не содержит отдельного «краткого» наименования —
    # только «Полное наименование организации» (full_name). Required-поле
    # name (краткое) заполняем тем же значением, если своей строки для него
    # нет — иначе ниже сработал бы неверный fallback по параграфам (берёт
    # первый абзац документа, которым обычно служит служебный заголовок
    # карточки, не название организации).
    if 'full_name' in seen_fields and 'name' not in seen_fields:
        idx = headers.index(_FIELD_TO_HEADER.get('full_name', 'Полное наименование'))
        headers.append(_FIELD_TO_HEADER['name'])
        values.append(values[idx])
        seen_fields.add('name')

    # ФИО руководителя по частям (владелец, 27.10.2026: «ФИО руководителя —
    # каждая часть отдельно») — «Фамилия Имя Отчество» (ровно 3 слова) из
    # значения, уже извлечённого для 'подписант'/signatory выше (ПРАВИЛО №6,
    # второй разбор не заводим — используем то же значение).
    if 'signatory' in seen_fields and not {'signatory_last_name', 'signatory_first_name', 'signatory_middle_name'} & seen_fields:
        idx = headers.index(_FIELD_TO_HEADER.get('signatory', 'Подписант'))
        sig_words = values[idx].split()
        if len(sig_words) == 3:
            for fio_field, word in zip(
                ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name'), sig_words
            ):
                headers.append(_FIELD_TO_HEADER[fio_field])
                values.append(word)
                seen_fields.add(fio_field)

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
