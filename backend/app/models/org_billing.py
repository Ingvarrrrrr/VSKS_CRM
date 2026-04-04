from sqlalchemy import Column, Integer, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class OrgBillingPaid(Base):
    """Хранит факт оплаты месяца для организации. Расчёт суммы — на лету."""
    __tablename__ = "org_billing_paid"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)   # 1-12 (календарный месяц)
    paid_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("org_id", "year", "month", name="uq_org_billing_month"),)
