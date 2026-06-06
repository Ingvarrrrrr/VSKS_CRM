from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime, func
from app.database import Base


class WishMember(Base):
    __tablename__ = "wish_members"

    id = Column(Integer, primary_key=True)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="participant")
    added_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consent_pending = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    added_by = relationship("User", foreign_keys=[added_by_id], lazy="joined")
