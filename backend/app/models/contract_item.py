from sqlalchemy import Boolean, Column, Integer, String, Text, Numeric, ForeignKey, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ContractItem(Base):
    """Phase 27.1: промежуточный слой «фактически заказано по договору».

    Ground truth между purchase_items (ТЗ) и delivery_items (Phase 27 поставка).
    Создаётся LAZY через UI кнопки (D-01): «Скопировать из заявки» или «Импорт из файла/QR».
    """
    __tablename__ = "contract_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(
        Integer, ForeignKey("purchases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_item_id = Column(
        Integer, ForeignKey("purchase_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_id = Column(
        Integer, ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(Text, nullable=False)
    quantity = Column(Numeric(15, 4))
    unit = Column(String(50))
    unit_price = Column(Numeric(15, 2))
    total = Column(Numeric(15, 2))
    vat_rate = Column(String(20), nullable=True)  # Phase 27.1.17: НДС ставка ('22%', '10%', 'Без НДС', custom)
    match_confirmed = Column(
        Boolean, nullable=False, default=True, server_default=text("TRUE"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # item-forms-accommodation-transport.md: копия extra_attrs исходной
    # purchase_items (mirrors purchase_items.extra_attrs) — «скопировать из
    # заявки» переносит и её, иначе договор теряет поля спец-формы позиции.
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    purchase = relationship("Purchase", back_populates="contract_items")
    source_item = relationship("PurchaseItem", foreign_keys=[source_item_id])
    product = relationship("Product")
    contract = relationship("Contract")
