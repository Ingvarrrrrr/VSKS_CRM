from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)

    # Приложение №3 fields
    region = Column(String(200), nullable=True)             # B: Регион проведения
    date_from = Column(Date, nullable=True)                 # C: Период — начало
    date_to = Column(Date, nullable=True)                   # C: Период — конец
    order_decree = Column(String(500), nullable=True)       # D: Приказ о мероприятии
    planned_indicators = Column(Text, nullable=True)        # E: Плановые показатели
    actual_indicators = Column(Text, nullable=True)         # G: Фактические показатели
    media_link_1 = Column(String(500), nullable=True)       # H: СМИ ссылка 1
    media_link_2 = Column(String(500), nullable=True)       # H: СМИ ссылка 2
    media_link_3 = Column(String(500), nullable=True)       # H: СМИ ссылка 3

    subsidy = relationship("Subsidy", backref="events")
