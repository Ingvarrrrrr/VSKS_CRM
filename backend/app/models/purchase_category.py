"""Категории закупки — отдельный справочник (владелец, 2026-09-16).

У товара ДВЕ разных категории:
  - «категория товара» — Product.category, одна строка, ведётся как раньше;
  - «категории закупки» — НЕСКОЛЬКО штук из ЭТОГО справочника, которые владелец
    ведёт сам (пример: краги пожарного — категория товара «СИЗ», категории
    закупки «Пожарное оборудование» и «СИЗ»).

product_purchase_categories — чистая связь many-to-many (без своих полей),
PK — пара (product_id, purchase_category_id), ON DELETE CASCADE с обеих сторон
(удалили товар — удалилась связь; удалили категорию закупки — см. роутер:
удаление категории, привязанной к товарам, запрещено 409, поэтому в реальности
каскад по purchase_category_id не сработает, но объявлен для целостности).
"""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.database import Base

product_purchase_categories = Table(
    "product_purchase_categories",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("purchase_category_id", Integer, ForeignKey("purchase_categories.id", ondelete="CASCADE"), primary_key=True),
)


class PurchaseCategory(Base):
    __tablename__ = "purchase_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
