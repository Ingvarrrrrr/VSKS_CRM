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
    deputy_head_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # зам.начальника отдела
    curator_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)      # курирующий зам
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)      # вышестоящее подразделение
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
