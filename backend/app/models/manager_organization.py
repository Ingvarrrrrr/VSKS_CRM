from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class ManagerOrganization(Base):
    """User who can give orders to an entire organization and all its children."""
    __tablename__ = "manager_organizations"
    __table_args__ = (UniqueConstraint("manager_user_id", "org_id"),)

    id = Column(Integer, primary_key=True)
    manager_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

    manager = relationship("User", foreign_keys=[manager_user_id], lazy="joined")
    organization = relationship("Organization", foreign_keys=[org_id], lazy="joined")
