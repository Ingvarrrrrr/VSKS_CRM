"""История актуализации цены товара (владелец, 2026-08-29).

Каждый вызов app.services.price_actualization.actualize_product_price
пишет сюда одну строку — снапшот цены на момент актуализации, источник
(договор / КП / ручной ввод / импорт / автомониторинг ссылок) и кто это
сделал. Используется для отображения истории цены в карточке товара
(GET /api/products/{id}/price-history).
"""
from sqlalchemy import Column, Integer, String, Numeric, Date, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Numeric(15, 2), nullable=True)
    source = Column(String(20), nullable=True)  # 'contract' | 'kp' | 'manual' | 'import' | 'monitoring'
    # String(1000) (владелец, 26.10.2026) — раньше 300: ссылки на страницу
    # товара у части магазинов (vseinstrumenti.ru с utm-параметрами и т.п.)
    # доходят до 607 символов на реальных файлах каталога GALA — 300
    # обрезало бы запись (миграция z2a3b4c5d6e7_widen_price_source_ref.py).
    source_ref = Column(String(1000), nullable=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    collected_at = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Средняя по региону и партии (clever-bouncing-lantern.md, Часть 2):
    # region — субъект РФ МЕСТА ПОСТАВКИ (Purchase.delivery_region,
    # нормализован app.services.ru_regions.canonical_region_name), НЕ юр.
    # адрес организации — нет места поставки → region=NULL, точка идёт только
    # в расчёт без фильтра. quantity/unit — количество и единица позиции
    # закупки на момент фиксации точки (для фильтра по партии и по единице
    # товара). purchase_item_id — ссылка на конкретную позицию: пишется один
    # раз (уникальный индекс ix_product_price_history_purchase_item_id_unique,
    # WHERE purchase_item_id IS NOT NULL) — защита от повторной записи той же
    # позиции при повторном запуске досчёта/перехода статуса.
    region = Column(String(100), nullable=True)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    purchase_item_id = Column(Integer, ForeignKey("purchase_items.id", ondelete="SET NULL"), nullable=True)
