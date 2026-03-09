from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class PurchaseFile(Base):
    __tablename__ = "purchase_files"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=False)
    filepath = Column(String(1000), nullable=False)
    mime_type = Column(String(100))
    size = Column(Integer)
    file_type = Column(String(50), default="other")
    doc_format = Column(String(20), default="scan")
    created_at = Column(DateTime, default=datetime.utcnow)

    purchase = relationship("Purchase", back_populates="files")
