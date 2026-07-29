from sqlalchemy import Column, Integer, String, Text, ForeignKey, Date
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
    # ГПХ-поля для физ.лица (используются в шаблонах contract_gph_individual ±RID)
    passport_series = Column(String(10), nullable=True)
    passport_number = Column(String(20), nullable=True)
    passport_issuer = Column(Text, nullable=True)
    passport_issued_date = Column(Date, nullable=True)
    snils = Column(String(20), nullable=True)
    registration_address = Column(Text, nullable=True)
    birth_date = Column(Date, nullable=True)
    website = Column(String(255), nullable=True)
    registration_date = Column(Date, nullable=True)
    okpo = Column(String(20), nullable=True)
    okved = Column(String(50), nullable=True)
    treasury_account = Column(String(50), nullable=True)
    single_treasury_account = Column(String(50), nullable=True)
    signatory_position = Column(String(255), nullable=True)
    signatory_last_name = Column(String(100), nullable=True)
    signatory_first_name = Column(String(100), nullable=True)
    signatory_middle_name = Column(String(100), nullable=True)
    personal_account = Column(String(50), nullable=True)  # лицевой счёт Заказчика
