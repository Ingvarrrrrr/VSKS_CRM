from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Numeric, Date, DateTime, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    description_44fz = Column(Text, nullable=True)  # Описание для 44-ФЗ (интервалы характеристик)
    category = Column(String(200), nullable=False, default='Прочее')  # Категория товара из таблицы
    product_type = Column(String(200), nullable=True)  # Вид
    # Единица измерения (владелец, 2026-09-01): либо задана вручную в карточке,
    # либо дозаполняется бэкфиллом/импортом по правилу — единственная ЕИ, с
    # которой товар фигурировал в позициях закупок (см. app/services/product_unit.py);
    # при разнобое единиц остаётся NULL.
    unit = Column(String(50), nullable=True)
    item_kind = Column(String(20), default="товар")  # "товар" или "услуга"
    is_reusable = Column(Boolean, default=True)  # Многоразовое или одноразовое
    photo_url = Column(String(1000), nullable=True)  # Внешняя ссылка (маркетплейс) — источник правды для повторного скачивания
    photo_link = Column(String(1000), nullable=True)  # Альтернативная ссылка на фото
    clarification_link = Column(String(1000), nullable=True)  # Уточнющая ссылка
    # Бинарное хранение фото в БД (Phase 17.1-08). Один бэкап БД = все фото в сохранности.
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime = Column(String(50), nullable=True)
    photo_size = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    price = Column(Numeric(10, 2), nullable=True)
    price_links = Column(JSONB, default=list, nullable=True)  # [{url, price}] — ссылки для сравнения цен

    # Контрактные цены — обновляются при переходе закупки в статус "contracted"
    contract_price = Column(Numeric(15, 2), nullable=True)
    contract_number = Column(String(100), nullable=True)
    contract_date = Column(Date, nullable=True)
    contract_org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    price_shared = Column(Boolean, default=False)  # делиться ценой с другими организациями

    # Актуализация цены (владелец, 2026-08-29): когда и откуда пришла текущая
    # цена товара. Используется для контроля устаревания (см.
    # app/services/price_freshness.py). Пишется через
    # app/services/price_actualization.py::actualize_product_price — единая
    # точка входа для ВСЕХ мест, где меняется product.price.
    price_updated_at = Column(DateTime, nullable=True)
    price_source = Column(String(20), nullable=True)  # 'contract' | 'kp' | 'manual' | 'import' | 'monitoring'
    price_source_ref = Column(String(300), nullable=True)  # № договора / «Запрос КП №N» / ссылка
    price_source_contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    price_ttl_days = Column(Integer, nullable=True)  # персональный override срока актуальности (дней)

    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    country_origin = Column(String(100), nullable=True, default="РФ")  # Страна производства (Приложение №3, кол. P)

    # ТЗ верификация
    tz_verified_at = Column(DateTime, nullable=True)
    tz_verified_by = Column(String(200), nullable=True)
    tz_44fz_verified_at = Column(DateTime, nullable=True)
    tz_44fz_verified_by = Column(String(200), nullable=True)

    # Кто и когда редактировал
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String(200), nullable=True)  # full_name пользователя

    # Примечание об импорте: кто загрузил данные, каким способом и когда
    import_note = Column(Text, nullable=True)

    feo_category = relationship("FeoCategory", backref="products")