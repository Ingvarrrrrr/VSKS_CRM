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
    item_type = Column(String(20), nullable=True)  # товар / услуга / работа
    amount = Column(Numeric(15, 2), nullable=True)
    # Цена ЗА ЕДИНИЦУ (владелец, 2026-09-02): «Я не хочу указывать количество
    # услуг точно, я знаю сумму (200 000) и знаю, что это примерно 20 услуг —
    # не надо автоматически делить сумму на количество и препятствовать
    # закупке 21-й услуги». Если заполнена — план полноценный: итог = quantity
    # × unit_price, контроль превышения (assert_tz_not_over_plan, feo_plan.py)
    # проверяет и количество, и цену за единицу, и сумму, как раньше. Если
    # NULL — amount является ИТОГОВОЙ суммой сама по себе, quantity считается
    # ОРИЕНТИРОВОЧНЫМ и НЕ ограничивается; единственное ограничение — сумма.
    # ПОСЛАБЛЕНИЕ (осознанное, не регресс): позиции, заведённые ДО появления
    # этого поля, имеют unit_price=NULL и автоматически попадают в этот же
    # «мягкий» режим — раньше по ним assert_tz_not_over_plan вычисляла цену за
    # единицу как amount/quantity и ограничивала её. См. миграцию
    # z1a2b3c4d5e6_feo_planned_item_unit_price.py.
    unit_price = Column(Numeric(15, 2), nullable=True)
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
    # Происхождение плановой позиции (владелец, 2026-09-01): «это плановая позиция
    # в соответствии с ФЭО, или только в соответствии с нашим внутренним планом, а
    # в ФЭО разбивки не было» — ДВЕ НЕЗАВИСИМЫЕ галочки (не переключатель!), обе
    # могут быть True/False одновременно, это осознанно (владелец явно просил
    # «две галочки», не одно поле-enum). Смысл: is_feo_breakdown — жёсткая
    # построчная разбивка ФЭО существует (напр. «карандаши»), покупать будут
    # именно это, отчётность строгая; is_internal_plan — в ФЭО была только более
    # широкая категория (напр. «канцтовары») или позиции вообще не было, состав
    # придумали сами. Правка — та же матрица доступа, что и у остальных полей
    # PUT /feo-planned-items/{id} (вкладка feo_categories либо wish.edit_feo, см.
    # app/routers/feo_planned_items.py::_check_planned_item_write_access) — новых
    # прав не заводим. Бэкфилл существующих строк — см. миграцию
    # aa1b2c3d4e5f_feo_planned_item_origin.py.
    is_feo_breakdown = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    is_internal_plan = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))

    feo_category = relationship(
        "FeoCategory",
        backref=backref("planned_items", cascade="all, delete-orphan", passive_deletes=True),
    )
