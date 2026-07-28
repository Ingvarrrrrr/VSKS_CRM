import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import hash_password, get_current_user, require_superadmin, require_role, OWNER_ROLES
from app.database import get_db
from app.models.organization import Organization
from app.models.contractor import Contractor
from app.models.user import User
from app.schemas.schemas import OrganizationCreate, OrganizationOut, RegisterRequest, UserOut
from app.utils.email import send_verification_email
from app.services.fio import compose_fio

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

    # Структурированные части подписанта: сначала из org, fallback из contractor
    _sig_last = getattr(org, 'signatory_last_name', None) or (getattr(c, 'signatory_last_name', None) if c else None)
    _sig_first = getattr(org, 'signatory_first_name', None) or (getattr(c, 'signatory_first_name', None) if c else None)
    _sig_middle = getattr(org, 'signatory_middle_name', None) or (getattr(c, 'signatory_middle_name', None) if c else None)
    # signatory: если есть структурированные части — пересобираем; иначе legacy fallback
    _signatory_resolved: Optional[str]
    if _sig_last or _sig_first:
        _signatory_resolved = compose_fio(_sig_last, _sig_first, _sig_middle) or pick(org.signatory, getattr(c, 'signatory', None))
    else:
        _signatory_resolved = pick(org.signatory, getattr(c, 'signatory', None))

    return OrganizationOut(
        id=org.id,
        name=org.name,
        full_name=pick(org.full_name, getattr(c, 'full_name', None)),
        inn=pick(org.inn, getattr(c, 'inn', None)),
        kpp=pick(org.kpp, getattr(c, 'kpp', None)),
        ogrn=pick(org.ogrn, getattr(c, 'ogrn', None)),
        address=pick(org.address, getattr(c, 'address', None)),
        signatory=_signatory_resolved,
        signatory_last_name=_sig_last,
        signatory_first_name=_sig_first,
        signatory_middle_name=_sig_middle,
        is_active=org.is_active,
        created_at=org.created_at,
        user_count=user_count,
        root_org_id=org.root_org_id,
        owner_user_id=org.owner_user_id,
        contractor_id=org.contractor_id,
        org_phone=getattr(c, 'org_phone', None) if c else None,
        org_email=getattr(c, 'org_email', None) if c else None,
        color=org.color,
        # Extended contractor requisites
        postal_address=getattr(c, 'postal_address', None) if c else None,
        okpo=getattr(c, 'okpo', None) if c else None,
        okved=getattr(c, 'okved', None) if c else None,
        bank_name=getattr(c, 'bank_name', None) if c else None,
        treasury_account=getattr(c, 'treasury_account', None) if c else None,
        bik=getattr(c, 'bik', None) if c else None,
        single_treasury_account=getattr(c, 'single_treasury_account', None) if c else None,
        registration_date=str(c.registration_date) if c and getattr(c, 'registration_date', None) else None,
        signatory_position=getattr(org, 'signatory_position', None) or (getattr(c, 'signatory_position', None) if c else None),
        signatory_basis=getattr(c, 'signatory_basis', None) if c else None,
        website=getattr(c, 'website', None) if c else None,
        # Geo/delivery fields — нужны фронту для дефолта адреса доставки
        region=org.region or None,
        contract_city=org.contract_city or None,
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


@router.get("/api/organizations/assignable", response_model=List[OrganizationOut])
async def assignable_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Орг, в которые current_user может создавать/добавлять сотрудников.

    Совпадает с бэкенд-гейтом create_user (get_org_filter): своя орг + UOA +
    контур + управляемые орг (ManagerOrganization, «ставит задачи организации»).
    SaaS-роли (superadmin/account_owner) → все орг. Нужен фронту, чтобы менеджер,
    управляющий несколькими орг (напр. Маркодеева → ВСКС + Донецкое), мог выбрать
    целевую орг при добавлении сотрудника, а не был жёстко привязан к своей.
    """
    from app.auth.jwt import get_org_filter
    base_q = select(Organization).options(selectinload(Organization.contractor)).order_by(Organization.name)
    if current_user.role in ('superadmin', 'account_owner'):
        orgs = (await db.execute(base_q)).scalars().all()
    else:
        allowed = get_org_filter(current_user)
        if not allowed:
            return []
        orgs = (await db.execute(base_q.where(Organization.id.in_(allowed)))).scalars().all()
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
    # ИНН уникален (бизнес-правило + UNIQUE-индекс uq_organizations_inn). Заранее
    # отдаём понятную 400 со ссылкой на существующую орг, а не сырой 500.
    _inn = (data.inn or '').strip() if data.inn else ''
    if _inn:
        from fastapi import HTTPException as _HTTPException
        _dup = (await db.execute(
            select(Organization).where(Organization.inn == _inn).limit(1)
        )).scalar_one_or_none()
        if _dup:
            raise _HTTPException(400, f"Организация с ИНН {_inn} уже существует: «{_dup.name}» (id={_dup.id}).")
    # Пересобираем signatory из структурированных частей, если они заданы
    _org_signatory = data.signatory
    if any([data.signatory_last_name, data.signatory_first_name, data.signatory_middle_name]):
        _org_signatory = compose_fio(
            data.signatory_last_name, data.signatory_first_name, data.signatory_middle_name
        ) or data.signatory

    if current_user.role == 'account_owner':
        org = Organization(
            name=data.name,
            full_name=data.full_name,
            inn=data.inn,
            kpp=data.kpp,
            ogrn=data.ogrn,
            address=data.address,
            signatory=_org_signatory,
            signatory_position=data.signatory_position,
            signatory_last_name=data.signatory_last_name,
            signatory_first_name=data.signatory_first_name,
            signatory_middle_name=data.signatory_middle_name,
            is_active=True,
            root_org_id=current_user.org_id,
            owner_user_id=current_user.id,
            contractor_id=data.contractor_id,
            color=data.color,
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
            signatory=_org_signatory,
            signatory_position=data.signatory_position,
            signatory_last_name=data.signatory_last_name,
            signatory_first_name=data.signatory_first_name,
            signatory_middle_name=data.signatory_middle_name,
            is_active=True,
            contractor_id=data.contractor_id,
            color=data.color,
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
    current_user: User = Depends(get_current_user),
):
    # 29.3-a5: GET LIST доступен любому залогиненному (нужен для dropdown'ов
    # «Владелец/Эксплуатат» во VehicleListView, VehicleDetailView, StaffView).
    # Раньше был require_superadmin → admin получал 403, ломая UI dropdown'ы.
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
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    res = await db.execute(
        select(Organization)
        .options(selectinload(Organization.contractor))
        .where(Organization.id == org_id)
    )
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Организация не найдена")
    # ИНН уникален: запрещаем смену на ИНН другой существующей орг (иначе 500 от индекса).
    _inn = (data.inn or '').strip() if data.inn else ''
    if _inn and _inn != (org.inn or ''):
        _dup = (await db.execute(
            select(Organization).where(Organization.inn == _inn, Organization.id != org_id).limit(1)
        )).scalar_one_or_none()
        if _dup:
            raise HTTPException(400, f"Организация с ИНН {_inn} уже существует: «{_dup.name}» (id={_dup.id}).")
    org.name = data.name
    # Explicit contractor_id override (allows un-linking by setting null)
    if data.contractor_id is not None:
        org.contractor_id = data.contractor_id
    for field in ('full_name', 'inn', 'kpp', 'ogrn', 'address', 'color',
                  'signatory_position', 'signatory_last_name', 'signatory_first_name', 'signatory_middle_name'):
        val = getattr(data, field, None)
        if val is not None:
            setattr(org, field, val or None)
    # signatory: если пришли структурированные части — пересобрать; иначе обновить как обычно
    if any([data.signatory_last_name, data.signatory_first_name, data.signatory_middle_name]):
        org.signatory = compose_fio(
            data.signatory_last_name, data.signatory_first_name, data.signatory_middle_name
        ) or org.signatory
    elif data.signatory is not None:
        org.signatory = data.signatory or None
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


@router.patch("/api/organizations/{org_id}/color")
async def update_organization_color(
    org_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    """Phase 30.6: лёгкий endpoint только для смены цвета орг.
    Body: {"color": "#1976d2" | null, "force": false}
    Используется color-picker'ом в HierarchyView чтобы цвет сохранялся в БД
    и был консистентен между Hierarchy / StaffView / другими браузерами.

    Phase 30.6b: каждый цвет должен быть уникален между орг. Если запрошенный
    цвет уже занят другой орг — 409 COLOR_TAKEN с указанием какая орг владелец.
    Передать `force: true` чтобы всё равно сохранить (override).
    """
    color = body.get('color')
    force = bool(body.get('force'))
    if color is not None and not isinstance(color, str):
        raise HTTPException(422, "color должен быть строкой hex или null")
    if color and (not color.startswith('#') or len(color) not in (4, 7)):
        raise HTTPException(422, "color должен быть hex #RGB или #RRGGBB")
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")

    # Phase 30.6b: проверка уникальности цвета (case-insensitive)
    if color and not force:
        normalized = color.lower()
        conflict = (await db.execute(
            select(Organization).where(
                Organization.id != org_id,
                func.lower(Organization.color) == normalized,
            )
        )).scalars().first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COLOR_TAKEN",
                    "message": f"Цвет {color} уже используется организацией «{conflict.name}». Выберите другой цвет или передайте force=true чтобы заменить.",
                    "conflict_org_id": conflict.id,
                    "conflict_org_name": conflict.name,
                },
            )

    org.color = color or None
    await db.commit()
    return {"id": org.id, "color": org.color}


@router.patch("/api/organizations/{org_id}/toggle-active")
async def toggle_org_active(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
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


@router.get("/api/organizations/{org_id}/delete-impact")
async def organization_delete_impact(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    from app.models.user import User as _U
    from app.models.user_organization import UserOrganization as _UO
    from app.models.department import Department as _D
    from app.models.subsidy import Subsidy as _S
    primary_users = (await db.execute(select(_U).where(_U.org_id == org_id, _U.role != 'superadmin'))).scalars().all()
    uo_user_ids = (await db.execute(select(_UO.user_id).where(_UO.org_id == org_id))).scalars().all()
    emp_ids = {u.id for u in primary_users} | set(uo_user_ids)
    employees = []
    if emp_ids:
        rows = (await db.execute(select(_U).where(_U.id.in_(emp_ids)))).scalars().all()
        employees = [{"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role} for u in rows]
    dept_count = (await db.execute(select(func.count()).select_from(_D).where(_D.org_id == org_id))).scalar() or 0
    subsidy_count = (await db.execute(select(func.count()).select_from(_S).where(_S.org_id == org_id))).scalar() or 0
    return {
        "org_id": org_id,
        "org_name": org.name,
        "employee_count": len(employees),
        "employees": employees,
        "department_count": int(dept_count),
        "subsidy_count": int(subsidy_count),
        "has_dependencies": bool(employees or dept_count or subsidy_count),
    }


@router.delete("/api/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: int,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not force:
        from app.models.user import User as _U
        from app.models.user_organization import UserOrganization as _UO
        from app.models.department import Department as _D
        from app.models.subsidy import Subsidy as _S
        emp = (await db.execute(select(func.count()).select_from(_U).where(_U.org_id == org_id, _U.role != 'superadmin'))).scalar() or 0
        emp += (await db.execute(select(func.count()).select_from(_UO).where(_UO.org_id == org_id))).scalar() or 0
        depts = (await db.execute(select(func.count()).select_from(_D).where(_D.org_id == org_id))).scalar() or 0
        subs = (await db.execute(select(func.count()).select_from(_S).where(_S.org_id == org_id))).scalar() or 0
        if emp or depts or subs:
            raise HTTPException(status_code=409, detail=(
                f"Нельзя удалить организацию: связано сотрудников {int(emp)}, "
                f"отделов {int(depts)}, субсидий {int(subs)}. "
                f"Сначала перенесите/отвяжите их или подтвердите принудительное удаление."
            ))
    await db.delete(org)
    await db.commit()
