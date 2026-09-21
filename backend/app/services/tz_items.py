"""Группировка дублирующихся строк ТЗ и их объединение в документе.

Решение владельца (21.09, план corrections-21-09.md, раздел W3): повторяющиеся
позиции ТЗ («Огнетушитель — 2 шт» и «Огнетушитель — 3 шт», возможно в разных
категориях ФЭО) — пользователь решает сам: объединить в документе ТЗ,
оставить раздельно, либо вернуть закупку на доработку (см.
app/routers/purchase_return.py). Строки покупки/заявки (purchase_items/
wish_items) слиянием НЕ трогаются — ТЗ едино для договора и приёмки, склейка
применяется только на выходе, при построении строк документа.

Правило №6: это ЕДИНСТВЕННОЕ место, которое решает, что считается дублем и
как он схлопывается в документе. Раньше решение молча принимала
`_merge_identical_items` (services/documents/formatting.py) — она удалена,
её преемник — build_tz_rows ниже; вызывающие места — contexts.py,
fabrikant_package.py.

Duck typing: работает и с PurchaseItem, и с WishItem — оба несут одинаковый
набор полей (item_name/unit/product_id/quantity/unit_price/total_price/
item_type/feo_category_id).
"""
from decimal import Decimal
from typing import Any, Iterable, Literal, Optional

from app.services.text_match import normalize as _normalize_name

Decision = Literal["merge", "keep"]


def group_key(item: Any) -> str:
    """Стабильный ключ группировки дублей одной строки ТЗ.

    product_id первичен — точное совпадение товара каталога сильнее текста.
    Без product_id — нормализованное имя (services.text_match.normalize,
    тот же движок, что и весь остальной проект — Правило №6) + единица
    измерения (разные единицы — заведомо разные позиции, не дубль).
    """
    product_id = getattr(item, "product_id", None)
    if product_id:
        return f"pid:{product_id}"
    name_norm = _normalize_name(getattr(item, "item_name", "") or "")
    unit = (getattr(item, "unit", "") or "").strip().lower()
    return f"name:{name_norm}|unit:{unit}"


def _sum_optional(values: list) -> Optional[Decimal]:
    """Σ непустых значений; None, если ни одного заданного значения нет
    (quantity у purchase_items — Numeric без дефолта, NULL встречается)."""
    present = [Decimal(str(v)) for v in values if v is not None]
    if not present:
        return None
    total = Decimal("0")
    for v in present:
        total += v
    return total


def find_duplicate_groups(items: Iterable[Any]) -> list[dict]:
    """Группы строк-дублей (≥2 строк с одинаковым group_key), в порядке
    первого появления в *items*. Используется и предпросмотром (баннер в
    заявке/закупке), и гейтом генерации документов (unresolved_keys).

    Каждая группа: {key, name, unit, items, qty_sum, total_sum, prices_differ,
    feo_category_ids}.
    """
    buckets: dict[str, list] = {}
    order: list[str] = []
    for item in items or []:
        key = group_key(item)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)

    result: list[dict] = []
    for key in order:
        group_items = buckets[key]
        if len(group_items) < 2:
            continue
        qty_sum = _sum_optional([getattr(it, "quantity", None) for it in group_items])
        total_sum = _sum_optional([getattr(it, "total_price", None) for it in group_items])
        prices = {
            str(getattr(it, "unit_price", None)) if getattr(it, "unit_price", None) is not None else None
            for it in group_items
        }
        feo_ids: list = []
        for it in group_items:
            fid = getattr(it, "feo_category_id", None)
            if fid is not None and fid not in feo_ids:
                feo_ids.append(fid)
        result.append({
            "key": key,
            "name": group_items[0].item_name or "",
            "unit": group_items[0].unit or "",
            "items": group_items,
            "qty_sum": qty_sum,
            "total_sum": total_sum,
            "prices_differ": len(prices) > 1,
            "feo_category_ids": feo_ids,
        })
    return result


def _row_from_single(item: Any) -> dict:
    return {
        "item": item,
        "quantity": getattr(item, "quantity", None),
        "unit_price": getattr(item, "unit_price", None),
        "total_price": getattr(item, "total_price", None),
        "price_averaged": False,
        "feo_category_ids": (
            [item.feo_category_id] if getattr(item, "feo_category_id", None) is not None else []
        ),
        "source_items": [item],
    }


def _row_from_group(group: dict) -> dict:
    representative = group["items"][0]
    qty_sum = group["qty_sum"]
    total_sum = group["total_sum"]
    price_averaged = group["prices_differ"]
    if price_averaged and qty_sum:
        unit_price = (total_sum / qty_sum) if total_sum is not None else representative.unit_price
    else:
        unit_price = representative.unit_price
    return {
        "item": representative,
        "quantity": qty_sum,
        "unit_price": unit_price,
        "total_price": total_sum,
        "price_averaged": price_averaged,
        "feo_category_ids": group["feo_category_ids"],
        "source_items": group["items"],
    }


def build_tz_rows(items: Iterable[Any], decisions: Optional[dict] = None) -> dict:
    """Строит строки итогового документа ТЗ из строк закупки/заявки.

    decisions — карта group_key → 'merge'|'keep' (Purchase.tz_duplicate_decisions).
    Группа без решения — строки идут КАК ЕСТЬ (раздельно), молчаливого
    слияния больше нет, но её key попадает в unresolved_keys: вызывающая
    сторона (генерация документа) обязана остановиться 409'м, пока
    пользователь явно не решит — см. contexts.py::_require_tz_duplicates_resolved_for_doc.

    Возвращает {"rows": [...], "duplicate_groups": [...], "unresolved_keys": [...]}.
    Каждая строка rows — dict (item/quantity/unit_price/total_price/
    price_averaged/feo_category_ids/source_items), чтобы builder'ы документов
    не пересчитывали группировку по-своему.
    """
    items = list(items or [])
    decisions = decisions or {}
    dup_groups = find_duplicate_groups(items)
    dup_by_key = {g["key"]: g for g in dup_groups}
    unresolved_keys = [g["key"] for g in dup_groups if decisions.get(g["key"]) not in ("merge", "keep")]

    rows: list[dict] = []
    emitted_merge_keys: set[str] = set()
    for item in items:
        key = group_key(item)
        group = dup_by_key.get(key)
        if group is None or decisions.get(key) != "merge":
            rows.append(_row_from_single(item))
            continue
        if key in emitted_merge_keys:
            continue
        emitted_merge_keys.add(key)
        rows.append(_row_from_group(group))

    return {
        "rows": rows,
        "duplicate_groups": dup_groups,
        "unresolved_keys": unresolved_keys,
    }


def serialize_tz_result(built: dict, decisions: Optional[dict] = None) -> dict:
    """JSON-safe представление build_tz_rows(...) для API (GET/PUT tz-rows) —
    единственный сериализатор и для закупок (routers/purchase_tz.py), и для
    заявок (routers/wish_tz.py) — Правило №6, форма ответа не дублируется."""
    decisions = decisions or {}

    def _item_id(item: Any):
        return getattr(item, "id", None)

    def _row_out(row: dict) -> dict:
        item = row["item"]
        return {
            "item_id": _item_id(item),
            "item_name": item.item_name or "",
            "unit": item.unit or "",
            "quantity": float(row["quantity"]) if row["quantity"] is not None else None,
            "unit_price": float(row["unit_price"]) if row["unit_price"] is not None else None,
            "total_price": float(row["total_price"]) if row["total_price"] is not None else None,
            "price_averaged": row["price_averaged"],
            "feo_category_ids": list(row["feo_category_ids"]),
            "source_item_ids": [_item_id(it) for it in row["source_items"]],
        }

    def _group_out(g: dict) -> dict:
        return {
            "key": g["key"],
            "name": g["name"],
            "unit": g["unit"],
            "item_ids": [_item_id(it) for it in g["items"]],
            "qty_sum": float(g["qty_sum"]) if g["qty_sum"] is not None else None,
            "total_sum": float(g["total_sum"]) if g["total_sum"] is not None else None,
            "prices_differ": g["prices_differ"],
            "feo_category_ids": list(g["feo_category_ids"]),
            "decision": decisions.get(g["key"]),
        }

    return {
        "rows": [_row_out(r) for r in built["rows"]],
        "duplicate_groups": [_group_out(g) for g in built["duplicate_groups"]],
        "unresolved_keys": built["unresolved_keys"],
        "decisions": decisions,
    }
