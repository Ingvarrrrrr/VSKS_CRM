"""
Смена сотрудника — владелец (организация спасателей), 2026-09.

Отдельная таблица (не поля на User): нужна ИСТОРИЯ смен (когда начиналась,
когда закончилась), а не только текущее состояние — это позволяет потом
разобрать «кто когда был на смене» без привязки к таблице позиций. Активная
смена — ровно одна на пользователя (частичный уникальный индекс).
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class StaffShift(Base):
    """Одна запись = один период "на смене" одного сотрудника.

    is_active дублирует (ended_at IS NULL), но даёт быстрый индексируемый
    фильтр "кто сейчас на смене" без вычисления по NULL.
    """
    __tablename__ = "staff_shifts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # Только одна активная смена на пользователя одновременно.
        Index(
            "uq_staff_shifts_active_user",
            "user_id",
            unique=True,
            postgresql_where=(is_active == True),  # noqa: E712
        ),
    )
