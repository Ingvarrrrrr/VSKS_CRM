"""Цены/история/проверка ТЗ товара — вынесено из products.py (Правило №5,
сессия 2026-09-08). Все пути здесь — "/{product_id}/<literal>", минимум на
сегмент длиннее catch-all "/{product_id}" products.router (ядро) — по форме
пути не конфликтуют, порядок регистрации относительно ядра не важен;
регистрируется рядом с ним для единообразия с остальными products_*
соседями.

Актуализация цены (единый источник — app.services.price_actualization,
Правило №6) вызывается отсюда И из ядра (create/update/patch); история и
sharing-флаг читаются/пишутся только здесь.
"""
from datetime import date as _date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_single_org_id, ADMIN_ROLES
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contractor import Contractor
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.schemas.schemas import (
    ProductOut, PriceActualizationIn, ProductPriceHistoryOut, PriceHistoryManualIn,
)
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.price_actualization import actualize_product_price, VALID_PRICE_SOURCES
from app.services.product_price_stats import compute_price_stats

router = APIRouter(prefix="/api/products", tags=["products"])

# POST /{product_id}/price-history (ручное добавление, владелец 2026-09-16) —
# подмножество VALID_PRICE_SOURCES: 'contract'/'import' проставляются ТОЛЬКО
# автоматически (переход в contracted / импорт файла), руками их указать
# нельзя — иначе история потеряет достоверность источника.
MANUAL_PRICE_SOURCES = ("manual", "kp", "monitoring")


@router.patch("/{product_id}/share-price")
async def toggle_price_sharing(
    product_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Включить/отключить sharing контрактной цены для других организаций."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Товар не найден")
    # Только владелец организации или superadmin
    if current_user.role != "superadmin":
        if product.contract_org_id != current_user.org_id:
            raise HTTPException(403, "Только организация-владелец контракта может управлять доступом к цене")
    product.price_shared = bool(data.get("shared", False))
    await db.commit()
    await db.refresh(product)
    return product


@router.post("/{product_id}/price-actualization", response_model=ProductOut)
async def actualize_price(
    product_id: int,
    data: PriceActualizationIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('products')),
):
    """Ручная актуализация цены товара (владелец, 2026-08-29) — например,
    когда пришёл ответ на запрос КП вне модуля «Запросы КП», или менеджер
    подтвердил цену по телефону/прайс-листу."""
    if data.source not in VALID_PRICE_SOURCES:
        raise HTTPException(422, {
            "code": "invalid_price_source",
            "message": f"Недопустимый источник цены: {data.source}. Допустимо: {', '.join(VALID_PRICE_SOURCES)}",
        })
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")
    await actualize_product_price(
        db, product,
        price=data.price,
        source=data.source,
        source_ref=data.source_ref,
        contractor_id=data.contractor_id,
        collected_at=data.collected_at,
        note=data.note,
        user=current_user,
    )
    await db.commit()
    await db.refresh(product)

    org_id = get_single_org_id(current_user)
    freshness_ctx = await load_freshness_context(db, org_id)
    product.price_freshness = evaluate_freshness(product, freshness_ctx)
    return product


@router.get("/{product_id}/price-history", response_model=List[ProductPriceHistoryOut])
async def get_price_history(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """История актуализации цены товара, новые сверху. Карточка товара
    (владелец, 2026-09-16, п.3): дата/источник/контрагент/ссылка по каждой
    записи — contractor_name донабирается join'ом с Contractor тут же, одним
    запросом (не второй эндпоинт истории, тот же — расширен полем)."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")
    rows = (await db.execute(
        select(ProductPriceHistory, Contractor.name.label("contractor_name"))
        .outerjoin(Contractor, Contractor.id == ProductPriceHistory.contractor_id)
        .where(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.created_at.desc())
    )).all()

    out: List[ProductPriceHistoryOut] = []
    for history_row, contractor_name in rows:
        item = ProductPriceHistoryOut.model_validate(history_row)
        item.contractor_name = contractor_name
        out.append(item)
    return out


@router.get("/{product_id}/price-stats")
async def get_price_stats(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Средняя цена товара за окно (владелец, 2026-09-16, п.4) — единая функция
    app.services.product_price_stats.compute_price_stats, без второй формулы
    для одиночного товара (списочный расчёт — compute_price_stats_bulk поверх
    той же функции, см. routers/products.py::_attach_price_stats)."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")
    rows = (await db.execute(
        select(ProductPriceHistory.price, ProductPriceHistory.collected_at)
        .where(ProductPriceHistory.product_id == product_id)
    )).all()
    stats = compute_price_stats(rows)
    return stats.as_dict()


@router.post("/{product_id}/price-history", response_model=ProductPriceHistoryOut)
async def add_manual_price_history(
    product_id: int,
    data: PriceHistoryManualIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('products')),
):
    """Ручное добавление цены в историю товара (владелец, 2026-09-16, п.3) —
    через ЕДИНУЮ точку записи app.services.price_actualization.actualize_product_price
    (тот же писатель, что и /price-actualization; отдельный путь — под
    контракт карточки товара «список цен» фронта, схема источников уже
    сужена до manual|kp|monitoring, см. MANUAL_PRICE_SOURCES)."""
    if data.source not in MANUAL_PRICE_SOURCES:
        raise HTTPException(422, {
            "code": "invalid_price_source",
            "message": f"Недопустимый источник для ручного добавления: {data.source}. Допустимо: {', '.join(MANUAL_PRICE_SOURCES)}",
        })
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")

    source_ref = data.source_ref or data.url
    collected_at = data.collected_at or _date.today().isoformat()

    await actualize_product_price(
        db, product,
        price=data.price,
        source=data.source,
        source_ref=source_ref,
        contractor_id=data.contractor_id,
        collected_at=collected_at,
        note=data.note,
        user=current_user,
    )
    await db.commit()

    row = (await db.execute(
        select(ProductPriceHistory)
        .where(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.id.desc())
        .limit(1)
    )).scalar_one()
    return row


@router.delete("/{product_id}/price-history/{history_id}")
async def delete_price_history_entry(
    product_id: int,
    history_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалить запись истории цены (владелец, 2026-09-16, п.3) — только автор
    записи сам, либо администратор."""
    row = (await db.execute(
        select(ProductPriceHistory).where(
            ProductPriceHistory.id == history_id,
            ProductPriceHistory.product_id == product_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Запись истории цены не найдена")
    if row.created_by != current_user.id and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Удалить запись может только её автор или администратор")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.patch("/{product_id}/verify-tz", response_model=ProductOut)
async def verify_product_tz(
    product_id: int,
    tz_type: str = Query(..., description="'standard' или '44fz'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметить ТЗ товара как проверенное (standard или 44fz)."""
    from datetime import datetime as _dt
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Товар не найден")
    verifier_name = current_user.full_name or current_user.username
    if tz_type == "44fz":
        product.tz_44fz_verified_at = _dt.utcnow()
        product.tz_44fz_verified_by = verifier_name
    else:
        product.tz_verified_at = _dt.utcnow()
        product.tz_verified_by = verifier_name
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}/verify-tz", response_model=ProductOut)
async def unverify_product_tz(
    product_id: int,
    tz_type: str = Query(..., description="'standard' или '44fz'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Снять отметку проверки ТЗ (только admin/superadmin)."""
    if current_user.role not in ("admin", "superadmin"):
        raise HTTPException(403, "Только администратор может снять отметку проверки ТЗ")
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Товар не найден")
    if tz_type == "44fz":
        product.tz_44fz_verified_at = None
        product.tz_44fz_verified_by = None
    else:
        product.tz_verified_at = None
        product.tz_verified_by = None
    await db.commit()
    await db.refresh(product)
    return product
