"""
Repair attachment (bytea) — Plan 29-01, Phase 29.

Decisions covered: D-07, D-12.

Isolated from VehicleAttachment per D-07 (thematic isolation of repair docs from vehicle docs).
Kind values: order_form / act / invoice / photo / other.
"""
from sqlalchemy import (
    Column, Integer, String, LargeBinary, ForeignKey, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class RepairAttachment(Base):
    """
    Документы по конкретному ремонту ТС.

    D-12 RepairAttachmentKind: order_form / act / invoice / photo / other
    FK: repair_id ON DELETE CASCADE (дочерний документ — удаляется вместе с ремонтом).
    SHA-256 для дедупликации.
    """
    __tablename__ = "repair_attachments"

    id = Column(Integer, primary_key=True, index=True)
    repair_id = Column(
        Integer, ForeignKey("vehicle_repairs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # RepairAttachmentKind values: order_form / act / invoice / photo / other
    kind = Column(String(20), nullable=False, default="other")

    name = Column(String(500), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    mime = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)  # SHA-256 dedup

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    uploaded_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    repair = relationship("VehicleRepair", back_populates="attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id], lazy="joined")
