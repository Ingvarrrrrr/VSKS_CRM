from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric, Boolean,
    ForeignKey, Text, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BankStatementImport(Base):
    """Журнал прогонов импорта Excel-выписок банка/казначейства."""
    __tablename__ = "bank_statement_imports"

    id = Column(Integer, primary_key=True, index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    file_name = Column(String(500))
    sheet_name = Column(String(200))
    rows_total = Column(Integer, default=0)
    rows_imported = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    rows_matched = Column(Integer, default=0)
    rows_unmatched = Column(Integer, default=0)
    rows_dup = Column(Integer, default=0)
    # processing | done | error
    status = Column(String(20), default="processing")
    error_message = Column(Text, nullable=True)

    uploader = relationship("User", foreign_keys=[uploaded_by_id])
    payments = relationship("BankPayment", back_populates="import_run",
                            cascade="all, delete-orphan", lazy="selectin")


class BankPayment(Base):
    """Одна строка из импортированной выписки.

    raw_json хранит все колонки файла {header_norm: value} для аудита.
    Если matched_confirmed=True — запись породила одну или N Payment-строк
    (multi-purchase split связан через source_row_hash).
    """
    __tablename__ = "bank_payments"

    id = Column(Integer, primary_key=True, index=True)
    import_id = Column(Integer, ForeignKey("bank_statement_imports.id", ondelete="CASCADE"))

    # Нормализованные поля (все опциональны — выписки разных банков неоднородны)
    payment_number = Column(String(100))
    payment_date = Column(Date)
    execution_datetime = Column(DateTime, nullable=True)
    status = Column(String(100))
    amount = Column(Numeric(15, 2))

    payer_inn = Column(String(20))
    payer_kpp = Column(String(20))
    payer_name = Column(String(500))
    payer_account = Column(String(50))

    payee_inn = Column(String(20))
    payee_kpp = Column(String(20))
    payee_name = Column(String(500))
    payee_account = Column(String(50))
    payee_bik = Column(String(20))
    payee_bank = Column(String(500))

    purpose_text = Column(Text)
    parsed_contract_number = Column(String(200))
    parsed_contract_date = Column(Date)
    parsed_kbk = Column(String(50))

    raw_json = Column(JSONB, default=dict)

    # Match state
    matched_contractor_id = Column(Integer, ForeignKey("contractors.id"), nullable=True)
    matched_contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    matched_confirmed = Column(Boolean, default=False, nullable=False)

    # Все строки split одного платёжного документа имеют одинаковый hash
    source_row_hash = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    import_run = relationship("BankStatementImport", back_populates="payments")
    matched_contractor = relationship("Contractor")
    matched_contract = relationship("Contract")
    payments = relationship("Payment", back_populates="bank_payment",
                            cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint(
            "payment_number", "payment_date", "payer_inn", "amount", "parsed_contract_number",
            name="uq_bank_payment_natural",
        ),
        Index("ix_bank_payment_payee_inn", "payee_inn"),
        Index("ix_bank_payment_contract_number", "parsed_contract_number"),
        Index("ix_bank_payment_matched", "matched_confirmed"),
    )
