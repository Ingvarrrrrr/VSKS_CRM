"""Разбор НДС из назначения платежа банковской/казначейской выписки.

Задача владельца (2026-09-26): «надо проверять НДС по выгрузке платежей: если
в платежах НДС указан другой, то об этом надо сообщать...». Единственное
место, где текст назначения платежа превращается в (сумма НДС, ставка) —
ПРАВИЛО №6, все места сверки (app/services/purchase_vat_check.py) читают
результат отсюда, копий разбора не заводить.

Реальный формат в назначении (72 платежа локальной БД, во всех есть):
  «... НДС0.00», «... НДС 0.00», «... НДС17581.97», «... НДС 19516.52» —
  СУММА НДС в конце строки, без ставки. Ставка вычисляется по стандартной
  формуле «НДС на сумму сверху»: rate = vat / (amount - vat) * 100, где
  amount — сумма платежа (сумма ВКЛЮЧАЕТ НДС).
Дополнительно поддерживаются (на случай другого формата выписки):
  «в т.ч. НДС 20%», «НДС (22%) 1234.56», «Без НДС», «НДС не облагается».
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.services.item_amounts import vat_included_amount as _vat_included_amount

# Единственный источник допустимых ставок НДС для сверки платежей (не путать
# со списком frontend/src/composables/useVatCalc.ts::VAT_RATE_OPTIONS — тот
# описывает, что можно ВЫБРАТЬ в форме закупки, 0/5/7/10/20/22; этот —
# что можно РАСПОЗНАТЬ в тексте банковского платежа, тот же набор чисел).
STANDARD_RATES = (0, 5, 7, 10, 20, 22)
RATE_TOLERANCE = Decimal("0.5")   # п.п. — допуск округления при вычислении ставки из суммы

_NO_VAT_RE = re.compile(r"без\s*ндс|ндс\s*не\s*облага", re.IGNORECASE)
# "ндс" затем (опционально в скобках) ставка с "%"
_PERCENT_RE = re.compile(r"ндс\s*\(?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%\)?", re.IGNORECASE)
# число вида "1 234.56" / "1234,56" / "0.00" — ищем ПОСЛЕДНЕЕ вхождение суммы НДС после слова "ндс"
_AMOUNT_AFTER_NDS_RE = re.compile(r"ндс\D{0,12}?(\d[\d\s]*[.,]\d{2})", re.IGNORECASE)


@dataclass
class ParsedPaymentVat:
    vat_amount: Optional[Decimal]
    rate: Optional[Decimal]           # None если не распознано
    kind: str                          # 'no_vat' | 'rate' | 'nonstandard' | 'unknown'

    def as_dict(self) -> dict:
        return {
            "vat_amount": self.vat_amount,
            "rate": self.rate,
            "kind": self.kind,
        }


def _to_decimal(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _nearest_standard_rate(rate: Decimal) -> Optional[int]:
    """Ближайшая стандартная ставка, если отклонение <= RATE_TOLERANCE п.п., иначе None."""
    best = None
    best_diff = None
    for std in STANDARD_RATES:
        diff = abs(rate - Decimal(std))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = std
    if best is not None and best_diff is not None and best_diff <= RATE_TOLERANCE:
        return best
    return None


def parse_payment_vat(purpose_text: Optional[str], amount: Optional[Decimal]) -> dict:
    """Разбор назначения платежа → {vat_amount, rate, kind}.

    kind:
      'no_vat'      — «Без НДС» / «НДС не облагается» / сумма НДС ровно 0.
      'rate'        — сумма/ставка НДС распознаны и совпадают (в допуске)
                      со стандартной ставкой (0,5,7,10,20,22).
      'nonstandard' — сумма/ставка НДС распознаны, но не попадают ни в одну
                      стандартную ставку (отклонение > RATE_TOLERANCE п.п.).
      'unknown'     — в тексте назначения не нашлось ни одного признака НДС.
    """
    text = (purpose_text or "").strip()
    if not text:
        return ParsedPaymentVat(None, None, "unknown").as_dict()

    if _NO_VAT_RE.search(text):
        return ParsedPaymentVat(Decimal("0"), Decimal("0"), "no_vat").as_dict()

    amount_dec = None
    if amount is not None:
        try:
            amount_dec = Decimal(str(amount))
        except InvalidOperation:
            amount_dec = None

    # 1) Ставка указана явно текстом ("НДС 20%", "НДС (22%) 1234.56", "в т.ч. НДС 20% - 1000.00").
    m_pct = _PERCENT_RE.search(text)
    if m_pct:
        rate_declared = _to_decimal(m_pct.group(1))
        vat_amount = None
        tail = text[m_pct.end(): m_pct.end() + 30]
        m_amt = re.search(r"(\d[\d\s]*[.,]\d{2})", tail)
        if m_amt:
            vat_amount = _to_decimal(m_amt.group(1))
        elif amount_dec is not None and rate_declared is not None:
            vat_amount = _vat_included_amount(amount_dec, rate_declared)
        if rate_declared is not None:
            if rate_declared == 0:
                return ParsedPaymentVat(vat_amount if vat_amount is not None else Decimal("0"), Decimal("0"), "no_vat").as_dict()
            std = _nearest_standard_rate(rate_declared)
            kind = "rate" if std is not None else "nonstandard"
            rate_out = Decimal(std) if std is not None else rate_declared
            return ParsedPaymentVat(vat_amount, rate_out, kind).as_dict()

    # 2) Только сумма НДС (реальный формат местной выгрузки: "... НДС17581.97").
    matches = list(_AMOUNT_AFTER_NDS_RE.finditer(text))
    if matches:
        vat_amount = _to_decimal(matches[-1].group(1))
        if vat_amount is not None:
            if vat_amount == 0:
                return ParsedPaymentVat(Decimal("0"), Decimal("0"), "no_vat").as_dict()
            if amount_dec is not None and amount_dec > vat_amount:
                rate_calc = (vat_amount / (amount_dec - vat_amount) * Decimal(100))
                std = _nearest_standard_rate(rate_calc)
                kind = "rate" if std is not None else "nonstandard"
                rate_out = Decimal(std) if std is not None else rate_calc.quantize(Decimal("0.01"))
                return ParsedPaymentVat(vat_amount, rate_out, kind).as_dict()
            # Сумма НДС есть, но не с чем сравнить (нет amount) — ставку не считаем.
            return ParsedPaymentVat(vat_amount, None, "nonstandard").as_dict()

    return ParsedPaymentVat(None, None, "unknown").as_dict()


def format_vat_label(parsed: dict) -> str:
    """Человекочитаемая подпись для UI ('22%', 'без НДС', 'не распознано')."""
    kind = parsed.get("kind")
    if kind == "no_vat":
        return "без НДС"
    if kind in ("rate", "nonstandard"):
        rate = parsed.get("rate")
        vat_amount = parsed.get("vat_amount")
        rate_s = f"{rate:g}" if rate is not None else "?"
        suffix = " (нестандартная)" if kind == "nonstandard" else ""
        if vat_amount is not None:
            return f"{rate_s}%{suffix}, НДС {vat_amount} ₽"
        return f"{rate_s}%{suffix}"
    return "не распознано"
