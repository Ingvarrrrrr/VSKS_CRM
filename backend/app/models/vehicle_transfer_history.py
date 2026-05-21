"""
VehicleTransferHistory — история передач ТС (Phase 29.3).

Записывается автоматически при PATCH vehicle, когда меняется
owner_org_id, assigned_org_id или assigned_text.
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class VehicleTransferHistory(Base):
    __tablename__ = "vehicle_transfer_history"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Снапшот ДО изменения → ДО
    from_owner_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    to_owner_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    from_assigned_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    to_assigned_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    from_assigned_text = Column(String(100), nullable=True)
    to_assigned_text = Column(String(100), nullable=True)

    # Основание передачи
    basis = Column(String(200), nullable=True)
    doc_number = Column(String(100), nullable=True)
    doc_date = Column(Date, nullable=True)
    comment = Column(Text, nullable=True)

    changed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    vehicle = relationship("Vehicle", back_populates="transfer_history")
    from_owner_org = relationship("Organization", foreign_keys=[from_owner_org_id])
    to_owner_org = relationship("Organization", foreign_keys=[to_owner_org_id])
    from_assigned_org = relationship("Organization", foreign_keys=[from_assigned_org_id])
    to_assigned_org = relationship("Organization", foreign_keys=[to_assigned_org_id])
    changed_by_user = relationship("User", foreign_keys=[changed_by_user_id])
