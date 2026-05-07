"""Phase 22 — парсер Excel-выписок банка/казначейства.

Читает xlsx (ScrollerHash или Scroller_FADM_2026), нормализует заголовки,
маппит известные колонки на нормализованные поля, остальное складывает в
raw_json. Возвращает список ParsedRow для дальнейшего сохранения в
bank_payments через bank_statement_parser_save.

Header dict — словарь нормализованных имён → имя поля BankPayment. См.
EXCEL-ANALYSIS.md для эталонного списка заголовков ScrollerHash.

Multi-row split: 20 групп «Расшифровка п/п/Контракт (договор)» в col 62-81
ScrollerHash. Если несколько групп заполнены — порождает N ParsedRow с
разными parsed_contract_number и долями суммы (если в группе есть отдельная
сумма) или равной долей.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Optional

from openpyxl import load_workbook


# ---------------------------------------------------------------------------
# Нормализатор заголовков
# ---------------------------------------------------------------------------

def _norm_header(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).upper().strip())


# ---------------------------------------------------------------------------
# Header → BankPayment field
# ---------------------------------------------------------------------------

HEADER_MAP: dict[str, str] = {
    "НОМЕР ДОКУМЕНТА": "payment_number",
    "ДАТА ДОКУМЕНТА": "payment_date",
    "СТАТУС ДОКУМЕНТА": "status",
    "СУММА": "amount",
    "ДАТА ИСПОЛНЕНИЯ ОПЕРАЦИИ": "execution_date",
    "ДАТА ПРОВОДКИ": "posting_date",
    "ДАТА И ВРЕМЯ УТВЕРЖДЕНИЯ ЦС": "execution_datetime",
    "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)": "purpose_text",
    "ИСТОЧНИК ОПЛАТЫ": "payment_source",
    # Реквизиты плательщика
    "ИНН ПЛАТЕЛЬЩИКА": "payer_inn",
    "КПП ПЛАТЕЛЬЩИКА": "payer_kpp",
    "НАИМЕНОВАНИЕ ПЛАТЕЛЬЩИКА": "payer_name",
    "СЧЕТ ПЛАТЕЛЬЩИКА": "payer_account",
    "РЕКВИЗИТЫ ПЛАТЕЛЬЩИКА": "payer_block",
    # Реквизиты получателя
    "ИНН ПОЛУЧАТЕЛЯ": "payee_inn",
    "КПП ПОЛУЧАТЕЛЯ": "payee_kpp",
    "НАИМЕНОВАНИЕ ПОЛУЧАТЕЛЯ": "payee_name",
    "СЧЕТ ПОЛУЧАТЕЛЯ": "payee_account",
    "БИК ПОЛУЧАТЕЛЯ": "payee_bik",
    "БАНК ПОЛУЧАТЕЛЯ": "payee_bank",
    "РЕКВИЗИТЫ ПОЛУЧАТЕЛЯ": "payee_block",
}

# Финальные ИСПОЛНЕНО-эквивалентные статусы
EXECUTED_STATUSES = {"ИСПОЛНЕН", "ИСПОЛНЕНО", "ОТРАЖЕНО НА Л/С ПЛАТЕЛЬЩИКА"}

# Откатанные/отменённые — пропускаются для матча, но сохраняются
REJECTED_STATUSES = {
    "АННУЛИРОВАН",
    "ОТМЕНЕН",
    "ОТКАЗАНО",
    "НЕ НАПРАВЛЯЛОСЬ В БАНК",
    "КОНТРОЛЬ ФК НЕ ПРОЙДЕН",
}

# Ключевое слово для multi-split групп
_PURPOSE_HEADER = "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)"

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# КБК в скобках вида (712ZU7L4002;0300022) — берём первую группу до «;» или «)»
RX_KBK = re.compile(r"\(([0-9]{3}[A-ZА-Я0-9]{6,10})[;)]", re.IGNORECASE)

# Приоритет: ДОГОВОР > СОГЛАШЕНИЕ > КОНТРАКТ > РЕЕСТР ДОК
RX_CONTRACT_PARTS = [
    ("ДОГОВОР",    re.compile(r"ДОГОВОР\s+([0-9А-ЯA-Z/\-\.]+)", re.IGNORECASE | re.UNICODE)),
    ("СОГЛАШЕНИЕ", re.compile(r"СОГЛАШЕНИЕ\s+([0-9А-ЯA-Z/\-\.]+)", re.IGNORECASE | re.UNICODE)),
    ("КОНТРАКТ",   re.compile(r"КОНТРАКТ\s+([0-9А-ЯA-Z/\-\.]+)", re.IGNORECASE | re.UNICODE)),
    ("РЕЕСТР",     re.compile(r"РЕЕСТР\s+ДОК\.?-?ОСН\.?\s+([0-9А-ЯA-Z/\-\.]+)", re.IGNORECASE | re.UNICODE)),
]

# Дата "ОТ ДД.ММ.ГГГГ" — все вхождения, берём последнее соответствующее слову
RX_DATE = re.compile(r"ОТ\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
RX_VAT = re.compile(r"НДС\s*([\d.,]+)", re.IGNORECASE)

# ИНН из текстовых блоков (10 или 12 цифр)
RX_INN = re.compile(r"\b(\d{10}|\d{12})\b")


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
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
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
        # Excel хранит ИНН как число → 2315176820.0
        s = str(int(v))
    else:
        s = str(v).strip()
        if s.endswith(".0"):
            s = s[:-2]
    return s if s else None


# ---------------------------------------------------------------------------
# parse_purpose
# ---------------------------------------------------------------------------

def parse_purpose(text: str) -> dict:
    """Возвращает {kbk, contract_number, contract_date, vat}. Все опциональны.

    Приоритет типа контракта: ДОГОВОР > СОГЛАШЕНИЕ > КОНТРАКТ > РЕЕСТР.
    Если несколько вхождений одного типа — берём последнее.
    Дата «ОТ» берётся следующая после найденного номера контракта.
    """
    if not text:
        return {}

    result: dict[str, Any] = {}

    # КБК
    kbk_m = RX_KBK.search(text)
    if kbk_m:
        result["kbk"] = kbk_m.group(1).upper()

    # Контракт: ищем по приоритету, берём последнее вхождение нужного типа
    contract_number = None
    contract_match_end = None

    for _label, rx in RX_CONTRACT_PARTS:
        matches = list(rx.finditer(text))
        if matches:
            # берём последнее вхождение
            m = matches[-1]
            contract_number = m.group(1)
            contract_match_end = m.end()
            break

    if contract_number:
        result["contract_number"] = contract_number
        # Ищем дату "ОТ ДД.ММ.ГГГГ" после найденного номера
        date_matches = list(RX_DATE.finditer(text))
        # Берём первую дату ПОСЛЕ позиции конца номера контракта
        contract_date = None
        for dm in date_matches:
            if dm.start() >= (contract_match_end or 0):
                ds = dm.group(1)
                try:
                    contract_date = datetime.strptime(ds, "%d.%m.%Y").date()
                except ValueError:
                    pass
                break
        if contract_date:
            result["contract_date"] = contract_date

    # НДС
    vat_m = RX_VAT.search(text)
    if vat_m:
        vat_s = vat_m.group(1).replace(",", ".")
        try:
            result["vat"] = Decimal(vat_s)
        except InvalidOperation:
            pass

    return result


# ---------------------------------------------------------------------------
# _row_hash
# ---------------------------------------------------------------------------

def _row_hash(payment_number: Any, payment_date: Any, payer_inn: Any, amount: Any) -> str:
    """SHA1 натурального ключа строки выписки — для multi-split linking."""
    s = f"{payment_number}|{payment_date}|{payer_inn}|{amount}"
    return hashlib.sha1(s.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ParsedRow
# ---------------------------------------------------------------------------

@dataclass
class ParsedRow:
    payment_number: Optional[str] = None
    payment_date: Optional[date] = None
    execution_datetime: Optional[datetime] = None
    status: Optional[str] = None
    amount: Optional[Decimal] = None

    payer_inn: Optional[str] = None
    payer_kpp: Optional[str] = None
    payer_name: Optional[str] = None
    payer_account: Optional[str] = None

    payee_inn: Optional[str] = None
    payee_kpp: Optional[str] = None
    payee_name: Optional[str] = None
    payee_account: Optional[str] = None
    payee_bik: Optional[str] = None
    payee_bank: Optional[str] = None

    purpose_text: Optional[str] = None
    parsed_contract_number: Optional[str] = None
    parsed_contract_date: Optional[date] = None
    parsed_kbk: Optional[str] = None

    raw_json: dict = field(default_factory=dict)
    source_row_hash: Optional[str] = None
    is_executed: bool = False
    skip_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# _extract_headers
# ---------------------------------------------------------------------------

def _extract_headers(ws) -> list[str]:
    """Читает первую строку листа, нормализует заголовки.

    Merged cells разворачиваются с None у подчинённых ячеек — наследуем
    последний непустой заголовок (логика FADM с Реквизиты получателя x3).
    """
    raw = [c.value for c in next(ws.iter_rows(max_row=1))]
    out: list[str] = []
    last = ""
    for v in raw:
        if v not in (None, ""):
            last = _norm_header(v)
            out.append(last)
        else:
            out.append(last)
    return out


# ---------------------------------------------------------------------------
# _build_row — заполнить ParsedRow из значений ячеек + headers
# ---------------------------------------------------------------------------

def _build_row(
    headers: list[str],
    values: list[Any],
    purpose_indices: list[int],
) -> Optional[ParsedRow]:
    """Строит ParsedRow из одной строки данных.

    Возвращает None если строка полностью пустая.
    """
    # Проверяем что строка не пустая
    if all(v is None or str(v).strip() == "" for v in values):
        return None

    row = ParsedRow()
    raw: dict[str, Any] = {}

    # Группировка по нормализованному заголовку для multi-col concat
    col_groups: dict[str, list[Any]] = {}
    for i, (h, v) in enumerate(zip(headers, values)):
        if not h:
            continue
        col_groups.setdefault(h, []).append(v)

    # Заполняем raw_json (первое значение для уникальных, join для повторяющихся)
    for h, vals in col_groups.items():
        non_null = [v for v in vals if v is not None and str(v).strip() != ""]
        if not non_null:
            raw[h] = None
        elif len(non_null) == 1:
            raw[h] = non_null[0]
        else:
            raw[h] = "\n".join(str(v) for v in non_null)

    row.raw_json = raw

    # Маппим известные поля
    for h, field_name in HEADER_MAP.items():
        v = raw.get(h)
        if v is None:
            continue

        if field_name == "payment_number":
            row.payment_number = _norm_inn(v)  # нормализация .0
        elif field_name == "payment_date":
            row.payment_date = _to_date(v)
        elif field_name == "status":
            row.status = str(v).strip().upper() if v else None
        elif field_name == "amount":
            row.amount = _to_decimal(v)
        elif field_name == "execution_datetime":
            row.execution_datetime = _to_datetime(v)
        elif field_name == "payer_inn":
            row.payer_inn = _norm_inn(v)
        elif field_name == "payer_kpp":
            row.payer_kpp = _norm_inn(v)
        elif field_name == "payer_name":
            row.payer_name = str(v).strip() if v else None
        elif field_name == "payer_account":
            row.payer_account = str(v).strip() if v else None
        elif field_name == "payer_block":
            # Вытаскиваем ИНН из текстового блока если нет явного поля
            block_text = str(v)
            if not row.payer_inn:
                inn_m = RX_INN.search(block_text)
                if inn_m:
                    row.payer_inn = inn_m.group(1)
        elif field_name == "payee_inn":
            row.payee_inn = _norm_inn(v)
        elif field_name == "payee_kpp":
            row.payee_kpp = _norm_inn(v)
        elif field_name == "payee_name":
            row.payee_name = str(v).strip() if v else None
        elif field_name == "payee_account":
            row.payee_account = str(v).strip() if v else None
        elif field_name == "payee_bik":
            row.payee_bik = str(v).strip() if v else None
        elif field_name == "payee_bank":
            row.payee_bank = str(v).strip() if v else None
        elif field_name == "payee_block":
            # Вытаскиваем ИНН из текстового блока если нет явного поля
            block_text = str(v)
            if not row.payee_inn:
                inn_m = RX_INN.search(block_text)
                if inn_m:
                    row.payee_inn = inn_m.group(1)
        elif field_name == "purpose_text":
            row.purpose_text = str(v).strip() if v else None

    # Парсим purpose_text
    if row.purpose_text:
        pp = parse_purpose(row.purpose_text)
        row.parsed_contract_number = pp.get("contract_number")
        row.parsed_contract_date = pp.get("contract_date")
        row.parsed_kbk = pp.get("kbk")

    # Статус
    status_norm = (row.status or "").upper().strip()
    if status_norm in EXECUTED_STATUSES:
        row.is_executed = True
    if status_norm in REJECTED_STATUSES:
        row.skip_reason = status_norm

    # source_row_hash
    row.source_row_hash = _row_hash(
        row.payment_number,
        row.payment_date,
        row.payer_inn,
        row.amount,
    )

    return row


# ---------------------------------------------------------------------------
# _split_by_purpose — multi-row split по повторяющимся purpose_text-группам
# ---------------------------------------------------------------------------

def _split_by_purpose(base_row: ParsedRow, purpose_values: list[str]) -> list[ParsedRow]:
    """Если несколько групп «Расшифровка п/п/Контракт (договор)» заполнены,
    порождает N ParsedRow с разными parsed_contract_number.

    У всех split-строк одинаковый source_row_hash (по базовой строке).
    """
    non_empty = [v for v in purpose_values if v and str(v).strip()]
    if len(non_empty) <= 1:
        # Нет смысла сплитить — возвращаем базовую строку как есть
        if non_empty:
            base_row.purpose_text = str(non_empty[0]).strip()
            pp = parse_purpose(base_row.purpose_text)
            base_row.parsed_contract_number = pp.get("contract_number")
            base_row.parsed_contract_date = pp.get("contract_date")
            base_row.parsed_kbk = pp.get("kbk")
        return [base_row]

    result: list[ParsedRow] = []
    shared_hash = base_row.source_row_hash

    for v in non_empty:
        new_row = deepcopy(base_row)
        new_row.source_row_hash = shared_hash
        new_row.purpose_text = str(v).strip()
        pp = parse_purpose(new_row.purpose_text)
        new_row.parsed_contract_number = pp.get("contract_number")
        new_row.parsed_contract_date = pp.get("contract_date")
        new_row.parsed_kbk = pp.get("kbk")
        result.append(new_row)

    return result


# ---------------------------------------------------------------------------
# parse_workbook — главная функция
# ---------------------------------------------------------------------------

def parse_workbook(
    file_bytes: bytes,
    sheet_name: Optional[str] = None,
) -> tuple[str, list[ParsedRow]]:
    """Главная функция парсера.

    1. Открывает xlsx
    2. Берёт sheet_name или первый активный
    3. Читает headers, нормализует, ищет в HEADER_MAP индексы
    4. Для каждой data row:
       - заполняет ParsedRow (известные поля)
       - сохраняет ВСЕ значения в raw_json по нормализованному ключу
       - парсит purpose_text → contract_number/date/kbk
       - ставит is_executed = True если status IN EXECUTED_STATUSES
       - детектирует 20 групп «Расшифровка п/п/Контракт (договор)»: если
         несколько подколонок с этим именем заполнены — split row на N
         ParsedRow с разными parsed_contract_number и одинаковым
         source_row_hash. Сумма копируется как есть.
    5. Возвращает (sheet_name, list[ParsedRow])
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)

    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        active_name = sheet_name
    else:
        ws = wb.active
        active_name = ws.title

    headers = _extract_headers(ws)

    # Индексы столбцов с purpose_text (может быть несколько — multi-split)
    purpose_indices: list[int] = [
        i for i, h in enumerate(headers) if h == _PURPOSE_HEADER
    ]

    parsed: list[ParsedRow] = []

    rows_iter = ws.iter_rows(min_row=2, values_only=True)
    for raw_values in rows_iter:
        values = list(raw_values)

        # Паддинг если меньше столбцов чем заголовков
        while len(values) < len(headers):
            values.append(None)

        # Строим базовую строку (purpose_text будет заполнен из первого индекса)
        base = _build_row(headers, values, purpose_indices)
        if base is None:
            continue

        # Multi-split: собираем все purpose-значения по всем purpose_indices
        if len(purpose_indices) > 1:
            purpose_values = [
                values[i] for i in purpose_indices if i < len(values)
            ]
            rows_out = _split_by_purpose(base, purpose_values)
        else:
            rows_out = [base]

        parsed.extend(rows_out)

    wb.close()
    return active_name, parsed
