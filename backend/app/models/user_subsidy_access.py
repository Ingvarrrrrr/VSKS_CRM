from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from app.database import Base


class UserSubsidyAccess(Base):
    __tablename__ = "user_subsidy_access"
    __table_args__ = (UniqueConstraint("user_id", "subsidy_id", name="uq_user_subsidy"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="employee")

    user = relationship(
        "User",
        backref=backref("subsidy_access_list", cascade="all, delete-orphan", passive_deletes=True),
    )
    subsidy = relationship("Subsidy", passive_deletes=True)


class UserSubsidyPermissionOverride(Base):
    __tablename__ = "user_subsidy_permission_overrides"
    __table_args__ = (UniqueConstraint("user_subsidy_access_id", "key", name="uq_usa_override"),)

    id = Column(Integer, primary_key=True, index=True)
    user_subsidy_access_id = Column(
        Integer,
        ForeignKey("user_subsidy_access.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(64), nullable=False, index=True)
    granted = Column(Boolean, nullable=False)
