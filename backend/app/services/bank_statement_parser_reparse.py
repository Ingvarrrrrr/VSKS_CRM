"""Phase 22 — typed reparse BankPayment из уже сохранённого raw_json.

Разрезание bank_statement_parser.py (Правило №5, сессия 2026-09-08):
reparse_bank_payment_typed — отдельный путь от «свежего» разбора xlsx
(bank_statement_parser_rows._build_row): применяется к уже импортированной
строке БД, когда исправлен HEADER_MAP/regex и нужно пересобрать typed-поля
без повторной загрузки файла (POST /imports/{id}/reparse-rows,
startup/backfills.py). Общие с _build_row карты/хелперы — не дублировать.
"""
from __future__ import annotations

from typing import Optional

from app.services.bank_statement_parser_helpers import (
    _norm_header,
    _norm_inn,
    _to_date,
    _to_datetime,
    _to_decimal,
    extract_all_documents,
    parse_basis_doc,
    parse_purpose,
)
from app.services.bank_statement_parser_maps import (
    HEADER_MAP,
    RX_INN,
    _normalize_lookup_key,
)


def reparse_bank_payment_typed(bp) -> None:
    """Idempotent — пересобрать ВСЕ typed-поля BankPayment из bp.raw_json.

    Включает: payment_number, payment_date, status, amount, execution_datetime,
    payer_*, payee_*, purpose_text, basis_doc_text, subsidy_code,
    + parsed_contract_number, parsed_contract_date, parsed_kbk, parsed_documents,
    + basis_doc_number, basis_doc_date.

    Использует _normalize_lookup_key для legacy raw_json с composite-ключами.
    Не трогает: matched_*_id (это работа matcher'а), source_row_hash, raw_json.
    """
    raw = bp.raw_json
    if not raw:
        return

    # Нормализуем ключи raw_json
    norm_raw: dict = {}
    for k, v in raw.items():
        norm_raw[_norm_header(k)] = v

    # Декомпозиция composite-ключей "MAIN (SUB)" → MAIN
    norm_raw_decomposed: dict = {}
    for nk, nv in norm_raw.items():
        mapped = _normalize_lookup_key(nk)
        if nv is not None and (mapped not in norm_raw_decomposed or norm_raw_decomposed[mapped] is None):
            norm_raw_decomposed[mapped] = nv

    # Применяем HEADER_MAP
    _expense_code_short: Optional[str] = None
    _expense_code_detail: Optional[str] = None
    for header, field_name in HEADER_MAP.items():
        v = norm_raw.get(header)
        if v is None:
            v = norm_raw_decomposed.get(header)
        if v is None:
            continue

        if field_name == "expense_code_short_col":
            _expense_code_short = str(v).strip() if v else None
            continue
        elif field_name == "expense_code_detail_col":
            _expense_code_detail = str(v).strip() if v else None
            continue

        if field_name == "payment_number":
            bp.payment_number = _norm_inn(v)
        elif field_name == "payment_date":
            bp.payment_date = _to_date(v)
        elif field_name == "status":
            bp.status = str(v).strip().upper() if v else None
        elif field_name == "amount":
            bp.amount = _to_decimal(v)
        elif field_name == "execution_datetime":
            bp.execution_datetime = _to_datetime(v)
        elif field_name == "payer_inn":
            bp.payer_inn = _norm_inn(v)
        elif field_name == "payer_kpp":
            bp.payer_kpp = _norm_inn(v)
        elif field_name == "payer_name":
            bp.payer_name = str(v).strip() if v else None
        elif field_name == "payer_account":
            bp.payer_account = str(v).strip() if v else None
        elif field_name == "payer_block":
            if not bp.payer_inn:
                inn_m = RX_INN.search(str(v))
                if inn_m:
                    bp.payer_inn = inn_m.group(1)
        elif field_name == "payee_inn":
            bp.payee_inn = _norm_inn(v)
        elif field_name == "payee_kpp":
            bp.payee_kpp = _norm_inn(v)
        elif field_name == "payee_name":
            bp.payee_name = str(v).strip() if v else None
        elif field_name == "payee_account":
            bp.payee_account = str(v).strip() if v else None
        elif field_name == "payee_bik":
            bp.payee_bik = str(v).strip() if v else None
        elif field_name == "payee_bank":
            bp.payee_bank = str(v).strip() if v else None
        elif field_name == "payee_block":
            if not bp.payee_inn:
                inn_m = RX_INN.search(str(v))
                if inn_m:
                    bp.payee_inn = inn_m.group(1)
        elif field_name == "purpose_text":
            if not bp.purpose_text:
                bp.purpose_text = str(v).strip() if v else None
        elif field_name == "basis_doc_text":
            bp.basis_doc_text = str(v).strip() if v else None
        elif field_name == "subsidy_code":
            bp.subsidy_code = str(v).strip() if v else None
        elif field_name == "external_doc_id":
            bp.external_doc_id = _norm_inn(v)  # снимает «.0» у числовых идентификаторов из xlsx

    # Парсим purpose_text → parsed_documents/contract_number/kbk
    if bp.purpose_text:
        from datetime import datetime as _dt
        pp = parse_purpose(bp.purpose_text)
        if not bp.parsed_contract_number:
            bp.parsed_contract_number = pp.get("contract_number")
        if not bp.parsed_contract_date:
            bp.parsed_contract_date = pp.get("contract_date")
        if not bp.parsed_kbk:
            bp.parsed_kbk = pp.get("kbk")
        bp.parsed_documents = extract_all_documents(bp.purpose_text)
        # Заполняем parsed_contract_number из parsed_documents.contracts[0] если parse_purpose не нашёл
        if not bp.parsed_contract_number and bp.parsed_documents.get("contracts"):
            first = bp.parsed_documents["contracts"][0]
            bp.parsed_contract_number = first.get("number")
            if first.get("date") and not bp.parsed_contract_date:
                try:
                    bp.parsed_contract_date = _dt.strptime(first["date"], "%d.%m.%Y").date()
                except ValueError:
                    pass
        # Авансовые отчёты: «Авансовый отчёт 20 от 28.04.2026» — берём номер и дату как parsed_contract_*
        # для отображения в UI колонке «Договор/Авансовый отчёт» и для матчинга авансовых.
        if not bp.parsed_contract_number and bp.parsed_documents.get("advance_reports"):
            first = bp.parsed_documents["advance_reports"][0]
            bp.parsed_contract_number = first.get("number")
            if first.get("date") and not bp.parsed_contract_date:
                try:
                    bp.parsed_contract_date = _dt.strptime(first["date"], "%d.%m.%Y").date()
                except ValueError:
                    pass

    # Парсим basis_doc_text → basis_doc_number/date
    if bp.basis_doc_text:
        bn, bd = parse_basis_doc(bp.basis_doc_text)
        if bn and not bp.basis_doc_number:
            bp.basis_doc_number = bn
        if bd and not bp.basis_doc_date:
            bp.basis_doc_date = bd

    # Этап 3: код расходов (КРЦС) — из колонок выписки (если есть) или
    # regex-fallback из purpose_text. Не перезаписываем уже сохранённое
    # значение (idempotent reparse не должен затирать ручную правку).
    if not bp.expense_code:
        from app.services.payment_basis import expense_code as _resolve_expense_code
        from types import SimpleNamespace
        _probe = SimpleNamespace(
            expense_code_short_col=_expense_code_short,
            expense_code_detail_col=_expense_code_detail,
            purpose_text=bp.purpose_text,
        )
        bp.expense_code = _resolve_expense_code(_probe)
