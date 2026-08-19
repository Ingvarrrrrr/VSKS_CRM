from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    document_number = Column(String(100))
    payment_purpose = Column(String(500))
    payment_date = Column(Date)
    amount = Column(Numeric(15, 2))

    # Phase 22: источник платежа из банковской выписки
    bank_payment_id = Column(
        Integer,
        ForeignKey("bank_payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    # True после явного подтверждения пользователем матча выписка↔закупка (=
    # «строка выписки разнесена на эту закупку»). НЕ означает «оплата прошла» —
    # см. confirmed_by_statement ниже. Ручной платёж (payment_source='manual')
    # больше НЕ ставит этот флаг при создании (владелец, 2026-08-19).
    matched_confirmed = Column(Boolean, default=False, nullable=False)

    # Владелец (2026-08-19): «поставленная человеком галочка, что платёж прошёл,
    # без подтверждения выпиской из казначейства, не является подтверждением,
    # что платёж прошёл» — два независимых факта, раньше смешанные в один флаг
    # matched_confirmed (который ручная форма тоже ставила в True).
    #
    #   payment_source        — кто завёл запись: 'manual' (человек — форма в
    #                            карточке закупки, импорт закупок из Excel) |
    #                            'statement' (платёж пришёл из казначейской
    #                            выписки, см. app/services/payment_lookup.py::attach
    #                            и app/services/purchase_payments.py::create_payments_from_bank).
    #   confirmed_by_statement — True, если платёж НАЙДЕН в выписке и разнесён
    #                            на закупку (для payment_source='statement' —
    #                            всегда True; для 'manual' — False, пока не
    #                            сопоставится с реальной строкой выписки — тогда
    #                            та же запись помечается confirmed_by_statement=True,
    #                            НЕ создаётся вторая, см. attach()/create_payments_from_bank()).
    #
    # app/services/purchase_payments.py::recompute_purchase_payments считает
    # Purchase.payment_amount ТОЛЬКО по confirmed_by_statement=True (реально
    # оплачено), Purchase.payment_amount_declared — по manual+не confirmed
    # (заявлено человеком, ждёт подтверждения). Автопереход закупки в статус
    # paid — только по подтверждённой сумме.
    payment_source = Column(String(20), nullable=False, default="manual", server_default="manual")
    confirmed_by_statement = Column(Boolean, nullable=False, default=False, server_default="false")

    # Третья очередь плана (Этап 4/5) — код расходов и основание платежа,
    # см. app/services/payment_basis.py (expense_code/extract_basis/basis_key).
    # Заполняются при разнесении платежа группы через app/services/payment_lookup.py::attach.
    expense_code = Column(String(10), nullable=True)
    basis_kind = Column(String(20), nullable=True)      # upd | act | invoice | waybill | registry | advance_report | contract | None
    basis_number = Column(String(100), nullable=True)
    basis_date = Column(Date, nullable=True)
    # Ключ «одно назначение — один платёж» (см. payment_basis.basis_key) — уникален
    # в паре с purchase_id (частичный индекс, см. миграцию), пока matched_confirmed.
    basis_key = Column(String(300), nullable=True)
    basis_label = Column(String(300), nullable=True)    # человекочитаемая подпись, напр. «УПД 6 от 20.02.2026»

    contract = relationship("Contract")
    purchase = relationship("Purchase")
    bank_payment = relationship("BankPayment", back_populates="payments")
