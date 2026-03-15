import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.auth.jwt import verify_password, create_access_token, get_current_user, hash_password
from app.schemas.schemas import LoginRequest, Token, UserOut
from app.utils.email import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Try email first, then username (backward compatibility for admin)
    result = await db.execute(select(User).where(User.email == req.username))
    user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(select(User).where(User.username == req.username))
        user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_email_confirmed:
        raise HTTPException(status_code=403, detail="Подтвердите email перед входом")
    org_name = None
    if user.org_id:
        org = await db.get(Organization, user.org_id)
        if org:
            if not org.is_active:
                raise HTTPException(status_code=403, detail="Подписка организации неактивна")
            org_name = org.name
    token = create_access_token({"sub": user.username, "role": user.role, "org_id": user.org_id})
    return Token(access_token=token, role=user.role, full_name=user.full_name,
                 org_id=user.org_id, org_name=org_name, user_id=user.id)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Send password reset link. Always returns success (no user enumeration)."""
    user = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if user:
        token = str(uuid.uuid4())
        user.password_reset_token = token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()
        await send_password_reset_email(req.email, token)
    # Always return success to prevent user enumeration
    return {"message": "Если аккаунт с таким email существует, ссылка для сброса отправлена"}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using token from email."""
    user = (await db.execute(
        select(User).where(User.password_reset_token == req.token)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(400, "Ссылка недействительна или уже использована")
    if user.password_reset_expires and user.password_reset_expires < datetime.utcnow():
        raise HTTPException(400, "Ссылка истекла. Запросите сброс пароля заново")
    user.password_hash = hash_password(req.password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()
    return {"message": "Пароль успешно изменён"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/my-orgs")
async def my_orgs(
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List organizations accessible to the current user."""
    from app.models.user_org_access import UserOrgAccess
    if user.role == 'superadmin':
        q = select(Organization).where(Organization.is_active == True).order_by(Organization.name)
        if search:
            q = q.where(Organization.name.ilike(f"%{search}%") | Organization.inn.ilike(f"%{search}%"))
        result = await db.execute(q)
        return [{"id": o.id, "name": o.name, "is_active": o.is_active} for o in result.scalars().all()]

    result = await db.execute(
        select(Organization)
        .join(UserOrgAccess, UserOrgAccess.org_id == Organization.id)
        .where(UserOrgAccess.user_id == user.id)
        .order_by(Organization.name)
    )
    orgs = [{"id": o.id, "name": o.name, "is_active": o.is_active} for o in result.scalars().all()]
    # Ensure current org is included
    if user.org_id and not any(o["id"] == user.org_id for o in orgs):
        org = await db.get(Organization, user.org_id)
        if org:
            orgs.insert(0, {"id": org.id, "name": org.name, "is_active": org.is_active})
    return orgs


class SwitchOrgRequest(BaseModel):
    org_id: int


class SelectOrgsRequest(BaseModel):
    org_ids: list[int]


@router.post("/switch-org")
async def switch_org(
    req: SwitchOrgRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Switch active organization (single) — returns new JWT token."""
    from app.models.user_org_access import UserOrgAccess
    target_org_id = req.org_id

    if user.role != 'superadmin':
        access = await db.execute(
            select(UserOrgAccess)
            .where(UserOrgAccess.user_id == user.id, UserOrgAccess.org_id == target_org_id)
        )
        if not access.scalar_one_or_none():
            raise HTTPException(403, "Нет доступа к этой организации")

    org = await db.get(Organization, target_org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")

    token = create_access_token({
        "sub": user.username, "role": user.role,
        "org_id": target_org_id, "org_ids": [target_org_id],
    })
    return {
        "access_token": token,
        "org_id": target_org_id,
        "org_name": org.name,
    }


@router.post("/select-orgs")
async def select_orgs(
    req: SelectOrgsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Select multiple organizations (superadmin) — returns new JWT with org_ids."""
    if user.role != 'superadmin':
        raise HTTPException(403, "Только для суперадмина")
    if not req.org_ids:
        raise HTTPException(400, "Выберите хотя бы одну организацию")

    # Validate all org_ids exist
    result = await db.execute(
        select(Organization).where(Organization.id.in_(req.org_ids))
    )
    orgs = result.scalars().all()
    found_ids = {o.id for o in orgs}
    missing = set(req.org_ids) - found_ids
    if missing:
        raise HTTPException(404, f"Организации не найдены: {missing}")

    org_names = [o.name for o in orgs if o.id in req.org_ids]
    token = create_access_token({
        "sub": user.username, "role": user.role,
        "org_ids": req.org_ids,
    })
    return {
        "access_token": token,
        "org_ids": req.org_ids,
        "org_names": org_names,
    }
