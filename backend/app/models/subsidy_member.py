from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime, func
from app.database import Base


class SubsidyMember(Base):
    """Совместная работа над черновой субсидией (план C1/C2) — калька WishMember,
    но без consent-флоу: субсидия ещё не «рабочая», приглашение участника не
    требует его согласия, как при добавлении в заявку."""
    __tablename__ = "subsidy_members"

    id = Column(Integer, primary_key=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    added_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    added_by = relationship("User", foreign_keys=[added_by_id], lazy="joined")
