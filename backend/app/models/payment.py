from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    document_number = Column(String(100))
    payment_purpose = Column(String(500))
    payment_date = Column(Date)
    amount = Column(Numeric(15, 2))
    contract = relationship("Contract")
    purchase = relationship("Purchase")
