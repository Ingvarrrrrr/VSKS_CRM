from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base

class FeoCategory(Base):
    __tablename__ = "feo_categories"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    level = Column(Integer, nullable=False)  # 1=направление расходов, 2=тип расходов, 3=конкретизированный
    sort_order = Column(Integer, nullable=True)  # порядок среди соседей (NULL = по id)
    name = Column(String(500), nullable=False)
    code = Column(String(50))
    appendix = Column(String(100), nullable=True)  # Номер приложения (например, "Прил. 2")
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)  # Пояснение: что входит в направление расходов
    # Итоговая сумма строки по документу ФЭО (ручное или NULL = авто из детей).
    # Заданный на родителе ОТМЕНЯЕТ авторасчёт по детям (см. feoEffectiveFor во фронте).
    budget = Column(Numeric(15, 2), nullable=True)
    feo_quantity = Column(Numeric(15, 2), nullable=True)  # Количество по ФЭО — заложено в документе ФЭО
    feo_unit = Column(String(50), nullable=True)  # Ед. изм. по ФЭО — заложено в документе ФЭО
    feo_amount = Column(Numeric(15, 2), nullable=True)  # Стоимость за ед. по документу ФЭО; NULL = авто из детей
    planned_quantity = Column(Numeric(15, 2), nullable=True)  # NULL = авто из детей; значение = ручной (CRM-план)
    # Плановая стоимость ЗА ЕДИНИЦУ (NULL = авто из детей); итог = planned_quantity × planned_amount
    planned_amount = Column(Numeric(15, 2), nullable=True)
    unit = Column(String(50), nullable=True)  # ед. измерения для planned_quantity (шт, кг, компл.) (CRM-план)
    # Владелец, план zany-fluttering-mountain.md (2026-08-13): переключатель способа
    # расчёта плана категории — раньше способ УГАДЫВАЛСЯ по тому, пустые ли поля
    # planned_quantity/planned_amount (см. app.services.feo_plan.compute_feo_plan_tree),
    # из-за чего правило «план разошёлся с вручную заданным» срабатывало на пустом месте.
    # 'planned_items' (умолчание) — план узла = Σ активных плановых позиций категории;
    # 'manual_sum' — план узла = manual_plan_amount, введённая ОДНИМ полем сумма (без
    # количества/цены за единицу).
    plan_source = Column(String(20), nullable=False, server_default='planned_items')
    # Плановая сумма ЦЕЛИКОМ (не за единицу) для plan_source='manual_sum'. Бэкфилл
    # миграции q5r6s7t8u9v0: у листьев со старым форматом (planned_quantity×planned_amount
    # оба > 0) = их произведение.
    manual_plan_amount = Column(Numeric(15, 2), nullable=True)
    parent = relationship("FeoCategory", remote_side=[id], backref="children")
    subsidy = relationship("Subsidy", back_populates="feo_categories")
