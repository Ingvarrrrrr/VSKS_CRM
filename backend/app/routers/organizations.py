import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import hash_password, get_current_user, require_superadmin, OWNER_ROLES
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.schemas import OrganizationCreate, OrganizationOut, RegisterRequest, UserOut
from app.utils.email import send_verification_email

router = APIRouter(tags=["organizations"])


@router.post("/api/register", response_model=UserOut, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Public endpoint: create org + first org_admin. Sends verification email."""
    # Check email uniqueness (email = login)
    existing_email = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if existing_email:
        raise HTTPException(400, "Пользователь с таким email уже зарегистрирован")
    # Username defaults to email if not provided
    username = data.username or data.email
    existing_username = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if existing_username:
        username = data.email  # fallback to email as username

    # Create organization (root of contour — owner set after user creation)
    org = Organization(name=data.org_name, inn=data.org_inn, is_active=True)
    db.add(org)
    await db.flush()  # get org.id

    # Create account_owner user
    token = str(uuid.uuid4())
    user = User(
        username=username,
        password_hash=hash_password(data.password),
        role="account_owner",
        full_name=data.full_name,
        email=data.email,
        is_email_confirmed=False,
        email_verification_token=token,
        org_id=org.id,
    )
    db.add(user)
    await db.flush()  # get user.id
    # Link org to its owner
    org.owner_user_id = user.id
    await db.commit()
    await db.refresh(user)

    # Send verification email (best-effort, non-blocking)
    await send_verification_email(data.email, token)

    return user


@router.get("/api/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Public: verify email token, then redirect to /login?verified=1"""
    user = (await db.execute(
        select(User).where(User.email_verification_token == token)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(400, "Ссылка недействительна или уже использована")
    user.is_email_confirmed = True
    user.email_verification_token = None
    await db.commit()
    return RedirectResponse(url="/login?verified=1")


@router.get("/api/organizations/my", response_model=List[OrganizationOut])
async def my_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """account_owner: список всех org своего контура с числом пользователей."""
    if current_user.role not in OWNER_ROLES:
        raise HTTPException(403, "Недостаточно прав")
    if current_user.role == 'superadmin':
        orgs = (await db.execute(select(Organization).order_by(Organization.name))).scalars().all()
    else:
        orgs = (await db.execute(
            select(Organization)
            .where(Organization.owner_user_id == current_user.id)
            .order_by(Organization.name)
        )).scalars().all()
    result = []
    for org in orgs:
        uc = (await db.execute(select(func.count()).where(User.org_id == org.id))).scalar() or 0
        result.append(OrganizationOut(
            id=org.id, name=org.name, inn=org.inn,
            is_active=org.is_active, created_at=org.created_at,
            user_count=uc, root_org_id=org.root_org_id, owner_user_id=org.owner_user_id,
        ))
    return result


@router.get("/api/organizations/me")
async def get_my_org(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not current_user.org_id:
        return {"id": None, "name": "Суперадмин", "is_active": True}
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    return {"id": org.id, "name": org.name, "is_active": org.is_active}


@router.post("/api/organizations/", response_model=OrganizationOut, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Superadmin: создать любую org. account_owner: добавить дочернюю org к своему контуру."""
    if current_user.role not in (*OWNER_ROLES,):
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(403, "Недостаточно прав")
    if current_user.role == 'account_owner':
        org = Organization(
            name=data.name, inn=data.inn, is_active=True,
            root_org_id=current_user.org_id,
            owner_user_id=current_user.id,
        )
    else:
        # superadmin — standalone org
        org = Organization(name=data.name, inn=data.inn, is_active=True)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return OrganizationOut(
        id=org.id, name=org.name, inn=org.inn,
        is_active=org.is_active, created_at=org.created_at, user_count=0,
        root_org_id=org.root_org_id, owner_user_id=org.owner_user_id,
    )


@router.get("/api/organizations/", response_model=List[OrganizationOut])
async def list_organizations(
    search: Optional[str] = Query(None),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    q = select(Organization)
    if search:
        like = f"%{search}%"
        q = q.where(Organization.name.ilike(like) | Organization.inn.ilike(like))
    if active_only:
        q = q.where(Organization.is_active == True)
    q = q.order_by(Organization.name)
    orgs = (await db.execute(q)).scalars().all()
    result = []
    for org in orgs:
        count_q = await db.execute(select(func.count()).where(User.org_id == org.id))
        user_count = count_q.scalar() or 0
        result.append(OrganizationOut(
            id=org.id, name=org.name, inn=org.inn,
            is_active=org.is_active, created_at=org.created_at,
            user_count=user_count,
        ))
    return result


@router.put("/api/organizations/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int,
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    org.name = data.name
    for field in ('full_name', 'inn', 'kpp', 'ogrn', 'address', 'signatory'):
        val = getattr(data, field, None)
        if val is not None:
            setattr(org, field, val or None)
    await db.commit()
    count_q = await db.execute(select(func.count()).where(User.org_id == org.id))
    return OrganizationOut(
        id=org.id, name=org.name, full_name=org.full_name, inn=org.inn,
        kpp=org.kpp, ogrn=org.ogrn, address=org.address, signatory=org.signatory,
        is_active=org.is_active, created_at=org.created_at,
        user_count=count_q.scalar() or 0,
    )


@router.patch("/api/organizations/{org_id}/toggle-active")
async def toggle_org_active(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    org.is_active = not org.is_active
    await db.commit()
    return {"id": org.id, "is_active": org.is_active}


@router.delete("/api/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    await db.delete(org)
    await db.commit()
