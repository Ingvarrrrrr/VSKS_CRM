"""Средняя цена товара ДЛЯ КОНКРЕТНОЙ ОРГАНИЗАЦИИ/ПАРТИИ — план
clever-bouncing-lantern.md, Часть 2, п.8 (14.10): подсказка у позиции
заявки/закупки («Средняя по ДНР, партия 10–99 шт.: 1 250 ₽ (4 договора)»).

Отдельный файл от routers/products_price.py (Правило №5 — новая логика
в своём файле; products_price.py в этой сессии не трогается параллельной
работой по правам каталога) и ОТДЕЛЬНЫЙ путь от уже существующего
GET /{product_id}/price-stats (тот — без фильтра, всегда прежнее поведение,
owner 2026-09-16; этот — с региона/партии).

Единственная формула — app.services.product_price_stats.compute_price_stats
(ПРАВИЛО №6, второй расчёт не заводится): этот роутер только резолвит
org_id → Organization.region и product.unit, остальное делает она же.
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User
from app.services.product_price_stats import compute_price_stats_bulk

router = APIRouter(prefix="/api/products", tags=["products"])

# Потолок product_ids в одном батче (владелец, 2026-10-26, ПРАВИЛО №8 п.6 —
# лимит тела запроса проверяется ДО обращения к БД, 422, а не 500/зависание
# на огромном списке id при росте каталога к 250+ тыс.).
MAX_AVG_PRICE_PRODUCT_IDS = 500


async def _resolve_org_region(db: AsyncSession, org_id: Optional[int]) -> Optional[str]:
    if org_id is None:
        return None
    return (await db.execute(
        select(Organization.region).where(Organization.id == org_id)
    )).scalar_one_or_none()


@router.get("/{product_id}/avg-price")
async def get_product_avg_price(
    product_id: int,
    org_id: Optional[int] = Query(None, description="Организация, для которой считается регион (заявка/закупка)"),
    quantity: Optional[float] = Query(None, description="Количество — определяет партию (1-9/10-99/100-999/1000+)"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """{avg_price, basis_count, stale, level, region_used, batch} — регион
    берётся из организации org_id (место поставки заявки/закупки ЭТОЙ орг.,
    НЕ юр. адрес её самой — см. compute_price_stats), партия — из quantity."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")
    region = await _resolve_org_region(db, org_id)
    stats_by_id = await compute_price_stats_bulk(
        db, [product_id], target_region=region, quantity=quantity,
    )
    stats = stats_by_id.get(product_id)
    return stats.as_dict() if stats is not None else None


@router.post("/avg-price/bulk")
async def get_products_avg_price_bulk(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Тот же расчёт для НЕСКОЛЬКИХ товаров одним запросом к БД (редактор
    позиций заявки/закупки с несколькими строками). body:
    {product_ids: [...], org_id: int|null, quantity: number|null} →
    {product_id: {avg_price, basis_count, stale, level, region_used, batch}}."""
    product_ids = [int(pid) for pid in (body.get("product_ids") or [])]
    if not product_ids:
        return {}
    if len(product_ids) > MAX_AVG_PRICE_PRODUCT_IDS:
        raise HTTPException(
            422,
            f"product_ids: не более {MAX_AVG_PRICE_PRODUCT_IDS} за один запрос "
            f"(передано {len(product_ids)})",
        )
    region = await _resolve_org_region(db, body.get("org_id"))
    stats_by_id = await compute_price_stats_bulk(
        db, product_ids, target_region=region, quantity=body.get("quantity"),
    )
    return {pid: stats.as_dict() for pid, stats in stats_by_id.items()}
