"""Группировка строк файла в будущие закупки.

Решение владельца: поставщик + «№ Закупки»; без номера — поставщик; без
поставщика — по листовой категории ФЭО. `decisions.groups` может явно
переопределить разбиение (список {rows: [...]} — любой другой ключ
игнорируется, формируются РОВНО эти группы, остальные строки группируются
по умолчанию).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services.vehicle_org_matching import normalize_org_name


def _supplier_key(supplier: Optional[str]) -> str:
    # Поставщик — организация: та же нормализация, что и contractor_resolve.
    # find_or_create_contractor (ПРАВИЛО №6) — иначе «ООО Ромашка» и
    # «ООО «Ромашка»» молчаливо попали бы в разные группы/закупки.
    return normalize_org_name(supplier)


def default_group_key(row: dict, match: dict) -> tuple:
    supplier_key = _supplier_key(row.get("supplier"))
    purchase_no = (row.get("purchase_no") or "").strip()
    if supplier_key and purchase_no:
        return ("supplier_no", supplier_key, purchase_no)
    if supplier_key:
        return ("supplier", supplier_key)
    # Без поставщика — по листовой категории ФЭО: category_id кандидата,
    # если позиция сматчилась, иначе путь строки файла (путь+имя) как ключ.
    cat_id = None
    for c in match.get("candidates", []):
        if c["id"] == match.get("planned_item_id"):
            cat_id = c.get("category_id")
            break
    if cat_id is not None:
        return ("category", cat_id)
    return ("path", tuple(row.get("path") or []), row.get("name"))


def build_groups(rows_with_match: list, decisions: Optional[dict] = None) -> list:
    """rows_with_match: [{row_data, match, status_info, ...}, ...] (уже
    обогащённые preview.py). Возвращает groups[] контракта: {key, supplier,
    purchase_no, category_path, status, rows, contract_amount, paid_amount,
    warnings}."""
    decisions = decisions or {}
    explicit_groups = decisions.get("groups") or []
    explicit_row_numbers: set = set()
    forced: list[list[dict]] = []
    for g in explicit_groups:
        wanted = set(g.get("rows") or [])
        matched_items = [r for r in rows_with_match if r["row"]["row"] in wanted]
        if matched_items:
            forced.append(matched_items)
            explicit_row_numbers |= wanted

    remaining = [r for r in rows_with_match if r["row"]["row"] not in explicit_row_numbers]

    buckets: dict = {}
    order: list = []
    for item in remaining:
        key = default_group_key(item["row"], item["match"])
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)

    group_lists = forced + [buckets[k] for k in order]

    groups = []
    for idx, items in enumerate(group_lists):
        first_row = items[0]["row"]
        statuses_present = {it["status_info"]["target_status"] for it in items if it["status_info"]["target_status"]}
        warnings = []
        if len(statuses_present) > 1:
            warnings.append(
                f"В группе смешаны статусы ({', '.join(sorted(s for s in statuses_present if s))}) — "
                "итоговый статус закупки возьмётся по наивысшей стадии."
            )
        # Наивысшая стадия: paid > contracted > work_in_progress.
        _rank = {"work_in_progress": 1, "contracted": 2, "ordered": 3, "delivered": 4, "paid": 5}
        target_status = None
        for it in items:
            ts = it["status_info"]["target_status"]
            if ts and (target_status is None or _rank.get(ts, 0) > _rank.get(target_status, 0)):
                target_status = ts

        # 🔵 правка 3 (план breezy-mixing-lovelace.md): сумма группы для
        # сравнения с существующими закупками (Часть А, «похожие закупки») не
        # должна включать пропущенные строки (needs_status/already_purchased/
        # payroll и т.п. — они не станут частью будущей закупки). `.get`,
        # т.к. у вызывающих тестов (test_fact_import_grouping.py) строки без
        # ключа "skip" — там он всегда отсутствует, что равнозначно False.
        non_skipped = [it for it in items if not it["row"].get("skip", False)] or items
        contract_amount = sum(
            (Decimal(str(it["row"]["fact"]["amount"])) if it["row"]["fact"]["amount"] is not None
             else (Decimal(str(it["row"]["contracted"])) if it["row"]["contracted"] is not None else Decimal(0)))
            for it in non_skipped
        )
        paid_amount = sum(
            (Decimal(str(it["row"]["paid"])) if it["row"]["paid"] is not None else Decimal(0))
            for it in non_skipped
        )

        groups.append({
            "key": "|".join(str(x) for x in (default_group_key(first_row, items[0]["match"]))),
            "supplier": first_row.get("supplier"),
            "purchase_no": first_row.get("purchase_no"),
            "category_path": " › ".join(first_row.get("path") or []) or None,
            "status": target_status,
            "rows": [it["row"]["row"] for it in items],
            "contract_amount": float(contract_amount),
            "paid_amount": float(paid_amount),
            "warnings": warnings,
        })
    return groups
