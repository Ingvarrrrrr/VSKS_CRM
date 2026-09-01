from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, DateTime, Date
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class UserOrganization(Base):
    """Multi-org membership — user can belong to multiple organizations simultaneously."""
    __tablename__ = "user_organizations"
    # Unique per user+org+dept (user can be in multiple depts of same org)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    position = Column(String(200), nullable=True)  # Position in this specific org
    dept_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    salary_amount = Column(Numeric(15, 2), nullable=True)  # Оклад
    employment_percent = Column(Integer, nullable=True, default=100)  # % ставки
    # Дата трудоустройства — ОБЩАЯ на пару (user_id, org_id), не per-dept-строку.
    # Пишется во все строки user_organizations этой пары (см. hierarchy.py patch_user_org_membership_row).
    hired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)  # дата трудоустройства / employment date
    dept_assigned_at = Column(Date, nullable=True)  # дата назначения В ОТДЕЛ (per-row, только для строк с dept_id)
    position_assigned_at = Column(Date, nullable=True)  # дата назначения НА ДОЛЖНОСТЬ (per-row)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    organization = relationship("Organization", foreign_keys=[org_id], lazy="joined")
