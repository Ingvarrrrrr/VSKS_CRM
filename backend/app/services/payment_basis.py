"""Этап 3 утверждённого плана — код расходов и основание платежа.

Три независимые функции, работающие поверх ParsedRow (парсер) или уже
сохранённого BankPayment (реестр/reparse) — оба объекта имеют одинаковые
атрибуты purpose_text / parsed_documents, поэтому все функции ниже duck-typed
и не завязаны на конкретный класс.

  expense_code(bp)  — код направления расходования целевых средств (КРЦС).
  expense_kind(db, code) — грубый тип платежа по справочнику ExpenseCode.
  extract_basis(bp) — документ-основание платежа (УПД/акт/счёт/...).
  basis_key(bp)     — нормализованный ключ для правила «одно назначение —
                       один платёж» (используется и в UI, и в проверках).
  normalize_doc_number — перенесено сюда из payment_matcher.py (Этап 3);
                       в payment_matcher.py оставлен ре-экспорт.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date, datetime as _datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# normalize_doc_number — перенесено из payment_matcher.py:21-24
# ---------------------------------------------------------------------------

def normalize_doc_number(s: str) -> str:
    if not s:
        return ""
    return s.replace(" ", "").replace("-", "").replace("/", "").replace(".", "").upper()


# ---------------------------------------------------------------------------
# expense_code — код расходов (КРЦС)
# ---------------------------------------------------------------------------

# «(711К0232001;0200032)» — первая часть до «;» это КБК/код цели (кладётся в
# parsed_kbk парсером как раньше), вторая — код расходов.
RX_EXPENSE_CODE = re.compile(
    r"\([0-9A-ZА-Я]{4,15};([0-9A-ZА-Я]{4,10})\)",
    re.IGNORECASE | re.UNICODE,
)


def expense_code(bp) -> Optional[str]:
    """Код расходов: сначала из колонок выписки, иначе регуляркой из purpose_text.

    Приоритет: детализированный код колонки (expense_code_detail_col, 7 знаков)
    > короткий код колонки (expense_code_short_col, 4 знака) > regex
    «(<КБК>;<КОД>)» из purpose_text. bp — ParsedRow или объект с такими же
    атрибутами (см. docstring модуля); отсутствующие атрибуты просто
    игнорируются через getattr.
    """
    detail = getattr(bp, "expense_code_detail_col", None)
    if detail and str(detail).strip():
        return str(detail).strip()

    short = getattr(bp, "expense_code_short_col", None)
    if short and str(short).strip():
        return str(short).strip()

    purpose = getattr(bp, "purpose_text", None)
    if purpose:
        m = RX_EXPENSE_CODE.search(purpose)
        if m:
            return m.group(1).strip().upper()

    return None


# ---------------------------------------------------------------------------
# expense_kind — тип платежа по справочнику ExpenseCode
# ---------------------------------------------------------------------------

async def expense_kind(db: AsyncSession, code: Optional[str]) -> Optional[str]:
    """Тип платежа (kind) по справочнику: точное совпадение по коду, иначе
    по укрупнённому коду (первые 4 знака). Нераспознанный код → None, ничего
    не блокирует."""
    if not code:
        return None

    from app.models.expense_code import ExpenseCode  # локальный импорт — без цикла на models на старте модуля

    code = str(code).strip()
    if not code:
        return None

    row = (await db.execute(
        select(ExpenseCode.kind).where(ExpenseCode.code == code)
    )).scalar_one_or_none()
    if row:
        return row

    prefix = code[:4]
    if prefix and prefix != code:
        row = (await db.execute(
            select(ExpenseCode.kind).where(ExpenseCode.code == prefix)
        )).scalar_one_or_none()
        if row:
            return row

    return None


# ---------------------------------------------------------------------------
# extract_basis — документ-основание платежа
# ---------------------------------------------------------------------------

@dataclass
class Basis:
    kind: Optional[str] = None      # upd | act | invoice | waybill | registry | advance_report | contract | None
    number: Optional[str] = None
    date: Optional[_date] = None
    label: Optional[str] = None


# Приоритет: УПД > Акт > Счёт > Накладная > Реестр док.-осн. > Авансовый отчёт
# > Договор. Ключ соглашения о субсидии (agreements/СОГЛАШЕНИЕ) сюда
# намеренно НЕ входит — оно одинаковое у всех платежей субсидии и не
# идентифицирует конкретный платёж.
_BASIS_PRIORITY = [
    ("upd", "upd", "УПД"),
    ("acts", "act", "Акт"),
    ("invoices", "invoice", "Счёт"),
    ("waybills", "waybill", "Накладная"),
    ("registry", "registry", "Реестр док.-осн."),
    ("advance_reports", "advance_report", "Авансовый отчёт"),
    ("contracts", "contract", "Договор"),
]


def _parse_doc_date(s: Optional[str]) -> Optional[_date]:
    if not s:
        return None
    try:
        return _datetime.strptime(s, "%d.%m.%Y").date()
    except (ValueError, TypeError):
        return None


def extract_basis(bp) -> Basis:
    """Документ, за который платят — по parsed_documents (см. приоритет выше)."""
    docs = getattr(bp, "parsed_documents", None) or {}

    for doc_key, kind, label_prefix in _BASIS_PRIORITY:
        items = docs.get(doc_key) or []
        if not items:
            continue
        first = items[0] or {}
        number = first.get("number")
        if not number:
            continue

        doc_date = _parse_doc_date(first.get("date"))

        if kind == "act" and number == "БН":
            label = "Акт б/н"
        else:
            label = f"{label_prefix} {number}"
        if doc_date:
            label += f" от {doc_date.strftime('%d.%m.%Y')}"

        return Basis(kind=kind, number=number, date=doc_date, label=label)

    return Basis()


# ---------------------------------------------------------------------------
# basis_key — нормализованный ключ «одно назначение — один платёж»
# ---------------------------------------------------------------------------

def _normalize_purpose_key(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().upper())


def basis_key(bp) -> str:
    """Документ, если распознан (kind:номер@дата), иначе нормализованный
    текст назначения. Пример: акт б/н от 15.04.2026 → 'act:БН@2026-04-15'."""
    basis = extract_basis(bp)
    if basis.kind and basis.number:
        num_norm = normalize_doc_number(basis.number)
        date_part = basis.date.isoformat() if basis.date else ""
        return f"{basis.kind}:{num_norm}@{date_part}"

    purpose = getattr(bp, "purpose_text", None) or ""
    return _normalize_purpose_key(purpose)
