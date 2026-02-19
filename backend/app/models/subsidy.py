from sqlalchemy import Column, Integer, String, Float, Date
from sqlalchemy.orm import relationship
from app.database import Base

class Subsidy(Base):
    __tablename__ = "subsidies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    year = Column(Integer, nullable=False)
    budget = Column(Float, nullable=False)
    description = Column(String(2000), nullable=True)
    feo_categories = relationship("FeoCategory", back_populates="subsidy")