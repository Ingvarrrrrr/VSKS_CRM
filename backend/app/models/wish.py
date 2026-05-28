from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Wish(Base):
    __tablename__ = "wishes"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    category = Column(String(50), nullable=True)   # Товар / Услуга / Работа
    description = Column(Text, nullable=True)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    estimated_price = Column(Numeric(15, 2), nullable=True)
    link = Column(String(2000), nullable=True)      # URL reference
    priority = Column(String(20), nullable=True)    # low / medium / high / urgent
    desired_date = Column(Date, nullable=True)       # желаемый срок
    justification = Column(Text, nullable=True)
    status = Column(String(30), default="draft", nullable=False, index=True)
    rejection_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    executor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Кто исполняет (ставит approver)
    execution_deadline = Column(Date, nullable=True)  # Срок исполнения (ставит approver)

    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    approver = relationship("User", foreign_keys=[approved_by], lazy="joined")
    assignee = relationship("User", foreign_keys=[assigned_to], lazy="selectin")
    executor = relationship("User", foreign_keys=[executor_id], lazy="selectin")
    purchase = relationship("Purchase", foreign_keys=[purchase_id])
    subsidy = relationship("Subsidy", lazy="selectin")
    event = relationship("Event", foreign_keys=[event_id], lazy="selectin")
    items = relationship("WishItem", back_populates="wish", cascade="all, delete-orphan", lazy="selectin")
