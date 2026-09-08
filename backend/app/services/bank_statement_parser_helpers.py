"""Phase 22 — переиспользуемые преобразователи для парсера банковских выписок.

Разрезание bank_statement_parser.py (Правило №5, сессия 2026-09-08): хэш
строки, нормализация заголовка, извлечение документов/КБК/НДС из
purpose_text, разбор basis_doc_text, приведение ячеек xlsx к
Decimal/date/datetime/ИНН. Используется bank_statement_parser_reparse (typed
reparse из raw_json) и bank_statement_parser_rows (свежий разбор xlsx) —
единая логика, не дублировать.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.services.bank_statement_parser_maps import (
    BASIS_DOC_PATTERN,
    DOC_PATTERNS,
    RX_CONTRACT_PARTS,
    RX_DATE,
    RX_KBK,
    RX_VAT,
)


# ---------------------------------------------------------------------------
# compute_row_hash — SHA-256 от нормализованного JSON всей строки xlsx
# ---------------------------------------------------------------------------

def compute_row_hash(row_dict: dict) -> str:
    """SHA-256 от нормализованного JSON всей строки xlsx.

    Стабилен: sorted keys, str(value).strip(), пустые значения нормализованы в "".
    Две идентичные строки xlsx → один hash. Любое отличие (включая регистры/whitespace) → разный hash.
    """
    normalized = {}
    for k, v in row_dict.items():
        key = str(k).strip().upper().replace('  ', ' ')  # collapse double spaces in key
        if v is None or v == '':
            normalized[key] = ''
        elif isinstance(v, (int, float)):
            normalized[key] = repr(v)  # deterministic float repr
        else:
            normalized[key] = str(v).strip()
    serialized = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Нормализатор заголовков
# ---------------------------------------------------------------------------

def _norm_header(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).upper().strip())


# ---------------------------------------------------------------------------
# extract_all_documents
# ---------------------------------------------------------------------------

def _is_garbage_number(num: Optional[str]) -> bool:
    """Чисто кириллическая «строка» ≤3 символов — падеж/окончание слова
    (напр. «ом» из «договором»), пойманное регуляркой мимо реального номера
    документа, не номер документа."""
    return bool(num) and len(num) <= 3 and bool(re.fullmatch(r"[А-Яа-яЁё]+", num))


def extract_all_documents(purpose_text: str) -> dict:
    """Возвращает {'contracts': [...], 'acts': [...], ...} — все находки из назначения платежа."""
    if not purpose_text:
        return {}
    result: dict[str, list] = {}
    for key, pattern in DOC_PATTERNS.items():
        matches = []
        for m in pattern.finditer(purpose_text):
            try:
                num = m.group("num")
            except IndexError:
                num = None
            is_bn = False
            if not num:
                # «acts» имеет альтернативную bn-ветку — «Акт б/н» без номера.
                # «БН» — намеренный маркер, не «мусорный номер» (см. _is_garbage_number).
                try:
                    bn = m.group("bn")
                except IndexError:
                    bn = None
                if bn:
                    num = "БН"
                    is_bn = True
            try:
                dt = m.group("date")
            except IndexError:
                dt = None
            if num and (is_bn or not _is_garbage_number(num)):
                matches.append({"number": num, "date": dt})
        if matches:
            result[key] = matches
    return result


# ---------------------------------------------------------------------------
# parse_basis_doc
# ---------------------------------------------------------------------------

def parse_basis_doc(basis_doc_text: str) -> tuple[Optional[str], Optional[date]]:
    """Парсит «№ xxx ОТ ДД.ММ.ГГГГ» из колонки «Документ-основание»."""
    if not basis_doc_text:
        return None, None
    m = BASIS_DOC_PATTERN.search(basis_doc_text)
    if not m:
        return None, None
    num = m.group(1).strip()
    try:
        d = datetime.strptime(m.group(2), "%d.%m.%Y").date()
    except ValueError:
        d = None
    return num or None, d


# ---------------------------------------------------------------------------
# parse_purpose — устаревшее имя сохранено для совместимости
# ---------------------------------------------------------------------------

def parse_purpose(text: str) -> dict:
    """Возвращает {kbk, contract_number, contract_date, vat}. Все опциональны.

    Приоритет типа: ДОГОВОР > СОГЛАШЕНИЕ > КОНТРАКТ > РЕЕСТР.
    """
    if not text:
        return {}

    result: dict[str, Any] = {}

    kbk_m = RX_KBK.search(text)
    if kbk_m:
        result["kbk"] = kbk_m.group(1).upper()

    contract_number = None
    contract_match_end = None
    for _label, rx in RX_CONTRACT_PARTS:
        # СОГЛАШЕНИЕ — это субсидия, не договор; не записываем в parsed_contract_number
        if _label == "СОГЛАШЕНИЕ":
            continue
        matches = list(rx.finditer(text))
        if matches:
            m = matches[-1]
            contract_number = m.group(1)
            contract_match_end = m.end()
            break

    if contract_number:
        result["contract_number"] = contract_number
        date_matches = list(RX_DATE.finditer(text))
        for dm in date_matches:
            if dm.start() >= (contract_match_end or 0):
                try:
                    result["contract_date"] = datetime.strptime(dm.group(1), "%d.%m.%Y").date()
                except ValueError:
                    pass
                break

    vat_m = RX_VAT.search(text)
    if vat_m:
        vat_s = vat_m.group(1).replace(",", ".")
        try:
            result["vat"] = Decimal(vat_s)
        except InvalidOperation:
            pass

    return result


# ---------------------------------------------------------------------------
# Вспомогательные преобразователи
# ---------------------------------------------------------------------------

def _to_decimal(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    s = str(v).strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    # ISO 8601 (с временем или без): 2026-05-07T00:00:00 / 2026-05-07
    # _json_safe() сохраняет datetime как isoformat для asyncpg JSONB —
    # обратное чтение должно понимать этот формат.
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_datetime(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    s = str(v).strip()
    if not s:
        return None
    # ISO 8601 — формат _json_safe() для asyncpg JSONB
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _norm_inn(v: Any) -> Optional[str]:
    """Обрезает .0 от числового представления, strip, None если пусто."""
    if v is None:
        return None
    if isinstance(v, float):
        s = str(int(v))
    else:
        s = str(v).strip()
        if s.endswith(".0"):
            s = s[:-2]
    return s if s else None
