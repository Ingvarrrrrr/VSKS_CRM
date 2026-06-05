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

async def has_role_via_hierarchy(user: User, db: AsyncSession, *roles: str) -> bool:
    """True если у current user role в roles ИЛИ в его visible_user_ids
    есть юзер с одной из этих ролей.

    Принцип «иерархия > роли»: кто может ставить задачи юзеру X —
    наследует его роль/доступ. Используется в require_role и
    require_superadmin для проверки иерархического старшинства.
    """
    if user.role in roles:
        return True

    # Per-org elevation: org_admin/manager в любой орг должен удовлетворять
    # require_role того же уровня (вкладки/действия по max-роли; данные скоупятся
    # отдельно). Не затрагивает require_superadmin: org_admin не равен superadmin.
    from app.models.user_org_access import UserOrgAccess
    uoa_roles = (await db.execute(
        select(UserOrgAccess.role).where(
            UserOrgAccess.user_id == user.id,
            UserOrgAccess.role.isnot(None),
        )
    )).scalars().all()
    if any(r in roles for r in uoa_roles):
        return True

    # Avoid circular import — lazy
    from app.auth.visibility import get_visible_user_ids
    visible = await get_visible_user_ids(user, db)
    if visible is None:
        # SaaS-роль (superadmin/account_owner) — уже всё видит. Сюда не дойдёт
        # потому что user.role был бы в roles, но защищаем.
        return True
    visible = visible - {user.id}
    if not visible:
        return False
    from app.models.user import User as _User
    res = await db.execute(
        select(_User.id).where(_User.id.in_(visible), _User.role.in_(roles)).limit(1)
    )
    return res.scalar_one_or_none() is not None


def require_role(*roles):
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if await has_role_via_hierarchy(user, db, *roles):
            return user
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для выполнения операции"
        )
    return checker

def get_org_filter(current_user: User) -> Optional[List[int]]:
    """Returns None for SaaS roles without selection, list of org_ids otherwise.

    Phase 26-Z: account_owner был ошибочно в обычной org-фильтрации, хотя по
    OWNER_ROLES/_SAAS_ROLES должен видеть всё. Цыганов (account_owner) без
    привязки к отделу не видел закупок, потому что _active_org_ids был пуст
    или фильтровал только его явные org'и.
    """
    # SaaS-роли — без фильтра по умолчанию, опционально с активной выборкой
    if current_user.role in ('superadmin', 'account_owner'):
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
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if await has_role_via_hierarchy(user, db, 'superadmin'):
            return user
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для выполнения операции"
        )
    return checker
