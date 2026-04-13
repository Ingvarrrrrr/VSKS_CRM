from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class FeoCategory(Base):
    __tablename__ = "feo_categories"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("feo_categories.id"), nullable=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id"), nullable=False)
    level = Column(Integer, nullable=False)  # 1=направление расходов, 2=тип расходов, 3=конкретизированный
    name = Column(String(500), nullable=False)
    code = Column(String(50))
    appendix = Column(String(100), nullable=True)  # Номер приложения (например, "Прил. 2")
    is_active = Column(Boolean, default=True)
    budget = Column(Numeric(15, 2), nullable=True)  # Финансирование по ФЭО (ручное или NULL = авто из детей)
    planned_quantity = Column(Numeric(15, 2), nullable=True)  # NULL = авто из детей; значение = ручной
    planned_amount = Column(Numeric(15, 2), nullable=True)  # Плановая сумма (NULL = авто из детей)
    unit = Column(String(50), nullable=True)  # ед. измерения для planned_quantity (шт, кг, компл.)
    parent = relationship("FeoCategory", remote_side=[id], backref="children")
    subsidy = relationship("Subsidy", back_populates="feo_categories")
