from sqlalchemy import Column, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class PurchaseSubsidyAllocation(Base):
    __tablename__ = "purchase_subsidy_allocations"
    id = Column(Integer, primary_key=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=True)
    subsidy = relationship("Subsidy")
