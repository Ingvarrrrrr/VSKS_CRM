from sqlalchemy import Column, Integer, String, Float, Date
from sqlalchemy.orm import relationship
from app.database import Base

class Subsidy(Base):
    __tablename__ = "subsidies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    year = Column(Integer, nullable=False)
    budget = Column(Float, nullable=False)
    calculated_budget = Column(Float, nullable=True)  # Рассчитанный из дочерних категорий
    description = Column(String(2000), nullable=True)
    customer_id = Column(Integer, ForeignKey("contractors.id"), nullable=True)  # Заказчик
    feo_categories = relationship("FeoCategory", back_populates="subsidy")
    approvers = relationship("SubsidyApprover", back_populates="subsidy", order_by="SubsidyApprover.order_num", cascade="all, delete-orphan")
    customer = relationship("Contractor", backref="subsidies")