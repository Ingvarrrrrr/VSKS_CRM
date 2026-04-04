from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class FeoPlannedItem(Base):
    __tablename__ = "feo_planned_items"

    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(500), nullable=False)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    feo_category = relationship("FeoCategory", backref="planned_items")
