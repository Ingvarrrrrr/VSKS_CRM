"""
Vehicle fleet main model — Plan 29-01, Phase 29 «Имущество → Автотранспорт».

Decisions covered: D-04, D-06, D-08, D-13, D-18, D-20.

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - registered_at
  - insurance_until
  - last_to_date
  - tech_inspection_until
  - assignment_doc_date  (Phase 29.3)
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Numeric,
    ForeignKey, Date, DateTime, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Vehicle(Base):
    """
    Основная карточка транспортного средства.

    D-06: owner_org_id — кому принадлежит; assigned_org_id — у кого в эксплуатации.
    D-08: mixed schema — канонические колонки + bool-слоты + JSONB props.
    D-20: fuel_norm_summer / fuel_norm_winter — нормы расхода л/100км.
    """
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)

    # D-06 Multi-tenancy visibility
    owner_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_text = Column(String(100), nullable=True)  # fallback: свободный текст для регионов без org

    # Identification
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    color = Column(String(50), nullable=True)
    vin = Column(String(17), nullable=True, index=True)
    plate = Column(String(20), nullable=False, unique=True, index=True)

    # Registration & docs
    registered_at = Column(Date, nullable=True)       # DATE — add to _DATE_FIELDS in 29-04
    insurance_until = Column(Date, nullable=True)     # DATE — add to _DATE_FIELDS in 29-04

    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture = Column(Integer, nullable=True)       # Год выпуска
    last_to_mileage_km = Column(Integer, nullable=True)        # Пробег при последнем ТО
    last_to_date = Column(Date, nullable=True)                 # Дата последнего ТО
    pts_number = Column(String(50), nullable=True)             # Номер ПТС
    sts_number = Column(String(50), nullable=True)             # Номер СТС
    tech_inspection_until = Column(Date, nullable=True)        # Техосмотр действителен до
    purchase_info = Column(String(200), nullable=True)         # Где/как куплено ("ФПГ Иркутск")

    # Type & state: VARCHAR (not PG ENUM) per RISKS: easier migration
    # VehicleType values: car_light / minivan / truck_van / truck_board / truck_tank /
    #   truck_metal / bus / special / quadbike / snowmobile / boat / boat_motor / trailer / other
    type = Column(String(30), nullable=True, index=True)

    # VehicleState values: working / broken / in_repair / needs_repair / destroyed / utilized
    state = Column(String(20), nullable=True, default="working", index=True)

    # Fuel — D-20
    # FuelType values: AI-92 / AI-95 / AI-98 / AI-100 / DT / GAS / other
    fuel_type = Column(String(20), nullable=True)
    fuel_norm_summer = Column(Float, nullable=True)   # л/100км, May-Sep
    fuel_norm_winter = Column(Float, nullable=True)   # л/100км, Oct-Apr

    # Equipment bool slots (D-08)
    has_tracker = Column(Boolean, nullable=True)
    akb_ok = Column(Boolean, nullable=True)
    has_radio = Column(Boolean, nullable=True)
    mirrors_ok = Column(Boolean, nullable=True)
    has_keys = Column(Boolean, nullable=True)
    has_first_aid_kit = Column(Boolean, nullable=True)
    has_spare_wheel = Column(Boolean, nullable=True)
    has_extinguisher = Column(Boolean, nullable=True)

    # Принадлежность — основание передачи (Phase 29.3)
    assignment_basis = Column(String(200), nullable=True)      # Основание для использования
    assignment_doc_number = Column(String(100), nullable=True) # Номер документа
    assignment_doc_date = Column(Date, nullable=True)          # Дата документа

    # Двигатель (Phase 29.3)
    engine_power_hp = Column(Integer, nullable=True)   # Мощность двигателя, л.с.
    engine_volume_l = Column(Float, nullable=True)     # Объём двигателя, л

    # TO warning (D-17)
    next_to_km = Column(Integer, nullable=True)             # километраж следующего ТО
    current_odometer_km = Column(Integer, nullable=True)    # snapshot из последнего VehicleOdometer

    # JSONB props (D-08): branding, paint_condition, tires_type, defect_description, note, custom.*
    # server_default='{}' to avoid mutable-default trap
    props = Column(JSONB, nullable=False, server_default="{}")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner_org = relationship("Organization", foreign_keys=[owner_org_id])
    assigned_org = relationship("Organization", foreign_keys=[assigned_org_id])

    attachments = relationship(
        "VehicleAttachment", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin"
    )
    repairs = relationship(
        "VehicleRepair", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleRepair.date.desc()"
    )
    field_history = relationship(
        "VehicleFieldHistory", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleFieldHistory.changed_at.desc()"
    )
    odometer_entries = relationship(
        "VehicleOdometer", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleOdometer.date.desc()"
    )
    fuel_logs = relationship(
        "FuelLog", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FuelLog.date.desc()"
    )
    trips = relationship(
        "Trip", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="Trip.date.desc()"
    )
    transfer_history = relationship(
        "VehicleTransferHistory", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleTransferHistory.changed_at.desc()"
    )
    fines = relationship(
        "VehicleFine", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleFine.issued_at.desc()"
    )
