from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric, Boolean,
    ForeignKey, Text, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BankStatementImport(Base):
    """Журнал прогонов импорта Excel-выписок банка/казначейства."""
    __tablename__ = "bank_statement_imports"

    id = Column(Integer, primary_key=True, index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Этап 1 (SaaS-изоляция): орг, к которой относится прогон. Проставляется
    # по субсидии первой опознанной строки (basis_doc_number). Может остаться
    # NULL если ни одна строка прогона не опознана — видна только account-admin.
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    file_name = Column(String(500))
    sheet_name = Column(String(200))
    rows_total = Column(Integer, default=0)
    rows_imported = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    rows_matched = Column(Integer, default=0)
    rows_unmatched = Column(Integer, default=0)
    rows_dup = Column(Integer, default=0)
    # Этап 1: сколько строк прогона не удалось привязать к субсидии
    # (basis_doc_number не найден ни в одной Subsidy) — subsidy_id/org_id остались NULL.
    rows_no_subsidy = Column(Integer, default=0)
    # processing | done | error
    status = Column(String(20), default="processing")
    error_message = Column(Text, nullable=True)

    uploader = relationship("User", foreign_keys=[uploaded_by_id])
    # Этап 1: партия удаляется автоматически после успешного импорта, но платежи
    # ДОЛЖНЫ остаться (FK bank_payments.import_id теперь ON DELETE SET NULL).
    # cascade="delete-orphan" тут раньше заставлял ORM удалять BankPayment вместе
    # с партией — убран; passive_deletes=True отдаёт SET NULL целиком на откуп БД.
    payments = relationship("BankPayment", back_populates="import_run",
                            lazy="selectin", passive_deletes=True)


class BankPayment(Base):
    """Одна строка из импортированной выписки.

    raw_json хранит все колонки файла {header_norm: value} для аудита.
    Одна строка xlsx = один платёж по одному договору.
    """
    __tablename__ = "bank_payments"

    id = Column(Integer, primary_key=True, index=True)
    # Этап 1: партия импорта удаляется автоматически после успешного прогона
    # (только журнал строк остаётся) — поэтому FK больше не CASCADE, а SET NULL,
    # иначе автоудаление партии снесло бы и сами платежи.
    import_id = Column(Integer, ForeignKey("bank_statement_imports.id", ondelete="SET NULL"), nullable=True)

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
    # Удобные поля для SQL-фильтров (дублируют parsed_documents.contracts[0])
    parsed_contract_number = Column(String(200))
    parsed_contract_date = Column(Date)
    parsed_kbk = Column(String(50))

    # Все документы из назначения платежа: {contracts:[], acts:[], invoices:[], upd:[], ttn:[], registry:[]}
    parsed_documents = Column(JSONB, nullable=True)

    # Колонка «Документ-основание» (соглашение о субсидии)
    basis_doc_text = Column(Text, nullable=True)
    basis_doc_number = Column(String(100), nullable=True)
    basis_doc_date = Column(Date, nullable=True)

    # Шифр субсидии из колонки «Аналитический код раздела плательщика/Код субсидии (цели)»
    subsidy_code = Column(String(50), nullable=True, index=True)

    # Этап 3: код направления расходования целевых средств (КРЦС) — вторая
    # часть в скобках назначения платежа «(711К0232001;0200032)», либо из
    # колонок «Код расходов»/«Детализированный код расходов». parsed_kbk
    # хранит только первую часть (КБК/код цели) — expense_code её не дублирует.
    expense_code = Column(String(10), nullable=True, index=True)

    # Идентификатор документа из одноимённой колонки казначейской выгрузки —
    # устойчивый natural key платёжки (в отличие от source_row_hash, который
    # ловит дубли только если строка побайтово идентична). Этап 1.
    external_doc_id = Column(String(100), nullable=True)

    raw_json = Column(JSONB, default=dict)

    # SHA-256 от всей xlsx-строки (нормализованной); NULL для legacy записей до Phase 22 dedup.
    # Остаётся запасным ключом дедупликации для выгрузок без «Идентификатора документа».
    source_row_hash = Column(String(64), nullable=True, unique=True, index=True)

    # Match state
    matched_contractor_id = Column(Integer, ForeignKey("contractors.id"), nullable=True)
    matched_contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    matched_purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True, index=True)
    matched_subsidy_id = Column(Integer, ForeignKey("subsidies.id"), nullable=True, index=True)
    matched_confirmed = Column(Boolean, default=False, nullable=False)

    # Этап 1: прямая привязка к субсидии/орг по basis_doc_number (независимо от
    # matched_* — та цепочка требует сначала опознанного контрагента и часто
    # остаётся NULL для платежей физлицам/авансовых). NULL = соглашение не опознано.
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    import_run = relationship("BankStatementImport", back_populates="payments")
    matched_contractor = relationship("Contractor", foreign_keys=[matched_contractor_id])
    matched_contract = relationship("Contract", foreign_keys=[matched_contract_id])
    matched_subsidy = relationship("Subsidy", foreign_keys=[matched_subsidy_id])
    subsidy = relationship("Subsidy", foreign_keys=[subsidy_id])
    payments = relationship("Payment", back_populates="bank_payment",
                            cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_bank_payment_payee_inn", "payee_inn"),
        Index("ix_bank_payment_contract_number", "parsed_contract_number"),
        Index("ix_bank_payment_matched", "matched_confirmed"),
        Index(
            "ix_bank_payment_external_doc_id", "external_doc_id",
            unique=True, postgresql_where=(external_doc_id.isnot(None)),
        ),
    )
