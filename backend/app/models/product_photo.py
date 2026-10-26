"""Байты фото товара — отдельная таблица (владелец, 26.10.2026): фото
носят информационный характер и не должны раздувать ежедневный бэкап БД
(`pg_backup.sh` исключает её data из основного дампа, см.
scripts/ops/pg_backup.sh), поэтому bytea вынесен из products.photo_data сюда.

products.photo_mime/photo_size остаются на Product как дёшевый кэш для
has_photo()/списков (ПРАВИЛО №6 — одна и та же пара полей, что и раньше, не
плодить второй признак наличия фото) — пишутся и читаются ТОЛЬКО через
app/services/product_photo_store.py.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, LargeBinary
from app.database import Base


class ProductPhoto(Base):
    __tablename__ = "product_photos"

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    data = Column(LargeBinary, nullable=False)
    mime = Column(String(50), nullable=True)
    size = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=True)
