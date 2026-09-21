from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlanExcessApproval(Base):
    """Запрос на согласование превышения плана ФЭО над финансированием узла
    (feo_categories.budget). См. миграцию h8i9j0k1l2m3 и
    app.services.feo_plan.assert_no_unapproved_excess.

    kind (миграция g5h7j9k1m3n5, задача владельца, план
    ancient-prancing-music.md раздел D, 2026-09-21) — вид согласуемого
    превышения, единственный источник видов/подписей —
    app.services.plan_excess_kinds. Записи, созданные ДО этой миграции, несут
    kind='legacy' (server_default) — approved legacy-запись по-прежнему гасит
    любой из трёх старых видов узла дерева (см. plan_excess_kinds.
    LEGACY_FALLBACK_KINDS и app.services.feo_plan_tree._latest_approval —
    фолбэк «своего вида нет → смотрим legacy»), чтобы согласования, принятые
    до разделения по видам, не пришлось запрашивать заново.

    feo_category_id nullable — level='subsidy' (см. plan_excess_kinds.
    level_for_category_id): запись согласования на субсидию целиком, а не на
    конкретный узел ФЭО.
    """
    __tablename__ = "plan_excess_approvals"
    __table_args__ = (
        Index(
            "ix_plan_excess_approvals_cat_kind_created",
            "subsidy_id", "feo_category_id", "kind", "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(40), nullable=False, default="legacy", server_default="legacy")

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
