"""Группировка строк файла в будущие закупки.

Решение владельца: поставщик + «№ Закупки»; без номера, но с поставщиком —
поставщик; без поставщика, но с «№ Закупки» — номер закупки. `decisions.groups`
может явно переопределить разбиение (список {rows: [...]} — любой другой ключ
игнорируется, формируются РОВНО эти группы, остальные строки группируются
по умолчанию).

Правка 12.10.2026 (владелец, план lazy-swimming-hollerith.md, п.4а, «ДНР 3»):
строка БЕЗ поставщика И БЕЗ «№ Закупки» больше не группируется по листовой
категории ФЭО — КАЖДАЯ такая строка становится ОТДЕЛЬНОЙ закупкой (ключ по
номеру строки файла). Было: строки 19 УАЗ (Заказано), 20 Gaz (Поставлено),
21 Haval (Заказано) — все из категории «Ремонт ТС» — слепились в ОДНУ закупку
со статусом «Поставлено» (наивысшая стадия), хотя это три разные машины с
разными статусами и датами. Группировка по поставщику/номеру не меняется.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services.vehicle_org_matching import normalize_org_name
# ПРАВИЛО №6: подписи статуса — тот же STATUS_LABELS, что и preview.py/
# statuses.py используют для STATUS_CHOICES/warnings строки, не вторая копия
# русских слов (задание 07.10.2026, п.5 — «смешаны статусы (delivered,
# ordered)» должно звучать по-русски).
from app.routers.purchase_transitions import STATUS_LABELS
# Группировка по договору (владелец, 16.10.2026, шаг 2) — «ИНН из R, иначе
# контрагент» + «№ Закупки» — valid_inn — ОДНО определение (ПРАВИЛО №6,
# contract_groups.py), не вторая копия регулярки.
from app.services.historical_fact_import.contract_groups import build_source_key, valid_inn


def _supplier_key(supplier: Optional[str]) -> str:
    # Поставщик — организация: та же нормализация, что и contractor_resolve.
    # find_or_create_contractor (ПРАВИЛО №6) — иначе «ООО Ромашка» и
    # «ООО «Ромашка»» молчаливо попали бы в разные группы/закупки.
    return normalize_org_name(supplier)


def default_group_key(row: dict, match: dict) -> tuple:
    # Группировка по договору (владелец, 16.10.2026, шаг 2, лист
    # GoodsService): «группа — одна закупка с договором: ключ (валидный ИНН
    # из «ИНН», иначе нормализованный «Контрагент») + «Номер закупки»».
    # ИНН — настоящий идентификатор контрагента (не текст-заглушка,
    # valid_inn), ПРИОРИТЕТНЕЕ названия поставщика (та же организация может
    # писать имя по-разному, ИНН не ошибается) — иначе, как раньше, по имени
    # поставщика.
    identity_key = valid_inn(row.get("inn"))
    identity_kind = "inn"
    if not identity_key:
        identity_key = _supplier_key(row.get("supplier"))
        identity_kind = "supplier"
    purchase_no = (row.get("purchase_no") or "").strip()
    if identity_key and purchase_no:
        return (f"{identity_kind}_no", identity_key, purchase_no)
    if identity_key:
        return (identity_kind, identity_key)
    if purchase_no:
        # Поставщика/ИНН нет, но «№ Закупки» указан — группа по номеру
        # закупки (несколько строк одной будущей закупки без явного поставщика).
        return ("purchase_no", purchase_no)
    # Правка 12.10.2026 (п.4а): без поставщика И без «№ Закупки» — КАЖДАЯ
    # строка отдельная закупка (ключ по номеру строки файла), а не общий
    # котёл по листовой категории ФЭО — иначе разные машины одной категории
    # («Ремонт ТС») слипаются в одну закупку с общим (наивысшим) статусом.
    return ("row", row.get("row"))


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
        # Задание 07.10.2026 (п.5): статус группы и «смешаны статусы» —
        # только по НЕ пропущенным строкам (active_rows), иначе пропущенная
        # строка с другим статусом молча красила бы весь статус группы.
        # Карточка, где пропущены ВСЕ строки, не имеет «активного» статуса —
        # all_skipped=True, фронт прячет такие карточки (StepGroups.vue).
        active_items = [it for it in items if not it["row"].get("skip", False)]
        all_skipped = not active_items
        status_items = active_items or items  # нет активных — показываем что есть, но помечаем all_skipped
        statuses_present = {
            it["status_info"]["target_status"] for it in status_items if it["status_info"]["target_status"]
        }
        warnings = []
        if len(statuses_present) > 1:
            labels = sorted(STATUS_LABELS.get(s, s) for s in statuses_present if s)
            warnings.append(
                f"В группе смешаны статусы ({', '.join(labels)}) — "
                "итоговый статус закупки возьмётся по наивысшей стадии."
            )
        # Наивысшая стадия: paid > contracted > work_in_progress.
        _rank = {"work_in_progress": 1, "contracted": 2, "ordered": 3, "delivered": 4, "paid": 5}
        target_status = None
        for it in status_items:
            ts = it["status_info"]["target_status"]
            if ts and (target_status is None or _rank.get(ts, 0) > _rank.get(target_status, 0)):
                target_status = ts

        # 🔵 правка 3 (план breezy-mixing-lovelace.md): сумма группы для
        # сравнения с существующими закупками (Часть А, «похожие закупки») не
        # должна включать пропущенные строки (needs_status/already_purchased/
        # payroll и т.п. — они не станут частью будущей закупки). `.get`,
        # т.к. у вызывающих тестов (test_fact_import_grouping.py) строки без
        # ключа "skip" — там он всегда отсутствует, что равнозначно False.
        # 🟢 Задача B: строки, обновляющие СУЩЕСТВУЮЩУЮ закупку (row[
        # 'existing_purchase']), тоже не часть будущей новой закупки —
        # исключаем их из суммы группы тем же приёмом, не заводя второй фильтр.
        effective_items = [it for it in items if not it["row"].get("existing_purchase")]
        non_skipped = (
            [it for it in effective_items if not it["row"].get("skip", False)]
            or effective_items or items
        )
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
            # Замер скорости (владелец 16.10.2026) — existing_link.
            # find_existing_matches_for_group ищет контрагента группы точно
            # по ИНН, когда он есть (приоритет ИНН — тот же, что уже решает
            # ключ группы выше, default_group_key, ПРАВИЛО №6: не второй
            # источник приоритета ИНН-vs-имя). Поле добавлено к уже
            # существующим — ничего из прежних ключей group{} не убрано.
            "inn": first_row.get("inn"),
            "purchase_no": first_row.get("purchase_no"),
            # Задача 4 владельца (16.10.2026) — ключ повторной заливки (см.
            # docstring build_source_key в contract_groups.py); None, когда
            # нет настоящего ИНН/№ закупки — тогда группа просто не умеет
            # опознать себя при повторном прогоне (как и раньше).
            "source_key": build_source_key(
                valid_inn(first_row.get("inn")), first_row.get("purchase_no"),
                supplier_fallback=_supplier_key(first_row.get("supplier")) or None,
            ),
            "category_path": " › ".join(first_row.get("path") or []) or None,
            "status": target_status,
            "rows": [it["row"]["row"] for it in items],
            "active_rows": [it["row"]["row"] for it in active_items],
            "all_skipped": all_skipped,
            "contract_amount": float(contract_amount),
            "paid_amount": float(paid_amount),
            "warnings": warnings,
        })
    return groups
