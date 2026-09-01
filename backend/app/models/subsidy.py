from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Text, Boolean, Numeric, DateTime, func
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
    require_planned_dates = Column(Boolean, nullable=False, server_default='true')  # обязательность даты потребности
    # Владелец (2026-08-30): порог предупреждения «сумма заказанного приближается
    # к потолку субсидии» — настраиваемый НА КАЖДОЙ субсидии, умолчание 90%.
    # Потолок = calculate_budget_from_categories (тот же источник, что и жёсткий
    # гейт PLAN_OVER_SUBSIDY_CEILING). См. app.services.feo_plan.calculate_ceiling_forecast*.
    ceiling_warn_percent = Column(Numeric(5, 2), nullable=True)  # None → фактическое умолчание 90 применяется в сервисе
    # Fabrikant: номер соглашения о субсидии (для документов закупки)
    agreement_number = Column(String(200), nullable=True)
    # Черновые субсидии (план C1/C2, владелец 2026-09-01): любой сотрудник может
    # создать субсидию-черновик и работать над ней вместе с участниками, но к
    # ней нельзя привязывать заявки/закупки/договоры, пока администратор её не
    # утвердит. Один флаг состояния — 'draft' | 'approved', никаких цепочек
    # согласования. Существующие субсидии backfill-нуты в 'approved' миграцией.
    status = Column(String(20), nullable=False, server_default='draft')
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
    feo_categories = relationship("FeoCategory", back_populates="subsidy")
    approvers = relationship("SubsidyApprover", back_populates="subsidy", order_by="SubsidyApprover.order_num", cascade="all, delete-orphan")
    contractor_overrides = relationship("SubsidyContractorOverride", back_populates="subsidy", cascade="all, delete-orphan")