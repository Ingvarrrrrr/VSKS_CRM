"""История актуализации цены товара (владелец, 2026-08-29).

Каждый вызов app.services.price_actualization.actualize_product_price
пишет сюда одну строку — снапшот цены на момент актуализации, источник
(договор / КП / ручной ввод / импорт / автомониторинг ссылок) и кто это
сделал. Используется для отображения истории цены в карточке товара
(GET /api/products/{id}/price-history).
"""
from sqlalchemy import Column, Integer, String, Numeric, Date, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Numeric(15, 2), nullable=True)
    source = Column(String(20), nullable=True)  # 'contract' | 'kp' | 'manual' | 'import' | 'monitoring'
    source_ref = Column(String(300), nullable=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    collected_at = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
