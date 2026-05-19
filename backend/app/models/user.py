from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Date
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="employee")  # superadmin/account_owner/manager/employee
    full_name = Column(String(255))
    city = Column(String(100))
    department = Column(String(200), nullable=True)  # Отдел (единый источник правды)
    position = Column(String(200), nullable=True)    # Должность (единый источник правды)
    phone = Column(String(30), nullable=True)         # Телефон (+7...)
    work_phone = Column(String(30), nullable=True)    # Стационарный/рабочий телефон (Phase 18)
    telegram_id = Column(String(100), nullable=True)  # Telegram chat_id (числовой)
    max_chat_id = Column(String(100), nullable=True)  # MAX (VK) chat_id
    avatar = Column(String(20), nullable=True)        # Аватарка (id из набора)
    email = Column(String(255), unique=True, nullable=True)
    is_email_confirmed = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(64), nullable=True)
    password_reset_token = Column(String(64), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    signature_image = Column(Text, nullable=True)  # base64 PNG подписи пользователя
    profile_photo = Column(Text, nullable=True)    # base64 JPEG/PNG фото профиля
    inn = Column(String(12), nullable=True)          # ИНН физ. лица
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    can_publish = Column(Boolean, default=False, nullable=False, server_default="false")  # Разрешение на публикацию закупок
    exclude_from_directory = Column(Boolean, default=False, nullable=False, server_default="false")  # Не включать в справочник сотрудников

    # Phase 29 D-04: водительские данные (раскрываются при can_drive=True)
    can_drive = Column(Boolean, default=False, nullable=False, server_default="false")  # Может водить ТС
    license_series = Column(String(10), nullable=True)           # Серия ВУ
    license_number = Column(String(20), nullable=True)           # Номер ВУ
    license_categories = Column(String(50), nullable=True)       # Категории A,B,C,D,CE,M,...
    license_issued_at = Column(Date, nullable=True)              # Дата выдачи ВУ — _DATE_FIELDS plan 29-09
    license_expires_at = Column(Date, nullable=True)             # Срок действия ВУ — _DATE_FIELDS plan 29-09
    medical_cert_expires_at = Column(Date, nullable=True)        # Срок медсправки — _DATE_FIELDS plan 29-09

    organization = relationship("Organization", back_populates="users", foreign_keys=[org_id])

    @property
    def has_signature(self) -> bool:
        return bool(self.signature_image)

    @property
    def photo_url(self) -> str | None:
        return self.profile_photo or None
