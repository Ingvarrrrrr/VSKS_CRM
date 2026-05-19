from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Subsidy(Base):
    __tablename__ = "subsidies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    year = Column(Integer, nullable=False)
    budget = Column(Float, nullable=False)
    calculated_budget = Column(Float, nullable=True)
    description = Column(String(2000), nullable=True)
    # Phase 19: large free-text agreement clause (федеральный бюджет / Росмолодёжь)
    agreement_text = Column(Text, nullable=True)
    # Phase 22: № и дата документа-основания (соглашения о субсидии) — для матчинга с банковской выпиской
    basis_doc_number = Column(String(100), nullable=True)
    basis_doc_date = Column(Date, nullable=True)
    # Phase 28: Реквизиты грантодателя для шаблонов договоров
    grantor_name = Column(String(200), nullable=True)    # "Российская Федерация" / "Тверская область"
    ministry_name = Column(String(300), nullable=True)   # "МИНИСТЕРСТВОМ МОЛОДЕЖНОЙ ПОЛИТИКИ РФ"
    # Phase 28: subsidy-specific clauses (пункты договора зависящие от субсидии — например раздельный учёт расходов)
    extra_contract_clause_1 = Column(Text, nullable=True)
    extra_contract_clause_2 = Column(Text, nullable=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
    feo_categories = relationship("FeoCategory", back_populates="subsidy")
    approvers = relationship("SubsidyApprover", back_populates="subsidy", order_by="SubsidyApprover.order_num", cascade="all, delete-orphan")
    contractor_overrides = relationship("SubsidyContractorOverride", back_populates="subsidy", cascade="all, delete-orphan")