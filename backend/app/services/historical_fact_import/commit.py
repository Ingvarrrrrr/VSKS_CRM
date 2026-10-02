"""POST /commit — одна транзакция на прогон: предпросмотр ещё раз (тот же
код, та же группировка — ПРАВИЛО №6, не второй расчёт) → запись.

Для каждой группы (не skip-строки): insert_purchase_with_items с позициями
по ФАКТУ → если есть договор (contracted/paid): copy_items_to_contract с
теми же числами + временный № + ensure_contract_linked → recalc_purchase_
money → платёж «по отметке» + recompute_purchase_payments → PurchaseEvent.
Без register_*_approvals и notify_* (владелец: «уведомления и согласования
не запускаются»).

db.commit() делает ВЫЗЫВАЮЩИЙ (роутер) — здесь только flush, чтобы вся
операция была одной транзакцией.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.historical_fact_import.preview import build_preview

_RANK = {"work_in_progress": 1, "contracted": 2, "ordered": 3, "delivered": 4, "paid": 5}


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    return Decimal(str(v))


async def commit_import(
    db: AsyncSession,
    subsidy_id: int,
    current_user,
    content: bytes,
    filename: str,
    sheet: Optional[str],
    mapping: Optional[dict],
    decisions: Optional[dict],
) -> dict:
    decisions = decisions or {}
    preview = await build_preview(db, subsidy_id, content, filename, sheet, mapping, decisions)

    from app.models.fact_import_run import FactImportRun
    from app.models.subsidy import Subsidy
    from app.models.contractor import Contractor
    from app.models.payment import Payment
    from app.models.purchase_event import PurchaseEvent
    from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
    from app.services.contractor_resolve import find_or_create_contractor
    from app.services.purchase_create_core import insert_purchase_with_items
    from app.services.contract_items_materialize import copy_items_to_contract
    from app.services.temp_contract_number import generate_temp_contract_number
    from app.routers.contracts import ensure_contract_linked
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.purchase_payments import recompute_purchase_payments

    subsidy = await db.get(Subsidy, subsidy_id)

    run = FactImportRun(
        subsidy_id=subsidy_id,
        user_id=getattr(current_user, "id", None),
        filename=filename,
        sheet=preview.get("sheet") or sheet,
        format=preview["format"],
        mapping=mapping or {},
        decisions=decisions,
        status="committed",
    )
    db.add(run)
    await db.flush()

    contract_confirmed = {int(r) for r in (decisions.get("contract_confirmed_rows") or [])}
    over_plan_decisions = decisions.get("over_plan") or {}
    supplier_overrides = decisions.get("supplier_overrides") or {}
    row_overrides = decisions.get("row_overrides") or {}

    rows_by_num = {r["row"]: r for r in preview["rows"]}
    created_refs: dict = {"contractor_ids": [], "contract_ids": [], "planned_item_ids": [], "purchase_ids": []}
    purchases_created = 0
    payments_created = 0
    contractors_created = 0

    # Дерево ФЭО относит факт/заказано/законтрактовано к категории через
    # COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id) —
    # найдено соседней сессией на прогоне 02.10 (обе колонки оставались
    # NULL, импортированные закупки «невидимы» в дереве). feo_planned_item_id
    # сам по себе дерево НЕ читает для разнесения по узлам — обязана быть
    # ещё и feo_category_id на каждой позиции, см. FeoPlannedItem.feo_category_id.
    _fpi_cat_cache: dict[int, Optional[int]] = {}

    async def _category_for_planned_item(fpi_id: Optional[int]) -> Optional[int]:
        if not fpi_id:
            return None
        if fpi_id not in _fpi_cat_cache:
            from app.models.feo_planned_item import FeoPlannedItem
            fpi = await db.get(FeoPlannedItem, fpi_id)
            _fpi_cat_cache[fpi_id] = fpi.feo_category_id if fpi else None
        return _fpi_cat_cache[fpi_id]

    for group in preview["groups"]:
        group_rows = [rows_by_num[rn] for rn in group["rows"] if not rows_by_num[rn]["skip"]]
        if not group_rows:
            continue

        items_data: list = []
        total_amount = Decimal(0)
        paid_total = Decimal(0)
        target_status: Optional[str] = None
        group_category_ids: set = set()

        for row in group_rows:
            row_key = str(row["row"])
            override = row_overrides.get(row_key) or {}
            planned_item_id = override.get("planned_item_id") or row["match"].get("planned_item_id")

            # Позиция без совпадения — явно велели создать новую плановую (иначе
            # пропускается ещё на этапе предпросмотра/группировки, т.к. ничего
            # привязать не удастся, а план импорт не трогает молча).
            if not planned_item_id and override.get("create_planned_item") and row["match"]["state"] == "not_found":
                from app.services.plan_autoassign import create_auto_planned_item
                eff_cat_id = override.get("feo_category_id")
                if eff_cat_id:
                    fake_item = SimpleNamespace(
                        item_name=row["name"],
                        quantity=_dec(row["fact"]["qty"]) or _dec(row["plan"]["qty"]),
                        unit=row.get("unit"),
                        total_price=_dec(row["plan"]["amount"]) or _dec(row["fact"]["amount"]),
                        item_type=row.get("item_type"),
                    )
                    new_fpi = await create_auto_planned_item(db, fake_item, eff_cat_id, note="импортом факта (02.10.2026)")
                    planned_item_id = new_fpi.id
                    created_refs["planned_item_ids"].append(new_fpi.id)

            row_status = row["status"]
            amount = row["fact"]["amount"] if row["fact"]["amount"] is not None else row["contracted"]

            if row["needs_contract_decision"]:
                if row["row"] in contract_confirmed:
                    row_status = "contracted"
                    amount = row["contracted"]
                else:
                    row_status = "work_in_progress"
                    amount = 0

            over_choice = over_plan_decisions.get(row_key)
            plan_amount = row["plan"]["amount"]
            if over_choice == "skip":
                continue
            if over_choice == "trim" and plan_amount is not None and amount is not None and amount > plan_amount:
                amount = plan_amount

            amount_dec = _dec(amount) or Decimal(0)
            qty_dec = _dec(row["fact"]["qty"]) or _dec(row["plan"]["qty"])
            price_dec = None
            if qty_dec and qty_dec != 0 and amount_dec:
                price_dec = (amount_dec / qty_dec)
            else:
                price_dec = _dec(row["fact"]["price"]) or _dec(row["plan"]["price"])

            item_category_id = await _category_for_planned_item(planned_item_id)
            if item_category_id:
                group_category_ids.add(item_category_id)

            items_data.append(PurchaseItemCreate(
                item_name=row["name"],
                item_type=row.get("item_type"),
                quantity=qty_dec,
                unit=row.get("unit"),
                unit_price=price_dec,
                total_price=amount_dec,
                feo_planned_item_id=planned_item_id,
                feo_category_id=item_category_id,
                match_confirmed=True,
            ))
            total_amount += amount_dec
            if row["paid"]:
                paid_total += _dec(row["paid"])

            if row_status and (target_status is None or _RANK.get(row_status, 0) > _RANK.get(target_status, 0)):
                target_status = row_status

        if not items_data or not target_status:
            continue

        # Поставщик группы — explicit override (contractor_id) либо найден/
        # создан по названию (ПРАВИЛО №6: find_or_create_contractor, точная
        # нормализация, без fuzzy — lesson feedback_dedup_exact_only).
        contractor_id = supplier_overrides.get(group["key"])
        if contractor_id is None and group.get("supplier"):
            max_id_before = (await db.execute(select(func.coalesce(func.max(Contractor.id), 0)))).scalar()
            contractor_id = await find_or_create_contractor(
                db, group["supplier"], None, org_id=getattr(subsidy, "org_id", None),
            )
            if contractor_id and contractor_id > max_id_before:
                contractors_created += 1
                created_refs["contractor_ids"].append(contractor_id)

        # Purchase.feo_category_id — заполняем только когда ВСЕ позиции группы
        # из одной категории (как create_purchase для обычной, не per-item,
        # закупки); при нескольких категориях оставляем None — per-item
        # feo_category_id на каждой строке достаточно (тот же приём, что и
        # feo_per_item=True путь, см. "_cid = it.feo_category_id or p.feo_category_id").
        group_category_id = next(iter(group_category_ids)) if len(group_category_ids) == 1 else None

        data = PurchaseCreate(
            subsidy_id=subsidy_id,
            status=target_status,
            contractor_id=contractor_id,
            purchase_method="single",
            feo_category_id=group_category_id,
            items=items_data,
        )
        p, _created_items = await insert_purchase_with_items(
            db, data, current_user, items_data=items_data, total_nmck=total_amount,
        )
        p.import_run_id = run.id

        # «План не трогаем, но у ИСТОРИЧЕСКОЙ закупки своего плана не было —
        # план=факт на момент постановки» (см. docstring recalc_purchase_money:
        # для уже «замороженного» статуса planned_total_price не пишется сам —
        # заполняем снимок здесь, один раз, вручную, не заводя второй писатель).
        if p.planned_total_price is None:
            p.planned_total_price = total_amount
            p.total_nmck = total_amount
            p.nmck = total_amount

        if target_status in ("contracted", "ordered", "delivered", "paid"):
            p.contract_number = await generate_temp_contract_number(p, db)
            p.contract_number_is_temporary = True
            await copy_items_to_contract(db, p.id)
            await ensure_contract_linked(p, db)
            await recalc_purchase_money(db, p)
        else:
            # «В работе» — договора ещё нет (владелец: «не отмечена → закупка
            # в работе БЕЗ суммы договора»). recalc_purchase_money внутри
            # insert_purchase_with_items уже заполнил contract_price снимком
            # позиций (фолбэк «заморожен, договорных позиций нет, поле
            # пусто») — это верно для contracted/paid, но не для work_in_
            # progress без договора: откатываем.
            p.contract_price = None

        if paid_total > 0:
            pay = Payment(
                purchase_id=p.id,
                amount=paid_total,
                payment_source="manual",
                confirmed_by_statement=False,
                import_run_id=run.id,
            )
            db.add(pay)
            payments_created += 1
            await db.flush()
            await recompute_purchase_payments(db, p.id)

        db.add(PurchaseEvent(
            purchase_id=p.id,
            user_id=getattr(current_user, "id", None),
            event_type="fact_import",
            data={"import_run_id": run.id, "rows": group["rows"]},
        ))

        purchases_created += 1
        created_refs["purchase_ids"].append(p.id)

    run.purchases_created = purchases_created
    run.payments_created = payments_created
    run.contractors_created = contractors_created
    run.created_refs = created_refs

    from app.services.historical_fact_import.report import build_report
    run.report = await build_report(db, created_refs["purchase_ids"])

    await db.flush()

    return {
        "run_id": run.id,
        "purchases_created": purchases_created,
        "payments_created": payments_created,
        "contractors_created": contractors_created,
        "report_url": f"/api/subsidies/{subsidy_id}/fact-import/runs/{run.id}",
    }
