from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True, index=True)
    row_number = Column(Integer)
    purchase_number = Column(Integer)
    order_number = Column(String(100))
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id"))
    item_type = Column(String(20))  # товар / услуга
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
    status = Column(String(20), default="planned")  # planned/confirmed/contracted/delivered/paid

    feo_category = relationship("FeoCategory")
    contractor = relationship("Contractor")
    contract = relationship("Contract", back_populates="purchases")
