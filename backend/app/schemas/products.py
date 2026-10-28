"""Products, pricing, and dashboard summary schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
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

class ProductCharacteristic(BaseModel):
    """Одна характеристика карточки товара — «название: значение ед.» (владелец,
    26.10). Единственная форма представления характеристик в проекте — та же
    форма отдают конвертеры app/services/catalog_gala/ и читает
    app/services/product_tech_description.py::build_tech_description.
    in_description (владелец, задача «ручное заполнение характеристик»,
    26.10) — ТОЛЬКО явное False исключает строку из build_tech_description
    (см. product_tech_description.py::_characteristic_line — проверка
    `is False`, не `is not True`). Дефолт схемы — None, а не False: если
    завести дефолт False, КАЖДАЯ характеристика, добавленная вручную без
    этого флага, молча исключалась бы из собранного описания — ровно
    противоположность задаче «заполнить характеристики → собрать из них
    описание». None/отсутствие — характеристика видна в описании, как и у
    существующих данных загрузчика поставщиков."""
    name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    in_description: Optional[bool] = None


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
    # Упаковка (владелец, 14.10): валидны только когда unit — упаковочная
    # единица (app.services.units.is_pack_unit); иначе роутер принудительно
    # очищает оба поля (routers/products.py::_apply_pack_fields_rule).
    pack_quantity: Optional[Decimal] = None
    pack_unit: Optional[str] = None
    item_kind: Optional[str] = "товар"  # "товар" / "услуга" / "работа" (app.services.item_types.ITEM_TYPES, ПРАВИЛО №6)
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
    # Характеристики каталога — приём на вход (владелец, задача «ручное
    # заполнение характеристик», 26.10.2026). Раньше ProductCharacteristic
    # использовалась только в ProductOut (показ); теперь карточка товара
    # может их и сохранять через тот же PUT/PATCH, что и description
    # (routers/products.py, продолжение генерика data.items()). Валидация
    # длины/отбрасывание пустых строк — явно в роутере, не только pydantic
    # (см. app/services/product_characteristics_validate.py).
    characteristics: Optional[List[ProductCharacteristic]] = None

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
    # Часть 2 плана clever-bouncing-lantern.md (14.10) — на каком уровне
    # лестницы нашлись данные (см. compute_price_stats): 'region_batch' |
    # 'region' | 'nearest_batch' | 'nearest' | 'batch' | 'all'; region_used —
    # регион, по которому фактически посчитано (может быть «ближайшим», не
    # регионом организации); batch — партия ('1-9' и т.п.) или None.
    avg_price_level: Optional[str] = None
    avg_price_region: Optional[str] = None
    avg_price_batch: Optional[str] = None
    # Характеристики каталога (владелец, 26.10) — см.
    # app/models/product.py::Product.characteristics/manufacturer/article.
    # Поле наследуется из ProductCreate уже как ЗАПИСЫВАЕМОЕ (задача «ручное
    # заполнение характеристик», 26.10.2026) — редекларация здесь не меняет
    # тип, оставлена только чтобы не потерять этот комментарий про manufacturer/article рядом.
    characteristics: Optional[List[ProductCharacteristic]] = None
    manufacturer: Optional[str] = None
    article: Optional[str] = None
    # Штрихкоды (владелец, 27.10.2026, app/models/product_barcode.py) —
    # ТОЛЬКО показ (карточка товара, рядом с «Артикул производителя» — см.
    # ProductFormDialog.vue); запись — только через products_import_apply.py/
    # product_merge.py (ПРАВИЛО №6), не через этот or другой PUT/PATCH.
    barcodes: List[str] = []
    model_config = {"from_attributes": True}

    # НЕ-Optional bool-поля, у которых в БД колонка nullable (нет NOT NULL —
    # SQLAlchemy default=... действует только при INSERT без явного
    # значения, а не как DB-constraint) — владелец, QA-находка 28.10.2026:
    # HTTP 500 на /api/products/page, 14 товаров с price_shared IS NULL
    # (напр. id 812302), на проде, вероятно, больше. field_validator(mode=
    # 'before') — per-field, получает уже ИЗВЛЕЧЁННОЕ из ORM-объекта
    # значение (НЕ сам ORM-объект) — безопасно, в отличие от
    # object.__setattr__(data, ...) в _compute_has_photo/_compute_barcodes
    # ниже: там это НЕ реальные колонки Product, а здесь price_shared/
    # is_active — реальные mapped-колонки, и запись через __setattr__
    # пометила бы ORM-объект dirty → риск случайно ЗАПИСАТЬ False/True в
    # БД при следующем commit той же сессии («данные в БД не трогать»).
    # Тип для фронта остаётся bool (не Optional) — None сюда не долетает.
    #
    # Сверено со всеми bool-колонками app/models/product.py: is_reusable
    # уже Optional[bool] в ProductCreate (None проходит валидацию без
    # ошибки, править не нужно); price_shared и is_active — НЕ Optional,
    # обе нуждались в фиксе (is_active на деве сейчас 0 NULL-строк, но тип
    # тот же, что у price_shared — тот же сбой НЕИЗБЕЖЕН при появлении
    # NULL, чиним заранее).
    @field_validator('price_shared', mode='before')
    @classmethod
    def _price_shared_none_to_false(cls, v):
        return False if v is None else v

    @field_validator('is_active', mode='before')
    @classmethod
    def _is_active_none_to_true(cls, v):
        return True if v is None else v

    @model_validator(mode='before')
    @classmethod
    def _compute_barcodes(cls, data):
        # Product.barcode_rows — relationship (lazy="selectin"), ORM-строки
        # ProductBarcode; схема отдаёт плоский список строк. Тот же приём,
        # что у _compute_has_photo ниже (ORM-объект vs dict на входе).
        try:
            if hasattr(data, 'barcode_rows'):
                try:
                    object.__setattr__(data, 'barcodes', [r.barcode for r in (data.barcode_rows or [])])
                except Exception:
                    pass
            elif isinstance(data, dict) and 'barcodes' not in data:
                data['barcodes'] = []
        except Exception:
            pass
        return data

    @model_validator(mode='after')
    def _sync_purchase_category_ids(self):
        # ПРАВИЛО №6: один источник истины — relationship purchase_categories.
        # purchase_category_ids раньше наследовался из ProductCreate с дефолтом
        # [] и в ответах API не заполнялся из БД, из-за чего GET всегда отдавал
        # [] даже после сохранённых категорий (товар 5461, баг владельца
        # "категория закупки не сохраняется" — на самом деле не читалась).
        # Пересчитываем всегда, чтобы ответ не мог расходиться с БД.
        self.purchase_category_ids = [c.id for c in self.purchase_categories]
        return self

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

# Серверный поиск/пагинация каталога (владелец, 26.10.2026) — GET
# /api/products/page, см. app/services/product_search.py. Контракт НОВЫЙ,
# не путать с ProductOut-массивом старого GET /api/products/.
class ProductSearchPageOut(BaseModel):
    items: List[ProductOut]
    total: int
    # total_capped — total достиг потолка точного count() (ПРАВИЛО №6,
    # product_search.py::TOTAL_COUNT_CAP — единственное место, где считается
    # сам потолок) и является ОЦЕНКОЙ «минимум total», не точным числом.
    total_capped: bool = False
    # query_specific/fuzzy — «этап 0» поиска по фразе (владелец, 28.10.2026,
    # см. app/services/product_query_parse.py::ParsedQuery.specific и
    # app/services/product_search.py::search_products(result_meta=...)).
    # Опциональные, со значением по умолчанию — фронт их пока не читает,
    # добавлены для будущего шага (подсказка «возможно, вы имели в виду»).
    query_specific: bool = False
    fuzzy: bool = False
    # relaxed/corrected — лестница поиска (владелец, 28.10.2026, доработка
    # «этап 0»): relaxed — какие цифровые/величина-токены или слова были
    # ОСЛАБЛЕНЫ (не совпали точно, см. search_products шаги 2/3), чтобы
    # найти хоть что-то — фронт может показать «точно не нашлось, похожие»;
    # corrected — {исходное: исправленное} слово при срабатывании шага 4
    # (product_words_correction, словарь слов каталога).
    relaxed: List[str] = []
    corrected: dict = {}


# GET /api/products/stale-count — счётчик для бейджа «требует актуализации»,
# ОТДЕЛЬНО от /page (владелец, 26.10.2026, см. docstring
# app/services/product_stale_count_cache.py — раньше считался безусловно на
# каждый /page, это самостоятельный full-scan).
class ProductStaleCountOut(BaseModel):
    stale_total: int


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
    # store_article (владелец, 27.10.2026) — номер товара в КОНКРЕТНОМ
    # магазине этой строки истории (не производителя, см.
    # app/models/product_price_history.py); показывается рядом с магазином
    # в карточке товара (PurchasePriceHistory.vue).
    store_article: Optional[str] = None
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


