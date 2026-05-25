"""
VehicleFine model — Phase 29.3, штрафы ТС с матчингом по путевому листу.

Matching logic:
  DATE(issued_at) → trips WHERE vehicle_id = f.vehicle_id AND date = that date
  If found → snapshot driver_user_id / driver_external_id / matched_trip_id.
  If not found → all driver_* are NULL (unmatched).
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Text, ForeignKey, DateTime, LargeBinary
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleFine(Base):
    """
    Штраф ГИБДД / административный штраф на транспортное средство.

    Матчинг водителя: автоматически при создании по DATE(issued_at) → Trip.
    Поля driver_user_id / driver_external_id — снимок на момент фиксации.
    """
    __tablename__ = "vehicle_fines"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    # Точное время фиксации нарушения (ГИБДД даёт datetime)
    issued_at = Column(DateTime(timezone=True), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    doc_number = Column(String(100), nullable=True)       # «постановление 0123456789»
    violation_type = Column(String(200), nullable=True)   # «превышение скорости 20-40 км/ч»
    location = Column(String(500), nullable=True)         # место нарушения
    # FineStatus values: unpaid / paid / disputed
    status = Column(String(20), nullable=False, default="unpaid", index=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, nullable=True)

    # Снимок водителя на момент фиксации (заполняется авто-матчингом по trip)
    driver_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    driver_external_id = Column(
        Integer, ForeignKey("external_drivers.id", ondelete="SET NULL"), nullable=True
    )
    matched_trip_id = Column(
        Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )

    # Phase 29.3-R3 (pt9): фото штрафа (приходит из API ГИБДД при импорте)
    photo_data = Column(LargeBinary, nullable=True)            # binary image bytes
    photo_mime = Column(String(50), nullable=True)             # 'image/jpeg', 'image/png'
    photo_source_url = Column(Text, nullable=True)             # оригинальный URL от ГИБДД

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    vehicle = relationship("Vehicle", back_populates="fines")
    driver_user = relationship("User", foreign_keys=[driver_user_id], lazy="joined")
    driver_external = relationship(
        "ExternalDriver", foreign_keys=[driver_external_id], lazy="joined"
    )
    matched_trip = relationship("Trip", foreign_keys=[matched_trip_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
