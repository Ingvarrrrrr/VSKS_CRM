"""
Vehicle field change audit log — Plan 29-01, Phase 29.

Decisions covered: D-10.

Auto-written on every PATCH to Vehicle fields (via update_vehicle endpoint in plan 29-04).
UI: popover timeline per field (old → new, when, who, optional comment).
"""
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleFieldHistory(Base):
    """
    Audit log изменений полей карточки ТС.

    D-10: field_key (VARCHAR 50) + old_value + new_value (TEXT) + changed_by + changed_at + comment.
    FK vehicle_id ON DELETE CASCADE.
    """
    __tablename__ = "vehicle_field_history"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key = Column(String(64), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    changed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment = Column(Text, nullable=True)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="field_history")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id], lazy="joined")
