from sqlalchemy import Column, Integer, String, Date, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(100), nullable=False)
    date = Column(Date)
    contract_type = Column(String(50), nullable=False)  # single / framework_cumulative / framework_with_amount
    contractor_id = Column(Integer, ForeignKey("contractors.id"))
    subsidy_id = Column(Integer, ForeignKey("subsidies.id"), nullable=True)
    subject = Column(Text)
    max_amount = Column(Numeric(15, 2))
    status = Column(String(50), default="active")
    notes = Column(Text)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    purchase_method = Column(String(50), nullable=True)  # single / competitive
    item_type = Column(String(20), nullable=True)  # товар / услуга
    planned_monthly = Column(Numeric(15, 2), nullable=True)
    contractor = relationship("Contractor")
    subsidy = relationship("Subsidy")
    purchases = relationship("Purchase", back_populates="contract")
    extra_subsidies = relationship("ContractSubsidy", cascade="all, delete-orphan", lazy="selectin")
