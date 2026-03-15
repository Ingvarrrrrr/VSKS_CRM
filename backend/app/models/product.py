from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Numeric, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id"), nullable=True)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    description_44fz = Column(Text, nullable=True)  # Описание для 44-ФЗ (интервалы характеристик)
    category = Column(String(200), nullable=True)  # Категория товара из таблицы
    product_type = Column(String(200), nullable=True)  # Вид
    is_reusable = Column(Boolean, default=True)  # Многоразовое или одноразовое
    photo_url = Column(String(1000), nullable=True)
    photo_link = Column(String(1000), nullable=True)  # Ссылка на фото
    clarification_link = Column(String(1000), nullable=True)  # Уточнющая ссылка
    is_active = Column(Boolean, default=True)
    price = Column(Numeric(10, 2), nullable=True)
    price_links = Column(JSONB, default=list, nullable=True)  # [{url, price}] — ссылки для сравнения цен

    # Контрактные цены — обновляются при переходе закупки в статус "contracted"
    contract_price = Column(Numeric(15, 2), nullable=True)
    contract_number = Column(String(100), nullable=True)
    contract_date = Column(Date, nullable=True)
    contract_org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    price_shared = Column(Boolean, default=False)  # делиться ценой с другими организациями

    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    feo_category = relationship("FeoCategory", backref="products")