"""
Incident — инцидент с ТС (ДТП, поломка, другое) — Phase 30-PR1.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Incident(Base):
    """
    Инцидент с ТС.

    incident_type: accident/breakdown/other
    severity: low/medium/urgent
    """
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    waybill_id = Column(
        Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    incident_type = Column(String(20), nullable=False)              # accident/breakdown/other
    severity = Column(String(20), nullable=False, default='medium')  # low/medium/urgent
    affected_system = Column(String(50), nullable=True)             # engine/brakes/akb/tires/electrical/other
    is_operational = Column(Boolean, nullable=True)
    location = Column(String(500), nullable=True)
    description = Column(Text, nullable=False)
    photos = Column(JSONB, server_default='[]')                     # array of {url, uploaded_at}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    notify_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])
    driver = relationship("User", foreign_keys=[driver_user_id])
    notify_user = relationship("User", foreign_keys=[notify_user_id])
