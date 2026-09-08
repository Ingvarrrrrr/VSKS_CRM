"""CRUD-ядро пользователей/сотрудников: список/карточка/создание/правка/удаление
+ синхронизация членства в отделе (используется CRUD-эндпоинтами здесь и
внешним потребителем app/routers/departments.py).

РАЗРЕЗАНО (Правило №5, сессия 2026-09-08) из монолитного users.py (1666 строк) на:
  - app/routers/users_access.py — GET /assignable-ids, /in-my-orgs, /i-can-act-for
    (списки для пикеров исполнителей/инициаторов; регистрируются ДО этого
    роутера в app/routes.py — литералы совпадают по форме с GET /{user_id}).
  - app/routers/users_me.py — GET /me + подпись/фото/скан-права/visibility-debug
    ТЕКУЩЕГО пользователя (/me/...). GET /me тоже литерал, регистрируется ДО
    этого роутера по той же причине.
  - app/routers/users_docs.py — фото/скан-удостоверения КОНКРЕТНОГО пользователя
    (/{user_id}/photo, /{user_id}/license-scan) + /{user_id}/sync-contractor.
  - app/routers/users_platform_credentials.py — /{user_id}/platform-credentials*
    (учётки для публикации на ЭТП).
  - app/routers/users_dictionaries.py — GET /dictionaries/departments|positions.
  - app/routers/users_import.py — /import/template, /import/excel (bulk-импорт).

_sync_head_hierarchy остаётся здесь: единственный внешний потребитель,
app/routers/departments.py, импортирует его по прежнему пути
`from app.routers.users import _sync_head_hierarchy` — путь не менялся,
потребитель не переписывался.
"""
from datetime import date as _date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Phase 29 D-04: date fields added to users PATCH (Lesson 2026-05-13)
_DATE_FIELDS = {
    "license_issued_at",
    "license_expires_at",
    "medical_cert_expires_at",
    "tachograph_card_expires_at",
    "psych_cert_expires_at",
    "periodic_medical_expires_at",
}
from app.database import get_db
from app.models.user import User
from app.services.fio import resolve_user_name_input
from app.auth.jwt import hash_password, get_current_user, get_org_filter
from app.schemas.schemas import UserCreate, UserUpdate, UserOut
from app.auth.permissions import require_action, ensure_user_org_access
from typing import List, Optional

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    can_drive: Optional[bool] = Query(None, description="Phase 30.2: фильтр водителей — can_drive=true"),
    fleet_role: Optional[str] = Query(None, description="Фильтр по fleet_role (driver/mechanic/doctor/...)"),
    limit: int = Query(500, ge=1, le=1000),
    org_id: Optional[int] = Query(None, description="Вернуть всех членов этой орг: primary User.org_id ИЛИ членство в user_organizations ИЛИ user_org_access"),
    subsidy_id: Optional[int] = Query(None, description="Вернуть всех сотрудников орг(а), связанных с субсидией: subsidy.org_id + орг по contractor_id + орг с тем же ИНН (учёт дублей орг)"),
):
    q = select(User).order_by(User.full_name)
    # D-09: hide superadmin from non-superadmin callers
    if current_user.role != "superadmin":
        q = q.where(User.role != "superadmin")
    org_ids = get_org_filter(current_user)
    explicit_assign_mode = org_id is not None or subsidy_id is not None
    # Контур вызывающего применяем НИЖЕ — только если НЕ передан явный org_id/subsidy_id.
    # В режиме назначения (явная цель) список = сотрудники орг субсидии
    # ∪ те, кому вызывающий может ставить задачи (подчинённые/управляемые орг и
    # отделы, в т.ч. из ДРУГИХ организаций). Контур НЕ применяем, иначе он резал бы
    # union до активной орг вызывающего (баг: super/owner с активной орг=5 видел 2 чел).
    # Резолвим целевой набор орг: явный org_id + (по субсидии) орг контрагента и
    # орг с тем же ИНН — чтобы дубли организаций (одно юрлицо = несколько org-строк)
    # не урезали список сотрудников.
    target_org_ids: set[int] = set()
    if org_id is not None:
        target_org_ids.add(org_id)
    if subsidy_id is not None:
        from app.models.subsidy import Subsidy
        from app.models.organization import Organization
        from app.models.contractor import Contractor
        sub = await db.get(Subsidy, subsidy_id)
        if sub is not None:
            inns: set[str] = set()
            if sub.org_id:
                target_org_ids.add(sub.org_id)
                o = await db.get(Organization, sub.org_id)
                if o is not None and o.inn:
                    inns.add(o.inn)
            if sub.contractor_id:
                c = await db.get(Contractor, sub.contractor_id)
                if c is not None and c.inn:
                    inns.add(c.inn)
                rows = (await db.execute(
                    select(Organization.id, Organization.inn).where(
                        Organization.contractor_id == sub.contractor_id
                    )
                )).all()
                for oid, oinn in rows:
                    target_org_ids.add(oid)
                    if oinn:
                        inns.add(oinn)
            if inns:
                inn_org_ids = (await db.execute(
                    select(Organization.id).where(Organization.inn.in_(list(inns)))
                )).scalars().all()
                target_org_ids.update(inn_org_ids)
    if explicit_assign_mode:
        from sqlalchemy import or_
        from app.models.user_organization import UserOrganization

        def _org_member_conds(target_list: list[int]) -> list:
            member_q = select(UserOrganization.user_id).where(UserOrganization.org_id.in_(target_list))
            conds = [User.org_id.in_(target_list), User.id.in_(member_q)]
            from app.models.user_org_access import UserOrgAccess
            uoa_q = select(UserOrgAccess.user_id).where(UserOrgAccess.org_id.in_(target_list))
            conds.append(User.id.in_(uoa_q))
            return conds

        if subsidy_id is not None:
            # СТРОГО по субсидии (для всех ролей, включая super): исполнителями и
            # согласующими могут быть только сотрудники орг(а) субсидии или люди
            # с персональным доступом к ней — иначе не закрыться по документам.
            # Никакого union с «кому могу ставить задачи» и контуром.
            from app.models.user_subsidy_access import UserSubsidyAccess
            conds = _org_member_conds(list(target_org_ids)) if target_org_ids else []
            conds.append(User.id.in_(
                select(UserSubsidyAccess.user_id).where(UserSubsidyAccess.subsidy_id == subsidy_id)
            ))
            q = q.where(or_(*conds))
        else:
            from app.services.consent import compute_assignable_user_ids
            # Кому вызывающий может ставить задачи. None = super-роль → ВСЕ (без ограничений).
            assignable = await compute_assignable_user_ids(current_user, db)
            if assignable is not None:
                conds = _org_member_conds(list(target_org_ids)) if target_org_ids else []
                if assignable:
                    conds.append(User.id.in_(list(assignable)))
                # Пустой conds (нет ни орг, ни assignable) → вернуть пусто, не весь список.
                q = q.where(or_(*conds)) if conds else q.where(User.id == -1)
    elif org_ids is not None:
        # Обычный режим (без явной цели) — ограничиваем орг вызывающего.
        # СТРОГИЙ скоуп (как в subsidies scope=strict): орг, где вызывающий реально
        # состоит (primary/членство/UOA) или которыми управляет. Контур аккаунта
        # (root+дети) НЕ применяется: менеджер ВСКС не должен видеть сотрудников
        # дочернего Центрпоиска только из-за дерева орг — наследования по дереву нет.
        from sqlalchemy import or_
        from app.models.user_organization import UserOrganization
        from app.models.user_org_access import UserOrgAccess
        if current_user.role not in ('superadmin', 'account_owner'):
            from app.models.manager_organization import ManagerOrganization
            strict: set[int] = set()
            if current_user.org_id:
                strict.add(int(current_user.org_id))
            strict |= {int(r[0]) for r in (await db.execute(
                select(UserOrganization.org_id).where(UserOrganization.user_id == current_user.id)
            )).all() if r[0]}
            strict |= {int(r[0]) for r in (await db.execute(
                select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == current_user.id)
            )).all() if r[0]}
            strict |= {int(r[0]) for r in (await db.execute(
                select(ManagerOrganization.org_id).where(ManagerOrganization.manager_user_id == current_user.id)
            )).all() if r[0]}
            org_ids = list(strict)
        # Bugfix: членство в орг определяется не только primary User.org_id, но и
        # записями user_organizations (отдел/иерархия) и user_org_access. Иначе
        # сотрудник, состоящий в отделе через user_organizations (виден в Иерархии),
        # но с другим/пустым User.org_id, пропадал из списка «Сотрудники».
        conds = [
            User.org_id.in_(org_ids),
            User.id.in_(select(UserOrganization.user_id).where(UserOrganization.org_id.in_(org_ids))),
            User.id.in_(select(UserOrgAccess.user_id).where(UserOrgAccess.org_id.in_(org_ids))),
        ]
        q = q.where(or_(*conds)) if org_ids else q.where(User.id == -1)
    # Phase 30.2: driver-only filter — can_drive=True OR fleet_role='driver'
    if can_drive is True:
        from sqlalchemy import or_
        q = q.where(or_(User.can_drive == True, User.fleet_role == "driver"))
    elif fleet_role:
        q = q.where(User.fleet_role == fleet_role)
    q = q.limit(limit)
    result = await db.execute(q)
    users = result.scalars().all()
    # Rule #6: единственный резолвер должности — users.position больше не
    # синхронизируется при каждой правке, поэтому подставляем актуальное
    # значение в ответ (не persist — сессия не коммитится после этого чтения).
    from app.services.user_position import resolve_user_position, bulk_load_memberships
    memberships_map = await bulk_load_memberships(db, (u.id for u in users))
    for u in users:
        u.position = resolve_user_position(u, memberships=memberships_map.get(u.id))
    return users


@router.post("/", response_model=UserOut)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action('user.manage')),
):
    # Email uniqueness check
    existing_email = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if existing_email:
        raise HTTPException(400, "Пользователь с таким email уже существует")

    # Auto-generate username from email if not provided
    username = data.username
    if not username:
        base = data.email.split('@')[0].lower()
        username = base
        suffix = 1
        while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"{base}{suffix}"
            suffix += 1
    else:
        existing = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "Пользователь с таким логином уже существует")

    # Куда создаём сотрудника. org_admin привязан к своей орг через user_org_access
    # (напр. Артеева → Донецкое, org 26), а его базовый User.org_id может быть пуст.
    # Поэтому принимаем org_id из запроса, если он входит в доступные пользователю
    # орг (get_org_filter учитывает JWT-контур + UOA). SaaS-роли — без ограничений.
    from app.auth.jwt import get_org_filter
    allowed = get_org_filter(current_user)  # None = все орг (SaaS), иначе список
    requested = data.org_id
    if current_user.role in ('superadmin', 'account_owner'):
        org_id = requested or current_user.org_id or (allowed[0] if allowed else None)
    elif requested and (allowed is None or requested in allowed):
        org_id = requested
    else:
        org_id = current_user.org_id or (allowed[0] if allowed else None)
    if not org_id:
        raise HTTPException(400, "Необходимо указать организацию")

    # Орг могла быть удалена при мерже дублей по ИНН — тогда id из localStorage/JWT
    # «протух». Без этой проверки insert падал FK-violation → INTERNAL_ERROR без
    # внятного сообщения. Отдаём чистую 400 с просьбой выбрать орг из списка.
    from app.models.organization import Organization
    if not await db.get(Organization, org_id):
        raise HTTPException(400, f"Организация (id={org_id}) не найдена — возможно, была объединена. Выберите организацию из списка.")

    # ФИО: last_name/first_name — источник истины, full_name пересобирается
    # (обратная совместимость со старыми клиентами — одна строка через split_fio).
    last_name, first_name, middle_name, full_name = resolve_user_name_input(
        data.last_name, data.first_name, data.middle_name, data.full_name
    )
    if not last_name or not first_name:
        raise HTTPException(400, "Укажите фамилию и имя сотрудника")

    norm_dept = data.department.strip().title() if data.department else data.department
    user = User(
        username=username,
        password_hash=hash_password(data.password),
        role=data.role,
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        full_name=full_name,
        city=data.city,
        department=norm_dept,
        position=data.position,
        phone=data.phone,
        telegram_id=__import__('re').sub(r'[^0-9]', '', str(data.telegram_id)) if data.telegram_id else None,
        email=data.email,
        avatar=data.avatar,
        is_email_confirmed=True,
        org_id=org_id,
        inn=data.inn,
        all_orgs_access=data.all_orgs_access,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Phase 17.1-05: sync primary org access entry
    if user.org_id:
        await ensure_user_org_access(user.id, user.org_id, user.role, db)
        await db.commit()
    # Sync to department if set (свежий пользователь — членств ещё нет, org_id
    # известен однозначно, никакой неоднозначности при записи должности).
    if user.department:
        await _sync_user_department(user, db, hired_at=data.hired_at, position=data.position)
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(404, "Пользователь не найден")
    from app.services.user_position import resolve_user_position, bulk_load_memberships
    memberships_map = await bulk_load_memberships(db, [user.id])
    user.position = resolve_user_position(user, memberships=memberships_map.get(user.id))
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action('user.manage')),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if current_user.role == 'account_owner' and user.org_id != current_user.org_id:
        raise HTTPException(403, "Нет доступа")

    update_data = data.dict(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd:
            if current_user.role not in ("superadmin", "account_owner"):
                raise HTTPException(403, "Изменение пароля доступно только владельцу аккаунта и выше")
            user.password_hash = hash_password(pwd)

    # ФИО: last_name/first_name/middle_name — источник истины, full_name всегда
    # пересобирается (см. app/services/fio.py:resolve_user_name_input). PATCH
    # частичный — недостающие части подтягиваем из текущего значения на user,
    # чтобы правка одного поля (напр. только first_name) не затирала остальные.
    explicit_parts = any(k in update_data for k in ("last_name", "first_name", "middle_name"))
    explicit_full = "full_name" in update_data
    if explicit_parts:
        merged_last, merged_first, merged_middle, merged_full = resolve_user_name_input(
            update_data.get("last_name", user.last_name),
            update_data.get("first_name", user.first_name),
            update_data.get("middle_name", user.middle_name),
            None,
        )
    elif explicit_full:
        merged_last, merged_first, merged_middle, merged_full = resolve_user_name_input(
            None, None, None, update_data.get("full_name")
        )
    if explicit_parts or explicit_full:
        if not merged_last or not merged_first:
            raise HTTPException(400, "У сотрудника должны быть заполнены фамилия и имя")
        update_data["last_name"] = merged_last
        update_data["first_name"] = merged_first
        update_data["middle_name"] = merged_middle
        update_data["full_name"] = merged_full

    # Normalize department name to Title Case
    if "department" in update_data and update_data["department"]:
        update_data["department"] = update_data["department"].strip().title()

    # Strip non-digits from telegram_id
    import re as _re
    if "telegram_id" in update_data and update_data["telegram_id"]:
        update_data["telegram_id"] = _re.sub(r'[^0-9]', '', str(update_data["telegram_id"]))

    # Rule #6: должность больше НЕ пишется на users.position из этого эндпоинта —
    # единственный писатель app.services.user_position.set_user_position решает,
    # в какую строку user_organizations она уйдёт (см. ниже, после department-sync).
    # Здесь только выдёргиваем поле из общего цикла setattr, чтобы оно не легло
    # напрямую на устаревшую колонку.
    position_provided = "position" in update_data
    new_position = update_data.pop("position", None)

    for k, v in update_data.items():
        # Phase 29 D-04: coerce ISO string → date for driver date fields (Lesson 2026-05-13)
        if k in _DATE_FIELDS and isinstance(v, str):
            try:
                v = _date_type.fromisoformat(v[:10]) if v else None
            except Exception:
                v = None
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)

    # Phase 17.1-05: sync primary org access when org/role changes
    if ("org_id" in update_data or "role" in update_data) and user.org_id:
        await ensure_user_org_access(user.id, user.org_id, user.role, db)
        await db.commit()

    # Sync department membership (создаёт/находит строку user_organizations для
    # user.org_id + user.department; если position тоже прислали — пишет её
    # ТУДА ЖЕ через set_user_position, однозначно, т.к. dept/org уже известны).
    from app.services.user_position import POSITION_UNSET
    dept_synced = None
    if "department" in update_data or position_provided:
        dept_synced = await _sync_user_department(
            user, db,
            position=new_position if position_provided else POSITION_UNSET,
        )

    # У пользователя нет legacy department/org_id (не с чем связать membership
    # однозначно через _sync_user_department) — «глобальная» правка position:
    # единственное новое поведение по плану. Одно членство → пишем в него;
    # ни одного — legacy users.position; несколько без явной орг — 422:
    # «Укажите организацию: должность задаётся по организации» (используйте
    # per-org редакторы — departments.py / hierarchy.py org-membership).
    if position_provided and dept_synced is None:
        from app.services.user_position import set_user_position, UserPositionError
        try:
            await set_user_position(db, new_position, user=user, org_id=None)
            await db.commit()
        except UserPositionError as exc:
            raise HTTPException(422, exc.user_message)

    await db.refresh(user)
    # Ответ показывает актуальную должность (не users.position, который больше
    # не синхронизируется при каждой правке — см. resolve_user_position).
    from app.services.user_position import resolve_user_position, bulk_load_memberships
    _memberships_map = await bulk_load_memberships(db, [user.id])
    user.position = resolve_user_position(user, memberships=_memberships_map.get(user.id))
    return user


async def _sync_user_department(user: User, db: AsyncSession, hired_at=None, position=None):
    """Sync user.department to user_organizations table and auto-set hierarchy.

    hired_at (дата приёма) — только для случая, когда это ПЕРВАЯ-ЕВЕР строка
    user_organizations для пары (user_id, org_id): дата назначения в отдел
    и на должность равна ей, а не «сегодня» (владелец, 2026-09-01, см.
    app/services/org_assignment_dates.py). Для перевода/смены должности у
    уже трудоустроенного человека hired_at не используется.

    position — Rule #6: единственный писатель должности (app.services.user_position)
    вызывается ОТСЮДА, а не читает user.position сам. POSITION_UNSET (сентинел,
    по умолчанию — обычный None тоже трактуется как «не меняли», см. вызовы
    выше) означает «в этом вызове должность не меняется» — существующая
    строка/значение не трогается; при создании новой строки — наследуем
    должность от предыдущей строки той же пары (user, org), если она была.

    Возвращает Department, если membership был найден/создан, иначе None
    (нет user.department/user.org_id — синхронизировать нечего).
    """
    from app.models.department import Department
    from app.models.user_organization import UserOrganization as _UO_sync
    from app.services.org_assignment_dates import (
        first_row_assignment_dates, dept_transfer_date, position_change_date,
    )
    from app.services.user_position import set_user_position, POSITION_UNSET

    if not user.department or not user.org_id:
        return None

    # Find or create department
    dept = (await db.execute(
        select(Department).where(
            Department.org_id == user.org_id,
            Department.name == user.department,
        )
    )).scalar_one_or_none()
    if not dept:
        dept = Department(name=user.department, org_id=user.org_id)
        db.add(dept)
        await db.flush()

    # Ensure UO membership (single source of truth)
    existing = (await db.execute(
        select(_UO_sync).where(
            _UO_sync.user_id == user.id,
            _UO_sync.org_id == user.org_id,
            _UO_sync.dept_id == dept.id,
        )
    )).scalar_one_or_none()
    if existing:
        member_row = existing
        if position is not POSITION_UNSET:
            position_changed = position != existing.position
            await set_user_position(db, position, membership=existing)
            existing.position_assigned_at = position_change_date(
                position_changed=position_changed, current=existing.position_assigned_at, explicit=None,
            )
        if existing.dept_assigned_at is None:
            existing.dept_assigned_at = dept_transfer_date(None)
    else:
        # Первая ли это строка вообще для пары (user_id, org_id)? Если да — это
        # приём на работу, обе даты назначения = hired_at. Если нет — человек
        # уже трудоустроен и это перевод в (ещё) один отдел той же пары.
        any_prior = (await db.execute(
            select(_UO_sync)
            .where(_UO_sync.user_id == user.id, _UO_sync.org_id == user.org_id)
            .order_by(_UO_sync.id.asc())
            .limit(1)
        )).scalar_one_or_none()
        new_position = position if position is not POSITION_UNSET else (any_prior.position if any_prior else None)
        kwargs = dict(user_id=user.id, org_id=user.org_id, dept_id=dept.id, position=new_position)
        if hired_at is not None:
            kwargs["hired_at"] = hired_at
        if any_prior is None:
            kwargs.update(first_row_assignment_dates(
                hired_at, has_position=bool(new_position), has_dept=True,
            ))
        else:
            kwargs["dept_assigned_at"] = dept_transfer_date(None)
            position_changed = bool(new_position) and new_position != any_prior.position
            pos_date = position_change_date(
                position_changed=position_changed, current=any_prior.position_assigned_at, explicit=None,
            )
            if pos_date is not None:
                kwargs["position_assigned_at"] = pos_date
        member_row = _UO_sync(**kwargs)
        db.add(member_row)
    await db.flush()

    # Должность в членстве → head/deputy отдела (двусторонняя синхронизация)
    from app.services.dept_role_sync import sync_head_from_position
    await sync_head_from_position(db, dept, user.id, member_row.position)

    # If user is head of this dept — auto-create hierarchy for all members
    if dept.head_user_id == user.id:
        await _sync_head_hierarchy(dept, db)

    await db.commit()
    return dept


async def _sync_head_hierarchy(dept, db: AsyncSession):
    """Make all department members subordinates of the head."""
    from app.models.user_organization import UserOrganization as _UO_hier
    from app.models.user_hierarchy import UserHierarchy

    if not dept.head_user_id:
        return
    members = (await db.execute(
        select(_UO_hier.user_id).where(
            _UO_hier.dept_id == dept.id,
            _UO_hier.user_id != dept.head_user_id,
        )
    )).scalars().all()

    for uid in members:
        existing = (await db.execute(
            select(UserHierarchy).where(
                UserHierarchy.manager_id == dept.head_user_id,
                UserHierarchy.subordinate_id == uid,
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(UserHierarchy(manager_id=dept.head_user_id, subordinate_id=uid))


async def _count_user_references(user_id: int, db: AsyncSession) -> dict:
    """Счётчики записей, которые ссылаются на пользователя (для предупреждения
    перед удалением: при удалении исполнитель/автор станут пустыми)."""
    from sqlalchemy import func
    from app.models.purchase import Purchase
    from app.models.task import Task
    from app.models.subsidy_approver import SubsidyApprover
    from app.models.user_subsidy_access import UserSubsidyAccess

    async def _cnt(q):
        return (await db.execute(q)).scalar() or 0

    refs = {
        "purchases": await _cnt(
            select(func.count()).select_from(Purchase)
            .where(Purchase.assigned_user_id == user_id)
        ),
        "active_purchases": await _cnt(
            select(func.count()).select_from(Purchase).where(
                Purchase.assigned_user_id == user_id,
                Purchase.status.notin_(['paid', 'cancelled']),
            )
        ),
        "tasks": await _cnt(
            select(func.count()).select_from(Task).where(
                (Task.assigned_user_id == user_id) | (Task.created_by_id == user_id)
            )
        ),
        "subsidy_approver": await _cnt(
            select(func.count()).select_from(SubsidyApprover)
            .where(SubsidyApprover.user_id == user_id)
        ),
        "subsidy_access": await _cnt(
            select(func.count()).select_from(UserSubsidyAccess)
            .where(UserSubsidyAccess.user_id == user_id)
        ),
    }
    return refs


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    confirm: bool = Query(False, description="true — подтверждённое удаление несмотря на связанные записи"),
    org_id: Optional[int] = Query(None, description="Контекст орг: если у пользователя есть другие орги — открепить только от этой, аккаунт НЕ удалять"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action('user.manage')),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    # Org-admin ограничен своей орг; account_owner/admin/superadmin — по всей учётке.
    if current_user.role == 'org_admin' and user.org_id != current_user.org_id:
        raise HTTPException(403, "Удалять можно только сотрудников своей организации.")

    # Удаление карточки в контексте орг = открепление от этой орг, а не
    # глобальное удаление аккаунта (инцидент с Филипповым 2026-07-06).
    # Глобальный hard delete — только когда это его последняя организация.
    if org_id is not None:
        from app.models.user_organization import UserOrganization
        from app.models.user_org_access import UserOrgAccess
        from app.auth.permissions import remove_user_org_access

        user_orgs: set[int] = set()
        if user.org_id:
            user_orgs.add(user.org_id)
        uo_orgs = (await db.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == user_id)
        )).scalars().all()
        uoa_orgs = (await db.execute(
            select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == user_id)
        )).scalars().all()
        user_orgs.update(uo_orgs)
        user_orgs.update(uoa_orgs)

        remaining = user_orgs - {org_id}
        if remaining:
            uo_rows = (await db.execute(
                select(UserOrganization).where(
                    UserOrganization.user_id == user_id,
                    UserOrganization.org_id == org_id,
                )
            )).scalars().all()
            for row in uo_rows:
                await db.delete(row)
            await remove_user_org_access(user_id, org_id, db)
            if user.org_id == org_id:
                user.org_id = min(remaining)
            await db.commit()
            return {"ok": True, "detached": True, "org_id": org_id}
        # Последняя орг — падаем в обычный confirm-flow глобального удаления.

    refs = await _count_user_references(user_id, db)
    if not confirm and (any(refs.values()) or org_id is not None):
        parts = []
        if refs["purchases"]:
            act = f" (из них активных: {refs['active_purchases']})" if refs["active_purchases"] else ""
            parts.append(f"закупок (исполнитель): {refs['purchases']}{act}")
        if refs["tasks"]:
            parts.append(f"задач (исполнитель/автор): {refs['tasks']}")
        if refs["subsidy_approver"]:
            parts.append(f"согласующий в субсидиях: {refs['subsidy_approver']}")
        if refs["subsidy_access"]:
            parts.append(f"персональных доступов к субсидиям: {refs['subsidy_access']}")
        msg = ""
        if org_id is not None:
            msg += ("Это единственная организация сотрудника — аккаунт будет удалён "
                    "ПОЛНОСТЬЮ из системы, а не только из этой организации. ")
        if parts:
            msg += (
                "С сотрудником связаны записи: " + "; ".join(parts) + ". "
                "При удалении исполнитель/автор в закупках и задачах станет пустым, "
                "согласующие потеряют привязку к пользователю, персональные доступы будут удалены. "
            )
        msg += "Подтвердите удаление повторно."
        raise HTTPException(409, detail={
            "code": "CONFIRM_DELETE_USER",
            "message": msg,
            "references": refs,
        })

    await db.delete(user)
    await db.commit()
    return {"ok": True}
