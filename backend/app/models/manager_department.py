from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class ManagerDepartment(Base):
    __tablename__ = "manager_departments"
    __table_args__ = (UniqueConstraint("manager_user_id", "dept_id"),)

    id = Column(Integer, primary_key=True)
    manager_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    dept_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    manager = relationship("User", foreign_keys=[manager_user_id], lazy="joined")
    department = relationship("Department", foreign_keys=[dept_id], lazy="joined")
