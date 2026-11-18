"""POST /api/products/market-price-check — актуальная рыночная цена товара
(розница + за похожий объём) для формы заявки и закупки."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.product_market_price import check_market_price

router = APIRouter(prefix="/api/products", tags=["products"])


class MarketPriceCheckIn(BaseModel):
    product_id: Optional[int] = Field(None, ge=1)
    item_name: Optional[str] = Field(None, max_length=500)
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=50)
    refresh_live: bool = False


class MarketPriceOfferOut(BaseModel):
    store_key: str
    store_name: str
    price: float
    url: Optional[str] = None
    is_live: bool = False


class MarketPriceCheckOut(BaseModel):
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    catalog_price: Optional[float] = None
    live_refreshed: bool = False
    retail_price: Optional[float] = None
    retail_min: Optional[float] = None
    retail_max: Optional[float] = None
    retail_count: int = 0
    volume_price: Optional[float] = None
    volume_batch: str = "1-9"
    volume_basis_count: int = 0
    volume_source: str = "none"
    volume_note: str = ""
    offers: list[MarketPriceOfferOut] = []


@router.post("/market-price-check", response_model=MarketPriceCheckOut)
async def post_market_price_check(
    body: MarketPriceCheckIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await check_market_price(
        db,
        current_user=current_user,
        product_id=body.product_id,
        item_name=body.item_name,
        quantity=body.quantity,
        unit=body.unit,
        refresh_live=body.refresh_live,
    )
