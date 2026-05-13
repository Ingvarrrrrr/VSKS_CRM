from datetime import datetime, timedelta, timezone
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User

# Role constants
ROLES = ("superadmin", "account_owner", "admin", "org_admin", "manager", "employee")
ADMIN_ROLES = ("superadmin", "account_owner", "admin", "org_admin")
MANAGER_ROLES = ("superadmin", "account_owner", "admin", "org_admin", "manager")
OWNER_ROLES = ("superadmin", "account_owner")
ALL_ROLES = ROLES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise cred_exc
    except JWTError:
        raise cred_exc
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise cred_exc
    # Multi-org: read org_ids list from JWT (superadmin multi-select)
    jwt_org_ids = payload.get("org_ids")
    if jwt_org_ids is not None:
        user._active_org_ids = [int(x) for x in jwt_org_ids]
    else:
        user._active_org_ids = None
    # Single org override (backward compat)
    jwt_org_id = payload.get("org_id")
    if jwt_org_id is not None:
        user._active_org_id = int(jwt_org_id)
    else:
        user._active_org_id = user.org_id
    return user

def require_role(*roles):
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Доступ только для ролей: {', '.join(roles)}. Ваша роль: {user.role}."
            )
        return user
    return checker

def get_org_filter(current_user: User) -> Optional[List[int]]:
    """Returns None for superadmin without selection, list of org_ids otherwise."""
    if current_user.role == 'superadmin':
        org_ids = getattr(current_user, '_active_org_ids', None)
        return org_ids  # None = no filter (all), list = selected orgs
    # For all other roles: use contour org_ids from JWT if available
    org_ids = getattr(current_user, '_active_org_ids', None)
    if org_ids:
        return org_ids
    # Fallback: single org
    active_org_id = getattr(current_user, '_active_org_id', current_user.org_id)
    return [active_org_id] if active_org_id else None

def get_single_org_id(current_user: User) -> Optional[int]:
    """Get single org_id for entity creation. Uses first selected org for superadmin."""
    if current_user.role == 'superadmin':
        org_ids = getattr(current_user, '_active_org_ids', None)
        if org_ids and len(org_ids) > 0:
            return org_ids[0]
        return None
    return getattr(current_user, '_active_org_id', current_user.org_id)

async def check_org_active(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Dependency: raises 403 if user's org is inactive."""
    if current_user.role in ('superadmin', 'account_owner'):
        return current_user
    if current_user.org_id is None:
        raise HTTPException(status_code=403, detail="Пользователь не привязан к организации")
    from app.models.organization import Organization
    org = await db.get(Organization, current_user.org_id)
    if not org or not org.is_active:
        raise HTTPException(status_code=403, detail="Подписка организации неактивна")
    return current_user

def require_superadmin():
    async def checker(user: User = Depends(get_current_user)):
        if user.role != 'superadmin':
            raise HTTPException(
                status_code=403,
                detail=f"Этот эндпоинт доступен только суперадминистратору SaaS. Ваша роль: {user.role}. Возможно фронтенд использует не тот endpoint — для своих организаций нужен /api/organizations/my."
            )
        return user
    return checker
