from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.database import Base

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True, index=True)
    row_number = Column(Integer)
    purchase_number = Column(Integer)
    order_number = Column(String(100))
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id"))
    item_type = Column(String(20))
    item_name = Column(String(500))
    contractor_id = Column(Integer, ForeignKey("contractors.id"))
    planned_quantity = Column(Numeric(15, 4))
    unit = Column(String(50))
    planned_unit_price = Column(Numeric(15, 2))
    planned_total_price = Column(Numeric(15, 2))
    confirmed = Column(Boolean, default=False)
    final_unit_price = Column(Numeric(15, 2))
    final_total_amount = Column(Numeric(15, 2))
    delivery_payment_amount = Column(Numeric(15, 2))
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    subsidy_id = Column(Integer, ForeignKey("subsidies.id"))
    status = Column(String(20), default="planned")

    # Phase 1: new fields
    contract_number = Column(String(100))
    contract_date = Column(Date)
    registry_number = Column(String(100))
    purchase_method = Column(String(50))  # 'single' | 'competitive'
    nmck = Column(Numeric(15, 2))
    contract_price = Column(Numeric(15, 2))
    economy = Column(Numeric(15, 2))
    price_increase = Column(Numeric(15, 2))
    execution_term = Column(Date)
    execution_term_changed = Column(Date)
    delivery_date = Column(Date)
    country_origin = Column(String(100))
    subject = Column(String(500))
    acceptance_doc_name = Column(String(200))
    acceptance_doc_date = Column(Date)
    acceptance_doc_number = Column(String(100))
    acceptance_doc_amount = Column(Numeric(15, 2))
    payment_doc_number = Column(String(100))
    payment_doc_date = Column(Date)
    payment_amount = Column(Numeric(15, 2))
    payment_federal = Column(Numeric(15, 2))
    purchase_contract_type = Column(String(50), nullable=True)  # single / framework_cumulative / framework_with_amount
    purchase_basis = Column(String(50), nullable=True)  # 'plan_schedule' | 'service_note'
    responsible_person = Column(String(500), nullable=True)

    feo_category = relationship("FeoCategory")
    contractor = relationship("Contractor")
    contract = relationship("Contract", back_populates="purchases")
    total_nmck = Column(Numeric(15, 2))
    items = relationship("PurchaseItem", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
    files = relationship("PurchaseFile", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
