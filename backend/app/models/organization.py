from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    inn = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Multi-org / contour support
    root_org_id   = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id",         ondelete="SET NULL"), nullable=True)

    users      = relationship("User", back_populates="organization", foreign_keys="User.org_id")
    child_orgs = relationship("Organization", foreign_keys="Organization.root_org_id", lazy="selectin")
