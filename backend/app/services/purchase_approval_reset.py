"""Сброс шагов согласования закупки — единственный источник (Правило №6).

Вынесено из routers/purchase_approvals.py::reset_approvals (админский сброс) —
та же операция (удалить все PurchaseApproval, обнулить approval_status, лог
PurchaseEvent, отменить связанные Task «Согласование») нужна и
routers/purchase_return.py::return_purchase_to_wish (возврат закупки в
заявку сбрасывает её согласование целиком, не только у заявки). Раньше это
жило только внутри одного роутер-эндпоинта — второй копии не заводим,
reset_approvals теперь тоже зовёт эту функцию.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_event import PurchaseEvent
from app.models.task import Task, TaskStatus


async def reset_purchase_approvals(
    purchase: Purchase,
    db: AsyncSession,
    current_user,
    *,
    event_type: str = "approval_reset",
    event_data: dict | None = None,
) -> None:
    """Удаляет все PurchaseApproval закупки, обнуляет approval_status,
    пишет PurchaseEvent и отменяет связанные Task «Согласование» (best-effort).

    Commit НЕ делает — это на вызывающем (тот же приём, что
    wish_distribution._reset_approvals/_withdraw_wish_from_plan).
    """
    result = await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == purchase.id)
    )
    for a in result.scalars().all():
        await db.delete(a)

    purchase.approval_status = None

    db.add(PurchaseEvent(
        purchase_id=purchase.id,
        user_id=getattr(current_user, "id", None),
        event_type=event_type,
        data=event_data or {},
    ))

    try:
        tasks_res = await db.execute(
            select(Task).where(
                Task.purchase_id == purchase.id,
                Task.category == "Согласование",
                Task.status == TaskStatus.todo,
            )
        )
        for t in tasks_res.scalars().all():
            t.status = TaskStatus.cancelled
    except Exception:
        pass  # best-effort
