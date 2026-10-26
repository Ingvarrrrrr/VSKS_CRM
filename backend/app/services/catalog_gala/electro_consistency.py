"""Проверка непротиворечивости размера кабеля из НАЗВАНИЯ и его
характеристик (electro_mpo, кабельные выгрузки) — владелец, 2026-10-26.

Повод: часть позиций в electro_mpo_cables_all.json несёт в названии формулу
сечения вида «1х2х1,5» (число жил × сечение, мм²), которая на части строк
расходится с полями "Сечение жилы кабеля"/"Количество жил кабеля" в
characteristics (опечатка/смешение разных товаров при выгрузке у
поставщика) — такие позиции решено не загружать в каталог вовсе, а не
просто пометить.

Правило (ЕДИНСТВЕННАЯ такая проверка в проекте, ПРАВИЛО №6 — используется
только from_electro_mpo.convert): ищем в названии хвост вида "N×S" или
"N1×N2×S" (×/х/x, S — число с запятой/точкой). Если такого хвоста нет, или
нет нужной характеристики — позиция НЕ отбрасывается (нет оснований усомниться).
Если есть:
  - S (последнее число формулы) сравнивается с характеристикой «Сечение
    жилы кабеля» (допуск 0.001) — расхождение → отбросить.
  - Если формула из РОВНО двух чисел (N×S, без троек-пар вида «1х2х1,5») —
    N сравнивается с «Количество жил кабеля», ТОЛЬКО если эта характеристика
    сама по себе чисто числовая (иначе сравнение бессмысленно, пропускаем).
    У троек («N1×N2×S» — пара жил) количество жил не сравниваем вовсе —
    формула неоднозначна (владелец, 26.10: сравнивать только последнее
    число с сечением).
"""
import re
from typing import Optional

_CHAIN_RE = re.compile(
    r"\d+(?:[.,]\d+)?(?:\s*[xх×]\s*\d+(?:[.,]\d+)?){1,2}", re.IGNORECASE
)
_SPLIT_RE = re.compile(r"[xх×]", re.IGNORECASE)

_SECTION_CHAR_NAME = "сечение жилы кабеля"
_COUNT_CHAR_NAME = "количество жил кабеля"


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _char_value(characteristics, name_lower) -> Optional[str]:
    for c in characteristics or []:
        if isinstance(c, dict) and (c.get("name") or "").strip().lower() == name_lower:
            return c.get("value")
    return None


def check_cable_consistency(name: Optional[str], characteristics: Optional[list]) -> tuple:
    """Возвращает (ok: bool, reason: str|None). ok=False — название и
    характеристики кабеля противоречат друг другу, позицию нужно
    отбросить (см. докстринг модуля)."""
    if not name:
        return True, None

    m = _CHAIN_RE.search(name)
    if not m:
        return True, None

    parts = [p.strip() for p in _SPLIT_RE.split(m.group(0))]
    numbers = [_to_float(p) for p in parts]
    if any(n is None for n in numbers):
        return True, None

    section = numbers[-1]
    count = numbers[0] if len(numbers) == 2 else None

    sech_raw = _char_value(characteristics, _SECTION_CHAR_NAME)
    sech_val = _to_float(sech_raw)
    if sech_val is not None and abs(sech_val - section) > 0.001:
        return False, (
            f"сечение в названии ({section}) не совпадает с «Сечение жилы "
            f"кабеля» ({sech_raw})"
        )

    if count is not None:
        count_raw = _char_value(characteristics, _COUNT_CHAR_NAME)
        count_val = _to_float(count_raw)
        if count_val is not None and abs(count_val - count) > 1e-9:
            return False, (
                f"количество жил в названии ({count:g}) не совпадает с "
                f"«Количество жил кабеля» ({count_raw})"
            )

    return True, None
