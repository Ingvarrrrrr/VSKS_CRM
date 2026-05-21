"""
Trip (путевой лист) — Plan 29-01, Phase 29.
Phase 30: расширен полями Waybill (Минтранс №3).

Decisions covered: D-14, D-15, D-19.

Driver XOR constraint: (driver_user_id IS NOT NULL) OR (driver_external_id IS NOT NULL).
Status: created/tech_inspect/med_inspect/in_progress/closing/on_review/closed/overdue
  (legacy: draft→created, rendered→closed)
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
    TripStatus values: created/tech_inspect/med_inspect/in_progress/closing/on_review/closed/overdue
      (legacy values: draft/rendered still supported for backward compat)
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

    # TripStatus values: created/tech_inspect/med_inspect/in_progress/closing/on_review/closed/overdue
    status = Column(String(20), nullable=False, default="draft", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Phase 30: Waybill fields (Минтранс №3)
    number = Column(String(20), nullable=True, unique=True)     # NN-MM/YYYY
    date_start = Column(DateTime(timezone=True), nullable=True)
    date_end = Column(DateTime(timezone=True), nullable=True)
    planned_mileage_km = Column(Integer, nullable=True)
    actual_mileage_km = Column(Integer, nullable=True)
    dispatcher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cargo_description = Column(Text, nullable=True)
    passengers_count = Column(Integer, nullable=True)

    # Pre-trip осмотры (ФИО+время+результат)
    pre_trip_mechanic_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    pre_trip_mechanic_inspected_at = Column(DateTime(timezone=True), nullable=True)
    pre_trip_mechanic_result = Column(Text, nullable=True)
    pre_trip_doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    pre_trip_doctor_inspected_at = Column(DateTime(timezone=True), nullable=True)
    pre_trip_doctor_result = Column(Text, nullable=True)

    # Post-trip осмотры
    post_trip_mechanic_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    post_trip_mechanic_inspected_at = Column(DateTime(timezone=True), nullable=True)
    post_trip_mechanic_result = Column(Text, nullable=True)
    post_trip_doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    post_trip_doctor_inspected_at = Column(DateTime(timezone=True), nullable=True)
    post_trip_doctor_result = Column(Text, nullable=True)

    # Подпись водителя (electronic)
    driver_signature = Column(Text, nullable=True)              # data:image/png;base64,...
    driver_signed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="trips")
    driver_user = relationship("User", foreign_keys=[driver_user_id], lazy="joined")
    driver_external = relationship(
        "ExternalDriver", back_populates="trips", foreign_keys=[driver_external_id], lazy="joined"
    )
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    dispatcher = relationship("User", foreign_keys=[dispatcher_id], lazy="joined")
    pre_trip_mechanic = relationship("User", foreign_keys=[pre_trip_mechanic_id], lazy="joined")
    pre_trip_doctor = relationship("User", foreign_keys=[pre_trip_doctor_id], lazy="joined")
    post_trip_mechanic = relationship("User", foreign_keys=[post_trip_mechanic_id], lazy="joined")
    post_trip_doctor = relationship("User", foreign_keys=[post_trip_doctor_id], lazy="joined")
    # Phase 30: waybill child tables
    route_stops = relationship(
        "RouteStop", back_populates="waybill",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="RouteStop.ord"
    )
    odometer_readings = relationship(
        "OdometerReading", back_populates="waybill",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="OdometerReading.recorded_at"
    )
    fuel_refills = relationship(
        "FuelRefill", back_populates="waybill",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FuelRefill.refilled_at"
    )


# Alias для нового именования (Phase 30): Waybill = Trip (Минтранс №3)
Waybill = Trip
