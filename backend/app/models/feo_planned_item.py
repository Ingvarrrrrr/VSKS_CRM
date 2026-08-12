from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, DateTime, Date, ForeignKey, func, text
from sqlalchemy.orm import relationship, backref
from app.database import Base


class FeoPlannedItem(Base):
    __tablename__ = "feo_planned_items"

    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(500), nullable=False)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    payment_mode = Column(String(20), nullable=False, server_default='one_time')  # 'one_time' | 'monthly'
    planned_date = Column(Date, nullable=True)          # «когда потребуется» для one_time
    monthly_start_date = Column(Date, nullable=True)    # первый платёж для monthly
    months_count = Column(Integer, nullable=True)       # на сколько месяцев
    monthly_amount = Column(Numeric(15, 2), nullable=True)  # платёж за ОДИН месяц
    # Владелец (2026-08-12, «закупка сама становится планом»): позиция заведена
    # автоматически из закупки/заявки (app/services/plan_autoassign.py), а не
    # человеком — UI-признак, не гейт бизнес-логики (см. миграцию m8n9o0p1q2r3).
    auto_created = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    # Порядок позиций внутри категории (владелец просил менять их местами);
    # выдача сортируется sort_order NULLS LAST, id — см. GET /feo-planned-items/.
    sort_order = Column(Integer, nullable=True)

    feo_category = relationship(
        "FeoCategory",
        backref=backref("planned_items", cascade="all, delete-orphan", passive_deletes=True),
    )
