"""
Vehicle repair record — Plan 29-01, Phase 29.

Decisions covered: D-12, D-18.

D-12: status ENUM planned/in_progress/done/cancelled.
D-18: nullable purchase_id FK for bidirectional Purchase ↔ VehicleRepair link.

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - date
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Text, ForeignKey, Date, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleRepair(Base):
    """
    Запись о ремонте ТС.

    D-12 RepairKind status: planned / in_progress / done / cancelled
    D-18: purchase_id — связь с закупкой на ремонт (nullable, ON DELETE SET NULL).
    """
    __tablename__ = "vehicle_repairs"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date = Column(Date, nullable=False)                         # DATE — add to _DATE_FIELDS in 29-04
    description = Column(Text, nullable=True)
    cost_amount = Column(Numeric(12, 2), nullable=True)
    performed_by_name = Column(String(255), nullable=True)
    mileage_at_repair = Column(Integer, nullable=True)

    # RepairStatus values: planned / in_progress / done / cancelled
    status = Column(String(20), nullable=False, default="planned", index=True)

    # D-18: bidirectional link to Purchase (purchase for repair costs)
    purchase_id = Column(
        Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    vehicle = relationship("Vehicle", back_populates="repairs")
    purchase = relationship("Purchase", foreign_keys=[purchase_id])
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    attachments = relationship(
        "RepairAttachment", back_populates="repair",
        cascade="all, delete-orphan", lazy="selectin"
    )
