from sqlalchemy import Column, Integer, String, Text
from app.database import Base

class Contractor(Base):
    __tablename__ = "contractors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    inn = Column(String(12))
    kpp = Column(String(9))
    address = Column(Text)
    contact_person = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    bank_details = Column(Text)
