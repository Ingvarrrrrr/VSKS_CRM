"""XLSX → row-dicts parser for vehicles import — extracted from
app/routers/vehicles_import.py (Правило №5, разрезание 2026-09-08).

Чистая функция разбора файла (байты → список dict-строк + предупреждения),
без DB/HTTP-сайд-эффектов (кроме HTTPException при отсутствии openpyxl —
поведение сохранено 1-в-1). Использует column-mapping из
app/services/fleet_import_columns.py и коэрсеры из
app/services/fleet_import_coerce.py.
"""
from io import BytesIO
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.services.fleet_import_columns import (
    _BOOL_COLS,
    _BRAND_MODEL_SPLIT_FIELD,
    _DATE_COLS,
    _DICT_BOOL_FIELDS,
    _DICT_STRING_FIELDS,
    _FLOAT_COLS,
    _INT_COLS,
    _MAX_LEN,
    _PASS_STATUS_MARK,
    _PASS_UNTIL_MARK,
    _PROPS_KEYS,
    _REPAIR_REQUIRED_FIELD,
    _resolve_header_columns,
)
from app.services.fleet_import_coerce import (
    _coerce_bool,
    _coerce_date,
    _coerce_enum_label,
    _coerce_pts_kind,
    _coerce_repair_required,
    _coerce_state_value,
    _ENUM_LABEL_FIELDS,
    _split_brand_model,
)
from app.services.vehicle_sheet_dictionaries import (
    FIELD_LABELS as _DICT_FIELD_LABELS,
    NO_DATA_LABEL as _NO_DATA_LABEL,
    PASS_STATUS_OPTIONS as _PASS_STATUS_OPTIONS,
    is_no_data_text,
    match_dictionary_value,
    match_value_in_options,
)

def _parse_xlsx_to_rows(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse xlsx bytes into list of row-dicts and list of warnings.

    Returns (rows, warnings). rows: list of dicts with Vehicle field names
    (плюс вложенный "props" dict для props-хранимых полей, см. _PROPS_KEYS).
    """
    try:
        from openpyxl import load_workbook as _lw
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail={"msg": "openpyxl не установлен на сервере", "code": "openpyxl_missing"},
        )

    wb = _lw(BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    # Find header row (first non-empty row)
    header_raw: Optional[tuple] = None
    header_row_idx = 0
    for idx, row in enumerate(rows_iter, start=1):
        if any(c is not None for c in row):
            header_raw = row
            header_row_idx = idx
            break

    if header_raw is None:
        return [], ["Файл не содержит данных"]

    # Build col_index → field_name mapping (позиционное разрешение неоднозначных
    # заголовков + occupied-tracking дублей, см. _resolve_header_columns).
    col_field, _unresolved_headers = _resolve_header_columns(header_raw)

    # Исходный текст заголовка по индексу колонки — для предупреждений о нераспознанных
    # значениях (coordinator review 2026-08-31): пользователь должен видеть, В КАКОЙ
    # колонке потерялось значение, а не только номер строки.
    col_header_label: Dict[int, str] = {
        ci: str(cell).strip() for ci, cell in enumerate(header_raw) if cell is not None
    }

    parsed_rows: list[dict] = []
    warnings: list[str] = []
    row_n = header_row_idx

    for raw_row in rows_iter:
        row_n += 1
        if all(c is None for c in raw_row):
            continue  # skip fully empty rows

        row_data: dict[str, Any] = {"_row_n": row_n}
        props_data: dict[str, Any] = {}
        passes_data: dict[str, dict[str, Any]] = {}
        state_note: Optional[str] = None
        dict_notes: list[str] = []

        for ci, field in col_field.items():
            val = raw_row[ci] if ci < len(raw_row) else None

            if val is not None and is_no_data_text(val):
                # «Нет данных» — осознанный ответ пользователя о том, что поле
                # не заполнено (см. vehicle_sheet_dictionaries.NO_DATA_LABEL,
                # прямое распоряжение владельца 2026-09: пустых ячеек в файле
                # быть не должно, вместо пустоты — «Нет данных»). Раньше это
                # распознавалось только для полей со справочником
                # (_DICT_STRING_FIELDS/_DICT_BOOL_FIELDS/pts_category/state) —
                # текстовые/числовые/датовые/булевы колонки без справочника
                # получали сырую строку "Нет данных" в поле (текст) либо
                # ошибочно интерпретировались (repair_required через
                # bool(str(val).strip()) считал "Нет данных" за True; сборный
                # "Марка и модель ТС" резал бы её на "Нет"/"данных"). Проверка
                # здесь, ДО диспетчеризации по типу поля, закрывает все ветки
                # разом: колонка трактуется как полностью пустая — ничего не
                # пишем, warning не поднимаем, props.note не трогаем.
                continue

            if isinstance(field, str) and field.startswith(_PASS_STATUS_MARK):
                # 2026-09: пропуск с произвольным названием → таблица vehicle_passes,
                # не колонка Vehicle (см. блок констант выше _resolve_header_columns).
                name = field[len(_PASS_STATUS_MARK):]
                matched = match_value_in_options(_PASS_STATUS_OPTIONS, val)
                if matched == _NO_DATA_LABEL:
                    pass
                elif matched is not None:
                    passes_data.setdefault(name, {})["status"] = matched
                elif val is not None and str(val).strip():
                    raw_text_v = str(val).strip()
                    warnings.append(
                        f"Строка {row_n}: «Пропуск: {name}» — значение «{raw_text_v}» не входит в "
                        f"список допустимых (Да/Нет/Не требуется/Не выпускался), статус не сохранён"
                    )
                continue

            if isinstance(field, str) and field.startswith(_PASS_UNTIL_MARK):
                name = field[len(_PASS_UNTIL_MARK):]
                coerced_date = _coerce_date(val)
                if coerced_date is not None:
                    passes_data.setdefault(name, {})["until"] = coerced_date
                elif val is not None and str(val).strip():
                    warnings.append(
                        f"Строка {row_n}: «Пропуск: {name} — до» — значение «{str(val).strip()}» "
                        f"не распознано как дата"
                    )
                continue

            if field == _BRAND_MODEL_SPLIT_FIELD:
                if val is not None and str(val).strip():
                    brand, model = _split_brand_model(str(val))
                    # Не перезаписываем, если отдельные колонки "Марка"/"Модель" уже есть
                    row_data.setdefault("brand", brand)
                    row_data.setdefault("model", model)
                continue

            if field == _REPAIR_REQUIRED_FIELD:
                row_data[field] = _coerce_repair_required(val)
                continue

            if field == "pts_kind":
                row_data[field] = _coerce_pts_kind(val)
                continue

            if field == "state":
                state_code, note = _coerce_state_value(val)
                row_data["state"] = state_code
                if (
                    state_code is None
                    and val is not None
                    and str(val).strip()
                    and not is_no_data_text(val)
                ):
                    # «Нет данных» (см. is_no_data_text) сюда не попадает — это
                    # осознанный ответ «пусто», а не нераспознанный текст,
                    # предупреждение/флаг для него не нужны (resolve_vehicle_state
                    # уже вернул note=None для этого случая, см. выше).
                    #
                    # Помечаем строку: значение было (не пустая ячейка), но не
                    # распозналось. Отличаем от случая "ячейка вообще пустая"
                    # (там row_data["state"] тоже None, но флага нет) — см.
                    # commit_import: только помеченные строки требуют
                    # пост-INSERT UPDATE state=NULL, иначе ORM Column
                    # default="working" молча подставит "Рабочее" вместо
                    # честной пустоты (Lesson 2026-08-31: default в
                    # SQLAlchemy срабатывает на explicit None точно так же,
                    # как на отсутствие атрибута — простое fields[f]=None
                    # его не подавляет, нужен отдельный UPDATE после flush).
                    row_data["_state_unrecognized"] = True
                    warnings.append(
                        f"Строка {row_n}: состояние «{str(val).strip()}» не распознано, "
                        f"поле «Состояние» оставлено пустым (исходный текст сохранён в "
                        f"«Сведения о техническом состоянии»)"
                    )
                if note:
                    state_note = note
                continue

            if field in _ENUM_LABEL_FIELDS:
                row_data[field] = _coerce_enum_label(field, val)
                continue

            target_dict = props_data if field in _PROPS_KEYS else row_data

            if field in _DICT_STRING_FIELDS:
                # Автоблок (актуализация 2026-08-31): поле ограничено набором
                # значений из правил проверки данных листа владельца (см.
                # vehicle_sheet_dictionaries.py). Несопоставленное значение НЕ
                # пишется в колонку — исходный текст уходит в предупреждение и
                # в props.note, чтобы не потерялся молча.
                #
                # Актуализация (2026-09, распоряжение владельца): «Нет данных» —
                # ОСОЗНАННЫЙ ответ пользователя, а не несопоставленный текст.
                # match_dictionary_value сопоставит его один-в-один (входит в
                # набор наравне с остальными вариантами), но значение "Нет
                # данных" в колонку не пишем, предупреждение не поднимаем и
                # props.note не засоряем — просто оставляем поле пустым.
                matched = match_dictionary_value(field, val)
                if matched is not None and matched != _NO_DATA_LABEL:
                    target_dict[field] = matched
                elif matched is None and val is not None and str(val).strip():
                    raw_text = str(val).strip()
                    label = col_header_label.get(ci, _DICT_FIELD_LABELS.get(field, field))
                    warnings.append(
                        f"Строка {row_n}: «{label}» — значение «{raw_text}» не входит в "
                        f"список допустимых, поле оставлено пустым (исходный текст "
                        f"сохранён в «Примечание»)"
                    )
                    dict_notes.append(f"{label} из файла: {raw_text}")
                continue

            if field in _DICT_BOOL_FIELDS:
                # Тот же справочник допустимых значений (Да/Нет/Нет данных), но
                # хранится bool-колонкой — сопоставляем через тот же
                # match_dictionary_value, а не через грубый _coerce_bool, чтобы
                # «Нет данных» отличался от текста, который вообще не входит в
                # список допустимых (тому положено предупреждение, этому — нет).
                matched = match_dictionary_value(field, val)
                if matched == _NO_DATA_LABEL:
                    target_dict[field] = None
                elif matched is not None:
                    target_dict[field] = (matched == "Да")
                else:
                    coerced_bool = _coerce_bool(val)
                    target_dict[field] = coerced_bool
                    if coerced_bool is None and val is not None and str(val).strip():
                        raw_text = str(val).strip()
                        label = col_header_label.get(ci, _DICT_FIELD_LABELS.get(field, field))
                        warnings.append(
                            f"Строка {row_n}: «{label}» — значение «{raw_text}» не входит в "
                            f"список допустимых (Да/Нет), поле оставлено пустым (исходный "
                            f"текст сохранён в «Примечание»)"
                        )
                        dict_notes.append(f"{label} из файла: {raw_text}")
                continue

            if field == "pts_category":
                # Категория ТС по ПТС — свободный текст (значения A/B/BE/.../Tm
                # в шаблоне лишь подсказка, showErrorMessage=False), поэтому у
                # него нет отдельной функции-коэрсера вроде label_to_code —
                # «Нет данных» перехватываем прямо здесь: не пишем в колонку,
                # без warning'а (см. распоряжение владельца 2026-09, тот же
                # принцип, что и для остальных полей со списком).
                if val is not None and is_no_data_text(val):
                    target_dict[field] = None
                else:
                    text_val = str(val).strip() if val is not None else None
                    max_len = _MAX_LEN.get(field)
                    if text_val and max_len:
                        text_val = text_val[:max_len]
                    target_dict[field] = text_val
                continue

            if field in _BOOL_COLS:
                target_dict[field] = _coerce_bool(val)
            elif field in _DATE_COLS:
                coerced_date = _coerce_date(val)
                if coerced_date is None and val is not None and str(val).strip():
                    label = col_header_label.get(ci, field)
                    warnings.append(
                        f"Строка {row_n}: «{label}» — значение «{str(val).strip()}» "
                        f"не распознано как дата, поле оставлено пустым"
                    )
                target_dict[field] = coerced_date
            elif field in _FLOAT_COLS:
                try:
                    target_dict[field] = float(val) if val is not None else None
                except (TypeError, ValueError):
                    target_dict[field] = None
            elif field in _INT_COLS:
                try:
                    target_dict[field] = int(float(val)) if val is not None else None
                except (TypeError, ValueError):
                    target_dict[field] = None
            else:
                text_val = str(val).strip() if val is not None else None
                max_len = _MAX_LEN.get(field)
                if text_val and max_len:
                    text_val = text_val[:max_len]
                target_dict[field] = text_val

        # Домержить заметку о состоянии (нераспознанный текст либо доп.
        # сведения в скобках вроде "(г.Ростов-на-Дону)" — место, а не
        # состояние) в tech_condition_info, НЕ перезаписывая то, что там уже
        # лежит из одноимённой колонки файла («Сведения о техническом
        # состоянии» — своя колонка, обрабатывается в общей ветке выше и
        # могла успеть записаться в row_data до или после колонки
        # «Состояние» в зависимости от порядка столбцов, поэтому мерж всегда
        # делаем постфактум, после полного прохода по колонкам строки).
        if state_note:
            existing_tci = (row_data.get("tech_condition_info") or "").strip()
            if state_note not in existing_tci:
                row_data["tech_condition_info"] = (
                    f"{existing_tci}; {state_note}" if existing_tci else state_note
                )
                max_len = _MAX_LEN.get("tech_condition_info")
                if max_len:
                    row_data["tech_condition_info"] = row_data["tech_condition_info"][:max_len]

        # Домержить исходные тексты несопоставленных значений справочника
        # (см. _DICT_STRING_FIELDS/_DICT_BOOL_FIELDS выше) в props.note — та же
        # логика "не перезаписывать уже занесённое", что и для state_note выше,
        # но целится в props (JSONB), а не в колонку tech_condition_info.
        if dict_notes:
            existing_note = (props_data.get("note") or "").strip()
            new_parts = [n for n in dict_notes if n not in existing_note]
            if new_parts:
                props_data["note"] = "; ".join(([existing_note] if existing_note else []) + new_parts)

        if props_data:
            row_data["props"] = props_data

        if passes_data:
            row_data["passes"] = passes_data

        # Пункт 6 задания (2026-09): дата документа основания права эксплуатации
        # не может быть раньше даты документа основания права собственности.
        # Импорт — не блокирует строку (владелец потребовал явно: "строка не
        # теряется"), только предупреждение в тот же канал warnings, что и
        # остальные проблемы разбора; обе даты уже сохраняются как есть.
        _own_date = row_data.get("ownership_doc_date")
        _assign_date = row_data.get("assignment_doc_date")
        if _own_date and _assign_date and _assign_date < _own_date:
            warnings.append(
                f"Строка {row_n}: дата документа основания права эксплуатации "
                f"({_assign_date}) раньше даты документа основания права "
                f"собственности ({_own_date}) — проверьте, обе даты сохранены как есть"
            )

        # plate is mandatory
        plate = row_data.get("plate")
        if not plate:
            warnings.append(f"Строка {row_n}: госномер отсутствует, пропущена")
            row_data["_skip"] = True

        parsed_rows.append(row_data)

    wb.close()
    return parsed_rows, warnings


# ─────────────────────────── Org lookup cache ────────────────────────────────
#
# Сопоставление организации-собственника/эксплуатанта — ИНН приоритетнее
# названия (app.services.vehicle_org_matching, не дублируем логику здесь).


