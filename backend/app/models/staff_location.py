"""
Точки местоположения сотрудников — владелец (организация спасателей), 2026-09.

Задача: в аварийной ситуации понимать, кто где находится. Точность в сотни
метров достаточна, частые обновления не нужны — это НЕ трекер реального
времени, а редкие фиксации при активной смене.

Персональные данные: координаты — чувствительные сведения. НЕ логировать их
(см. app/routers/staff_location.py — в логах только счётчики, не lat/lon).

Индекс (user_id, recorded_at) обслуживает оба сценария выборки:
  - "последняя точка каждого" — DISTINCT ON (user_id) ORDER BY user_id, recorded_at DESC
  - "трек за период" — WHERE user_id = :id AND recorded_at BETWEEN :from AND :to
Отдельный индекс по recorded_at — для фонового удаления записей старше 30 дней
(app/__init__.py::_staff_location_cleanup_loop), которое работает по всем
пользователям сразу и не может использовать составной индекс, начинающийся с user_id.
"""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class StaffLocationPoint(Base):
    __tablename__ = "staff_location_points"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    accuracy_m = Column(Float, nullable=True)  # точность в метрах, если устройство её отдаёт

    # recorded_at — время фиксации НА УСТРОЙСТВЕ (может прийти с опозданием,
    # если приложение копило точки без связи); received_at — когда сервер
    # реально принял точку (для диагностики задержек доставки).
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source = Column(String(20), nullable=False, default="browser", server_default="browser")

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # Дубли по времени не плодим — повторная отправка одной и той же точки
        # (после потери связи) должна молча схлопнуться, а не создать строку-двойник.
        UniqueConstraint("user_id", "recorded_at", name="uq_staff_location_user_recorded"),
        Index("ix_staff_location_points_user_recorded", "user_id", "recorded_at"),
        Index("ix_staff_location_points_recorded_at", "recorded_at"),
    )
