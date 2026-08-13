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

    # Владелец, план zany-fluttering-mountain.md (2026-08-13): «прежний план обязан
    # сохраниться в базе» — заполняются в момент создания запроса ТОЛЬКО для превышения
    # вида plan_over_manual (Σ плановых позиций против вручную заданной суммы, см.
    # app.routers.plan_excess.request_plan_excess_approval): plan_before — ручная сумма
    # на тот момент (manual_plan_entered), plan_after — Σ активных плановых позиций
    # (manual_plan_entered + excess_plan_over_manual — на момент СОЗДАНИЯ запроса
    # node["plan_manual"] ещё РАВЕН ручной сумме, а не Σ позиций: подмена происходит
    # только ПОСЛЕ approved, см. app.services.feo_plan._manual_plan_for). NULL для
    # остальных двух видов превышения (over_feo/fact_over_plan) — там «план был →
    # стал» не запрашивался.
    plan_before = Column(Numeric(15, 2), nullable=True)
    plan_after = Column(Numeric(15, 2), nullable=True)

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
