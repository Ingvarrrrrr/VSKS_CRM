from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base


class WishItem(Base):
    __tablename__ = "wish_items"

    id = Column(Integer, primary_key=True, index=True)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(Text, nullable=False)
    item_type = Column(String(20), default="товар")  # товар / услуга / работа
    quantity = Column(Numeric(15, 4), default=1)
    unit = Column(String(50), default="шт")
    unit_price = Column(Numeric(15, 2), default=0)
    total_price = Column(Numeric(15, 2), default=0)
    country_origin = Column(String(100), default="Россия")

    wish = relationship("Wish", back_populates="items")
