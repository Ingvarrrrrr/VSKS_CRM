from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.delivery_address import DeliveryAddress
from app.auth.jwt import get_current_user
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/delivery-addresses", tags=["delivery-addresses"])


class DeliveryAddressOut(BaseModel):
    id: int
    org_id: int
    address: str

    model_config = {"from_attributes": True}


@router.get("/", response_model=List[DeliveryAddressOut])
async def search_addresses(
    org_id: int = Query(...),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stmt = select(DeliveryAddress).where(DeliveryAddress.org_id == org_id)
    if q:
        stmt = stmt.where(DeliveryAddress.address.ilike(f"%{q}%"))
    stmt = stmt.order_by(DeliveryAddress.created_at.desc()).limit(20)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("/", response_model=DeliveryAddressOut)
async def save_address(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = body.get("org_id")
    address = (body.get("address") or "").strip()
    if not org_id or not address:
        return {"id": 0, "org_id": org_id or 0, "address": address}

    # Check duplicate
    existing = (await db.execute(
        select(DeliveryAddress).where(
            DeliveryAddress.org_id == org_id,
            func.lower(DeliveryAddress.address) == address.lower(),
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    da = DeliveryAddress(org_id=org_id, address=address)
    db.add(da)
    await db.commit()
    await db.refresh(da)
    return da
