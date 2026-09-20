"""Перенос ОДНОЙ позиции между «сестринскими» закупками одной заявки/родителя —
задача C (владелец, лист 2 №2, 2026-09-20).

Контекст: задача A (app/services/wish_multi_sync.py) синхронизирует состав
каждой закупки заявки САМОСТОЯТЕЛЬНО — совпавшая позиция обновляется НА
МЕСТЕ, никогда не переезжая между закупками сама по себе (см. докстринг
wish_multi_sync.py, п.2). Если позицию нужно переложить в ДРУГУЮ закупку той
же заявки (или того же рамочного/разбитого родителя — те же «сёстры», что
видны в канбане PurchaseSplitKanban.vue) — это отдельное явное действие
пользователя, вот оно.

POST /api/purchases/{purchase_id}/items/{item_id}/move — подключён
под-роутером в конце app/routers/purchase_split_columns.py
(`router.include_router(...)`), тот же приём, что plan_to_wish.py →
feo_planned_items_matching.py: ЭТОТ router БЕЗ собственного prefix — путь
складывается из префикса родителя ("/api/purchases") + полного пути
декоратора ниже.

Права — как у split-column (`app.routers.purchases._has_purchase_write_access`,
тот же принцип: доступ к КОНКРЕТНОЙ закупке гейтится списком/видимостью выше
по стеку, точечные мутации открыты любому аутентифицированному).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract_item import ContractItem
from app.models.user import User
from app.auth.jwt import get_current_user
from app.routers.purchases import _has_purchase_write_access

router = APIRouter(tags=["purchases"])

# Тот же набор статусов, что блокирует правку ТЗ позиции (заморозка «план ≠
# факт», см. app.routers.purchases.TZ_FROZEN_STATUSES) — плюс 'split' (сама
# закупка уже разбита на дочерние, её позиции больше не редактируются, тот же
# принцип, что у PATCH split-column).
_MOVE_LOCKED_STATUSES = {"work_in_progress", "contracted", "ordered", "delivered", "paid", "split"}


class _MoveItemBody(BaseModel):
    target_purchase_id: int


def _purchase_brief(p: Purchase, items_count: int) -> dict:
    return {
        "id": p.id,
        "purchase_number": p.purchase_number,
        "registry_number": p.registry_number,
        "planned_total_price": float(p.planned_total_price or 0),
        "total_nmck": float(p.total_nmck or 0),
        "items_count": items_count,
    }


@router.post("/{purchase_id}/items/{item_id}/move")
async def move_purchase_item(
    purchase_id: int,
    item_id: int,
    body: _MoveItemBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки")

    target_purchase_id = body.target_purchase_id
    if target_purchase_id == purchase_id:
        raise HTTPException(409, "Позиция уже в этой закупке — переносить некуда")

    source = await db.get(Purchase, purchase_id)
    if not source:
        raise HTTPException(404, f"Закупка №{purchase_id} не найдена")
    target = await db.get(Purchase, target_purchase_id)
    if not target:
        raise HTTPException(404, f"Закупка №{target_purchase_id} не найдена")

    item = await db.get(PurchaseItem, item_id)
    if not item or item.purchase_id != purchase_id:
        raise HTTPException(404, f"Позиция №{item_id} не найдена в закупке №{purchase_id}")

    # «Сёстры» — одна заявка ИЛИ один родитель (parent_purchase_id), оба не null.
    same_wish = source.wish_id is not None and source.wish_id == target.wish_id
    same_parent = (
        source.parent_purchase_id is not None
        and source.parent_purchase_id == target.parent_purchase_id
    )
    if not same_wish and not same_parent:
        raise HTTPException(
            409,
            f"Закупки №{source.purchase_number or source.id} и №{target.purchase_number or target.id} "
            "не связаны одной заявкой или одним родителем разбивки — перенос позиции между ними запрещён",
        )

    from app.services.dictionaries import STATUS_LABELS as _STATUS_LABELS

    for p in (source, target):
        if p.status in _MOVE_LOCKED_STATUSES:
            label = _STATUS_LABELS.get(p.status, p.status)
            raise HTTPException(
                409,
                f"Закупка №{p.purchase_number or p.id} уже на стадии «{label}» — перенос позиций запрещён",
            )

    has_contract_item = await db.scalar(
        select(ContractItem.id).where(ContractItem.source_item_id == item.id).limit(1)
    )
    if has_contract_item:
        raise HTTPException(
            409,
            f"Позиция «{item.item_name}» уже привязана к строке договора — перенос между закупками запрещён, "
            "правьте её в текущей закупке",
        )

    item.purchase_id = target.id
    # Черновая раскладка канбана «Разбить на несколько» относится к ИСХОДНОЙ
    # закупке — при переносе в другую закупку теряет смысл (см. app.routers.
    # purchase_split_columns.py про то же поле).
    item.split_column_key = None
    await db.flush()

    from app.services.purchase_money_writer import recalc_purchase_money
    await recalc_purchase_money(db, source)
    await recalc_purchase_money(db, target)
    await db.flush()

    source_items_count = (await db.execute(
        select(PurchaseItem.id).where(PurchaseItem.purchase_id == source.id)
    )).scalars().all()
    target_items_count = (await db.execute(
        select(PurchaseItem.id).where(PurchaseItem.purchase_id == target.id)
    )).scalars().all()

    await db.commit()

    return {
        "item_id": item.id,
        "source": _purchase_brief(source, len(source_items_count)),
        "target": _purchase_brief(target, len(target_items_count)),
    }
