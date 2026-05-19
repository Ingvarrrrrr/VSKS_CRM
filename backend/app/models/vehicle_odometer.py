"""
Vehicle odometer time-series — Plan 29-01, Phase 29.

Decisions covered: D-13.

Absolute odometer values (not delta — delta computed on read).
UNIQUE(vehicle_id, date) — one reading per vehicle per day.
Source: manual / trip / fuel_log.

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - date
"""
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, Date, DateTime, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleOdometer(Base):
    """
    Запись пробега ТС за дату.

    D-13: UNIQUE(vehicle_id, date) — одна запись на машину в день.
    Абсолютные значения одометра, не delta.
    OdometerSource values: manual / trip / fuel_log.
    """
    __tablename__ = "vehicle_odometer"

    __table_args__ = (
        UniqueConstraint("vehicle_id", "date", name="uq_vehicle_odometer_vehicle_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = Column(Date, nullable=False)              # DATE — add to _DATE_FIELDS in 29-04
    odometer_km = Column(Integer, nullable=False)

    entered_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note = Column(Text, nullable=True)

    # OdometerSource values: manual / trip / fuel_log
    source = Column(String(20), nullable=False, default="manual")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="odometer_entries")
    entered_by = relationship("User", foreign_keys=[entered_by_id], lazy="joined")
