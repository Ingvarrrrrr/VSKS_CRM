"""POST /runs/{id}/rollback — откат прогона «Импорта факта».

Блокеры (dry_run=True просто их перечисляет, не трогая БД): закупку правили
после импорта (есть PurchaseEvent кроме самого 'fact_import'), есть платёж
подтверждённый выпиской, есть загруженные файлы, есть заявки (Wish),
ссылающиеся на закупку. Любой блокер на ЛЮБОЙ закупке прогона — весь откат
отклоняется (частичный откат мог бы оставить несогласованный остаток).

Удаление (dry_run=False, без блокеров): платежи прогона → delete_purchase_
core (ПРАВИЛО №6 — тот же, что и ручное удаление закупки,
app.routers.purchases.delete_purchase_core) → осиротевшие объекты из
created_refs (контрагент/плановая позиция, заведённые ТОЛЬКО этим прогоном
и не используемые больше ничем).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession


async def _collect_blockers(db: AsyncSession, run) -> dict:
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseEvent
    from app.models.payment import Payment
    from app.models.purchase_file import PurchaseFile
    from app.models.wish import Wish

    purchase_ids = (run.created_refs or {}).get("purchase_ids") or []
    existing_match_backups = (run.created_refs or {}).get("existing_match_item_backups") or []
    # Задача B («Оплачено, но уже в закупке») — закупки, которым этот прогон
    # поднял статус/добавил оплату БЕЗ создания новой закупки.
    existing_update_backups = (run.created_refs or {}).get("existing_update_backups") or []
    existing_update_purchase_ids = [b["purchase_id"] for b in existing_update_backups]
    blockers: list[str] = []
    will_delete = {
        "purchases": 0, "payments": 0, "contractors": 0, "contracts": 0, "planned_items": 0,
        # 🟢🔵 «та же закупка» (Часть А) — позиции СУЩЕСТВУЮЩЕЙ закупки,
        # которым откат вернёт прежнюю (до импорта) привязку к плану.
        "existing_match_items_restored": len(existing_match_backups),
        "existing_updates_restored": len(existing_update_backups),
    }
    if not purchase_ids and not existing_match_backups and not existing_update_backups:
        return {"can_rollback": False, "blockers": ["В этом прогоне нет созданных закупок"], "will_delete": will_delete}

    purchases = (await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))).scalars().all()
    will_delete["purchases"] = len(purchases)

    other_events = (await db.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id.in_(purchase_ids),
            PurchaseEvent.event_type != "fact_import",
        )
    )).scalars().all()
    touched_ids = sorted({e.purchase_id for e in other_events})
    if touched_ids:
        blockers.append(f"Закупки правили после импорта: {touched_ids}")

    confirmed_payments = (await db.execute(
        select(Payment).where(
            Payment.purchase_id.in_(purchase_ids),
            Payment.confirmed_by_statement == True,  # noqa: E712
        )
    )).scalars().all()
    if confirmed_payments:
        blockers.append(
            f"Есть платежи, подтверждённые выпиской: {[pay.purchase_id for pay in confirmed_payments]}"
        )

    files = (await db.execute(select(PurchaseFile).where(PurchaseFile.purchase_id.in_(purchase_ids)))).scalars().all()
    if files:
        blockers.append(f"Загружены файлы по закупкам: {sorted({f.purchase_id for f in files})}")

    wishes = (await db.execute(select(Wish).where(Wish.purchase_id.in_(purchase_ids)))).scalars().all()
    if wishes:
        blockers.append(f"Есть заявки, связанные с закупками: {sorted({w.purchase_id for w in wishes})}")

    all_payments = (await db.execute(select(Payment).where(Payment.purchase_id.in_(purchase_ids)))).scalars().all()
    will_delete["payments"] = len(all_payments)

    # Задача B — блокеры по аналогии с покупками, которые ЭТОТ прогон создал
    # (выше): закупку правили после импорта (любое событие кроме fact_
    # import_existing_update) или есть платёж, подтверждённый выпиской.
    if existing_update_purchase_ids:
        eu_other_events = (await db.execute(
            select(PurchaseEvent).where(
                PurchaseEvent.purchase_id.in_(existing_update_purchase_ids),
                PurchaseEvent.event_type != "fact_import_existing_update",
            )
        )).scalars().all()
        eu_touched = sorted({e.purchase_id for e in eu_other_events})
        if eu_touched:
            blockers.append(f"Закупки (обновление существующих) правили после импорта: {eu_touched}")

        eu_confirmed_payments = (await db.execute(
            select(Payment).where(
                Payment.purchase_id.in_(existing_update_purchase_ids),
                Payment.confirmed_by_statement == True,  # noqa: E712
            )
        )).scalars().all()
        if eu_confirmed_payments:
            blockers.append(
                "Есть платежи, подтверждённые выпиской (обновление существующих закупок): "
                f"{[pay.purchase_id for pay in eu_confirmed_payments]}"
            )

    created_refs = run.created_refs or {}
    will_delete["contractors"] = len(created_refs.get("contractor_ids") or [])
    # created_refs["contract_ids"] не заполняется commit.py (контракты создаёт
    # ensure_contract_linked неявно, find-or-create) — считаем по факту, как и
    # execute_rollback ниже, а не по неполному списку созданных ссылок.
    will_delete["contracts"] = len({p.contract_id for p in purchases if p.contract_id})
    will_delete["planned_items"] = len(created_refs.get("planned_item_ids") or [])

    return {"can_rollback": not blockers, "blockers": blockers, "will_delete": will_delete}


async def preview_rollback(db: AsyncSession, run) -> dict:
    return await _collect_blockers(db, run)


async def execute_rollback(db: AsyncSession, run) -> dict:
    from datetime import datetime, timezone
    from app.models.purchase import Purchase
    from app.models.payment import Payment
    from app.models.contractor import Contractor
    from app.models.contract import Contract
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchases import delete_purchase_core

    info = await _collect_blockers(db, run)
    if not info["can_rollback"]:
        return {"can_rollback": False, "blockers": info["blockers"], "will_delete": info["will_delete"]}

    purchase_ids = (run.created_refs or {}).get("purchase_ids") or []

    deleted_payments = (await db.execute(
        select(Payment).where(Payment.import_run_id == run.id)
    )).scalars().all()
    for pay in deleted_payments:
        await db.delete(pay)
    await db.flush()

    purchases = (await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))).scalars().all()
    contract_ids_to_check = {p.contract_id for p in purchases if p.contract_id}
    for p in purchases:
        await delete_purchase_core(p, db)

    created_refs = run.created_refs or {}

    # 🟢🔵 «та же закупка» (Часть А, план breezy-mixing-lovelace.md) —
    # восстановить позиции СУЩЕСТВУЮЩЕЙ (не созданной этим прогоном, поэтому
    # delete_purchase_core её не трогает) закупки как было ДО привязки.
    # Защита: восстанавливаем ТОЛЬКО если позиция до сих пор равна тому, что
    # поставил этот прогон (set_feo_*) — если её успели поменять ещё раз
    # после импорта (вручную или другим прогоном), откат не затирает чужую
    # правку молча, просто оставляет эту позицию как есть.
    restored_purchase_ids: set = set()
    for backup in created_refs.get("existing_match_item_backups") or []:
        pi = await db.get(PurchaseItem, backup["purchase_item_id"])
        if not pi:
            continue
        if (
            pi.feo_planned_item_id == backup.get("set_feo_planned_item_id")
            and pi.feo_category_id == backup.get("set_feo_category_id")
        ):
            pi.feo_planned_item_id = backup.get("prev_feo_planned_item_id")
            pi.feo_category_id = backup.get("prev_feo_category_id")
            restored_purchase_ids.add(pi.purchase_id)
    if restored_purchase_ids:
        await db.flush()
        from app.services.purchase_money_writer import recalc_purchase_money
        for pid in restored_purchase_ids:
            existing_purchase = await db.get(Purchase, pid)
            if existing_purchase:
                await recalc_purchase_money(db, existing_purchase)

    # Задача B («Оплачено, но уже в закупке») — вернуть статус/поля закупки,
    # которую прогон обновил БЕЗ создания новой (платёж с import_run_id уже
    # удалён выше — тем же общим запросом, что и для обычного пути). Если
    # закупка раньше не имела договора (backup['contract_id'] is None), а
    # теперь имеет — ставим её contract_id на проверку вместе с контрактами
    # созданных закупок (contract_ids_to_check ниже), чтобы осиротевший
    # договор, заведённый этим прогоном, удалился тем же циклом, не вторым.
    restored_eu_purchase_ids: set = set()
    # Закупка не имела договора ДО этого прогона (contract_number пуст в
    # backup) → все её ContractItem (если появились) заведены ИМ, удаляем
    # их на откате (владелец: «удалить договор/договорные позиции, если их
    # создал этот прогон»). Была реальная/временная нумерация ДО прогона —
    # ContractItem могли существовать и до импорта, трогать их не будем.
    eu_contract_items_purchase_ids: set = set()
    for backup in created_refs.get("existing_update_backups") or []:
        eu_p = await db.get(Purchase, backup["purchase_id"])
        if not eu_p:
            continue
        if eu_p.contract_id and not backup.get("contract_id"):
            contract_ids_to_check.add(eu_p.contract_id)
        if not backup.get("contract_number"):
            eu_contract_items_purchase_ids.add(eu_p.id)
        eu_p.status = backup["status"]
        eu_p.contract_number = backup["contract_number"]
        eu_p.contract_number_is_temporary = backup["contract_number_is_temporary"]
        eu_p.is_prepayment = backup["is_prepayment"]
        eu_p.contract_price = (
            Decimal(backup["contract_price"]) if backup.get("contract_price") is not None else None
        )
        eu_p.contract_id = backup.get("contract_id")
        restored_eu_purchase_ids.add(eu_p.id)
    if eu_contract_items_purchase_ids:
        from app.models.contract_item import ContractItem
        eu_cis = (await db.execute(
            select(ContractItem).where(ContractItem.purchase_id.in_(eu_contract_items_purchase_ids))
        )).scalars().all()
        for ci in eu_cis:
            await db.delete(ci)
    if restored_eu_purchase_ids:
        await db.flush()
        from app.services.purchase_money_writer import recalc_purchase_money
        from app.services.purchase_payments import recompute_purchase_payments
        for pid in restored_eu_purchase_ids:
            eu_pp = await db.get(Purchase, pid)
            if eu_pp:
                await recalc_purchase_money(db, eu_pp)
                await recompute_purchase_payments(db, pid)

    for contractor_id in created_refs.get("contractor_ids") or []:
        still_used = (await db.execute(
            select(PurchaseItem.id).where(PurchaseItem.contractor_id == contractor_id).limit(1)
        )).scalar_one_or_none()
        still_used_contract = (await db.execute(
            select(Contract.id).where(Contract.contractor_id == contractor_id).limit(1)
        )).scalar_one_or_none()
        still_used_purchase = (await db.execute(
            select(Purchase.id).where(Purchase.contractor_id == contractor_id).limit(1)
        )).scalar_one_or_none()
        if not still_used and not still_used_contract and not still_used_purchase:
            contractor = await db.get(Contractor, contractor_id)
            if contractor:
                await db.delete(contractor)

    for contract_id in contract_ids_to_check:
        still_linked = (await db.execute(
            select(Purchase.id).where(Purchase.contract_id == contract_id).limit(1)
        )).scalar_one_or_none()
        if not still_linked:
            contract = await db.get(Contract, contract_id)
            if contract:
                await db.delete(contract)

    for fpi_id in created_refs.get("planned_item_ids") or []:
        still_used = (await db.execute(
            select(PurchaseItem.id).where(PurchaseItem.feo_planned_item_id == fpi_id).limit(1)
        )).scalar_one_or_none()
        if not still_used:
            fpi = await db.get(FeoPlannedItem, fpi_id)
            if fpi:
                await db.delete(fpi)

    run.status = "rolled_back"
    run.rolled_back_at = datetime.now(timezone.utc)
    await db.flush()

    return {"can_rollback": True, "blockers": [], "will_delete": info["will_delete"], "rolled_back": True}
