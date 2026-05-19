"""
Vehicle attachment (bytea + SHA-256 dedup) — Plan 29-01, Phase 29.

Decisions covered: D-07, D-11.

Typed slots: sts / pts / osago / kasko / dk / permit_to / photo / other.
Extra metadata fields (policy_number, issued_at, expires_at) used only for osago/kasko/dk.

DATE COLUMNS (needed in _DATE_FIELDS for attachment PATCH routers — plans 29-04+):
  - issued_at
  - expires_at
"""
from sqlalchemy import (
    Column, Integer, String, LargeBinary, ForeignKey, Date, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleAttachment(Base):
    """
    Документы и фото ТС. Pattern from purchase_file.py + bytea storage (D-07).

    D-11 AttachmentKind: sts / pts / osago / kasko / dk / permit_to / photo / other
    SHA-256 for dedup (index=True for fast lookup).
    """
    __tablename__ = "vehicle_attachments"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # D-11 kind values: sts / pts / osago / kasko / dk / permit_to / photo / other
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

    # Extra policy metadata — only used for kind in {osago, kasko, dk}
    policy_number = Column(String(50), nullable=True)
    issued_at = Column(Date, nullable=True)     # DATE — add to _DATE_FIELDS in 29-04
    expires_at = Column(Date, nullable=True)    # DATE — add to _DATE_FIELDS in 29-04

    # Relationships
    vehicle = relationship("Vehicle", back_populates="attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id], lazy="joined")
