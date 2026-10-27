from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Numeric, Date, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.purchase_category import product_purchase_categories

# Дефолт категории товара — одна константа (владелец, 2026-09-20: ручное
# добавление товара падало 422, т.к. ProductCreate требовала непустую
# категорию; теперь она опциональна, а пустая/None подменяется этим значением
# в routers/products.py — не два литерала 'Прочее', ПРАВИЛО №6).
DEFAULT_PRODUCT_CATEGORY = 'Прочее'


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    description_44fz = Column(Text, nullable=True)  # Описание для 44-ФЗ (интервалы характеристик)
    category = Column(String(200), nullable=False, default=DEFAULT_PRODUCT_CATEGORY)  # Категория товара из таблицы
    product_type = Column(String(200), nullable=True)  # Вид
    # Единица измерения (владелец, 2026-09-01): либо задана вручную в карточке,
    # либо дозаполняется бэкфиллом/импортом по правилу — единственная ЕИ, с
    # которой товар фигурировал в позициях закупок (см. app/services/product_unit.py);
    # при разнобое единиц остаётся NULL.
    unit = Column(String(50), nullable=True)
    # Упаковка (владелец, 14.10): когда unit — упаковочная единица
    # (app.services.units.is_pack_unit), сюда — сколько штук/других единиц
    # внутри одной упаковки и какая это внутренняя единица. У
    # неупаковочных unit — оба поля NULL (см. routers/products.py —
    # очищаются при смене unit на неупаковочный).
    pack_quantity = Column(Numeric(14, 3), nullable=True)
    pack_unit = Column(String(50), nullable=True)
    # Тип товара каталога — "товар"/"услуга"/"работа" (владелец, 21.09, раздел
    # W2 плана corrections-21-09.md: третье значение добавлено, чтобы
    # соответствовать типу плановой позиции ФЭО). Допустимые значения — ЕДИНЫЙ
    # источник app.services.item_types.ITEM_TYPES (ПРАВИЛО №6), тот же набор,
    # что и у FeoPlannedItem.item_type; сюда автозаписывается из плановой
    # позиции через apply_item_type_to_product (sync_product_kind=true).
    item_kind = Column(String(20), default="товар")
    is_reusable = Column(Boolean, default=True)  # Многоразовое или одноразовое
    photo_url = Column(String(1000), nullable=True)  # Внешняя ссылка (маркетплейс) — источник правды для повторного скачивания
    photo_link = Column(String(1000), nullable=True)  # Альтернативная ссылка на фото
    clarification_link = Column(String(1000), nullable=True)  # Уточнющая ссылка
    # Бинарное хранение фото (Phase 17.1-08) вынесено в отдельную таблицу
    # product_photos (владелец, 26.10.2026 — не раздувать ежедневный бэкап БД
    # фотографиями; см. app/models/product_photo.py). Здесь остаётся только
    # дёшевый кэш метаданных — читать/писать ТОЛЬКО через
    # app/services/product_photo_store.py (ПРАВИЛО №6).
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
    # String(1000) (владелец, 26.10.2026) — как и ProductPriceHistory.source_ref,
    # ссылка на страницу товара (а не только № договора/КП) на реальных файлах
    # каталога GALA доходит до 607 символов.
    price_source_ref = Column(String(1000), nullable=True)  # № договора / «Запрос КП №N» / ссылка
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

    # Характеристики каталога (владелец, 26.10): карточка товара пока только
    # ПОКАЗЫВАЕТ эти поля (см. ProductFormDialog.vue), заполняет их позже
    # загрузчик из прайсов поставщиков (app/services/catalog_gala/).
    # Список объектов [{"name","value","unit"}], порядок как у поставщика.
    characteristics = Column(JSONB, nullable=True)
    manufacturer = Column(String(300), nullable=True)  # Производитель
    article = Column(String(200), nullable=True)  # Артикул/номер по каталогу поставщика

    feo_category = relationship("FeoCategory", backref="products")

    # Категории закупки (владелец, 2026-09-16) — НЕСКОЛЬКО, отдельный
    # справочник purchase_categories (см. app/models/purchase_category.py).
    # lazy="selectin": один доп. SELECT на весь результат запроса (не N+1) без
    # необходимости расставлять .options(selectinload(...)) в каждом из
    # многочисленных мест, где грузится Product (products.py, products_match.py,
    # products_import_apply.py, feo_planned_items_matching.py, ...).
    purchase_categories = relationship(
        "PurchaseCategory",
        secondary=product_purchase_categories,
        backref="products",
        lazy="selectin",
    )

    # Штрихкоды (владелец, 27.10.2026, app/models/product_barcode.py) —
    # lazy="selectin", тот же приём, что у purchase_categories выше (один
    # доп. SELECT на весь результат запроса, не N+1). Строки истории
    # читаются/пишутся ТОЛЬКО через products_import_apply.py/product_merge.py
    # (ПРАВИЛО №6) — здесь только связь для показа в ProductOut.barcodes.
    barcode_rows = relationship(
        "ProductBarcode",
        lazy="selectin",
        order_by="ProductBarcode.id",
    )