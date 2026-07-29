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
    parent = relationship("FeoCategory", remote_side=[id], backref="children")
    subsidy = relationship("Subsidy", back_populates="feo_categories")
