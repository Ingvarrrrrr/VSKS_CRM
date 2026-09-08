"""Каталог товаров — ядро CRUD/поиск (Правило №5, разрезано в сессии
2026-09-08 по образцу users.py → users_access.py/users_me.py/...).

Соседи на том же префиксе /api/products, регистрируются в app/routes.py
(см. комментарий там про порядок):
  - products_summary.py — GET /summary (сводная по продукции)
  - products_match.py   — POST /match, POST /deduplicate (дедуп/матчинг)
  - products_photos.py  — фото (serve/upload/download, legacy filesystem)
  - products_import.py  — GET /import/template, POST /import,
                           POST /bulk-from-purchase-items
  - products_price.py   — share-price, price-actualization, price-history,
                           verify-tz/unverify-tz

Каталог товаров общий (org_id IS NULL допустим) — без per-org разбивки
(Правило №6, память проекта). GET /{product_id} и PUT/PATCH/DELETE
/{product_id} — БЕЗ явного int-конвертера в пути, поэтому любой литеральный
односегментный путь-сосед (только "/summary") обязан регистрироваться ДО
этого роутера.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_single_org_id
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.schemas import ProductCreate, ProductOut
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.price_actualization import actualize_product_price

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=List[ProductOut])
async def list_products(
    feo_category_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Полнотекстовый поиск по имени/описанию/типу"),
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Ограничить кол-во результатов (фронт грузит весь каталог в пикер)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Phase 17.1-08 perf: defer photo_data (bytea, up to 10MB per row).
    # The list endpoint must stay small (~1-2MB); clients fetch bytes via
    # GET /{product_id}/photo when has_photo=True.
    q = select(Product).options(defer(Product.photo_data))
    # Products are global — no org_id filter
    if feo_category_id is not None:
        q = q.where(Product.feo_category_id == feo_category_id)
    if category is not None:
        q = q.where(Product.category == category)
    if is_active is not None:
        q = q.where(Product.is_active == is_active)
    if search:
        from sqlalchemy import or_
        pattern = f"%{search}%"
        q = q.where(or_(
            Product.name.ilike(pattern),
            Product.description.ilike(pattern),
            Product.product_type.ilike(pattern),
            Product.category.ilike(pattern),
        ))
    q = q.order_by(Product.name)
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    products = result.scalars().all()

    # Скрыть контрактные цены для чужих организаций (если не shared)
    if current_user.role != "superadmin":
        user_org_id = current_user.org_id
        for p in products:
            if p.contract_org_id and p.contract_org_id != user_org_id and not p.price_shared:
                p.contract_price = None
                p.contract_number = None
                p.contract_date = None
                p.contract_org_id = None

    # Актуализация цены (владелец, 2026-08-29): контекст правил + курс USD
    # грузится ОДИН раз на весь список, не в цикле по товарам.
    org_id = get_single_org_id(current_user)
    freshness_ctx = await load_freshness_context(db, org_id)
    for p in products:
        p.price_freshness = evaluate_freshness(p, freshness_ctx)

    return products


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Phase 17.1-08 perf: defer photo_data — detail endpoint doesn't return
    # bytes; frontend uses GET /{product_id}/photo for raw image.
    result = await db.execute(
        select(Product)
        .options(defer(Product.photo_data))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    org_id = get_single_org_id(current_user)
    freshness_ctx = await load_freshness_context(db, org_id)
    product.price_freshness = evaluate_freshness(product, freshness_ctx)
    return product


def _calc_price_from_links(links: list) -> float | None:
    """Average price using only links from the 3 most recent distinct dates."""
    if not links:
        return None
    # Get all distinct dates that have a price, sorted descending
    dated = [(l.get("collected_at") or "", l["price"]) for l in links if l.get("price") is not None]
    if not dated:
        return None
    top_dates = sorted({d for d, _ in dated if d}, reverse=True)[:3]
    # Include links with no date only if no dated links exist
    if top_dates:
        prices = [p for d, p in dated if d in top_dates]
    else:
        prices = [p for _, p in dated]
    return round(sum(prices) / len(prices), 2) if prices else None


def _apply_price_links(data: dict, target: object) -> None:
    """Auto-calculate price as average of price_links (3 most recent dates)."""
    price = _calc_price_from_links(data.get("price_links") or [])
    if price is not None:
        data["price"] = price


def _price_links_max_collected_at(links: list) -> Optional[str]:
    """Владелец 2026-08-29: source_ref/collected_at для source='monitoring' —
    самая свежая дата среди ссылок сравнения цен."""
    dates = [l.get("collected_at") for l in (links or []) if l.get("collected_at")]
    return max(dates) if dates else None


@router.post("/", response_model=ProductOut)
async def create_product(
    product: ProductCreate,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Phase 21.x: prevent catalog clutter — if a similar product already exists,
    # return 409 with the suggestion. Frontend asks the user "use existing?"
    # and either links to it or retries with ?force=true.
    if not force and (product.name or '').strip():
        from app.product_matcher import find_matching_product
        org_id = get_single_org_id(current_user) or current_user.org_id
        existing = await find_matching_product(
            db, product.name, org_id=org_id, threshold=0.7,
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_product",
                    "message": f'Похожий товар уже есть в каталоге: "{existing.name}"',
                    "existing": ProductOut.model_validate(existing).model_dump(mode='json'),
                },
            )

    data = product.model_dump()
    _apply_price_links(data, None)
    db_product = Product(**data)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    product: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    old_price = db_product.price
    data = product.model_dump()
    had_links = bool(data.get("price_links"))
    _apply_price_links(data, db_product)
    new_price = data.get("price")
    for key, value in data.items():
        setattr(db_product, key, value)
    from datetime import datetime
    db_product.updated_at = datetime.utcnow()
    db_product.updated_by = current_user.full_name or current_user.username

    # Актуализация цены (владелец, 2026-08-29): price изменился — записать
    # источник + историю. Если пришли price_links и из них посчиталась цена —
    # это автомониторинг ссылок ('monitoring'), иначе ручной ввод ('manual').
    if new_price is not None and new_price != old_price:
        if had_links and _calc_price_from_links(data.get("price_links") or []) is not None:
            collected = _price_links_max_collected_at(data.get("price_links") or [])
            await actualize_product_price(
                db, db_product, price=new_price, source="monitoring",
                collected_at=collected, user=current_user,
            )
        else:
            await actualize_product_price(
                db, db_product, price=new_price, source="manual", user=current_user,
            )

    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.patch("/{product_id}", response_model=ProductOut)
async def patch_product(
    product_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Частичное обновление товара (цена, ссылки, категория, вид, ед. изм.)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(404, "Product not found")
    if "unit" in data:
        db_product.unit = (data["unit"] or "").strip() or None
    if "category" in data:
        cat = (data["category"] or "").strip()
        if not cat:
            raise HTTPException(422, "Категория не может быть пустой")
        db_product.category = cat
    if "product_type" in data:
        pt = (data["product_type"] or "").strip()
        db_product.product_type = pt or None
    if "category" in data or "product_type" in data:
        from datetime import datetime
        db_product.updated_at = datetime.utcnow()
        db_product.updated_by = current_user.full_name or current_user.username
    old_price = db_product.price
    if "price_links" in data:
        db_product.price_links = data["price_links"]
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_product, "price_links")
        # Auto-update price from 3 most recent dates (if not explicitly provided)
        if "price" not in data:
            calc = _calc_price_from_links(data["price_links"])
            if calc is not None:
                new_price = Decimal(str(calc))
                if new_price != old_price:
                    # Актуализация цены (владелец, 2026-08-29): пересчёт из price_links
                    # — это автомониторинг ('monitoring'), collected_at — самая свежая
                    # дата среди ссылок.
                    collected = _price_links_max_collected_at(data["price_links"])
                    await actualize_product_price(
                        db, db_product, price=new_price, source="monitoring",
                        collected_at=collected, user=current_user,
                    )
                else:
                    db_product.price = new_price
    if "price" in data:
        if data["price"] is not None:
            # Явный ручной ввод цены ('manual') — актуализация с историей.
            await actualize_product_price(
                db, db_product, price=data["price"], source="manual", user=current_user,
            )
        else:
            db_product.price = None
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(db_product)
    await db.commit()
    return {"message": "Product deleted"}


@router.delete("/bulk/all")
async def delete_all_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалить все товары. Только для superadmin."""
    if current_user.role != "superadmin":
        raise HTTPException(403, "Только суперадмин может удалить все товары")
    from sqlalchemy import delete as sa_delete
    result = await db.execute(sa_delete(Product))
    await db.commit()
    return {"message": f"Удалено {result.rowcount} товаров"}
