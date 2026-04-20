"""Purchase members / assignment / consent / kanban router — extracted from purchases.py (Phase 16-05).

Handles:
  PATCH /api/purchases/{pid}/assign           — assign/unassign executor (with hierarchy check + consent flow)
  POST  /api/purchases/{pid}/consent          — accept consent to be executor
  PATCH /api/purchases/{pid}/kanban-status    — quick status change from kanban board
  PATCH /api/purchases/{pid}/substatus        — set substatus for work_in_progress purchases
  PATCH /api/purchases/{pid}/comment          — update kanban task comment
  Helper: _create_assignment_chat_room        — create/find ChatRoom for assignment context
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models.purchase import Purchase
from app.models.user import User
from app.models.user_hierarchy import UserHierarchy
from app.models.chat_room import ChatRoom, ChatParticipant
from app.models.chat_message import ChatMessage
from app.auth.jwt import get_current_user, MANAGER_ROLES
from app.chat_manager import manager as chat_manager
from app.routers.purchases import _purchase_to_full, STATUS_ORDER

router = APIRouter(prefix="/api/purchases", tags=["purchase-members"])

# Mirror VALID_SUBSTATUSES from purchases.py (same constant, used locally)
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform")


# ---------------------------------------------------------------------------
# Chat-room helper (G-05: self-contained)
# ---------------------------------------------------------------------------

async def _create_assignment_chat_room(
    db: AsyncSession,
    assignor_id: int,
    assignee_id: int,
    org_id: int,
    room_name: str,
) -> int:
    """Create or find a ChatRoom for this assignment context. Returns room_id."""
    existing_q = select(ChatRoom.id).where(ChatRoom.name == room_name, ChatRoom.org_id == org_id)
    existing = await db.execute(existing_q)
    room_id = existing.scalar_one_or_none()
    if room_id:
        return room_id

    room = ChatRoom(
        name=room_name,
        is_group=False,
        org_id=org_id,
        created_by=assignor_id,
    )
    db.add(room)
    await db.flush()

    db.add(ChatParticipant(room_id=room.id, user_id=assignor_id))
    db.add(ChatParticipant(room_id=room.id, user_id=assignee_id))
    await db.flush()

    sys_msg = ChatMessage(
        room_id=room.id,
        sender_id=assignor_id,
        content=f"[СИСТЕМА] Чат создан для обсуждения: {room_name}",
    )
    db.add(sys_msg)
    await db.flush()

    return room.id


# ---------------------------------------------------------------------------
# PATCH /{pid}/assign
# ---------------------------------------------------------------------------

@router.patch("/{pid}/assign")
async def assign_purchase(
    pid: int,
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign a purchase to a user (or unassign if user_id is None).

    Hierarchy validation (D-14/D-15):
    - Subordinate: direct assignment + ChatRoom + notification
    - Non-subordinate: consent flow (consent_pending=True) + ChatRoom + request notification
    """
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # Unassign case
    if user_id is None:
        p.assigned_user_id = None
        await db.commit()
        return {"ok": True, "assigned_user_id": None}

    # Validate user exists
    user_check = await db.execute(select(User).where(User.id == user_id))
    target_user = user_check.scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "Пользователь не найден")

    # Skip hierarchy check if assigning to self
    if user_id == current_user.id:
        p.assigned_user_id = user_id
        await db.commit()
        return {"ok": True, "assigned_user_id": user_id}

    # Hierarchy check: is target a direct subordinate?
    sub_res = await db.execute(
        select(UserHierarchy.subordinate_id).where(
            UserHierarchy.manager_id == current_user.id
        )
    )
    subordinate_ids = [r[0] for r in sub_res.all()]
    is_subordinate = user_id in subordinate_ids

    purchase_title = p.subject or p.item_name or f"Закупка #{p.id}"
    org_id = current_user.org_id or 1  # fallback

    if not is_subordinate:
        # D-15: Non-subordinate requires consent flow
        from app.models.purchase_event import PurchaseMember
        existing_member = await db.execute(
            select(PurchaseMember).where(
                PurchaseMember.purchase_id == p.id,
                PurchaseMember.user_id == user_id,
            )
        )
        member = existing_member.scalar_one_or_none()
        if not member:
            member = PurchaseMember(
                purchase_id=p.id,
                user_id=user_id,
                role="executor",
                added_by_id=current_user.id,
                consent_pending=True,
            )
            db.add(member)
        else:
            member.consent_pending = True

        # D-18: Create chat room for this purchase assignment context
        room_id = await _create_assignment_chat_room(
            db, current_user.id, user_id, org_id,
            f"Закупка: {purchase_title}",
        )

        await db.commit()

        # D-16: Send consent request notification via WS, include room_id
        try:
            await chat_manager.send_to_user(user_id, {
                "type": "system_notification",
                "subtype": "consent_request",
                "purchase_id": p.id,
                "room_id": room_id,
                "message": f"[СИСТЕМА] Запрос на назначение исполнителем закупки: «{purchase_title}»",
                "link": f"/orders/{p.id}/edit",
            })
        except Exception:
            pass  # WS notification is best-effort

        return {"ok": True, "consent_pending": True, "assigned_user_id": None, "room_id": room_id}
    else:
        # Subordinate: assign directly (D-14)
        p.assigned_user_id = user_id

        # D-18: Create chat room for this purchase assignment context
        room_id = await _create_assignment_chat_room(
            db, current_user.id, user_id, org_id,
            f"Закупка: {purchase_title}",
        )

        await db.commit()

        # D-16: Send assignment notification via WS, include room_id
        try:
            await chat_manager.send_to_user(user_id, {
                "type": "system_notification",
                "subtype": "executor_assigned",
                "purchase_id": p.id,
                "room_id": room_id,
                "message": f"[СИСТЕМА] Вы назначены исполнителем закупки: «{purchase_title}»",
                "link": f"/orders/{p.id}/edit",
            })
        except Exception:
            pass  # WS notification is best-effort

        return {"ok": True, "assigned_user_id": user_id, "room_id": room_id}


# ---------------------------------------------------------------------------
# POST /{pid}/consent
# ---------------------------------------------------------------------------

@router.post("/{pid}/consent")
async def accept_purchase_consent(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept consent to be executor on a purchase (D-15)."""
    from app.models.purchase_event import PurchaseMember
    member_res = await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == current_user.id,
            PurchaseMember.consent_pending == True,  # noqa: E712
        )
    )
    pm = member_res.scalar_one_or_none()
    if not pm:
        raise HTTPException(404, "Нет ожидающего запроса согласия")
    pm.consent_pending = False
    # Set as executor on the purchase
    purchase = await db.get(Purchase, pid)
    if purchase:
        purchase.assigned_user_id = current_user.id
    await db.commit()
    return {"status": "accepted", "purchase_id": pid}


# ---------------------------------------------------------------------------
# PATCH /{pid}/kanban-status
# ---------------------------------------------------------------------------

@router.patch("/{pid}/kanban-status")
async def kanban_status_change(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Quick status change from kanban board (same rules as transition)."""
    # Map common aliases
    STATUS_ALIASES = {"in_progress": "work_in_progress", "planned": "plan_schedule"}
    target_status = STATUS_ALIASES.get(target_status, target_status)
    if target_status not in STATUS_ORDER:
        STATUS_LABELS_RU = dict(zip(STATUS_ORDER, ["Желания", "План-график", "Подтверждено", "Ведётся работа", "Договор", "Заказано", "Поставлено", "Оплачено"]))
        allowed = ", ".join(f"{k} ({v})" for k, v in STATUS_LABELS_RU.items())
        raise HTTPException(422, f"Недопустимый статус: «{target_status}». Допустимые: {allowed}")
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # Only assigned user, managers or admins can change status
    is_assigned = p.assigned_user_id == current_user.id
    is_admin_or_manager = current_user.role in MANAGER_ROLES
    if not is_assigned and not is_admin_or_manager:
        raise HTTPException(403, "Недостаточно прав")

    old_status = p.status
    p.status = target_status
    await db.commit()

    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="status_changed",
            data={"from": old_status, "to": target_status, "via": "kanban"},
        ))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "status": target_status}


# ---------------------------------------------------------------------------
# PATCH /{pid}/substatus
# ---------------------------------------------------------------------------

@router.patch("/{pid}/substatus")
async def update_substatus(
    pid: int,
    substatus: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set substatus for work_in_progress purchases."""
    if substatus and substatus not in VALID_SUBSTATUSES:
        raise HTTPException(422, f"Недопустимый подстатус: {substatus}. Допустимые: {', '.join(VALID_SUBSTATUSES)}")
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    is_assigned = p.assigned_user_id == current_user.id
    is_admin_or_manager = current_user.role in MANAGER_ROLES
    if not is_assigned and not is_admin_or_manager:
        raise HTTPException(403, "Недостаточно прав")

    # Auto-set status to work_in_progress if setting a substatus
    if substatus and p.status != "work_in_progress":
        p.status = "work_in_progress"
    p.substatus = substatus
    await db.commit()

    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="substatus_changed",
            data={"substatus": substatus},
        ))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "substatus": substatus, "status": p.status}


# ---------------------------------------------------------------------------
# PATCH /{pid}/comment
# ---------------------------------------------------------------------------

@router.patch("/{pid}/comment")
async def update_task_comment(
    pid: int,
    comment: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update task comment for kanban card."""
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    p.task_comment = comment
    await db.commit()
    return {"ok": True}
