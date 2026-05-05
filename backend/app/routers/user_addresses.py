import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.models.user_address import UserAddress

router = APIRouter(prefix="/api/user-addresses", tags=["user_addresses"])


@router.get("/")
async def list_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(UserAddress)
        .where(UserAddress.user_id == current_user.id)
        .order_by(desc(UserAddress.last_used_at))
    )).scalars().all()
    return [{"id": r.id, "address": r.address} for r in rows]


@router.post("/")
async def add_address(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    addr = (body.get("address") or "").strip()
    if not addr or len(addr) < 3:
        return {"ok": False}
    # Upsert
    existing = (await db.execute(
        select(UserAddress).where(
            UserAddress.user_id == current_user.id,
            UserAddress.address == addr,
        )
    )).scalar_one_or_none()
    if existing:
        await db.execute(
            update(UserAddress).where(UserAddress.id == existing.id).values(
                last_used_at=datetime.datetime.now(datetime.timezone.utc)
            )
        )
    else:
        row = UserAddress(user_id=current_user.id, address=addr)
        db.add(row)
    await db.commit()
    return {"ok": True}


@router.delete("/{addr_id}")
async def delete_address(
    addr_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.get(UserAddress, addr_id)
    if not row or row.user_id != current_user.id:
        return {"ok": False}
    await db.delete(row)
    await db.commit()
    return {"ok": True}
