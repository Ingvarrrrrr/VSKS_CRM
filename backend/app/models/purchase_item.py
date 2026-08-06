from sqlalchemy import Boolean, Column, Integer, String, Text, Numeric, ForeignKey, text, Date
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
    # Снимок плана (Шаг 1, «план ≠ факт», zany-fluttering-mountain.md) — заполняется
    # при постановке позиции в план закупок (из заявки/импорта/ручного ввода) и
    # НЕ трогается после ухода закупки из статуса «План закупок» (заморозка ТЗ —
    # сама блокировка правки поля вводится Шагом 2, здесь только не портим снимок).
    # unit_price/total_price остаются «текущей» ценой ТЗ; planned_* — зафиксированный
    # план, который дерево ФЭО должно читать вместо мутирующей unit_price/total_price.
    planned_quantity = Column(Numeric(15, 4), nullable=True)
    planned_unit_price = Column(Numeric(15, 2), nullable=True)
    planned_total = Column(Numeric(15, 2), nullable=True)
    country_origin = Column(String(100), nullable=True)
    feo_planned_item_id = Column(Integer, ForeignKey("feo_planned_items.id", ondelete="SET NULL"), nullable=True)
    feo_category_id = Column(Integer, ForeignKey('feo_categories.id', ondelete='SET NULL'), nullable=True, index=True)
    match_confirmed = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor_inn = Column(String(20), nullable=True)
    contractor_name = Column(String(500), nullable=True)
    vat_rate = Column(String(20), nullable=True)  # Phase 26-U-3: per-item НДС ставка
    vat_amount = Column(Numeric(15, 2), nullable=True)      # import-vat-cols: сумма НДС по позиции
    total_with_vat = Column(Numeric(15, 2), nullable=True)  # import-vat-cols: стоимость с НДС
    receipt_id = Column(Integer, ForeignKey('purchase_receipts.id', ondelete='SET NULL'), nullable=True, index=True)  # Phase 26-BB
    needed_date = Column(Date, nullable=True)   # дата потребности per-item
    wish_item_id = Column(Integer, ForeignKey("wish_items.id", ondelete="SET NULL"), nullable=True)  # W1: hard link to source WishItem
    # false — позиция расходует план своего конечного элемента ФЭО; true — «сверх плана»,
    # прибавляется к плановой сумме (не вычитается из исходного лимита элемента).
    over_plan = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    # Стадия «Приняли» (5-я стадия жизненного цикла позиции, «в голубой обложке»):
    # заполняется автоматически при переходе закупки в delivered (из contract_items
    # по source_item_id, либо из самой purchase_items), правится вручную дальше.
    accepted_name = Column(Text, nullable=True)
    accepted_quantity = Column(Numeric(15, 4), nullable=True)
    accepted_unit = Column(String(50), nullable=True)

    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")
    feo_planned_item = relationship("FeoPlannedItem")
    feo_category = relationship("FeoCategory")
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
