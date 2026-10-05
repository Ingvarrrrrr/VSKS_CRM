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
  clean_purpose_subject(purpose_text) — назначение платежа БЕЗ технического
                       префикса «(КБК;код)»/«(КБК)» и БЕЗ упоминания
                       «Соглашение № ... от ...» — единственное место этой
                       очистки (ПРАВИЛО №6), используется
                       app/services/purchase_from_bank_payment.py («Создать
                       закупку по платёжке» — наименование позиции, когда
                       код расходов не найден в справочнике).
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


def _first_code_line(raw: str) -> str:
    """Живая выписка (ФАДМ, 21.09.2026): ячейка «Детализированный код» иногда
    несёт НЕСКОЛЬКО кодов, разделённых переносом строки (один казначейский
    платёж закрывает документ сразу по двум КРЦС, напр. '0300022\\n0300033') —
    колонка bank_payments.expense_code — VARCHAR(10), на такую строку падает
    StringDataRightTruncationError и импорт выписки обрывается ЦЕЛИКОМ.
    Берём первый код (как и раньше для ОДНОй строки): сортировка/разбор по
    второму коду этого же платежа — отдельная задача, здесь — не терять
    импорт СЕЙЧАС (деньги по строке всё равно одни, назначение видно в
    purpose_text целиком)."""
    first = re.split(r"[\r\n]+", raw.strip())[0].strip()
    return first


# Технический префикс «(<КБК>;<КОД>)» или просто «(<КБК>)» в начале purpose_text
# (см. RX_EXPENSE_CODE выше) — пользователю в наименовании позиции закупки не
# нужен, см. clean_purpose_subject().
_RX_LEADING_CODE_PREFIX = re.compile(
    r"^\([0-9A-ZА-Я]{4,15}(?:;[0-9A-ZА-Я]{4,10})?\)\s*",
    re.IGNORECASE | re.UNICODE,
)
# «Соглашение № 091-10-2026-008 от 28.01.2026» (в любом месте строки, с «№»
# или без) — одинаковое у ВСЕХ платежей субсидии, не идентифицирует саму
# покупку (см. тот же довод в payment_basis.py::_BASIS_PRIORITY выше).
_RX_AGREEMENT_MENTION = re.compile(
    r"Соглашени[ея]\s*№?\s*[0-9A-ZА-Я./-]+\s*от\s*\d{1,2}\.\d{1,2}\.\d{2,4}\.?",
    re.IGNORECASE | re.UNICODE,
)


def clean_purpose_subject(purpose_text: Optional[str]) -> str:
    """Назначение платежа без технического префикса «(КБК;код)» и без
    упоминания «Соглашение № ... от ...». Используется, когда код расходов
    не найден в справочнике ExpenseCode — тогда наименование позиции берётся
    из самого назначения (см. app/services/purchase_from_bank_payment.py).
    Пустая строка на входе/после очистки → "" (решает вызывающий, чем заменить)."""
    text = (purpose_text or "").strip()
    if not text:
        return ""
    text = _RX_LEADING_CODE_PREFIX.sub("", text, count=1)
    text = _RX_AGREEMENT_MENTION.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


def expense_code(bp) -> Optional[str]:
    """Код расходов: сначала из колонок выписки, иначе регуляркой из purpose_text.

    Приоритет: детализированный код колонки (expense_code_detail_col, 7 знаков)
    > короткий код колонки (expense_code_short_col, 4 знака) > regex
    «(<КБК>;<КОД>)» из purpose_text. bp — ParsedRow или объект с такими же
    атрибутами (см. docstring модуля); отсутствующие атрибуты просто
    игнорируются через getattr. Многострочную ячейку (несколько кодов сразу,
    см. _first_code_line) схлопывает до первого кода — иначе значение не
    помещается в bank_payments.expense_code (VARCHAR(10)) и падает весь импорт.
    """
    detail = getattr(bp, "expense_code_detail_col", None)
    if detail and str(detail).strip():
        return _first_code_line(str(detail))[:10]

    short = getattr(bp, "expense_code_short_col", None)
    if short and str(short).strip():
        return _first_code_line(str(short))[:10]

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
    текст назначения. Пример: акт б/н от 15.04.2026 → 'act:БН@2026-04-15'.

    Задача 2026-10-05 («разбор сверки ФАДМ 2026_2», п.1): если у bp есть id
    (строка выписки, реально сохранённый BankPayment — оба писателя,
    app/services/payment_lookup.py::attach и
    app/services/purchase_payments.py::create_payments_from_bank, зовут
    basis_key ИМЕННО на таком объекте) — id дописывается в ключ. Причина:
    ДВЕ РАЗНЫЕ строки выписки (разные bank_payment_id — п/п 297 и 379 на
    проде) с ОДИНАКОВЫМ текстом назначения (частичная оплата одного и того
    же УПД/акта двумя траншами) раньше получали одинаковый basis_key и
    сталкивались на partial unique индексе (purchase_id, basis_key) —
    хотя это два совершенно законных платежа, не дубль (дубль — та же
    строка выписки, см. app/services/payment_lookup.py::attach docstring).
    basis_label (человекочитаемая подпись) по-прежнему БЕЗ этого суффикса —
    на UI не влияет, меняется только защитный ключ уникальности."""
    basis = extract_basis(bp)
    if basis.kind and basis.number:
        num_norm = normalize_doc_number(basis.number)
        date_part = basis.date.isoformat() if basis.date else ""
        key = f"{basis.kind}:{num_norm}@{date_part}"
    else:
        purpose = getattr(bp, "purpose_text", None) or ""
        key = _normalize_purpose_key(purpose)

    bp_id = getattr(bp, "id", None)
    if bp_id is not None:
        key = f"{key}#{bp_id}"
    return key
