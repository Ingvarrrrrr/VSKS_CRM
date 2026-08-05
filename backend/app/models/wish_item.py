from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text, Date, Boolean, text
from sqlalchemy.orm import relationship
from app.database import Base


class WishItem(Base):
    __tablename__ = "wish_items"

    id = Column(Integer, primary_key=True, index=True)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(Text, nullable=False)
    item_type = Column(String(200), default="товар")  # товар / услуга / работа (фронт может слать описательный тип)
    quantity = Column(Numeric(15, 4), default=1)
    unit = Column(String(50), default="шт")
    unit_price = Column(Numeric(15, 2), default=0)
    total_price = Column(Numeric(15, 2), default=0)
    country_origin = Column(String(100), default="РФ")
    target_column_key = Column(String(200), nullable=True)  # Phase 13 D-04: kanban column override; falls back to product.category when null
    # B9: per-item FEO category link (mirroring purchase_items.feo_category_id)
    # TODO: ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS feo_category_id INTEGER REFERENCES feo_categories(id) ON DELETE SET NULL
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"), nullable=True)
    # Привязка к конкретной плановой позиции плана закупок (уровень 5 ФЭО, mirroring
    # purchase_items.feo_planned_item_id) — чтобы согласование заявки расходовало
    # уже запланированную строку, а не создавало новую (иначе план задваивается).
    feo_planned_item_id = Column(Integer, ForeignKey("feo_planned_items.id", ondelete="SET NULL"), nullable=True, index=True)
    needed_date = Column(Date, nullable=True)   # дата потребности per-item
    vat_rate = Column(String(20), nullable=True)  # per-item НДС ставка (mirrors purchase_items.vat_rate)
    # false — позиция расходует план своего конечного элемента ФЭО; true — «сверх плана»,
    # прибавляется к плановой сумме (mirrors purchase_items.over_plan)
    over_plan = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))

    wish = relationship("Wish", back_populates="items")
    product = relationship("Product", foreign_keys=[product_id])
