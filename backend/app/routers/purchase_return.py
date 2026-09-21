"""POST /api/purchases/{id}/return-to-wish, GET .../return-to-wish/preview.

Под-роутер purchases.py (Правило №5), подключается `router.include_router
(purchase_return_router)` БЕЗ своего prefix — routes.py не трогается.

Третий вариант работы с дублями строк ТЗ (владелец, 21.09,
corrections-21-09.md W3): «ошибка — вернуть на доработку». Закупка уходит
обратно во «Заявки», согласование закупки сбрасывается (переиспользует
app.services.purchase_approval_reset — тот же механизм, что и админский
POST /purchases/{id}/approvals/reset), заявка-источник помечается 'rejected'
с комментарием — та же семантика, что и обычное отклонение заявки
(app/routers/wish_transitions.py::reject_wish), не второй способ отклонения.

Права — как у POST /purchases/{id}/transition (purchase_transitions.py):
manager+ или permission action 'purchase.status_change'.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, MANAGER_ROLES
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.user import User
from app.models.wish import Wish
from app.services.purchase_approval_reset import reset_purchase_approvals
from app.services.purchase_return_to_wish import compute_return_to_wish_preview

router = APIRouter(tags=["purchase-return-to-wish"])


class ReturnToWishIn(BaseModel):
    comment: str = Field(..., min_length=1, description="Причина возврата — уйдёт в заявку как причина отказа")


async def _require_status_change_permission(current_user: User, db: AsyncSession) -> None:
    """Тот же гейт, что и у POST /purchases/{id}/transition (не-SaaS-владелец
    ветка): manager+ роли ИЛИ permission action 'purchase.status_change'."""
    if current_user.role in MANAGER_ROLES:
        return
    from app.auth.permissions import get_effective_actions, _active_org
    actions = await get_effective_actions(current_user, db, _active_org(current_user))
    if 'purchase.status_change' not in actions:
        raise HTTPException(403, "Нужно разрешение «Изменение статуса закупки»")


async def _load_purchase(pid: int, db: AsyncSession) -> Purchase:
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    return p


@router.get("/{pid}/return-to-wish/preview")
async def preview_return_to_wish(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await _load_purchase(pid, db)
    return compute_return_to_wish_preview(p)


@router.post("/{pid}/return-to-wish")
async def return_purchase_to_wish(
    pid: int,
    body: ReturnToWishIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_status_change_permission(current_user, db)

    p = await _load_purchase(pid, db)
    preview = compute_return_to_wish_preview(p)
    if not preview["allowed"]:
        raise HTTPException(409, preview["reason"])

    wish = await db.get(Wish, p.wish_id)
    if not wish:
        raise HTTPException(409, "Заявка-источник закупки не найдена")

    old_status = p.status
    p.status = "wishes"
    p.approval_status = None

    # Сброс согласования ЗАКУПКИ — тот же механизм, что и админский
    # POST /purchases/{id}/approvals/reset (Правило №6).
    await reset_purchase_approvals(
        p, db, current_user,
        event_type="returned_to_wish",
        event_data={"wish_id": wish.id, "comment": body.comment},
    )

    # Аудит перехода статуса — тот же формат события, что и в
    # purchase_transitions.py::transition_status ("status_changed", from/to).
    db.add(PurchaseEvent(
        purchase_id=p.id,
        user_id=current_user.id,
        event_type="status_changed",
        data={"from": old_status, "to": "wishes", "reason": body.comment},
    ))

    wish.status = "rejected"
    wish.rejection_reason = body.comment
    wish.rejected_by = current_user.id
    wish.rejected_at = datetime.now(timezone.utc)

    # Заявка «на доработке» целиком — сбрасываем и её собственную цепочку
    # согласующих (тот же приём, что reject_wish, чтобы после исправления
    # согласование стартовало заново, а не с чьим-то устаревшим "approved").
    from app.routers import wishes as wishes_core
    await wishes_core._reset_approvals(wish.id, db)

    await db.commit()

    creator = await db.get(User, wish.created_by) if wish.created_by else None
    if creator and creator.id != current_user.id:
        try:
            from app.notifications import notify_wish_rejected
            decided_name = current_user.full_name or current_user.username
            await notify_wish_rejected(wish, creator, decided_name, body.comment)
        except Exception:
            pass

    return {
        "ok": True,
        "purchase_id": p.id,
        "purchase_status": p.status,
        "wish_id": wish.id,
        "wish_status": wish.status,
    }
