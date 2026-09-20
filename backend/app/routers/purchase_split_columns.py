"""Черновая раскладка позиций закупки по колонкам канбана «Разбить на несколько».

Вынесено в отдельный файл (Правило №5, модульность), а не добавлено в общий
PATCH /{pid}/items/{item_id} (app/routers/purchase_items_edit.py) — тот эндпоинт
несёт заморозку ТЗ (TZ_FROZEN_STATUSES), пересчёт плановых позиций и категорий
ФЭО; split_column_key — чисто организационное поле для черновика канбана,
цеплять его к тяжёлой бизнес-логике редактирования ТЗ не нужно и опасно (правка
раскладки колонок не обязана спотыкаться о заморозку цены/количества).

Путь "/{pid}/items/{item_id}/split-column" на 3 сегмента длиннее catch-all
"/{pid}" ядра purchases.py — не конфликтует с ним независимо от порядка
регистрации (тот же принцип, что purchase_items_edit.py/wish_items.py).

Владелец (2026-09-16): «перекидывал по категориям в канбане разбиения закупки,
случайно вышел из окна — всё слетело». Каждый бросок карточки теперь сохраняется
сюда СРАЗУ (как и wish_items.target_column_key у заявки — см.
app/routers/wish_items.py), а не только в памяти компонента до нажатия
«Разбить». POST /{pid}/split (app/routers/purchase_ops.py) очищает это поле
на исходных позициях после успешного разбиения — черновик одноразовый.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.user import User
from app.auth.jwt import get_current_user, ADMIN_ROLES
from app.routers.purchases import _has_purchase_write_access

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

# Тот же порог, что и у самого разбиения (app/routers/purchase_ops.py::split_purchase) —
# раскладка колонок бессмысленна отдельно от права его провести.
_LOCKED_SPLIT_STATUSES = {"contracted", "delivered", "paid"}


class _SplitColumnBody(BaseModel):
    split_column_key: Optional[str] = None  # None — сброс к product.category


@router.patch("/{pid}/items/{item_id}/split-column")
async def patch_split_column(
    pid: int,
    item_id: int,
    body: _SplitColumnBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки")
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if p.status == "split":
        raise HTTPException(409, "Закупка уже разбита — раскладка зафиксирована")
    if p.status in _LOCKED_SPLIT_STATUSES and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Перераспределять закупку в статусе 'Договор' и далее могут только администраторы")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    key = (body.split_column_key or "").strip() or None
    it.split_column_key = key
    await db.commit()
    return {"id": it.id, "split_column_key": it.split_column_key}


# Под-роутер (Правило №5 — не раздувать ядро этого файла, сессия 2026-09-20,
# задача C): POST .../items/{item_id}/move (перенос позиции между
# «сестринскими» закупками одной заявки/родителя, app/routers/
# purchase_items_move.py). Тот же приём, что plan_to_wish.py →
# feo_planned_items_matching.py — см. докстринг purchase_items_move.py про
# отсутствие у него собственного prefix (иначе include_router задвоил бы
# "/api/purchases").
from app.routers.purchase_items_move import router as _purchase_items_move_router

router.include_router(_purchase_items_move_router)
