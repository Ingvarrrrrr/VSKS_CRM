"""Сервис объединения нескольких закупок в одну (задача владельца 03.11.2026).

Позволяет объединить несколько автоматически созданных закупок (или закупок по заявкам)
в одну целевую с сохранением всех позиций, платежей, документов и фиксацией списка
исходных заявок и номеров закупок.

Права: супер-админ, владелец аккаунта (по умолчанию) либо пользователь с галочкой can_merge_purchases.
"""
from typing import List, Optional
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.payment import Payment
from app.models.purchase_file import PurchaseFile
from app.models.purchase_event import PurchaseEvent
from app.models.user import User
from app.services.purchase_money_writer import recalc_purchase_money
from app.services.purchase_payments import recompute_purchase_payments
from app.services.contracts_linking import ensure_contract_linked, copy_items_to_contract
from app.routers.purchases import delete_purchase_core


def assert_can_merge_purchases(user: User) -> None:
    """Проверка прав: супер-админ, владелец аккаунта или явная галочка can_merge_purchases."""
    if user.role in ("superadmin", "account_owner") or getattr(user, "can_merge_purchases", False):
        return
    raise HTTPException(
        status_code=403,
        detail="У вас нет прав на объединение закупок. Обратитесь к администратору аккаунта.",
    )


async def merge_purchases(
    db: AsyncSession,
    target_purchase_id: int,
    source_purchase_ids: List[int],
    current_user: User,
) -> dict:
    """Объединяет source_purchase_ids в target_purchase_id."""
    assert_can_merge_purchases(current_user)

    clean_source_ids = [pid for pid in source_purchase_ids if pid != target_purchase_id]
    if not clean_source_ids:
        raise HTTPException(status_code=400, detail="Не выбраны закупки для присоединения")

    target_res = await db.execute(
        select(Purchase).options(
            selectinload(Purchase.items),
            selectinload(Purchase.contractor),
        ).where(Purchase.id == target_purchase_id)
    )
    target: Optional[Purchase] = target_res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Целевая закупка не найдена")

    source_res = await db.execute(
        select(Purchase).options(
            selectinload(Purchase.items),
            selectinload(Purchase.contractor),
        ).where(Purchase.id.in_(clean_source_ids))
    )
    sources: List[Purchase] = source_res.scalars().all()
    if len(sources) != len(clean_source_ids):
        found_ids = {s.id for s in sources}
        missing = set(clean_source_ids) - found_ids
        raise HTTPException(status_code=404, detail=f"Не найдены закупки: {list(missing)}")

    for s in sources:
        if s.subsidy_id != target.subsidy_id:
            raise HTTPException(
                status_code=400,
                detail=f"Закупка #{s.id} относится к другой субсидии (#{s.subsidy_id})",
            )

    # Контрагент: если у целевой не задан, берем у источников
    if not target.contractor_id:
        for s in sources:
            if s.contractor_id:
                target.contractor_id = s.contractor_id
                break

    # Сбор номеров исходных закупок и заявок
    source_regs = [s.registry_number or f"#{s.id}" for s in sources]
    all_wish_ids = [p.wish_id for p in [target] + sources if p.wish_id]
    unique_wish_ids = list(dict.fromkeys(all_wish_ids))
    if not target.wish_id and unique_wish_ids:
        target.wish_id = unique_wish_ids[0]

    # 1. Перенос позиций (PurchaseItem)
    items_to_move = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_(clean_source_ids))
    )).scalars().all()
    for item in items_to_move:
        item.purchase_id = target.id

    # 2. Перенос оплат (Payment)
    payments_to_move = (await db.execute(
        select(Payment).where(Payment.purchase_id.in_(clean_source_ids))
    )).scalars().all()
    for pmt in payments_to_move:
        pmt.purchase_id = target.id

    # 3. Перенос файлов (PurchaseFile)
    files_to_move = (await db.execute(
        select(PurchaseFile).where(PurchaseFile.purchase_id.in_(clean_source_ids))
    )).scalars().all()
    for f in files_to_move:
        f.purchase_id = target.id

    # 4. Фиксация в комментарии и аудите
    wishes_note = (
        f"исходные заявки: {', '.join(f'#{w}' for w in unique_wish_ids)}"
        if unique_wish_ids
        else "созданы автоматически без заявок"
    )
    merge_comment = (
        f"Объединено с закупками: {', '.join(source_regs)} ({wishes_note})"
    )
    if target.task_comment:
        target.task_comment = f"{target.task_comment}\n{merge_comment}"
    else:
        target.task_comment = merge_comment

    # Событие в журнале
    db.add(PurchaseEvent(
        purchase_id=target.id,
        user_id=current_user.id,
        event_type="merged",
        comment=merge_comment,
    ))

    # 5. Удаление поглощенных закупок
    for s in sources:
        await delete_purchase_core(s, db)

    await db.flush()

    # 6. Пересчет денег и договора целевой закупки
    await copy_items_to_contract(db, target.id)
    await ensure_contract_linked(target, db)
    await recalc_purchase_money(db, target)
    await recompute_purchase_payments(db, target.id)

    await db.commit()

    return {
        "ok": True,
        "target_purchase_id": target.id,
        "target_registry_number": target.registry_number,
        "merged_count": len(sources),
        "source_registry_numbers": source_regs,
        "wish_ids": unique_wish_ids,
        "message": f"Успешно объединено {len(sources)} закупок в {target.registry_number or target.id}",
    }
