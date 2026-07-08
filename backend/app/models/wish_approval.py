from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class WishApproval(Base):
    """Согласующий заявки (wish). Восходящая цепочка либо ручное добавление."""
    __tablename__ = "wish_approvals"

    id = Column(Integer, primary_key=True, index=True)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    order_num = Column(Integer, nullable=False, default=0)  # 0 = самый нижний в цепочке
    role_name = Column(String(255), nullable=True)          # снапшот роли, напр. "Начальник отдела"
    approver_full_name = Column(String(500), nullable=True)
    is_auto = Column(Boolean, nullable=False, default=False, server_default="false")  # True = добавлен каскадом

    status = Column(String(30), nullable=False, default="pending")  # pending/approved/rejected/skipped
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    wish = relationship("Wish", back_populates="approvals")
    linked_user = relationship("User", foreign_keys=[user_id])
    decided_by_user = relationship("User", foreign_keys=[decided_by_user_id])
