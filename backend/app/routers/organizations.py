import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import hash_password, get_current_user, require_superadmin, OWNER_ROLES
from app.database import get_db
from app.models.organization import Organization
from app.models.contractor import Contractor
from app.models.user import User
from app.schemas.schemas import OrganizationCreate, OrganizationOut, RegisterRequest, UserOut
from app.utils.email import send_verification_email

router = APIRouter(tags=["organizations"])


def _merge_org_with_contractor(org: Organization, user_count: int = 0) -> OrganizationOut:
    """Return OrganizationOut with fields resolved through linked Contractor when present.

    Organization's own fields (name, inn, etc.) take precedence ONLY if they are
    explicitly set (non-null & non-empty). Otherwise they fall back to the
    linked Contractor's field.

    The short `name` field keeps Organization's override so the display name in
    admin lists stays distinct from a contractor's legal short-name.
    """
    c = getattr(org, 'contractor', None)

    def pick(org_val: Optional[str], contractor_val: Optional[str]) -> Optional[str]:
        if org_val is not None and str(org_val).strip() != '':
            return org_val
        return contractor_val

    return OrganizationOut(
        id=org.id,
        name=org.name,
        full_name=pick(org.full_name, getattr(c, 'full_name', None)),
        inn=pick(org.inn, getattr(c, 'inn', None)),
        kpp=pick(org.kpp, getattr(c, 'kpp', None)),
        ogrn=pick(org.ogrn, getattr(c, 'ogrn', None)),
        address=pick(org.address, getattr(c, 'address', None)),
        signatory=pick(org.signatory, getattr(c, 'signatory', None)),
        is_active=org.is_active,
        created_at=org.created_at,
        user_count=user_count,
        root_org_id=org.root_org_id,
        owner_user_id=org.owner_user_id,
        contractor_id=org.contractor_id,
        org_phone=getattr(c, 'org_phone', None) if c else None,
        org_email=getattr(c, 'org_email', None) if c else None,
    )


async def _auto_link_contractor_by_inn(
    db: AsyncSession,
    org: Organization,
    data: OrganizationCreate,
) -> None:
    """If data has an INN and org.contractor_id is NULL, find-or-create
    Contractor with that INN and link it. Safe to call on POST and PUT.
    """
    if org.contractor_id:
        return
    inn = (data.inn or '').strip() if data.inn else ''
    if not inn:
        return
    res = await db.execute(select(Contractor).where(Contractor.inn == inn).limit(1))
    contractor = res.scalar_one_or_none()
    if contractor is None:
        # Create minimal Contractor from available Organization fields
        contractor = Contractor(
            name=data.name or inn,
            full_name=data.full_name,
            inn=inn,
            kpp=data.kpp,
            ogrn=data.ogrn,
            address=data.address,
            signatory=data.signatory,
            org_id=org.id,
        )
        db.add(contractor)
        await db.flush()
    org.contractor_id = contractor.id


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
    base_q = select(Organization).options(selectinload(Organization.contractor))
    if current_user.role == 'superadmin':
        orgs = (await db.execute(base_q.order_by(Organization.name))).scalars().all()
    else:
        orgs = (await db.execute(
            base_q
            .where(Organization.owner_user_id == current_user.id)
            .order_by(Organization.name)
        )).scalars().all()
    result = []
    for org in orgs:
        uc = (await db.execute(select(func.count()).where(User.org_id == org.id))).scalar() or 0
        result.append(_merge_org_with_contractor(org, user_count=uc))
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
            name=data.name,
            full_name=data.full_name,
            inn=data.inn,
            kpp=data.kpp,
            ogrn=data.ogrn,
            address=data.address,
            signatory=data.signatory,
            is_active=True,
            root_org_id=current_user.org_id,
            owner_user_id=current_user.id,
            contractor_id=data.contractor_id,
        )
    else:
        # superadmin — standalone org
        org = Organization(
            name=data.name,
            full_name=data.full_name,
            inn=data.inn,
            kpp=data.kpp,
            ogrn=data.ogrn,
            address=data.address,
            signatory=data.signatory,
            is_active=True,
            contractor_id=data.contractor_id,
        )
    db.add(org)
    await db.flush()  # get org.id so we can link a new Contractor back
    # Auto-link to Contractor by INN (or create minimal Contractor if missing)
    await _auto_link_contractor_by_inn(db, org, data)
    await db.commit()
    await db.refresh(org)
    # Re-fetch with contractor eager-loaded
    res = await db.execute(
        select(Organization)
        .options(selectinload(Organization.contractor))
        .where(Organization.id == org.id)
    )
    org = res.scalar_one()
    return _merge_org_with_contractor(org, user_count=0)


@router.get("/api/organizations/", response_model=List[OrganizationOut])
async def list_organizations(
    search: Optional[str] = Query(None),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    q = select(Organization).options(selectinload(Organization.contractor))
    if search:
        like = f"%{search}%"
        q = q.where(
            Organization.name.ilike(like) |
            Organization.full_name.ilike(like) |
            Organization.inn.ilike(like)
        )
    if active_only:
        q = q.where(Organization.is_active == True)
    q = q.order_by(Organization.name)
    orgs = (await db.execute(q)).scalars().all()
    result = []
    for org in orgs:
        count_q = await db.execute(select(func.count()).where(User.org_id == org.id))
        user_count = count_q.scalar() or 0
        result.append(_merge_org_with_contractor(org, user_count=user_count))
    return result


@router.put("/api/organizations/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int,
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    res = await db.execute(
        select(Organization)
        .options(selectinload(Organization.contractor))
        .where(Organization.id == org_id)
    )
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Организация не найдена")
    org.name = data.name
    # Explicit contractor_id override (allows un-linking by setting null)
    if data.contractor_id is not None:
        org.contractor_id = data.contractor_id
    for field in ('full_name', 'inn', 'kpp', 'ogrn', 'address', 'signatory'):
        val = getattr(data, field, None)
        if val is not None:
            setattr(org, field, val or None)
    # Auto-link by INN if still unlinked
    await _auto_link_contractor_by_inn(db, org, data)
    await db.commit()
    # Re-fetch with contractor eager-loaded
    res = await db.execute(
        select(Organization)
        .options(selectinload(Organization.contractor))
        .where(Organization.id == org.id)
    )
    org = res.scalar_one()
    count_q = await db.execute(select(func.count()).where(User.org_id == org.id))
    return _merge_org_with_contractor(org, user_count=count_q.scalar() or 0)


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


@router.get("/api/organizations/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """27.4-03: получить одну Organization по id — доступно любому authenticated.
    Нужно для preview Заказчика в CreateOrderView (раньше employee получал 403 на /organizations/).
    Visibility: superadmin → любая; иначе только org_id ∈ visible_orgs пользователя."""
    res = await db.execute(
        select(Organization)
        .options(selectinload(Organization.contractor))
        .where(Organization.id == org_id)
    )
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if current_user.role not in ('superadmin', 'account_owner'):
        from app.auth.jwt import get_org_filter
        visible = get_org_filter(current_user)
        if visible is not None and org_id not in visible:
            raise HTTPException(403, "Нет доступа к этой организации")
    uc = (await db.execute(select(func.count()).where(User.org_id == org.id))).scalar() or 0
    return _merge_org_with_contractor(org, user_count=uc)


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
