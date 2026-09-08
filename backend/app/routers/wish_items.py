"""Позиции заявки (WishItem) — точечная правка одной позиции (drag-drop/автосейв).

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-08,
вторая резка wishes.py по образцу первой — commit 89187a0 — и users.py →
commit ca7b02c) БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

Путь "/{wish_id}/items/{item_id}" на 2 сегмента длиннее catch-all "/{wish_id}"
из wishes.router — не конфликтует с ним независимо от порядка регистрации
(тот же принцип, что в wish_transitions.py/wish_convert.py/wish_export.py).

Хелперы ядра (_load_wish/_is_saas) вызываются через `wishes_core.<имя>`, не
`from app.routers.wishes import <имя>` — чтобы monkeypatch на ядре (тесты,
если появятся) видели переопределение и здесь тоже (см. докстринг
wish_transitions.py про этот приём).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.schemas.wishes import WishItemPatch
from app.routers import wishes as wishes_core

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


@router.patch("/{wish_id}/items/{item_id}")
async def patch_wish_item(
    wish_id: int,
    item_id: int,
    body: WishItemPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """D-04: Drag-drop target update. Scoped to wish — cannot move items between wishes.

    Returns 409 if wish уже распределена (converted) — read-only.
    Returns 404 if item does not belong to wish_id.

    Владелец (2026-09-04, заявка №55): гейт раньше блокировал перенос уже на статусе
    'approved', хотя /approve-distribution (app/routers/wish_convert.py) на этом
    статусе распределение ещё РАЗРЕШАЕТ — пользователь видел кнопку «Распределить
    и одобрить», но перетащить ничего не мог (409 «уже одобрена»). Статус, после
    которого распределение зафиксировано и правда нельзя менять — 'converted'
    (создались закупки), поэтому гейт здесь приведён в соответствие с
    approve_distribution: draft/submitted/approved — редактируемо, converted —
    только чтение.
    """
    wish = await wishes_core._load_wish(wish_id, db)
    if not wishes_core._is_saas(current_user) and wish.status not in ("draft", "submitted", "approved"):
        raise HTTPException(status_code=409, detail="Заявка уже распределена — редактирование запрещено")
    # Find item BELONGING TO THIS WISH
    item = next((i for i in wish.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена в данной заявке")
    # body.target_column_key may be None (clear) or a non-empty string (override)
    item.target_column_key = body.target_column_key
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "target_column_key": item.target_column_key}
