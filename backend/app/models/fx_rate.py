"""Курсы валют ЦБ РФ (владелец, 2026-08-29).

Владелец: «Дополнительный критерий — курс доллара к рублю: если USD/RUB
изменился более чем на 10%, срок актуальности сокращается до месяца».
Заполняется app.services.fx_rates.refresh_cbr_rates (раз в сутки, non-fatal
если ЦБ недоступен — см. lifespan в app/__init__.py).
"""
from sqlalchemy import Column, Integer, String, Date, Numeric, UniqueConstraint
from app.database import Base


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("code", "rate_date", name="uq_fx_rate_code_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(3), nullable=False)  # 'USD'
    rate_date = Column(Date, nullable=False)
    value = Column(Numeric(14, 6), nullable=False)
