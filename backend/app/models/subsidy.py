from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Subsidy(Base):
    __tablename__ = "subsidies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    year = Column(Integer, nullable=False)
    budget = Column(Float, nullable=False)
    calculated_budget = Column(Float, nullable=True)
    description = Column(String(2000), nullable=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
    feo_categories = relationship("FeoCategory", back_populates="subsidy")
    approvers = relationship("SubsidyApprover", back_populates="subsidy", order_by="SubsidyApprover.order_num", cascade="all, delete-orphan")
    contractor_overrides = relationship("SubsidyContractorOverride", back_populates="subsidy", cascade="all, delete-orphan")