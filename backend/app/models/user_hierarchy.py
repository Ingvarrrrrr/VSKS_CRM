from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class UserHierarchy(Base):
    __tablename__ = "user_hierarchy"
    __table_args__ = (UniqueConstraint("manager_id", "subordinate_id"),)

    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subordinate_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    manager = relationship("User", foreign_keys=[manager_id], lazy="joined", primaryjoin="UserHierarchy.manager_id == User.id")
    subordinate = relationship("User", foreign_keys=[subordinate_id], lazy="joined", primaryjoin="UserHierarchy.subordinate_id == User.id")
