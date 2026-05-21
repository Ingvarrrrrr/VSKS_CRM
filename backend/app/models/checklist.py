"""
Checklist + ChecklistItem — Phase 30-PR1.

Pre-trip / post-trip / weekly / monthly осмотр ТС.
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Text, LargeBinary
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Checklist(Base):
    """Чеклист осмотра транспортного средства."""
    __tablename__ = "checklists"

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
    type = Column(String(20), nullable=False)          # pre_trip/post_trip/weekly/monthly
    overall_state = Column(String(20), nullable=True)  # ok/with_remarks/not_running
    fuel_level = Column(String(20), nullable=True)     # quarter/half/threequarter/full
    paint_condition = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    signed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ChecklistItem", back_populates="checklist",
        cascade="all, delete-orphan", lazy="selectin"
    )
    driver = relationship("User", foreign_keys=[driver_user_id])


class ChecklistItem(Base):
    """Элемент чеклиста (конкретный узел/агрегат)."""
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(
        Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String(50), nullable=False)   # akb/tires/mirrors/radio/firstaid/extinguisher/spare/lkp
    status = Column(String(20), nullable=False)  # ok/issue/missing
    photo_url = Column(String(500), nullable=True)
    photo_data = Column(LargeBinary, nullable=True)
    note = Column(Text, nullable=True)

    checklist = relationship("Checklist", back_populates="items")
