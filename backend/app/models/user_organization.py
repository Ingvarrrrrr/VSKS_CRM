from sqlalchemy import Column, Integer, String, ForeignKey, Numeric
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

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    organization = relationship("Organization", foreign_keys=[org_id], lazy="joined")
