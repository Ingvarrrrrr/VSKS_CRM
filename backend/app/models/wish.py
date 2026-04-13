from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Wish(Base):
    __tablename__ = "wishes"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    estimated_price = Column(Numeric(15, 2), nullable=True)
    justification = Column(Text, nullable=True)
    status = Column(String(30), default="draft", nullable=False, index=True)
    rejection_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    approver = relationship("User", foreign_keys=[approved_by], lazy="joined")
    purchase = relationship("Purchase", foreign_keys=[purchase_id])
