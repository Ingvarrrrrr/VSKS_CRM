from sqlalchemy import Boolean, Column, Integer, String, Text, Numeric, ForeignKey, text
from sqlalchemy.orm import relationship
from app.database import Base


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    item_name = Column(Text, nullable=False)
    item_type = Column(String(20))
    quantity = Column(Numeric(15, 4))
    unit = Column(String(50))
    unit_price = Column(Numeric(15, 2))
    total_price = Column(Numeric(15, 2))
    final_unit_price = Column(Numeric(15, 2))
    final_total = Column(Numeric(15, 2))
    country_origin = Column(String(100), nullable=True)
    feo_planned_item_id = Column(Integer, ForeignKey("feo_planned_items.id", ondelete="SET NULL"), nullable=True)
    match_confirmed = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor_inn = Column(String(20), nullable=True)
    contractor_name = Column(String(500), nullable=True)
    vat_rate = Column(String(20), nullable=True)  # Phase 26-U-3: per-item НДС ставка

    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")
    feo_planned_item = relationship("FeoPlannedItem")
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
