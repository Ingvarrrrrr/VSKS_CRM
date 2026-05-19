"""
Trip (путевой лист) — Plan 29-01, Phase 29.

Decisions covered: D-14, D-15, D-19.

Driver XOR constraint: (driver_user_id IS NOT NULL) OR (driver_external_id IS NOT NULL).
Status: draft / rendered.
docx_path — path to generated .docx file (docxtpl, D-14).

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - date
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Text, ForeignKey, Date, DateTime,
    CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Trip(Base):
    """
    Путевой лист ТС.

    D-14: 3 шаблона docx (trip_light / trip_truck / trip_special) по vehicle.type.
    D-15: driver_user_id XOR driver_external_id (CHECK constraint).
    D-19: .docx output через docxtpl.
    TripStatus values: draft / rendered.
    """
    __tablename__ = "trips"

    __table_args__ = (
        CheckConstraint(
            "driver_user_id IS NOT NULL OR driver_external_id IS NOT NULL",
            name="ck_trip_driver_xor"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = Column(Date, nullable=False, index=True)           # DATE — add to _DATE_FIELDS in 29-04

    # Driver: User (can_drive=True) XOR ExternalDriver
    driver_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    driver_external_id = Column(
        Integer, ForeignKey("external_drivers.id", ondelete="SET NULL"), nullable=True
    )

    # Route
    route_from = Column(String(255), nullable=True)
    route_to = Column(String(255), nullable=True)
    purpose = Column(Text, nullable=True)

    # Odometer
    odometer_start = Column(Integer, nullable=True)
    odometer_finish = Column(Integer, nullable=True)

    # Fuel remaining
    fuel_remaining_start = Column(Numeric(6, 2), nullable=True)
    fuel_remaining_finish = Column(Numeric(6, 2), nullable=True)
    fuel_issued_l = Column(Numeric(6, 2), nullable=True)

    # Cargo (for truck trips)
    cargo_name = Column(String(255), nullable=True)
    cargo_weight_t = Column(Numeric(8, 2), nullable=True)

    # Generated document
    docx_path = Column(String(500), nullable=True)

    # TripStatus values: draft / rendered
    status = Column(String(20), nullable=False, default="draft", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    vehicle = relationship("Vehicle", back_populates="trips")
    driver_user = relationship("User", foreign_keys=[driver_user_id], lazy="joined")
    driver_external = relationship(
        "ExternalDriver", back_populates="trips", foreign_keys=[driver_external_id], lazy="joined"
    )
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
