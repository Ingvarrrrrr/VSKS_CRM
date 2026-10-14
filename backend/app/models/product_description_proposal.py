"""Предложения правок описания товара каталога (Этап В, план
item-tz-description.md, владелец 14.10.2026): «у позиции кнопка «предложить
в каталог»: без галочки — заявка на правку, принимает/отклоняет человек с
галочкой (с галочкой — сразу применяется, тоже с историей)». Создание/приём/
отклонение — app/services/product_description_proposals.py (ПРАВИЛО №6,
единая точка), эндпоинты — app/routers/product_description.py.
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class ProductDescriptionProposal(Base):
    __tablename__ = "product_description_proposals"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    # 'description' | 'description_44fz'
    field = Column(String(30), nullable=False)
    proposed_value = Column(Text, nullable=True)
    # Текст товара в каталоге НА МОМЕНТ подачи предложения — чтобы при
    # принятии увидеть, что каталог успел измениться (changed_since_proposal).
    current_value_at_proposal = Column(Text, nullable=True)
    # Откуда пришло предложение — позиция заявки/закупки (опционально,
    # кнопка «предложить в каталог» у позиции). Оба nullable — предложение
    # можно подать и без привязки к конкретной позиции.
    wish_item_id = Column(Integer, ForeignKey("wish_items.id", ondelete="SET NULL"), nullable=True)
    purchase_item_id = Column(Integer, ForeignKey("purchase_items.id", ondelete="SET NULL"), nullable=True)
    proposed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    proposed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # 'pending' | 'accepted' | 'rejected'
    status = Column(String(20), nullable=False, default="pending")
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_comment = Column(Text, nullable=True)

    product = relationship("Product")
    proposed_by_user = relationship("User", foreign_keys=[proposed_by])
    decided_by_user = relationship("User", foreign_keys=[decided_by])
