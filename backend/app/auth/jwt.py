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
    # Per-org data scope: орг, к которым у пользователя есть явный доступ через
    # user_org_access (напр. org_admin привязан к Донецкому через роль).
    # Без этого data-scope опирался только на JWT-контур/user_organizations —
    # пользователь видел вкладки, но не данные своей орг (субсидии/персонал пусты).
    user._uoa_org_ids = []
    if user.role not in ('superadmin', 'account_owner'):
        from app.models.user_org_access import UserOrgAccess
        # Модель A: user_org_access — самодостаточный источник полномочий.
        # Data-scope = все орги с допуском, БЕЗ требования членства в
        # user_organizations. Полномочия ≠ трудоустройство: управляющий, дающий
        # распоряжения нескольким орг, имеет допуск, но не обязан быть их штатом.
        _uoa_ids = (await db.execute(
            select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == user.id)
        )).scalars().all()
        user._uoa_org_ids = list({int(x) for x in _uoa_ids if x})
    # Контур аккаунта: глобальная роль (user.role) действует на ВЕСЬ аккаунт
    # (корневая орга + все её дочерние), а не только на primary-оргу. Без этого
    # сотрудники корня теряют субсидии, перепривязанные к дочерним оргам
    # (Wave 2: org_id = грантополучатель), а орг-роли остаются per-org через UOA.
    user._contour_org_ids = []
    if user.role not in ('superadmin', 'account_owner') and user.org_id:
        from app.models.organization import Organization
        _org = await db.get(Organization, user.org_id)
        if _org:
            _root_id = int(_org.root_org_id or _org.id)
            _kid_ids = (await db.execute(
                select(Organization.id).where(Organization.root_org_id == _root_id)
            )).scalars().all()
            user._contour_org_ids = list({_root_id, *(int(x) for x in _kid_ids)})
    return user

async def has_role_via_hierarchy(
    user: User, db: AsyncSession, *roles: str, org_id: Optional[int] = None
) -> bool:
    """True если у current user role в roles ИЛИ в его visible_user_ids
    есть юзер с одной из этих ролей.

    Принцип «иерархия > роли»: кто может ставить задачи юзеру X —
    наследует его роль/доступ. Используется в require_role и
    require_superadmin для проверки иерархического старшинства.

    org_id — орг-осознанный режим: UOA-роль засчитывается только если выдана
    для этой орги (орг-роль даёт власть только в своей орге). Без org_id —
    гейт-режим: любая UOA-роль проходит (данные скоупятся отдельно).

    'superadmin' НЕ достижим через UOA или иерархию: суперадмин невидим для
    не-суперадминов, его роль не наследуется (только сам user.role).
    """
    if user.role in roles:
        return True

    roles = tuple(r for r in roles if r != 'superadmin')
    if not roles:
        return False

    from app.models.user_org_access import UserOrgAccess
    # Модель A: UOA-роль повышает права (вкладки/действия), без требования
    # членства. user_org_access — источник полномочий; членство — только HR.
    uoa_q = select(UserOrgAccess.role).where(
        UserOrgAccess.user_id == user.id,
        UserOrgAccess.role.isnot(None),
    )
    if org_id is not None:
        uoa_q = uoa_q.where(UserOrgAccess.org_id == org_id)
    uoa_rows = (await db.execute(uoa_q)).all()
    uoa_roles = [r for (r,) in uoa_rows]
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
    # For all other roles: account contour (глобальная роль действует на весь
    # аккаунт) + JWT-выборка + per-org access (UOA).
    uoa_ids = getattr(current_user, '_uoa_org_ids', None) or []
    contour_ids = getattr(current_user, '_contour_org_ids', None) or []
    org_ids = getattr(current_user, '_active_org_ids', None)
    base = list(org_ids) if org_ids else []
    if not base:
        active_org_id = getattr(current_user, '_active_org_id', current_user.org_id)
        if active_org_id:
            base = [active_org_id]
    merged = list({*base, *uoa_ids, *contour_ids})
    return merged or None

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
