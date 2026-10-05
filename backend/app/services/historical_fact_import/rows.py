"""Разбор строк листа (оба формата) в нормализованные записи.

Иерархия задана «залитой вниз» ячейкой (как в Excel с объединёнными
ячейками уровня, но тут просто пусто у строк-потомков) — несём последнее
непустое значение каждой колонки уровня вперёд по строкам того же листа.

Строка считается ЛИСТОВОЙ (попадает в предпросмотр) только если у неё есть
листовое имя — «Плановая позиция» (ХО) / «Подкатегория» (ЛНР), или самый
глубокий заполненный уровень. Строка только с верхним уровнем (итог раздела/
направления расходов, без собственных кол-ва/цены) — пропускается молча,
это не отдельная плановая позиция, а сумма детей.

ХО: количество факта (колонка S) бывает испорчено порядковыми номерами
(владелец) — кол-во ВСЕГДА пересчитывается из сумма/цена, когда и то, и то
заполнено и цена ненулевая (не читаем сырое значение колонки вообще).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip().replace("\xa0", "").replace(" ", "")
        if not v:
            return None
        v = v.replace(",", ".")
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d


def _to_text(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


_ADVANCE_TRUE = {"да", "yes", "true", "1", "y", "аванс"}


def _to_advance_bool(v) -> bool:
    """Колонка «Аванс (да/нет)» (задача 2, владелец 05.10.2026) — пусто/«нет»/
    что угодно непризнанное = False (постоплата, текущее поведение), «да»/
    «yes»/«true»/«1» = True. Не блокирующий список (как и остальные dropdown
    колонки шаблона — lesson feedback_excel_template_dropdowns), нераспознанный
    текст не считается авансом."""
    s = _to_text(v)
    if not s:
        return False
    return s.strip().lower().replace("ё", "е") in _ADVANCE_TRUE


def parse_rows(detected: dict, columns: list, header_row: int) -> list:
    """Возвращает [{row, name, path, item_type, unit, plan:{...}, fact:{...},
    paid, contracted, status_raw, purchase_no, supplier, comment}, ...].

    `row` — номер строки Excel (1-based), для ссылок в предупреждениях/
    decisions.row_overrides.
    """
    all_rows = detected["rows"]
    by_field = {}
    for c in columns:
        if c.get("field"):
            by_field.setdefault(c["field"], c["index"])

    def get(raw_row: list, field: str):
        idx = by_field.get(field)
        if idx is None or idx >= len(raw_row):
            return None
        return raw_row[idx]

    carry = {"path_l2": None, "path_l3": None, "path_l4": None}
    out = []
    data_rows = all_rows[header_row:]
    for offset, raw_row in enumerate(data_rows):
        excel_row = header_row + offset + 1
        if raw_row is None or not any(c is not None and str(c).strip() != "" for c in raw_row):
            continue

        l2 = _to_text(get(raw_row, "path_l2"))
        l3 = _to_text(get(raw_row, "path_l3"))
        l4 = _to_text(get(raw_row, "path_l4"))
        if l2:
            carry["path_l2"] = l2
            carry["path_l3"] = None
            carry["path_l4"] = None
        if l3:
            carry["path_l3"] = l3
            carry["path_l4"] = None
        if l4:
            carry["path_l4"] = l4

        leaf_name = _to_text(get(raw_row, "plan_item_name")) or carry["path_l4"] or carry["path_l3"]
        if not leaf_name:
            # Строка-итог раздела/направления расходов (нет листового имени) — пропуск.
            continue

        path = [p for p in (carry["path_l2"], carry["path_l3"]) if p and p != leaf_name]
        if carry["path_l4"] and carry["path_l4"] != leaf_name:
            path.append(carry["path_l4"])

        plan_qty = _to_dec(get(raw_row, "plan_qty"))
        plan_price = _to_dec(get(raw_row, "plan_price"))
        plan_amount = _to_dec(get(raw_row, "plan_amount"))

        fact_amount = _to_dec(get(raw_row, "fact_amount"))
        fact_price = _to_dec(get(raw_row, "fact_price"))
        fact_qty_raw = _to_dec(get(raw_row, "fact_qty"))
        fact_qty = fact_qty_raw
        if fact_amount is not None and fact_price not in (None, Decimal(0)):
            fact_qty = (fact_amount / fact_price)

        paid = _to_dec(get(raw_row, "paid"))
        advance = _to_advance_bool(get(raw_row, "advance"))
        contracted = _to_dec(get(raw_row, "contracted"))
        status_raw = _to_text(get(raw_row, "status_raw")) or _to_text(get(raw_row, "status"))
        purchase_no = _to_text(get(raw_row, "purchase_no"))
        supplier = _to_text(get(raw_row, "supplier"))
        comment = _to_text(get(raw_row, "comment"))
        item_type = _to_text(get(raw_row, "item_type"))
        unit = _to_text(get(raw_row, "unit"))

        out.append({
            "row": excel_row,
            "name": leaf_name,
            "path": path,
            "item_type": item_type,
            "unit": unit,
            "plan": {"qty": plan_qty, "price": plan_price, "amount": plan_amount},
            "fact": {"qty": fact_qty, "price": fact_price, "amount": fact_amount},
            "paid": paid,
            "advance": advance,
            "contracted": contracted,
            "status_raw": status_raw,
            "purchase_no": purchase_no,
            "supplier": supplier,
            "comment": comment,
        })
    return out
