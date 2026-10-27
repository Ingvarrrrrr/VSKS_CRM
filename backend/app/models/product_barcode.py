"""Штрихкоды товара (владелец, 27.10.2026, решение: EAN-13/EAN-8/UPC-12/
GTIN-14 — главный ключ сведения одной карточки товара из разных магазинов).

У одного товара — несколько штрихкодов (упаковка/видели в разных местах
выгрузки); у одного штрихкода — несколько магазинов, у которых он встретился
(contractor_id, NULL — магазин строки не определён). UNIQUE(product_id,
barcode) — повтор того же штрихкода у того же товара не плодит вторую строку
(см. app/services/products_import_apply.py — запись «без дублей»).

Запись/чтение ТОЛЬКО через:
  - app/services/products_import_apply.py (импорт каталога),
  - app/services/product_merge.py (перенос на winner при слиянии),
  - app/services/products_import_match.py (сопоставление строки импорта),
  - scripts/merge_by_barcode.py (пакетное слияние уже загруженного каталога).
Вторую запись не заводить (ПРАВИЛО №6)."""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base


class ProductBarcode(Base):
    __tablename__ = "product_barcodes"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    barcode = Column(String(14), nullable=False)
    # Магазин, у которого ЭТОТ штрихкод встретился в выгрузке (владелец,
    # 27.10.2026) — NULL, если контрагент строки не определён (seller_inn
    # неизвестен/невалиден). Используется правилом «один магазин не продаёт
    # товар дважды» в products_import_match.py — та же семантика, что у
    # ProductPriceHistory.contractor_id.
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "barcode", name="uq_product_barcodes_product_barcode"),
        Index("ix_product_barcodes_barcode", "barcode"),
    )
