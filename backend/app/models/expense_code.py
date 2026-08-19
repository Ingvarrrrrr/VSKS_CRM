from sqlalchemy import Column, String, Text, Boolean
from app.database import Base


class ExpenseCode(Base):
    """Справочник кодов направления расходования целевых средств (КРЦС).

    code — «0200» (укрупнённый, 4 знака) или «0200032» (детализированный,
    4+3 знака). parent_code — укрупнённый код для детализированной записи
    (NULL для укрупнённых). kind — грубая классификация назначения платежа
    (товар/услуга/работа/персонал/налог/аванс/командировка/накладные/прочее),
    используется для авто-подсказки типа позиции. is_procurement — относится
    ли код к закупкам товаров/работ/услуг (0200/0300) в отличие от налогов,
    зарплаты и т.п.
    """
    __tablename__ = "expense_codes"

    code = Column(String(10), primary_key=True)
    parent_code = Column(String(10), nullable=True, index=True)
    name = Column(Text, nullable=False)
    kind = Column(String(20), nullable=True)
    is_procurement = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
