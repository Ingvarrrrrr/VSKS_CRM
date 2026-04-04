from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base


class BudgetHistory(Base):
    __tablename__ = "budget_history"

    id = Column(Integer, primary_key=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    entity_type = Column(String(20), nullable=False)  # "subsidy" | "purchase"
    old_value = Column(Numeric(15, 2), nullable=True)
    new_value = Column(Numeric(15, 2), nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(200), nullable=True)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
