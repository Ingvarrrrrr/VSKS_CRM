from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.database import Base


class ApprovalSignatureKey(Base):
    __tablename__ = "approval_signature_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    algorithm = Column(String(100), nullable=False, default="GOST-34.10-2018")
    public_key = Column(Text, nullable=True)
    encrypted_private_key = Column(Text, nullable=True)
    certificate = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
