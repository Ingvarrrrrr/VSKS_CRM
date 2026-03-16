from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="employee")  # superadmin/org_admin/manager/employee
    full_name = Column(String(255))
    city = Column(String(100))
    department = Column(String(200), nullable=True)  # Отдел (единый источник правды)
    position = Column(String(200), nullable=True)    # Должность (единый источник правды)
    phone = Column(String(30), nullable=True)         # Телефон (+7...)
    telegram_id = Column(String(100), nullable=True)  # Telegram username или chat_id
    avatar = Column(String(20), nullable=True)        # Аватарка (id из набора)
    email = Column(String(255), unique=True, nullable=True)
    is_email_confirmed = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(64), nullable=True)
    password_reset_token = Column(String(64), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    signature_image = Column(Text, nullable=True)  # base64 PNG подписи пользователя
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    organization = relationship("Organization", back_populates="users")
