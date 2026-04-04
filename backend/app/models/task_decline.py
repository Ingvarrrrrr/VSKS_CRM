from sqlalchemy import Column, Integer, ForeignKey, Boolean, DateTime, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class TaskConsentDecline(Base):
    """Запись когда исполнитель отклонил задачу, требующую согласия."""
    __tablename__ = "task_consent_declines"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    declined_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    acknowledged = Column(Boolean, default=False, nullable=False)
    is_accepted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", foreign_keys=[task_id], lazy="joined")
    declined_user = relationship("User", foreign_keys=[declined_user_id], lazy="joined")
