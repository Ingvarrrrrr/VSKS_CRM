"""Числовые парсеры, общие для нескольких роутеров (Правило №6)."""
from decimal import Decimal
from typing import Optional


def to_decimal(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(" ", "").replace(",", ".").replace("\xa0", ""))
    except Exception:
        return None
