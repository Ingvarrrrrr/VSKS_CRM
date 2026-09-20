"""Products, pricing, and dashboard summary schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

# Product
class PriceLink(BaseModel):
    url: str
    price: Optional[float] = None
    # Дата сбора цены по ссылке — читается _calc_price_from_links (было мёртвой
    # веткой: схема раньше отбрасывала поле, хотя парсер уже искал l.get("collected_at")).
    collected_at: Optional[str] = None


# ── Price freshness (владелец, 2026-08-29) ──────────────────────────────────
# Контракт с фронтом — см. app/services/price_freshness.py::evaluate docstring.
# Поля/имена менять нельзя без согласования.
class PriceFreshnessOut(BaseModel):
    is_stale: bool
    age_days: Optional[int] = None
    ttl_days: int
    base_ttl_days: int
    reason: str  # 'ok' | 'never' | 'expired' | 'fx'
    fx_change_pct: Optional[float] = None
    label: str

class PurchaseCategoryRef(BaseModel):
    """Категория закупки (владелец, 2026-09-16) — отдельный справочник от
    «категории товара» (Product.category, поле ниже). См. app.models.purchase_category."""
    id: int
    name: str
    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    feo_category_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    description_44fz: Optional[str] = None
    # Опционально (владелец, 2026-09-20): ручное добавление товара падало 422
    # на пустой категории — пусто/None допускается на входе, роутер создания
    # подставляет app.models.product.DEFAULT_PRODUCT_CATEGORY.
    category: Optional[str] = None
    product_type: Optional[str] = None
    unit: Optional[str] = None  # Единица измерения (владелец, 2026-09-01)
    item_kind: Optional[str] = "товар"  # "товар" или "услуга"
    is_reusable: Optional[bool] = True
    photo_url: Optional[str] = None
    photo_link: Optional[str] = None
    clarification_link: Optional[str] = None
    is_active: bool = True
    price: Optional[Decimal] = None
    price_links: List[PriceLink] = []
    country_origin: Optional[str] = "РФ"
    # Категории закупки (владелец, 2026-09-16) — несколько, id из
    # purchase_categories; сохраняется отдельно от остальных полей (см.
    # routers/products.py — не колонка Product, а M2M связь).
    purchase_category_ids: List[int] = []

class ProductOut(ProductCreate):
    id: int
    # Override: in the DB old rows may still have category=NULL until the
    # n1o2p3q4r5s6 backfill migration is applied. ProductCreate enforces
    # non-empty on input, but responses must tolerate legacy NULLs.
    category: Optional[str] = None
    contract_price: Optional[Decimal] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    contract_org_id: Optional[int] = None
    price_shared: bool = False
    tz_verified_at: Optional[datetime] = None
    tz_verified_by: Optional[str] = None
    tz_44fz_verified_at: Optional[datetime] = None
    tz_44fz_verified_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    import_note: Optional[str] = None
    # Phase 17.1-08 — photo bytea storage. We expose only metadata here,
    # never the raw bytes (would bloat API responses to MBs per product).
    has_photo: bool = False
    photo_size: Optional[int] = None
    photo_mime: Optional[str] = None
    # Актуализация цены (владелец, 2026-08-29)
    price_updated_at: Optional[datetime] = None
    price_source: Optional[str] = None
    price_source_ref: Optional[str] = None
    price_source_contractor_id: Optional[int] = None
    price_ttl_days: Optional[int] = None
    price_freshness: Optional[PriceFreshnessOut] = None
    # Категории закупки (владелец, 2026-09-16) — читаются из relationship
    # Product.purchase_categories (lazy="selectin", см. app/models/product.py).
    purchase_categories: List[PurchaseCategoryRef] = []
    # Средняя цена (владелец, 2026-09-16) — одна функция-источник
    # app.services.product_price_stats.compute_price_stats; проставляется
    # роутером ОДНИМ запросом на весь список (не N+1), не колонка БД.
    avg_price: Optional[Decimal] = None
    avg_price_basis: Optional[int] = None
    avg_price_stale: Optional[bool] = None
    model_config = {"from_attributes": True}

    @model_validator(mode='before')
    @classmethod
    def _compute_has_photo(cls, data):
        # Derive `has_photo` from ORM object / dict so callers don't need to
        # set it manually. Phase 17.1-08 perf: check `photo_size` (cheap scalar)
        # instead of `photo_data` (bytea — triggers lazy load when deferred on
        # the list query). `photo_size` is populated whenever bytes are cached
        # (see _download_and_save_photo / upload_product_photo).
        try:
            if hasattr(data, 'photo_size'):
                has_photo_val = getattr(data, 'photo_size', None) is not None
                try:
                    object.__setattr__(data, 'has_photo', has_photo_val)
                except Exception:
                    pass
            elif isinstance(data, dict) and 'has_photo' not in data:
                data['has_photo'] = (
                    data.get('photo_size') is not None
                    or data.get('photo_data') is not None
                )
        except Exception:
            pass
        return data

class PriceActualizationIn(BaseModel):
    """Тело POST /api/products/{id}/price-actualization — ручная актуализация цены."""
    price: Decimal
    source: str  # 'contract' | 'kp' | 'manual' | 'import' | 'monitoring'
    source_ref: Optional[str] = None
    contractor_id: Optional[int] = None
    collected_at: Optional[str] = None  # ISO date
    note: Optional[str] = None


class ProductPriceHistoryOut(BaseModel):
    id: int
    product_id: int
    price: Optional[Decimal] = None
    source: Optional[str] = None
    source_ref: Optional[str] = None
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None  # владелец, 2026-09-16 — донабирается в роутере join'ом
    collected_at: Optional[date] = None
    note: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class PriceHistoryManualIn(BaseModel):
    """Тело POST /api/products/{id}/price-history — ручное добавление цены в
    историю (владелец, 2026-09-16, п.3: список цен в карточке товара + ручное
    добавление). Источник ограничен подмножеством VALID_PRICE_SOURCES —
    'contract'/'import' проставляются только автоматически (переход в
    contracted / импорт), сюда их передавать нельзя."""
    price: Decimal
    source: str = "manual"  # 'manual' | 'kp' | 'monitoring'
    source_ref: Optional[str] = None
    url: Optional[str] = None
    contractor_id: Optional[int] = None
    collected_at: Optional[str] = None  # ISO date; пусто — сегодня
    note: Optional[str] = None


# Product Summary (сводная по продукции)
class ProductSummaryItem(BaseModel):
    purchase_id: int
    subsidy_name: str
    org_name: Optional[str] = None
    org_id: Optional[int] = None
    region: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    status: Optional[str] = None
    delivery_date: Optional[date] = None
    delivery_address: Optional[str] = None
    procurement_planned_date: Optional[date] = None
    purchase_method: Optional[str] = None

class ProductSummaryGroup(BaseModel):
    product_id: int
    product_name: str
    category: Optional[str] = None
    product_type: Optional[str] = None
    total_quantity: Decimal
    total_amount: Decimal
    purchase_count: int
    items: List[ProductSummaryItem]

# Dashboard
class DashboardCategory(BaseModel):
    id: int
    name: str
    level: int
    total_planned: Decimal = Decimal("0")
    total_confirmed: Decimal = Decimal("0")
    total_payment: Decimal = Decimal("0")
    children: List["DashboardCategory"] = []

class DashboardSummary(BaseModel):
    subsidy_limit: Decimal
    total_obligations: Decimal
    total_payments: Decimal
    remaining: Decimal
    categories: List[DashboardCategory]


