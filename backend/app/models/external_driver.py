"""
External (hired) driver entity — Plan 29-01, Phase 29.

Decisions covered: D-15.

Drivers without a User account (contractors, hired personnel).
Reused across Trips — accumulates history.

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-09+):
  - license_issued_at
  - license_expires_at
  - medical_cert_expires_at (optional)
"""
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, Date, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ExternalDriver(Base):
    """
    Наёмный водитель без аккаунта в системе.

    D-15: full_name, license_*, phone, org_id (nullable FK), notes.
    Объединяется с User WHERE can_drive=True для селекта водителя в путёвке.
    """
    __tablename__ = "external_drivers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)

    # Driver license fields
    license_series = Column(String(10), nullable=True)
    license_number = Column(String(20), nullable=True)
    license_categories = Column(String(50), nullable=True)      # A,B,C,D,CE,M,...
    license_issued_at = Column(Date, nullable=True)             # DATE — add to _DATE_FIELDS in 29-09
    license_expires_at = Column(Date, nullable=True)            # DATE — add to _DATE_FIELDS in 29-09
    medical_cert_expires_at = Column(Date, nullable=True)       # DATE — add to _DATE_FIELDS in 29-09

    # Optional link to Organization (for subcontractor drivers)
    org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    org = relationship("Organization", foreign_keys=[org_id])
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    trips = relationship("Trip", back_populates="driver_external", lazy="select")
