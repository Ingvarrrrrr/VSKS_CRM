from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime
from app.database import Base
from datetime import datetime


class DeliveryAddress(Base):
    __tablename__ = "delivery_addresses"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    address = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
