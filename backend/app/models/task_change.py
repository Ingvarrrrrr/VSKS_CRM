from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class TaskChange(Base):
    """Records which fields changed when a task is updated."""
    __tablename__ = "task_changes"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(50), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(200), nullable=True)


class TaskFieldSeen(Base):
    """Tracks when a user last dismissed (viewed) a specific changed field on a task."""
    __tablename__ = "task_field_seen"
    __table_args__ = (UniqueConstraint("user_id", "task_id", "field_name"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(50), nullable=False)
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
