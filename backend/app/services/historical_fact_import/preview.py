"""POST /preview — собирает контракт-ответ БЕЗ записи в БД.

Склеивает columns.py → rows.py → statuses.py → matching.py → grouping.py и
добавляет сигналы для UI мастера (needs_contract_decision, is_payroll, skip,
warnings) — ровно то, что commit.py потом читает из decisions, чтобы решить,
что писать.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import rows as rows_mod
from app.services.historical_fact_import import statuses as statuses_mod
from app.services.historical_fact_import import matching as matching_mod
from app.services.historical_fact_import import grouping as grouping_mod


async def build_preview(
    db: AsyncSession,
    subsidy_id: int,
    content: bytes,
    filename: str,
    sheet: Optional[str],
    mapping: Optional[dict],
    decisions: Optional[dict],
) -> dict:
    decisions = decisions or {}
    row_overrides = decisions.get("row_overrides") or {}
    over_plan_decisions = decisions.get("over_plan") or {}
    include_payroll = bool(decisions.get("include_payroll", False))

    detected = columns_mod.detect_format_and_header(content, filename, sheet)
    cols = columns_mod.build_columns(detected)
    cols = columns_mod.apply_mapping_override(cols, mapping)
    parsed_rows = rows_mod.parse_rows(detected, cols, detected["header_row"])

    ctx = await matching_mod.build_matching_context(db, subsidy_id)

    # Превышение плана (owner: «договор больше плана» — предупреждение с
    # выбором). Переиспользуем tz_excess_approval.collect_tz_over_plan_violations
    # (ПРАВИЛО №6) — read-only здесь, ничего не пишет.
    from app.services.tz_excess_approval import collect_tz_over_plan_violations

    tz_units = []
    row_to_match: dict = {}
    for row in parsed_rows:
        match = matching_mod.match_row(ctx, row)
        row_to_match[row["row"]] = match
        if match["planned_item_id"]:
            amount = row["fact"]["amount"] if row["fact"]["amount"] is not None else row["contracted"]
            tz_units.append(SimpleNamespace(
                over_plan=False,
                feo_planned_item_id=match["planned_item_id"],
                feo_category_id=None,
                quantity=row["fact"]["qty"],
                unit_price=row["fact"]["price"],
                total_price=amount,
                item_name=row["name"],
            ))
    violations = await collect_tz_over_plan_violations(db, tz_units, fallback_category_id=None)
    violations_by_fpi: dict = {}
    for v in violations:
        if v.get("feo_planned_item_id"):
            violations_by_fpi.setdefault(v["feo_planned_item_id"], []).append(v)

    out_rows = []
    totals_contract = Decimal(0)
    totals_paid = Decimal(0)
    skipped_count = 0
    top_warnings: list[str] = []

    for row in parsed_rows:
        match = row_to_match[row["row"]]
        override = row_overrides.get(str(row["row"])) or {}

        status_info = statuses_mod.resolve_status(row["status_raw"])
        needs_status = False
        if override.get("status"):
            # Явный выбор пользователя (decisions.row_overrides[row].status,
            # код из statuses_mod.STATUS_CHOICES) — побеждает автоопределение,
            # «приведением» не считается (пользователь уже выбрал код).
            status_info = statuses_mod.resolve_status_by_code(override["status"])
        elif not status_info["recognized"] and row["status_raw"]:
            # 🔵 Неизвестное значение — строка ждёт выбора статуса из
            # выпадающего списка (6 кодов), не создаётся молча.
            needs_status = True

        # Задача 2 (владелец, 05.10.2026) — «Аванс (да/нет)»: строка со
        # статусом «Оплачено» и Аванс=да означает оплату ДО поставки — закупка
        # обязана встать в статус «Заказано» (ordered), не «Оплачено»
        # (committed_amounts.py — «Заключён договор» уже включает её, но
        # «Поставлено»/статус «Оплачено» нет, пока поставка не отмечена
        # отдельно). commit.py прочитает is_advance ниже и выставит
        # Purchase.is_prepayment=True на созданной закупке.
        is_advance = bool(row.get("advance")) and status_info["target_status"] == "paid"
        if is_advance:
            status_info = {**status_info, "target_status": "ordered"}

        is_payroll = statuses_mod.is_payroll_path(row["path"], row["name"])

        warnings: list[str] = []
        fact_amount = row["fact"]["amount"]
        if fact_amount and not row["status_raw"]:
            warnings.append("Есть факт, но статус не указан")
        if status_info["target_status"] is None and row["status_raw"] and status_info["recognized"] and fact_amount:
            warnings.append('Статус «План закупок», но в строке уже есть факт')
        if needs_status:
            warnings.append(f'Нераспознанный статус: «{row["status_raw"]}» — выберите статус из списка')
        if status_info.get("correction"):
            warnings.append(status_info["correction"])
        if status_info["target_status"] == "contracted" and status_info["needs_payment"] and not row["paid"]:
            warnings.append('Статус «Заключён договор» (из «Оплачено частично»), но «Оплачено» не заполнено')
        if is_advance:
            warnings.append("аванс: оплачено до поставки")

        plan_amount = row["plan"]["amount"]
        contract_amount_for_row = fact_amount if fact_amount is not None else row["contracted"]
        over_plan_choice = over_plan_decisions.get(str(row["row"]))
        if plan_amount is not None and contract_amount_for_row is not None and contract_amount_for_row > plan_amount:
            warnings.append(
                f"Договор больше плана ({contract_amount_for_row} > {plan_amount}) — "
                "выберите: оставить с пометкой / урезать / пропустить"
            )
        if match["planned_item_id"] in violations_by_fpi and not over_plan_choice:
            for v in violations_by_fpi[match["planned_item_id"]]:
                warnings.append(v["message"])

        # «Законтрактовано» без факта при статусе «В работе» (правка 2, план) —
        # решается ПОЧЕЛОВЕЧНО через decisions.contract_confirmed_rows в commit.
        needs_contract_decision = bool(
            status_info["target_status"] == "work_in_progress"
            and not fact_amount
            and row["contracted"]
        )

        if override.get("planned_item_id"):
            # Пользователь уже разрешил привязку вручную (в т.ч. ambiguous —
            # РЕЕ-2026-08630: несколько строк файла на одно имя плановой
            # позиции) — применяем ДО решения про skip, иначе состояние
            # «до override» (already_purchased/ambiguous) продолжало бы
            # пропускать строку даже после явного выбора.
            match = {**match, "planned_item_id": override["planned_item_id"], "state": "found"}

        skip = bool(override.get("skip", False))
        if match["state"] == "already_purchased" and "skip" not in override:
            skip = True
            warnings.append("У плановой позиции уже есть закупка — строка пропущена по умолчанию")
        if match["state"] == "ambiguous" and "skip" not in override:
            skip = True
            warnings.append(
                "Несколько строк файла претендуют на одну плановую позицию — "
                "выберите привязку вручную (row_overrides.planned_item_id)"
            )
        if status_info["target_status"] is None:
            skip = True
        if needs_status:
            # 🔵 Статус не распознан и пользователь ещё не выбрал его явно —
            # строка не создаётся молча (владелец, правка 3).
            skip = True
        if is_payroll and not include_payroll:
            skip = True

        if skip:
            skipped_count += 1
        else:
            amt = contract_amount_for_row or Decimal(0)
            if over_plan_choice == "trim" and plan_amount is not None:
                amt = min(amt, plan_amount)
            totals_contract += Decimal(str(amt))
            if row["paid"]:
                totals_paid += Decimal(str(row["paid"]))

        out_rows.append({
            "row": row["row"],
            "name": row["name"],
            "path": row["path"],
            "status": status_info["target_status"],
            "status_raw": row["status_raw"],
            "plan": {
                "qty": float(row["plan"]["qty"]) if row["plan"]["qty"] is not None else None,
                "price": float(row["plan"]["price"]) if row["plan"]["price"] is not None else None,
                "amount": float(row["plan"]["amount"]) if row["plan"]["amount"] is not None else None,
            },
            "fact": {
                "qty": float(row["fact"]["qty"]) if row["fact"]["qty"] is not None else None,
                "price": float(row["fact"]["price"]) if row["fact"]["price"] is not None else None,
                "amount": float(row["fact"]["amount"]) if row["fact"]["amount"] is not None else None,
            },
            "paid": float(row["paid"]) if row["paid"] is not None else None,
            "advance": bool(row.get("advance")),
            "is_advance": is_advance,
            "contracted": float(row["contracted"]) if row["contracted"] is not None else None,
            "supplier": row["supplier"],
            "purchase_no": row["purchase_no"],
            "unit": row["unit"],
            "item_type": row["item_type"],
            "match": match,
            "needs_contract_decision": needs_contract_decision,
            "needs_status": needs_status,
            "is_payroll": is_payroll,
            "skip": skip,
            "warnings": warnings,
            "_status_info": status_info,
        })
        if warnings:
            top_warnings.extend(f"Строка {row['row']}: {w}" for w in warnings)

    rows_with_match = [{"row": r, "match": r["match"], "status_info": r["_status_info"]} for r in out_rows]
    groups = grouping_mod.build_groups(rows_with_match, decisions)

    for r in out_rows:
        r.pop("_status_info", None)

    # 🔵 правка 3 (план breezy-mixing-lovelace.md, Часть А «Похожие закупки в
    # импорте факта»): для каждой будущей закупки (группы) — поиск уже
    # существующей закупки того же поставщика/суммы (historical_fact_import.
    # existing_link, ПРАВИЛО №6 — переиспользует purchase_similar +
    # contractor_resolve.find_contractors_by_name, не второй поиск
    # контрагента). Группа без ни одной незапропущенной строки (всё skip) —
    # искать нечего, она всё равно не станет закупкой (commit.py её
    # пропускает).
    from app.services.historical_fact_import import existing_link as existing_link_mod
    from app.services.tz_excess_approval import collect_tz_over_plan_violations as _collect_violations
    from types import SimpleNamespace as _SimpleNamespace

    rows_by_num = {r["row"]: r for r in out_rows}
    existing_decisions = decisions.get("existing_match") or {}
    for group in groups:
        group_rows = [rows_by_num[rn] for rn in group["rows"] if not rows_by_num[rn]["skip"]]
        if not group_rows:
            group["existing_matches"] = []
            group["needs_existing_decision"] = False
            continue

        group_amount = Decimal(str(group["contract_amount"])) if group["contract_amount"] else None
        matches = await existing_link_mod.find_existing_matches_for_group(
            db, subsidy_id, group.get("supplier"), group_amount,
        )
        if matches:
            file_row_planned_item_id = group_rows[0]["match"].get("planned_item_id")
            excess_units: list = []
            for m in matches:
                m["items"] = await existing_link_mod.build_existing_match_items(
                    db, m["id"], ctx, file_row_planned_item_id,
                )
                for it in m["items"]:
                    if it.get("suggested") and it["suggested"].get("planned_item_id"):
                        excess_units.append(_SimpleNamespace(
                            over_plan=False,
                            feo_planned_item_id=it["suggested"]["planned_item_id"],
                            feo_category_id=None,
                            quantity=it.get("qty"),
                            unit_price=it.get("price"),
                            total_price=it.get("total"),
                            item_name=it.get("name"),
                        ))
            if excess_units:
                excess_violations = await _collect_violations(db, excess_units, fallback_category_id=None)
                excess_by_fpi: dict = {}
                for v in excess_violations:
                    if v.get("feo_planned_item_id"):
                        excess_by_fpi.setdefault(v["feo_planned_item_id"], []).append(v["message"])
                for m in matches:
                    for it in m["items"]:
                        sug = it.get("suggested")
                        if sug and sug.get("planned_item_id") in excess_by_fpi:
                            it["warnings"] = excess_by_fpi[sug["planned_item_id"]]

        group["existing_matches"] = matches
        decided = group["key"] in existing_decisions
        has_same_amount = any(m["kind"] == "same_amount" for m in matches)
        has_same_supplier_only = bool(matches) and not has_same_amount
        # «Скорее всего та же» (same_amount) — предвыбрано, коммит может идти
        # без явного решения. «Возможно» (same_supplier, сумма другая) —
        # решение обязательно (владелец: «импорт не идёт, пока по каждому
        # „возможно“ не выбрано»).
        group["needs_existing_decision"] = has_same_supplier_only and not decided

    return {
        "format": detected["format"],
        "sheet": sheet,
        "header_row": detected["header_row"],
        "columns": cols,
        "rows": out_rows,
        "groups": groups,
        "statuses": statuses_mod.STATUS_CHOICES,
        "totals": {
            "rows": len(out_rows),
            "purchases": len(groups),
            "contract_amount": float(totals_contract),
            "paid_amount": float(totals_paid),
            "skipped": skipped_count,
        },
        "warnings": top_warnings,
    }
