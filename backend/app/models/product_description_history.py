"""История изменений описания товара каталога (Этап В, план
item-tz-description.md, владелец 14.10.2026): «каждое изменение описания —
в историю (кто, когда, было/стало) + вернуть прежнее». Пишется ТОЛЬКО через
app.services.product_description_history.set_product_description (ПРАВИЛО
№6 — единственный писатель), читается в GET /api/products/{id}/description-history
(app/routers/product_description.py).
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class ProductDescriptionHistory(Base):
    __tablename__ = "product_description_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    # 'description' | 'description_44fz' — какое из двух текстовых полей товара
    field = Column(String(30), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # 'edit' (правка через PUT/PATCH, с галочкой) | 'proposal' (принятое
    # предложение) | 'revert' (откат) | 'fill_empty' (заполнение пустого
    # поля сотрудником без products.edit_catalog, 14.10.2026 Часть 1 плана)
    source = Column(String(20), nullable=False, default="edit")
    proposal_id = Column(
        Integer,
        ForeignKey("product_description_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )

    product = relationship("Product")
    user = relationship("User")
