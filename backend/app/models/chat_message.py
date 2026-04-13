from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=True)         # NULL if file-only message
    file_path = Column(String(1000), nullable=True)  # NULL if text-only; stored at /app/uploads/chat/{room_id}/
    file_name = Column(String(255), nullable=True)
    file_mime = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    mention_ids = Column(JSONB, nullable=True)   # [user_id, ...]  populated on send
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    room = relationship("ChatRoom", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_room_id_desc", "room_id", "id"),  # keyset pagination
    )


class MessageRead(Base):
    __tablename__ = "message_reads"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_read_message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_message_read"),
        Index("ix_message_reads_user_id", "user_id"),
    )
