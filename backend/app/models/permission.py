from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class PermissionTab(Base):
    __tablename__ = "permission_tabs"

    id = Column(Integer, primary_key=True, index=True)
    tab_key = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PermissionAction(Base):
    __tablename__ = "permission_actions"

    id = Column(Integer, primary_key=True, index=True)
    action_key = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(String(256), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_name", "key", name="uq_role_perm"),)

    id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String(32), nullable=False, index=True)  # one of ROLES enum
    key = Column(String(64), nullable=False, index=True)        # tab_key OR action_key
    granted = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserOrgPermissionOverride(Base):
    __tablename__ = "user_org_permission_overrides"
    __table_args__ = (UniqueConstraint("user_org_access_id", "key", name="uq_uoa_override"),)

    id = Column(Integer, primary_key=True, index=True)
    user_org_access_id = Column(
        Integer,
        ForeignKey("user_org_access.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(64), nullable=False, index=True)
    granted = Column(Boolean, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user_org_access = relationship("UserOrgAccess", backref="permission_overrides")
