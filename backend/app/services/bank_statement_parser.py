"""Phase 22 — парсер Excel-выписок банка/казначейства.

Читает xlsx (ScrollerHash или Scroller_FADM_2026), нормализует заголовки,
маппит известные колонки на нормализованные поля, остальное складывает в
raw_json. Возвращает список ParsedRow для дальнейшего сохранения в
bank_payments через bank_statement_parser_save.

Одна строка xlsx = один платёж по одному договору (multi-row split удалён).

Header dict — словарь нормализованных имён → имя поля BankPayment.

Разрезание (Правило №5, сессия 2026-09-08): 1054 строк исходного модуля
разъехались на bank_statement_parser_maps (HEADER_MAP/regex/статусы),
bank_statement_parser_helpers (хэш строки, нормализация заголовка,
Decimal/date/ИНН, extract_all_documents/parse_purpose/parse_basis_doc),
bank_statement_parser_reparse (reparse_bank_payment_typed — typed reparse из
raw_json) и bank_statement_parser_rows (ParsedRow + parse_workbook — целиком,
без внутренних границ). Этот файл — фасад: реэкспортирует все публичные и
приватные имена, чтобы существующие импорты (`from
app.services.bank_statement_parser import parse_workbook`, тесты, monkeypatch
на `app.routers.bank_statements.match_all_in_import` и т.п.) продолжали
работать без изменений.
"""
from __future__ import annotations

import hashlib
import json
import logging as _logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Optional

from openpyxl import load_workbook

from app.services.bank_statement_parser_helpers import (  # noqa: F401
    _is_garbage_number,
    _norm_header,
    _norm_inn,
    _to_date,
    _to_datetime,
    _to_decimal,
    compute_row_hash,
    extract_all_documents,
    parse_basis_doc,
    parse_purpose,
)
from app.services.bank_statement_parser_maps import (  # noqa: F401
    BASIS_DOC_PATTERN,
    DOC_PATTERNS,
    EXECUTED_STATUSES,
    HEADER_MAP,
    REJECTED_STATUSES,
    RX_CONTRACT_PARTS,
    RX_DATE,
    RX_INN,
    RX_KBK,
    RX_VAT,
    _EXPECTED_HEADERS,
    _normalize_lookup_key,
)
from app.services.bank_statement_parser_reparse import (  # noqa: F401
    reparse_bank_payment_typed,
)
from app.services.bank_statement_parser_rows import (  # noqa: F401
    ParsedRow,
    _build_row,
    _expand_merged_row,
    _extract_headers,
    _find_first_data_row,
    _find_header_row,
    _is_numbering_row,
    parse_workbook,
)
from app.services.bank_statement_parser_rows import _parser_log  # noqa: F401

# dir()-паритет со старым модулем: HEADER_MAP/DOC_PATTERNS там были объявлены
# с PEP 526 аннотацией ПРЯМО в модуле, из-за чего Python сам создавал
# module.__annotations__. Здесь они реэкспортированы (не объявлены заново),
# аннотации не возникают сами — восстанавливаем атрибут явно.
__annotations__: dict = {}
