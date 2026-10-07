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
from app.services.historical_fact_import import existing_update as existing_update_mod
# ПРАВИЛО №6: подпись статуса — тот же источник, что statuses.py/
# purchase_transitions.py используют для STATUS_CHOICES, не вторая копия.
from app.routers.purchase_transitions import STATUS_LABELS
# ЕДИНСТВЕННЫЙ резолвер «категория ФЭО — ФОТ» (себя или предка) — задача A
# (владелец, 07.10.2026): «ФОТ определяется по категории, а не по названиям».
from app.services.feo_payroll import payroll_category_ids
# ПРАВИЛО №6: формат суммы в ₽ для текста предупреждений строки — тот же
# _fmt_money, что уже используется в commit.py (_format_rub) и шаблонах
# документов, не второй форматтер.
from app.services.documents.formatting import _fmt_money


def _rub(v) -> str:
    formatted = _fmt_money(v)
    return f"{formatted} ₽" if formatted else "0,00 ₽"


def paid_not_delivered_predicate(paid, target_status: Optional[str], is_advance: bool) -> bool:
    """Единственный предикат «оплата есть, а статус строки ниже «Поставлено»/
    «Оплачено»» (owner, 07.10.2026, прод id=74 «ЛНР»: РЕЕ-2026-03421). Один
    источник ПРАВИЛО №6 — используется и для текста предупреждения строки
    (ниже), и для totals.paid_not_delivered (владелец, доп. задача: «при
    импорте об этом должно идти уведомление» — на шаге итогов мастера, не
    только у самой строки). Аванс (is_advance) — оплата до поставки сама по
    себе законна и уже объяснена отдельным предупреждением «аванс», здесь не
    считается."""
    return bool(paid and target_status and target_status not in ("delivered", "paid") and not is_advance)


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

    # Задача A (владелец, 07.10.2026): ФОТ — по категории ФЭО плановой
    # позиции строки (себя или предка, feo_payroll.payroll_category_ids),
    # НЕ по словам в названии/пути. Один набор категорий на весь
    # предпросмотр. planned_item_category — та же карта id→category_id, что
    # уже лежит в каталоге плановых позиций (matching_mod.build_matching_
    # context → ctx['catalog']), повторного похода в БД не делаем.
    payroll_cat_ids = await payroll_category_ids(db, [subsidy_id])
    # ПРАВИЛО №6: один словарь id→каталожная запись — источник и для
    # категории (ФОТ), и для имени/пути/суммы найденной плановой позиции в
    # match (показывается владельцу в колонке «Сопоставление», задание
    # 07.10.2026), второй поход в БД/второй словарь не заводим.
    catalog_by_id: dict[int, dict] = {
        entry["id"]: entry
        for entry in ctx["catalog"] if entry.get("kind") == "planned_item"
    }
    planned_item_category: dict[int, Optional[int]] = {
        pid: entry.get("category_id") for pid, entry in catalog_by_id.items()
    }

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
        if status_info["target_status"] == "paid" and not row["paid"]:
            # Повод: файл ЛНР МАО 07.10.2026 — колонка «Оплата» не
            # распозналась как paid, 35 строк «Оплачено» ушли с суммой 0 ₽ и
            # без единого платежа, молча (columns.py теперь ловит «Оплата»
            # через _is_paid_header, но на случай ручного mapping/override
            # оставляем предупреждение).
            warnings.append(
                'Статус «Оплачено», но сумма оплаты пуста — платёж не будет создан '
                '(проверьте, что колонка оплаты сопоставлена)'
            )

        # Задача (владелец, 07.10.2026, прод id=74 «ЛНР», РЕЕ-2026-03421) —
        # «Оплачено больше, чем поставлено» должно быть видно уже на импорте,
        # не только постфактум на дашборде (см. paid_over_delivered.py —
        # зеркало той же идеи «оплата раньше поставки» на уровне закупки,
        # не вторая формула: здесь просьба предупредить СТРОКУ импорта, там —
        # посчитать уже созданные закупки). Аванс (is_advance) уже объяснён
        # отдельным предупреждением выше — не дублируем.
        if paid_not_delivered_predicate(row["paid"], status_info["target_status"], is_advance):
            status_label = STATUS_LABELS.get(status_info["target_status"], status_info["target_status"])
            warnings.append(
                f'Оплата {_rub(row["paid"])} при статусе «{status_label}» — '
                'оплачено, но не поставлено; проверьте статус'
            )

        plan_amount = row["plan"]["amount"]
        contract_amount_for_row = fact_amount if fact_amount is not None else row["contracted"]
        over_plan_choice = over_plan_decisions.get(str(row["row"]))
        # Жалоба владельца (чек-лист 07.10.2026, п.4): суммы — с разрядами и
        # копейками, словами владельца («выберите решение в колонке
        # «Превышение»», не внутреннее «оставить с пометкой / урезать /
        # пропустить» вперемешку с координатами UI).
        is_over_plan = bool(
            plan_amount is not None and contract_amount_for_row is not None
            and contract_amount_for_row > plan_amount
        )
        if is_over_plan:
            warnings.append(
                f"Договор больше плана ({_rub(contract_amount_for_row)} > {_rub(plan_amount)}) — "
                "выберите решение в колонке «Превышение»"
            )
        # Если превышение уже показано строкой выше — текст нарушения ТЗ
        # (collect_tz_over_plan_violations) про то же самое превышение не
        # дублируется: это тот же сигнал второй раз, да ещё с советом
        # «измените плановую позицию в Плане закупок или уменьшите ТЗ»,
        # который в импорте факта неприменим (решение здесь — колонка
        # «Превышение», не правка ТЗ/плана). Сам факт превышения (is_over_plan)
        # остаётся сигналом независимо от этого дедупа.
        if match["planned_item_id"] in violations_by_fpi and not over_plan_choice and not is_over_plan:
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

        # Задание 07.10.2026 (чек-лист, п.3): для found/already_purchased
        # показать владельцу, С КАКОЙ плановой позицией сопоставлено —
        # имя/путь/сумма из ТОГО ЖЕ catalog_by_id, что уже строит категорию
        # ФОТ выше (ПРАВИЛО №6, второй запрос/словарь не заводим). После
        # override (если пользователь выбрал другую позицию) — имя уже новой.
        if match.get("planned_item_id") is not None:
            _entry = catalog_by_id.get(match["planned_item_id"])
            match = {
                **match,
                "planned_item_name": _entry.get("name") if _entry else None,
                "planned_item_path": _entry.get("path") if _entry else None,
                "planned_item_amount": _entry.get("amount") if _entry else None,
            }

        # Задача A — ФОТ по категории плановой позиции (после override, т.к.
        # override.planned_item_id может сменить, какая категория у строки).
        _cat_id = planned_item_category.get(match.get("planned_item_id"))
        is_payroll = bool(_cat_id) and _cat_id in payroll_cat_ids

        skip = bool(override.get("skip", False))
        existing_purchase: Optional[dict] = None
        if match["state"] == "already_purchased" and "skip" not in override:
            # Задача B (владелец, 07.10.2026): «он должен статусы смотреть» —
            # не пропускать строку молча, а обновить закупку, которой уже
            # принадлежит эта плановая позиция, по статусу/оплате из файла
            # (см. existing_update.py). ctx['bound_purchases'] — тот же запрос,
            # что и already_bound (matching.py), просто с данными о закупке.
            bound = ctx.get("bound_purchases", {}).get(match["planned_item_id"]) or []
            status_ok = status_info["target_status"] is not None and not needs_status
            if len(bound) == 1 and status_ok:
                bp = bound[0]
                existing_purchase = {"id": bp["id"], "registry_number": bp["registry_number"], "status": bp["status"]}
                warnings.append(
                    f'Плановая позиция уже в закупке {bp["registry_number"] or bp["id"]} — она будет '
                    f'обновлена по файлу (статус «{STATUS_LABELS.get(status_info["target_status"], status_info["target_status"])}», '
                    'оплата по отметке)'
                )
            elif len(bound) > 1:
                skip = True
                regs = ", ".join(str(b["registry_number"] or b["id"]) for b in bound)
                warnings.append(f"У плановой позиции уже есть закупки: {regs} — строка пропущена по умолчанию")
            else:
                skip = True
                warnings.append("У плановой позиции уже есть закупка — строка пропущена по умолчанию")
        if match["state"] == "ambiguous" and "skip" not in override:
            skip = True
            warnings.append(
                "Несколько строк файла претендуют на одну плановую позицию — "
                "выберите плановую позицию в колонке «Сопоставление»"
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
            # Строка полностью пропущена — не одновременно «обновит
            # существующую» (иначе она бы вошла и в skipped_count, и в
            # existing_updates — состояния взаимоисключающие).
            existing_purchase = None

        if skip:
            skipped_count += 1
        elif existing_purchase:
            # Задача B: эта строка НЕ создаёт новую закупку (см. grouping.py/
            # commit.py — существующая закупка обновляется отдельно, не через
            # обычную группировку) — в totals.contract_amount/«Договоров на
            # сумму» не попадает, но её «Оплачено» всё равно реальная оплата
            # по субсидии.
            if row["paid"]:
                totals_paid += Decimal(str(row["paid"]))
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
            "existing_purchase": existing_purchase,
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
    purchases_count = 0
    for group in groups:
        group_rows = [
            rows_by_num[rn] for rn in group["rows"]
            if not rows_by_num[rn]["skip"] and not rows_by_num[rn].get("existing_purchase")
        ]
        if group_rows:
            purchases_count += 1
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

    # Задача B: агрегируем строки с существующей закупкой (row['existing_
    # purchase']) по id закупки — несколько строк файла могут указывать на
    # одну и ту же существующую закупку (разные плановые позиции одной
    # РЕЕ-...). build_preview_entries (existing_update.py) считает paid_add/
    # status_to; commit.py применит РОВНО этот же список (ПРАВИЛО №6).
    existing_update_buckets: dict[int, dict] = {}
    for r in out_rows:
        ep = r.get("existing_purchase")
        if not ep or r["skip"]:
            continue
        bucket = existing_update_buckets.setdefault(ep["id"], {
            "registry_number": ep["registry_number"],
            "status_from": ep["status"],
            "rows": [],
            "paid_sum": Decimal(0),
            "target_status": None,
            "is_advance": False,
        })
        bucket["rows"].append(r["row"])
        if r["paid"]:
            bucket["paid_sum"] += Decimal(str(r["paid"]))
        if r.get("is_advance"):
            bucket["is_advance"] = True
        rs = r["status"]
        if rs and (bucket["target_status"] is None or existing_update_mod.rank_of(rs) > existing_update_mod.rank_of(bucket["target_status"])):
            bucket["target_status"] = rs

    existing_updates_list = await existing_update_mod.build_preview_entries(db, existing_update_buckets)

    # Доп. задача (владелец, 07.10.2026): «при импорте об этом должно идти
    # уведомление» — предупреждение у строки уже есть (paid_not_delivered_
    # predicate выше), но на шаге итогов мастера (FactImportStepConfirm.vue)
    # его не видно среди плиток. Тот же предикат, тот же источник подписи
    # статуса (STATUS_LABELS) — не вторая формула (ПРАВИЛО №6). НЕ пропущенные
    # строки (skip=False) — это покрывает и обычные строки, и existing_purchase
    # (та же проверка read.status/.paid/.is_advance на уровне строки файла,
    # existing_purchase не меняет её «итоговый статус ниже delivered»).
    paid_not_delivered_rows: list[dict] = []
    paid_not_delivered_amount = Decimal(0)
    for r in out_rows:
        if r["skip"]:
            continue
        if paid_not_delivered_predicate(r["paid"], r["status"], r["is_advance"]):
            paid_not_delivered_rows.append({
                "row": r["row"],
                "name": r["name"],
                "status_label": STATUS_LABELS.get(r["status"], r["status"]),
                "paid": r["paid"],
            })
            paid_not_delivered_amount += Decimal(str(r["paid"]))

    return {
        "format": detected["format"],
        "sheet": sheet,
        "header_row": detected["header_row"],
        "columns": cols,
        "rows": out_rows,
        "groups": groups,
        "statuses": statuses_mod.STATUS_CHOICES,
        "existing_updates": existing_updates_list,
        "totals": {
            "rows": len(out_rows),
            "purchases": purchases_count,
            "contract_amount": float(totals_contract),
            "paid_amount": float(totals_paid),
            "skipped": skipped_count,
            "existing_updates": len(existing_updates_list),
            "paid_not_delivered": {
                "count": len(paid_not_delivered_rows),
                "amount": float(paid_not_delivered_amount),
                "rows": paid_not_delivered_rows,
            },
        },
        "warnings": top_warnings,
    }
