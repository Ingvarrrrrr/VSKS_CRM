from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum, Boolean, UniqueConstraint, Sequence
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"        # ожидает подтверждения создателем
    done = "done"
    cancelled = "cancelled"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_number = Column(Integer, nullable=True, unique=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TaskStatus), default=TaskStatus.todo, nullable=False)
    priority = Column(SAEnum(TaskPriority), default=TaskPriority.medium, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    category = Column(String(200), nullable=True)  # "Склад", "Документы", "Строительство" и т.д.
    parent_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True)
    import_to_parent = Column(Boolean, default=False, nullable=False)
    # Phase 29 D-17: идемпотентный тег для авто-задач по просрочкам ТС
    # Формат: [VEHICLE:{vehicle_id}:OSAGO_EXPIRY] / [VEHICLE:{vehicle_id}:TO_WARNING] / etc.
    system_tag = Column(String(200), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignees = relationship("TaskAssignee", back_populates="task", cascade="all, delete-orphan", lazy="selectin")
    purchase = relationship("Purchase", foreign_keys=[purchase_id], backref="tasks")


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    consent_pending = Column(Boolean, default=False, nullable=False, server_default="false")

    task = relationship("Task", back_populates="assignees")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")


class TelegramMessageMap(Base):
    """Maps Telegram message_id → task_id for routing replies back to CRM."""
    __tablename__ = "telegram_message_map"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(50), nullable=False, index=True)   # Telegram user chat_id
    message_id = Column(Integer, nullable=False)                # Telegram message_id sent by bot
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
