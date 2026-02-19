from sqlalchemy import Column, Integer, String, Date, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(100), nullable=False)
    date = Column(Date)
    contract_type = Column(String(20), nullable=False)  # framework / one-time
    contractor_id = Column(Integer, ForeignKey("contractors.id"))
    subject = Column(Text)
    max_amount = Column(Numeric(15, 2))
    status = Column(String(50), default="active")
    notes = Column(Text)
    contractor = relationship("Contractor")
    purchases = relationship("Purchase", back_populates="contract")
