"""purchase_summary.py — единый формат «карточки закупки» для UI-переходов
(владелец, план zany-fluttering-mountain.md, 2026-08-13).

Вынесено из app.routers.wishes._wish_purchase_summaries_map («из согласованной
заявки нужно перейти в закупку(и), которые из неё исполняются; если их
несколько — выпадающий список с номером/статусом/суммой»), чтобы ТОТ ЖЕ формат
переиспользовал новый excess_plan_items (виновники превышения плана над вручную
заданной суммой — клик по виновнику должен открыть его закупку так же, как клик
по закупке заявки) — без второго параллельного формата карточки.
"""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase


async def purchase_summaries_by_id(
    db: AsyncSession, purchase_ids: Iterable[Optional[int]]
) -> dict[int, dict]:
    """{purchase_id: {id, purchase_number, registry_number, item_name, status,
    status_label, amount, stopped_at}} — один батч-запрос, без N+1.

    Сумма закупки — тот же приоритет полей, что и в
    app.services.match_candidates._purchase_amount (переиспользуем формулу, не
    дублируем): contract_price → planned_total_price → total_nmck.

    amount/stopped_at отдаются «как есть» (Decimal/datetime) — вызывающий код
    (эндпоинт FastAPI без явного response_model, либо pydantic-схема) сам
    сериализует их в JSON; это тот же приём, что был раньше в
    _wish_purchase_summaries_map.
    """
    ids = list({pid for pid in purchase_ids if pid is not None})
    result: dict[int, dict] = {}
    if not ids:
        return result

    from app.routers.purchase_export import _STATUS_LABELS  # local: avoid router import cycle

    rows = (await db.execute(
        select(
            Purchase.id, Purchase.purchase_number, Purchase.registry_number,
            Purchase.item_name, Purchase.status, Purchase.stopped_at,
            Purchase.contract_price, Purchase.planned_total_price, Purchase.total_nmck,
        ).where(Purchase.id.in_(ids))
    )).all()
    for pid, pnum, regnum, iname, status, stopped_at, contract_price, planned_total, total_nmck in rows:
        amount = contract_price if contract_price is not None else (
            planned_total if planned_total is not None else total_nmck
        )
        result[pid] = {
            "id": pid,
            "purchase_number": pnum,
            "registry_number": regnum,
            "item_name": iname,
            "status": status,
            "status_label": _STATUS_LABELS.get(status, status),
            "amount": amount,
            "stopped_at": stopped_at,
        }
    return result
