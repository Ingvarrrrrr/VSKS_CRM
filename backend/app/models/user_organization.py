from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class UserOrganization(Base):
    """Multi-org membership — user can belong to multiple organizations simultaneously."""
    __tablename__ = "user_organizations"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    position = Column(String(200), nullable=True)  # Position in this specific org

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    organization = relationship("Organization", foreign_keys=[org_id], lazy="joined")
