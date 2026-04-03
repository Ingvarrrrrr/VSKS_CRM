from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

class Contractor(Base):
    __tablename__ = "contractors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    full_name = Column(String(1000), nullable=True)
    inn = Column(String(12))
    kpp = Column(String(9))
    address = Column(Text)
    contact_person = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    org_phone = Column(String(50))
    org_email = Column(String(255))
    bank_details = Column(Text)
    # Contract document fields
    signatory = Column(String(255))
    signatory_basis = Column(String(500))
    postal_address = Column(Text)
    ogrn = Column(String(20))
    settlement_account = Column(String(100))
    bank_name = Column(String(500))
    bik = Column(String(20))
    correspondent_account = Column(String(100))
    org_type = Column(String(50))  # Юр.лицо / ИП / Самозанятый / Физ.лицо
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    # Категории товаров (ручной ввод): ["Компьютеры", "Мебель"] или ["Все"]
    manual_product_categories = Column(JSONB, nullable=True, default=list)
