"""
Chat REST API + WebSocket endpoint.
REST endpoints are registered under /api/chat prefix.
WS endpoint is registered at /api/ws/chat (separate ws_router without prefix).
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.chat_manager import manager
from app.config import settings
from app.database import get_db
from app.models.chat_message import ChatMessage, MessageRead
from app.models.chat_room import ChatParticipant, ChatRoom
from app.models.user import User

logger = logging.getLogger(__name__)

# ────────────────────────────── Constants ──────────────────────────────────

CHAT_UPLOAD_DIR = "/app/uploads/chat"

ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/jpg",
    "image/png",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# ────────────────────────────── Routers ──────────────────────────────────

router = APIRouter(prefix="/api/chat", tags=["chat"])
ws_router = APIRouter(tags=["chat-ws"])

# ────────────────────────────── Pydantic Schemas ──────────────────────────

class RoomOut(BaseModel):
    id: int
    name: Optional[str] = None
    is_group: bool
    org_id: int
    created_at: datetime
    last_message: Optional[dict] = None
    unread_count: int = 0
    participants: List[dict] = []

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: int
    room_id: int
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    content: Optional[str] = None
    file_name: Optional[str] = None
    file_mime: Optional[str] = None
    file_size: Optional[int] = None
    has_file: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ────────────────────────────── Helpers ────────────────────────────────────

async def _get_room_unread(room_id: int, user_id: int, db: AsyncSession) -> int:
    """Count unread messages in a room for a user (not sent by that user)."""
    q = (
        select(func.count(ChatMessage.id))
        .outerjoin(
            MessageRead,
            and_(
                MessageRead.room_id == room_id,
                MessageRead.user_id == user_id,
            ),
        )
        .where(
            ChatMessage.room_id == room_id,
            ChatMessage.sender_id != user_id,
            or_(
                MessageRead.last_read_message_id.is_(None),
                ChatMessage.id > MessageRead.last_read_message_id,
            ),
        )
    )
    result = await db.execute(q)
    return result.scalar() or 0


async def _get_participant_ids(room_id: int, db: AsyncSession) -> List[int]:
    """Return list of user_ids that are participants of the room."""
    result = await db.execute(
        select(ChatParticipant.user_id).where(ChatParticipant.room_id == room_id)
    )
    return [row[0] for row in result.all()]


async def _compute_unread_total(user_id: int, db: AsyncSession) -> int:
    """Compute total unread messages across all rooms for a user."""
    # Find all rooms the user participates in
    room_ids_q = select(ChatParticipant.room_id).where(ChatParticipant.user_id == user_id)
    room_ids_result = await db.execute(room_ids_q)
    room_ids = [row[0] for row in room_ids_result.all()]

    if not room_ids:
        return 0

    total = 0
    for room_id in room_ids:
        total += await _get_room_unread(room_id, user_id, db)
    return total


async def _check_room_participant(room_id: int, user_id: int, db: AsyncSession) -> None:
    """Raise 403 if user is not a participant of the room."""
    result = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.room_id == room_id,
            ChatParticipant.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Вы не являетесь участником этой комнаты")


async def _build_room_out(room: ChatRoom, user_id: int, db: AsyncSession) -> dict:
    """Enrich a ChatRoom with last_message, unread_count, participants."""
    # Last message
    last_msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.room_id == room.id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    last_message = None
    if last_msg:
        sender_name = None
        if last_msg.sender_id:
            sender = await db.get(User, last_msg.sender_id)
            sender_name = sender.full_name if sender else None
        last_message = {
            "id": last_msg.id,
            "content": last_msg.content,
            "sender_name": sender_name,
            "created_at": last_msg.created_at.isoformat(),
            "has_file": bool(last_msg.file_path),
        }

    # Unread count
    unread_count = await _get_room_unread(room.id, user_id, db)

    # Participants
    participants_result = await db.execute(
        select(ChatParticipant, User)
        .join(User, User.id == ChatParticipant.user_id)
        .where(ChatParticipant.room_id == room.id)
    )
    participants = []
    for cp, u in participants_result.all():
        participants.append({
            "id": u.id,
            "full_name": u.full_name,
            "username": u.username,
            "avatar": u.avatar,
            "department": u.department,
            "position": u.position,
        })

    return {
        "id": room.id,
        "name": room.name,
        "is_group": room.is_group,
        "org_id": room.org_id,
        "created_at": room.created_at,
        "last_message": last_message,
        "unread_count": unread_count,
        "participants": participants,
    }


def _message_to_dict(msg: ChatMessage, sender_name: Optional[str] = None) -> dict:
    """Convert ChatMessage to dict matching MessageOut."""
    return {
        "id": msg.id,
        "room_id": msg.room_id,
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "content": msg.content,
        "file_name": msg.file_name,
        "file_mime": msg.file_mime,
        "file_size": msg.file_size,
        "has_file": bool(msg.file_path),
        "created_at": msg.created_at.isoformat(),
    }


# ────────────────────────────── REST Endpoints ─────────────────────────────

@router.get("/rooms", response_model=List[RoomOut])
async def get_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List chat rooms the current user participates in."""
    room_ids_q = select(ChatParticipant.room_id).where(
        ChatParticipant.user_id == current_user.id
    )
    rooms_result = await db.execute(
        select(ChatRoom).where(ChatRoom.id.in_(room_ids_q))
    )
    rooms = rooms_result.scalars().all()

    # Build enriched rooms
    enriched = []
    for room in rooms:
        data = await _build_room_out(room, current_user.id, db)
        enriched.append(data)

    # Sort by last message desc (rooms without messages go last)
    def sort_key(r):
        lm = r.get("last_message")
        if lm:
            return lm.get("id", 0)
        return 0

    enriched.sort(key=sort_key, reverse=True)
    return enriched


@router.post("/rooms/direct", response_model=RoomOut)
async def create_direct(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get or create a 1-on-1 chat room with another user."""
    target_user_id: int = body.get("target_user_id")
    if not target_user_id:
        raise HTTPException(status_code=422, detail="target_user_id обязателен")

    # Verify target user belongs to same org
    target_user = await db.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target_user.org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="Пользователь из другой организации")

    # Find existing 1-on-1 room between these two users
    # Rooms where both users are participants and is_group=False
    current_rooms_q = (
        select(ChatParticipant.room_id)
        .join(ChatRoom, ChatRoom.id == ChatParticipant.room_id)
        .where(
            ChatParticipant.user_id == current_user.id,
            ChatRoom.is_group == False,  # noqa: E712
        )
    )
    target_rooms_q = (
        select(ChatParticipant.room_id)
        .where(ChatParticipant.user_id == target_user_id)
    )

    existing_result = await db.execute(
        select(ChatRoom).where(
            ChatRoom.id.in_(current_rooms_q),
            ChatRoom.id.in_(target_rooms_q),
            ChatRoom.is_group == False,  # noqa: E712
        )
    )
    existing_room = existing_result.scalar_one_or_none()

    if existing_room:
        data = await _build_room_out(existing_room, current_user.id, db)
        return data

    # Create new 1-on-1 room
    new_room = ChatRoom(
        is_group=False,
        org_id=current_user.org_id,
        created_by=current_user.id,
    )
    db.add(new_room)
    await db.flush()

    db.add(ChatParticipant(room_id=new_room.id, user_id=current_user.id))
    db.add(ChatParticipant(room_id=new_room.id, user_id=target_user_id))
    await db.commit()
    await db.refresh(new_room)

    data = await _build_room_out(new_room, current_user.id, db)
    return data


@router.post("/rooms", response_model=RoomOut)
async def create_group(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a group chat room."""
    name: Optional[str] = body.get("name")
    participant_ids: List[int] = body.get("participant_ids", [])

    if not name:
        raise HTTPException(status_code=422, detail="name обязателен для группового чата")

    # Verify all participants belong to same org
    for uid in participant_ids:
        u = await db.get(User, uid)
        if not u:
            raise HTTPException(status_code=404, detail=f"Пользователь {uid} не найден")
        if u.org_id != current_user.org_id:
            raise HTTPException(status_code=403, detail=f"Пользователь {uid} из другой организации")

    # Create group room
    new_room = ChatRoom(
        is_group=True,
        name=name,
        org_id=current_user.org_id,
        created_by=current_user.id,
    )
    db.add(new_room)
    await db.flush()

    # Add creator + all participants (deduplicated)
    all_ids = list({current_user.id} | set(participant_ids))
    for uid in all_ids:
        db.add(ChatParticipant(room_id=new_room.id, user_id=uid))

    await db.commit()
    await db.refresh(new_room)

    data = await _build_room_out(new_room, current_user.id, db)
    return data


@router.get("/rooms/{room_id}/messages", response_model=List[MessageOut])
async def get_messages(
    room_id: int,
    before_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get message history for a room with keyset pagination."""
    await _check_room_participant(room_id, current_user.id, db)

    q = select(ChatMessage).where(ChatMessage.room_id == room_id)
    if before_id is not None:
        q = q.where(ChatMessage.id < before_id)
    q = q.order_by(ChatMessage.id.desc()).limit(limit)

    result = await db.execute(q)
    messages = result.scalars().all()

    # Reverse to chronological order and enrich with sender_name
    messages = list(reversed(messages))
    output = []
    for msg in messages:
        sender_name = None
        if msg.sender_id:
            sender = await db.get(User, msg.sender_id)
            sender_name = sender.full_name if sender else None
        output.append(MessageOut(
            id=msg.id,
            room_id=msg.room_id,
            sender_id=msg.sender_id,
            sender_name=sender_name,
            content=msg.content,
            file_name=msg.file_name,
            file_mime=msg.file_mime,
            file_size=msg.file_size,
            has_file=bool(msg.file_path),
            created_at=msg.created_at,
        ))
    return output


@router.post("/rooms/{room_id}/messages", response_model=MessageOut)
async def send_message(
    room_id: int,
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a text message or file attachment to a room."""
    await _check_room_participant(room_id, current_user.id, db)

    if not content and not file:
        raise HTTPException(status_code=422, detail="Необходимо передать текст или файл")

    file_path = None
    file_name = None
    file_mime = None
    file_size = None

    if file:
        # Validate MIME type
        if file.content_type not in ALLOWED_MIME:
            raise HTTPException(
                status_code=415,
                detail=f"Недопустимый тип файла: {file.content_type}",
            )

        # Read and validate size
        data = await file.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Файл превышает максимальный размер 50 МБ")

        # Save to disk
        room_dir = os.path.join(CHAT_UPLOAD_DIR, str(room_id))
        os.makedirs(room_dir, exist_ok=True)
        safe_name = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(room_dir, safe_name)
        with open(file_path, "wb") as f_out:
            f_out.write(data)

        file_name = file.filename
        file_mime = file.content_type
        file_size = len(data)

    # Create message in DB
    msg = ChatMessage(
        room_id=room_id,
        sender_id=current_user.id,
        content=content,
        file_path=file_path,
        file_name=file_name,
        file_mime=file_mime,
        file_size=file_size,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    sender_name = current_user.full_name
    msg_dict = _message_to_dict(msg, sender_name)

    # Push WS message event to all room participants
    participant_ids = await _get_participant_ids(room_id, db)
    await manager.send_to_users(participant_ids, {
        "type": "message",
        "room_id": room_id,
        "message": msg_dict,
    })

    # Push unread_count update to each participant (except sender)
    for uid in participant_ids:
        if uid != current_user.id:
            total = await _compute_unread_total(uid, db)
            await manager.send_to_user(uid, {"type": "unread_count", "total_unread": total})

    return MessageOut(
        id=msg.id,
        room_id=msg.room_id,
        sender_id=msg.sender_id,
        sender_name=sender_name,
        content=msg.content,
        file_name=msg.file_name,
        file_mime=msg.file_mime,
        file_size=msg.file_size,
        has_file=bool(msg.file_path),
        created_at=msg.created_at,
    )


@router.post("/rooms/{room_id}/read")
async def mark_read(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all messages in a room as read for current user."""
    await _check_room_participant(room_id, current_user.id, db)

    # Get max message id in room
    max_id_result = await db.execute(
        select(func.max(ChatMessage.id)).where(ChatMessage.room_id == room_id)
    )
    max_id = max_id_result.scalar()

    if max_id is not None:
        # UPSERT message_reads
        stmt = pg_insert(MessageRead).values(
            room_id=room_id,
            user_id=current_user.id,
            last_read_message_id=max_id,
        ).on_conflict_do_update(
            index_elements=None,
            constraint="uq_message_read",
            set_={"last_read_message_id": max_id},
        )
        await db.execute(stmt)
        await db.commit()

    # Push read event to all participants
    participant_ids = await _get_participant_ids(room_id, db)
    await manager.send_to_users(participant_ids, {
        "type": "read",
        "room_id": room_id,
        "user_id": current_user.id,
        "last_read_message_id": max_id,
    })

    # Push updated unread_count to current user
    total = await _compute_unread_total(current_user.id, db)
    await manager.send_to_user(current_user.id, {"type": "unread_count", "total_unread": total})

    return {"ok": True}


@router.get("/staff")
async def get_staff(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of staff members in the same organization (for new chat creation)."""
    result = await db.execute(
        select(User).where(
            User.org_id == current_user.org_id,
            User.id != current_user.id,
        )
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "username": u.username,
            "avatar": u.avatar,
            "department": u.department,
            "position": u.position,
        }
        for u in users
    ]


@router.get("/rooms/{room_id}/files/{msg_id}")
async def download_file(
    room_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a file attachment from a chat message."""
    await _check_room_participant(room_id, current_user.id, db)

    msg = await db.get(ChatMessage, msg_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    if msg.room_id != room_id:
        raise HTTPException(status_code=404, detail="Сообщение не принадлежит этой комнате")
    if not msg.file_path:
        raise HTTPException(status_code=404, detail="Файл не прикреплён к сообщению")
    if not os.path.exists(msg.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден на диске")

    return FileResponse(
        path=msg.file_path,
        filename=msg.file_name,
        media_type=msg.file_mime,
    )


# ────────────────────────────── WebSocket ──────────────────────────────────

@ws_router.websocket("/api/ws/chat")
async def chat_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint authenticated via JWT query param ?token=..."""
    # 1. Decode JWT
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if not username:
            await ws.close(code=4001)
            return
    except JWTError:
        await ws.close(code=4001)
        return

    # 2. Load user from DB
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        await ws.close(code=4001)
        return

    # 3. Connect
    await manager.connect(user.id, ws)

    # 4. Send initial unread_count event
    try:
        total = await _compute_unread_total(user.id, db)
        await ws.send_json({"type": "unread_count", "total_unread": total})

        # 5. Keep alive — all actions are REST; just drain incoming frames
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error for user %s: %s", user.id, e)
    finally:
        # 6. Disconnect
        manager.disconnect(user.id, ws)
