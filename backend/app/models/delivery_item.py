from sqlalchemy import Column, Integer, String, Text, Numeric, ForeignKey, DateTime, Date, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class DeliveryItem(Base):
    """Phase 27: Физические поставки по накладным (УПД/ТТН) и ручное сопоставление с договором."""
    __tablename__ = "delivery_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(
        Integer, ForeignKey("purchases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contract_item_id = Column(
        Integer, ForeignKey("contract_items.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    purchase_item_id = Column(
        Integer, ForeignKey("purchase_items.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    name = Column(Text, nullable=False)
    unit = Column(String(50), nullable=True)
    qty = Column(Numeric(14, 4), nullable=False, default=0, server_default=text("0"))
    unit_price = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))
    total = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))
    delivery_date = Column(Date, nullable=True)
    doc_number = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="pending", server_default=text("'pending'"))
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    purchase = relationship("Purchase", backref="delivery_items")
    contract_item = relationship("ContractItem")
    purchase_item = relationship("PurchaseItem")
    product = relationship("Product")
