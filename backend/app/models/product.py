from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id"), nullable=True)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(200), nullable=True)  # Категория товара из таблицы
    product_type = Column(String(200), nullable=True)  # Вид
    is_reusable = Column(Boolean, default=True)  # Многоразовое или одноразовое
    photo_url = Column(String(1000), nullable=True)
    photo_link = Column(String(1000), nullable=True)  # Ссылка на фото
    clarification_link = Column(String(1000), nullable=True)  # Уточнющая ссылка
    is_active = Column(Boolean, default=True)
    price = Column(Numeric(10, 2), nullable=True)  # Цена за единицу из Google Sheets
    
    feo_category = relationship("FeoCategory", backref="products")