"""
Waybill child models — Phase 30-PR1.

RouteStop, OdometerReading, FuelRefill — дочерние сущности путевого листа.
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Text, Numeric, LargeBinary
)
from sqlalchemy.orm import relationship
from app.database import Base


class RouteStop(Base):
    """Остановка маршрута путевого листа."""
    __tablename__ = "waybill_route_stops"

    id = Column(Integer, primary_key=True)
    waybill_id = Column(
        Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ord = Column(Integer, nullable=False)          # порядок 1,2,3...
    kind = Column(String(20), nullable=False)      # start/regular/end
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    planned_time = Column(DateTime(timezone=True), nullable=True)
    actual_time = Column(DateTime(timezone=True), nullable=True)
    lat = Column(Numeric(9, 6), nullable=True)
    lon = Column(Numeric(9, 6), nullable=True)

    waybill = relationship("Trip", back_populates="route_stops")


class OdometerReading(Base):
    """Показание одометра в путевом листе."""
    __tablename__ = "waybill_odometer_readings"

    id = Column(Integer, primary_key=True)
    waybill_id = Column(
        Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(200), nullable=True)
    mileage_km = Column(Integer, nullable=False)
    fuel_remaining_l = Column(Numeric(6, 2), nullable=True)
    note = Column(Text, nullable=True)

    waybill = relationship("Trip", back_populates="odometer_readings")


class FuelRefill(Base):
    """Заправка в путевом листе."""
    __tablename__ = "waybill_fuel_refills"

    id = Column(Integer, primary_key=True)
    waybill_id = Column(
        Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refilled_at = Column(DateTime(timezone=True), nullable=False)
    station_name = Column(String(200), nullable=True)
    liters = Column(Numeric(6, 2), nullable=False)
    amount_rub = Column(Numeric(10, 2), nullable=True)
    receipt_photo_url = Column(String(500), nullable=True)
    receipt_photo_data = Column(LargeBinary, nullable=True)

    waybill = relationship("Trip", back_populates="fuel_refills")
