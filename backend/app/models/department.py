from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class Department(Base):
    """Отдел в организации, опционально привязан к субсидии."""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True)
    head_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DepartmentMember(Base):
    """Привязка сотрудника к отделу."""
    __tablename__ = "department_members"
    __table_args__ = (UniqueConstraint("department_id", "user_id", name="uq_dept_user"),)

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position = Column(String(300), nullable=True)  # Должность в отделе
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TaskEditDelegate(Base):
    """Кастомное право: delegate_user_id может редактировать задачи target_user_id."""
    __tablename__ = "task_edit_delegates"
    __table_args__ = (UniqueConstraint("target_user_id", "delegate_user_id", name="uq_task_delegate"),)

    id = Column(Integer, primary_key=True, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delegate_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
