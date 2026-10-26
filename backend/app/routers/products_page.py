"""GET /api/products/page — серверный поиск/фильтры/пагинация каталога
товаров (владелец, 26.10.2026). Разрезание products.py (Правило №5): файл
уже на границе ~630 строк, новый эндпоинт — отдельный модуль, как и соседние
products_summary.py/products_match.py/products_price.py на том же префиксе.

Путь "/page" — ОДИН литеральный сегмент, регистрируется в app/routes.py ДО
products.router (тот несёт catch-all GET "/{product_id}" без int-конвертера
в строке пути — тот же принцип, что у products_summary.router).

Вся логика поиска/фильтров — в app/services/product_search.py (ПРАВИЛО №6,
единый механизм для /page, для GET /api/products/ без ids и, позже, для
пикера товара в закупке/сужения кандидатов в /products/match). Этот роутер
только валидирует вход (ПРАВИЛО №8 п.6 — лимиты/формат ДО запроса в БД,
никогда 500 на плохом вводе) и зовёт сервис.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_single_org_id
from app.database import get_db
from app.models.user import User
from app.schemas.products import ProductSearchPageOut, ProductStaleCountOut
from app.services.price_freshness import load_context as load_freshness_context
from app.services.product_list_postprocess import postprocess_catalog_list
from app.services.product_search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SORTABLE_COLUMNS,
    ProductSearchFilters,
    count_stale_products,
    search_products,
)
from app.services.product_stale_count_cache import get_stale_count_cached

router = APIRouter(prefix="/api/products", tags=["products"])

_VALID_ORDERS = {"asc", "desc"}


def _parse_multi(values: Optional[List[str]]) -> Optional[List[str]]:
    """category/product_type принимают И повторяемый параметр
    (?category=A&category=B), И CSV в одном (?category=A,B) — сворачивает
    то и другое в один список, пустые элементы отбрасывает."""
    if not values:
        return None
    out: list[str] = []
    for raw in values:
        out.extend(part.strip() for part in raw.split(",") if part.strip())
    return out or None


@router.get("/page", response_model=ProductSearchPageOut)
async def search_products_page(
    search: Optional[str] = Query(None, description="Поиск по имени/артикулу/производителю (многословный, AND)"),
    category: Optional[List[str]] = Query(None),
    product_type: Optional[List[str]] = Query(None),
    is_active: Optional[bool] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    price_min: Optional[Decimal] = Query(None, ge=0),
    price_max: Optional[Decimal] = Query(None, ge=0),
    stale_only: bool = Query(False),
    sort: str = Query("name"),
    order: str = Query("asc"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0, le=1_000_000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Валидация ДО запроса в БД (ПРАВИЛО №8 п.6) — sort/order вне белого
    # списка это ошибка клиента (422), не повод строить ORDER BY по
    # произвольной строке и падать 500 на несуществующей колонке.
    if sort not in SORTABLE_COLUMNS:
        raise HTTPException(422, f"Параметр sort: допустимые значения — {', '.join(sorted(SORTABLE_COLUMNS))}")
    if order not in _VALID_ORDERS:
        raise HTTPException(422, "Параметр order: 'asc' или 'desc'")
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(422, "price_min не может быть больше price_max")

    org_id = get_single_org_id(current_user)
    freshness_ctx = await load_freshness_context(db, org_id) if stale_only else None

    filters = ProductSearchFilters(
        search=search,
        feo_category_id=feo_category_id,
        category=_parse_multi(category),
        product_type=_parse_multi(product_type),
        is_active=is_active,
        price_min=price_min,
        price_max=price_max,
        stale_only=stale_only,
        sort=sort,
        order=order,
    )
    items, total, total_capped = await search_products(
        db, filters, limit=limit, offset=offset, freshness_ctx=freshness_ctx,
    )

    await postprocess_catalog_list(db, items, current_user)
    return ProductSearchPageOut(items=items, total=total, total_capped=total_capped)


@router.get("/stale-count", response_model=ProductStaleCountOut)
async def get_stale_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Счётчик товаров «требует актуализации» по ВСЕМУ каталогу — отдельно от
    /page (владелец, 26.10.2026): раньше /page считал его БЕЗУСЛОВНО на
    каждый вызов (на каждое нажатие клавиши при поиске), это самостоятельный
    full-scan ~200-240мс на 263 тыс. товаров (см. докстринг
    product_stale_count_cache.py, почему именно TTL-кэш, а не индекс).
    Фронт зовёт этот эндпоинт при открытии страницы и после актуализации
    цены — не на каждый /page."""
    org_id = get_single_org_id(current_user)

    async def _compute() -> int:
        freshness_ctx = await load_freshness_context(db, org_id)
        return await count_stale_products(db, freshness_ctx)

    stale_total = await get_stale_count_cached(org_id, _compute)
    return ProductStaleCountOut(stale_total=stale_total)
