from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.database import Base


class PurchaseApproval(Base):
    __tablename__ = "purchase_approvals"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True)

    # Snapshot from SubsidyApprover at creation time
    subsidy_approver_id = Column(Integer, ForeignKey("subsidy_approvers.id", ondelete="SET NULL"), nullable=True)
    order_num = Column(Integer, nullable=False, default=0)
    role_name = Column(String(255), nullable=False)
    approver_full_name = Column(String(500), nullable=False)

    # Link to system user (nullable — approver may not be a system user)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Decision
    status = Column(String(30), nullable=False, default="pending")
    # Values: pending, approved, rejected, skipped
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_username = Column(String(100), nullable=True)
    decided_by_ip = Column(String(45), nullable=True)

    # Future crypto fields (nullable, unused for now)
    signature_hash = Column(String(512), nullable=True)
    signature_data = Column(Text, nullable=True)
    signature_algorithm = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    purchase = relationship("Purchase", back_populates="approvals")
    decided_by_user = relationship("User", foreign_keys=[decided_by_user_id])
    linked_user = relationship("User", foreign_keys=[user_id])
