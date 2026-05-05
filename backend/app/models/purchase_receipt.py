from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Numeric, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from app.database import Base


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint(
            "fiscal_drive_number", "fiscal_document_number", "fiscal_sign",
            name="uq_receipt_fiscal",
        ),
    )

    id = Column(Integer, primary_key=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    # Fiscal triple
    fiscal_drive_number = Column(String(64))     # fn
    fiscal_document_number = Column(Integer)     # fd
    fiscal_sign = Column(String(32))             # fpd
    kkt_reg_id = Column(String(64))

    receipt_datetime = Column(DateTime)
    total_sum = Column(Numeric(15, 2))
    cash_sum = Column(Numeric(15, 2))
    ecash_sum = Column(Numeric(15, 2))
    prepaid_sum = Column(Numeric(15, 2))
    nds_sum = Column(Numeric(15, 2))

    seller_name = Column(String(500))
    seller_inn = Column(String(20))
    retail_place = Column(String(500))
    retail_place_address = Column(String(1000))
    operator = Column(String(200))
    operator_inn = Column(String(20))
    taxation_type = Column(Integer)

    source = Column(String(20))                  # json_import | qr_scan | manual
    raw_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())

    # Phase 23.7: passive_deletes ДОЛЖЕН быть на ОБОИХ сторонах relationship.
    # Раньше: backref="receipts" + passive_deletes=True (только child-side) →
    # SQLAlchemy ORM при db.delete(purchase) загружал Purchase.receipts (parent-side
    # БЕЗ passive_deletes) и пытался UPDATE purchase_receipts SET purchase_id=NULL
    # → NotNullViolationError, хотя в БД ON DELETE CASCADE.
    # Теперь backref(...) явно передаёт passive_deletes + cascade — БД делает CASCADE,
    # ORM не трогает receipts.
    purchase = relationship(
        "Purchase",
        backref=backref("receipts", passive_deletes=True, cascade="all, delete-orphan"),
        passive_deletes=True,
    )
