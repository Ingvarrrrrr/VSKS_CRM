from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class UserOrgAccess(Base):
    __tablename__ = "user_org_access"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_user_org"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="org_admin")

    user = relationship("User", backref="org_access_list")
    organization = relationship("Organization")
