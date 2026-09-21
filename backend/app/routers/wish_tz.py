"""GET /api/wishes/{id}/tz-rows — предпросмотр дублей строк ТЗ заявки.

Под-роутер wishes.py (Правило №5), подключается `router.include_router
(wish_tz_router)` БЕЗ своего prefix — routes.py не трогается.

В отличие от routers/purchase_tz.py (закупка), у заявки нет собственного
хранилища решений — конвертация заявки в закупку заводит purchase_items
заново, и решения принимаются уже на закупке (PUT /purchases/{id}/tz-duplicates).
Здесь только rows (без решений — как есть, дубли не схлопнуты) и
duplicate_groups — фронт показывает баннер «есть повторяющиеся позиции» ДО
согласования/конвертации.

Права — как у чтения самой заявки (GET /{wish_id}), Правило №6: тот же
ensure_wish_read_access, что и там.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.tz_items import build_tz_rows, serialize_tz_result
from app.services.wish_access import ensure_wish_read_access

router = APIRouter(tags=["wish-tz"])


@router.get("/{wish_id}/tz-rows")
async def get_wish_tz_rows(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Wish).options(selectinload(Wish.items)).where(Wish.id == wish_id)
    )
    wish = result.scalar_one_or_none()
    if not wish:
        raise HTTPException(404, "Заявка не найдена")
    await ensure_wish_read_access(wish, current_user, db)

    # Заявка не хранит decisions — build_tz_rows без них ничего не сливает,
    # rows приходят «как есть»; duplicate_groups/unresolved_keys нужны только
    # для баннера-предупреждения на фронте.
    built = build_tz_rows(wish.items or [], None)
    out = serialize_tz_result(built, {})
    out.pop("decisions", None)
    return out
