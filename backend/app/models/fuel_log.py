"""
Fuel log (заправки) — Plan 29-01, Phase 29.

Decisions covered: D-03, D-20.

Each row = one fueling event.
receipt_attachment_id — FK to VehicleAttachment for the receipt scan.
total_amount = liters * price_per_liter (if NULL, computed in Pydantic / router).

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - date
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Text, ForeignKey, Date, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class FuelLog(Base):
    """
    Журнал заправок ТС.

    D-03: liters + price_per_liter + total_amount + fuel_type.
    D-20: fuel_type per-row (может отличаться от нормативного vehicle.fuel_type).
    FK receipt_attachment_id — чек заправки (VehicleAttachment kind='photo'/'other').
    """
    __tablename__ = "fuel_logs"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = Column(Date, nullable=False, index=True)   # DATE — add to _DATE_FIELDS in 29-04
    liters = Column(Numeric(8, 2), nullable=True)
    price_per_liter = Column(Numeric(8, 2), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)  # computed or manual

    # FuelType values: AI-92 / AI-95 / AI-98 / AI-100 / DT / GAS / other
    fuel_type = Column(String(20), nullable=True)

    # FK to receipt scan stored in vehicle_attachments
    receipt_attachment_id = Column(
        Integer, ForeignKey("vehicle_attachments.id", ondelete="SET NULL"), nullable=True
    )
    note = Column(Text, nullable=True)

    # Source: manual / trip / import
    source = Column(String(20), nullable=False, default="manual")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    vehicle = relationship("Vehicle", back_populates="fuel_logs")
    receipt_attachment = relationship("VehicleAttachment", foreign_keys=[receipt_attachment_id])
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
