"""Правило «строка выписки принадлежит субсидии» (план 2026-10-04,
.planning/quick/2026-10-04-fadm-statement/PLAN.md, п.1).

Раньше (app/services/payment_lookup.py, до этой задачи) строка видна была
РОВНО одной субсидии — через BankPayment.subsidy_id (прямая привязка по
basis_doc_number при импорте выписки, см. app/models/bank_statement.py). Но
если у субсидии ПУСТОЕ поле номера соглашения на момент импорта (как было у
ФАДМ_2026), subsidy_id у всех её строк остаётся NULL навсегда — заполнить его
задним числом для уже импортированных строк нечем.

Владелец, 04.10.2026: «выписка это просто данные, фильтруются по субсидии» —
правило расширено: строка видна субсидии S, если

  1. bp.subsidy_id == S.id (прямая привязка, как раньше) ИЛИ
  2. у S есть номер соглашения (Subsidy.agreement_number) и его нормализованная
     форма (без пробелов/№/регистра) встречается ПОДСТРОКОЙ в нормализованной
     форме назначения платежа (purpose_text) ИЛИ документа-основания
     (basis_doc_text / basis_doc_number) строки.

Одна строка может быть видна НЕСКОЛЬКИМ субсидиям сразу, если у них общий
номер соглашения (разовая/рамочная части одного и того же гранта) — это
осознанно, не баг: «использованность» строки разруливается ВНУТРИ каждой
субсидии отдельно (см. app/services/payment_lookup.py — _attached_bank_payment_ids
теперь тоже скоупится по subsidy_id, не глобально).

ПРАВИЛО №6 — единственное место этого правила: любой код, которому нужно
понять «видна ли эта строка выписки этой субсидии», обязан звать
bank_payment_matches_subsidy() (Python, одна запись) или subsidy_scope_clause()
(SQL, запрос по многим строкам) — а не писать второй фильтр
`BankPayment.subsidy_id == ...` самостоятельно.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import func as sa_func, or_

_WS_OR_NUMBER_SIGN_RE = re.compile(r"[\s№]+")


def normalize_agreement_number(value: Optional[str]) -> Optional[str]:
    """Убрать пробелы/символ «№», привести к верхнему регистру. None/пусто → None.
    Та же нормализация должна применяться к обеим сторонам сравнения — см.
    subsidy_scope_clause() (SQL-эквивалент этой же функции)."""
    if not value:
        return None
    normalized = _WS_OR_NUMBER_SIGN_RE.sub("", str(value)).strip().upper()
    return normalized or None


def _normalize_text_sql(column):
    """SQL-эквивалент normalize_agreement_number() для WHERE-условий —
    убрать пробелы/№, привести к верхнему регистру, NULL → ''."""
    return sa_func.upper(sa_func.regexp_replace(sa_func.coalesce(column, ""), r"[\s№]+", "", "g"))


def bank_payment_matches_subsidy(bp, subsidy) -> bool:
    """Одна строка (bp: BankPayment) — принадлежит ли субсидии subsidy (Subsidy).
    См. докстринг модуля — правило п.1/2."""
    if bp is None or subsidy is None:
        return False
    if getattr(bp, "subsidy_id", None) is not None and bp.subsidy_id == subsidy.id:
        return True
    agreement = normalize_agreement_number(getattr(subsidy, "agreement_number", None))
    if not agreement:
        return False
    for raw in (
        getattr(bp, "purpose_text", None),
        getattr(bp, "basis_doc_text", None),
        getattr(bp, "basis_doc_number", None),
    ):
        norm = normalize_agreement_number(raw)
        if norm and agreement in norm:
            return True
    return False


def subsidy_scope_clause(subsidy):
    """SQL-условие для select(BankPayment).where(...) — строки, видные субсидии
    subsidy (объект Subsidy, не id — нужен agreement_number). Используется вместо
    прежнего `BankPayment.subsidy_id == subsidy_id` всюду, где выписка
    фильтруется по субсидии для сопоставления/реестра."""
    from app.models.bank_statement import BankPayment

    conditions = [BankPayment.subsidy_id == subsidy.id]
    agreement = normalize_agreement_number(getattr(subsidy, "agreement_number", None))
    if agreement:
        # agreement состоит из цифр/дефисов/букв — без %/_ (LIKE-спецсимволов),
        # экранировать нечего; взято из Subsidy.agreement_number (не ввод с формы).
        needle = f"%{agreement}%"
        conditions.append(_normalize_text_sql(BankPayment.purpose_text).like(needle))
        conditions.append(_normalize_text_sql(BankPayment.basis_doc_text).like(needle))
        conditions.append(_normalize_text_sql(BankPayment.basis_doc_number).like(needle))
    return or_(*conditions)
