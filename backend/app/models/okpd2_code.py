from sqlalchemy import Column, String, Text
from app.database import Base


class Okpd2Code(Base):
    __tablename__ = "okpd2_codes"

    code = Column(String(20), primary_key=True)
    name = Column(Text, nullable=False)
    section = Column(String(2), nullable=True)
