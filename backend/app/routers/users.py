from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.auth.jwt import hash_password, require_role
from app.schemas.schemas import UserCreate, UserOut
from typing import List

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(User))
    return result.scalars().all()

@router.post("/", response_model=UserOut)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    user = User(username=data.username, password_hash=hash_password(data.password),
                role=data.role, full_name=data.full_name, city=data.city)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    await db.delete(user)
    await db.commit()
    return {"ok": True}
