from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlanExcessApproval(Base):
    """Запрос на согласование превышения плана ФЭО над финансированием узла
    (feo_categories.budget). См. миграцию h8i9j0k1l2m3 и
    app.services.feo_plan.assert_no_unapproved_excess."""
    __tablename__ = "plan_excess_approvals"

    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False, index=True)

    excess_amount = Column(Numeric(15, 2), nullable=False)
    plan_amount = Column(Numeric(15, 2), nullable=True)
    budget_amount = Column(Numeric(15, 2), nullable=True)

    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    mode = Column(String(20), nullable=False, default="sequential")  # sequential/parallel

    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, nullable=True)

    steps = relationship(
        "PlanExcessApprovalStep",
        back_populates="approval",
        order_by="PlanExcessApprovalStep.order_num",
        cascade="all, delete-orphan",
    )
    feo_category = relationship("FeoCategory")
    requested_by = relationship("User", foreign_keys=[requested_by_id])


class PlanExcessApprovalStep(Base):
    """Шаг восходящей цепочки согласующих превышения плана (по образцу WishApproval)."""
    __tablename__ = "plan_excess_approval_steps"

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(Integer, ForeignKey("plan_excess_approvals.id", ondelete="CASCADE"), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    order_num = Column(Integer, nullable=False, default=0)  # 0 = самый нижний в цепочке
    role_name = Column(String(255), nullable=True)
    approver_full_name = Column(String(500), nullable=True)

    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    approval = relationship("PlanExcessApproval", back_populates="steps")
    linked_user = relationship("User", foreign_keys=[user_id])
    decided_by_user = relationship("User", foreign_keys=[decided_by_user_id])
