"""
VehiclePass model — произвольный набор пропусков ТС (владелец, 2026-09).

Заменяет десять фиксированных колонок vehicles.pass_zo / pass_zo_until /
pass_ho / pass_ho_until / pass_dnr / pass_dnr_until / pass_lnr / pass_lnr_until /
pass_moscow / pass_moscow_until (Автоблок §1) — разные организации заводят
разные зоны/названия пропусков, поэтому набор не может быть фиксированным
списком колонок. Старые десять колонок НЕ удалены (см. миграцию, добавившую эту
таблицу) — оставлены как историческая заморозка, но больше не читаются и не
пишутся ни реестром полей (app/services/vehicle_fields.py), ни импортом
(app/routers/vehicles_import.py), ни PATCH /api/vehicles — единственный
источник правды теперь эта таблица + app/routers/vehicle_passes.py.

UniqueConstraint(vehicle_id, name) — одно название пропуска на машину не может
повторяться (иначе "какой из двух ЗО актуален" не имеет ответа).
"""
from sqlalchemy import Column, Integer, String, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class VehiclePass(Base):
    __tablename__ = "vehicle_passes"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "name", name="uq_vehicle_passes_vehicle_name"),
    )

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer, ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(100), nullable=False)     # свободное название/зона пропуска (не enum)
    status = Column(String(20), nullable=True)      # Да / Нет / Не требуется / Не выпускался / Нет данных
    expires_at = Column(Date, nullable=True)         # дата истечения
    note = Column(String(300), nullable=True)

    vehicle = relationship("Vehicle", back_populates="passes")
