"""
FleetDocument — документы транспортного средства (ОСАГО, ПТС, СТС, ТО и др.)
Phase 30-PR1.
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, DateTime, Text, Numeric, LargeBinary
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class FleetDocument(Base):
    """
    Документ ТС.

    type values: osago / sts / pts / to / tachograph / fpg / purchase_contract
    """
    __tablename__ = "fleet_documents"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = Column(String(30), nullable=False, index=True)  # osago/sts/pts/to/tachograph/fpg/purchase_contract
    number = Column(String(100), nullable=True)
    issued_at = Column(Date, nullable=True)
    expires_at = Column(Date, nullable=True, index=True)
    counterparty = Column(String(200), nullable=True)   # для purchase_contract
    amount_rub = Column(Numeric(12, 2), nullable=True)  # для purchase_contract
    file_url = Column(String(500), nullable=True)
    file_data = Column(LargeBinary, nullable=True)
    file_name = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    vehicle = relationship("Vehicle", back_populates="fleet_documents")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
