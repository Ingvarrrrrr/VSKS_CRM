"""Кто может быть инициатором служебной записки (Правило владельца, 14.10.2026,
уточнено 15.10.2026).

Единственное место (Правило №6), где считаются:
  - org_staff_user_ids   — «штат» организации: кто физически числится в ней
    (primary User.org_id ИЛИ членство user_organizations). Персональный
    доступ (user_org_access) в «штат» для инициатора НЕ входит (см. ниже).
  - initiator_candidate_ids — кого текущий пользователь вправе указать
    инициатором служебной записки по конкретной субсидии.

«Штат» = кто числится в организации: основная организация пользователя
(User.org_id) или членство в user_organizations (с должностью). Персональный
доступ к организации (user_org_access) штатом НЕ является (Правило владельца
15.10.2026: Новичкова, User.org_id=1 (ВСКС), с user_org_access.role='employee'
на орг 29 (Донецкое отделение) — НЕ входит в штат орг 29, попадать в список
инициаторов служебки по субсидии орг 29 не должна).

GET /users/ (app/routers/users.py::list_users, параметр org_id) считает ШИРЕ:
штат (см. выше) ОБЪЕДИНЁННЫЙ с персональным доступом (user_org_access) — этот
список используют другие экраны (пикеры исполнителей и т.п.), его поведение
здесь не меняется; он вызывает _staff_conditions() + _org_access_conditions()
(include_access=True), а не ведёт вторую копию формулы (Правило №6).

Правило владельца (дословно, 14.10.2026, штат сужен 15.10.2026):
  «Штат» = сотрудники организации субсидии (subsidy.org_id) — primary org_id
  или членство в user_organizations. НЕ включать людей с персональным доступом
  (ни user_org_access, ни user_subsidy_access) и сотрудников орг-контрагента.
  Вне штата нельзя выбрать НИКОГО, даже подчинённого.

  Кто выбирает (эффективная роль в орг субсидии через
  app.auth.permissions._resolve_role_for_org):
    - account_owner, superadmin → любой из штата;
    - admin («Администратор аккаунта») → любой из штата, ЕСЛИ орг субсидии
      входит в контур его аккаунта (app.auth.visibility.
      compute_account_contour_org_ids);
    - org_admin ЭТОЙ организации (эффективная роль в subsidy.org_id ==
      org_admin) → любой из штата;
    - персональная роль ИМЕННО на ЭТУ субсидию (user_subsidy_access.role,
      привязка к subsidy.id, а не к организации) уровня org_admin/admin/
      account_owner → любой из штата организации субсидии. Пример
      владельца 15.10.2026: Филиппов (org_id=5, глобально ниже) получил
      user_subsidy_access.role='org_admin' на субсидию «ДНР_Правильная»
      (org_id=29) → видит весь штат орг 29, но сам Филиппов не входит в
      штат орг 29 (не её сотрудник) и в список кандидатов не попадает —
      это ожидаемо, этот грант не делает его частью штата;
    - manager, employee (и org_admin другой организации — т.е. эффективная
      роль здесь ниже) → сам + подчинённые (app.routers.task_visibility.
      _get_visible_user_ids; None → SaaS-wide, трактуется как «весь штат»)
      ∩ штат.
  Если выбирающий сам не в штате — себя выбрать не может (пересечение пустое).

Используется: backend/app/routers/users_access.py (/i-can-act-for?subsidy_id=)
и backend/app/services/documents/stages_relations.py::resolve_initiator —
единый источник, не дублируется в wish_documents.py (тот импортирует
resolve_initiator оттуда же).
"""
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _staff_conditions(org_ids):
    """SQL-условия (НЕ выполняются здесь) — «штат» одной или нескольких орг:
    primary User.org_id ИЛИ членство в user_organizations. Персональный доступ
    (user_org_access) сюда НЕ входит — он не штат (Правило владельца
    15.10.2026, см. docstring модуля). Для списков, которым нужен «штат +
    персональный доступ» (например users.py::list_users), складывать с
    _org_access_conditions() — вторая формула штата не пишется (Правило №6).
    """
    from app.models.user import User
    from app.models.user_organization import UserOrganization

    ids = [org_ids] if isinstance(org_ids, int) else list(org_ids)
    member_q = select(UserOrganization.user_id).where(UserOrganization.org_id.in_(ids))
    return [User.org_id.in_(ids), User.id.in_(member_q)]


def _org_access_conditions(org_ids):
    """SQL-условие (НЕ выполняется здесь) — персональный доступ user_org_access
    к одной или нескольким орг. НЕ является «штатом» (см. _staff_conditions);
    используется отдельно там, где нужен штат ∪ доступ (users.py::list_users).
    """
    from app.models.user import User
    from app.models.user_org_access import UserOrgAccess

    ids = [org_ids] if isinstance(org_ids, int) else list(org_ids)
    uoa_q = select(UserOrgAccess.user_id).where(UserOrgAccess.org_id.in_(ids))
    return [User.id.in_(uoa_q)]


async def org_staff_user_ids(db: AsyncSession, org_id: int) -> set[int]:
    """«Штат» организации org_id как множество user_id (см. _staff_conditions).
    Персональный доступ (user_org_access) не включён — не штат.
    """
    from app.models.user import User

    if not org_id:
        return set()
    rows = (await db.execute(
        select(User.id).where(or_(*_staff_conditions(org_id)))
    )).scalars().all()
    return {int(x) for x in rows}


async def initiator_candidate_ids(db: AsyncSession, current_user, subsidy) -> set[int]:
    """Кого current_user вправе указать инициатором служебной записки по subsidy.

    Фолбэк: у субсидии нет org_id (отсутствует привязка к организации) —
    штата как такового не существует, безопасный минимум — только сам
    current_user (иначе служебку нельзя было бы напечатать вовсе).
    """
    org_id = getattr(subsidy, "org_id", None) if subsidy else None
    if not org_id:
        return {current_user.id}

    staff = await org_staff_user_ids(db, org_id)

    if current_user.role == "superadmin":
        return staff
    # ИСПРАВЛЕНИЕ К1 (QA-итерация 2, 19.10.2026): account_owner раньше получал
    # штат ЛЮБОЙ организации — теперь как у admin ниже, только если org_id в
    # контуре его аккаунта (единственный источник — compute_account_contour_org_ids).
    if current_user.role == "account_owner":
        from app.auth.visibility import compute_account_contour_org_ids
        contour = await compute_account_contour_org_ids(db, current_user.org_id)
        if org_id in contour:
            return staff

    # admin («Администратор аккаунта») — весь штат, если орг субсидии в контуре
    # его аккаунта.
    if current_user.role == "admin":
        from app.auth.visibility import compute_account_contour_org_ids
        contour = await compute_account_contour_org_ids(db, current_user.org_id)
        if org_id in contour:
            return staff

    # org_admin ИМЕННО этой организации — ИЛИ персональный UOA-грант уровня
    # admin/account_owner именно в этой орге (Доправка 14.10.2026: человек
    # глобально employee/manager, но user_org_access этой орги даёт роль
    # 'admin'/'account_owner' — _resolve_role_for_org подберёт её как более
    # высокую через combine_role_rank, и это ДОЛЖНО открывать весь штат, как
    # обычному admin/org_admin). Условие `current_user.role != "admin"`
    # отсекает глобального admin ВНЕ контура своего аккаунта (ветка выше):
    # для него effective_role тоже окажется 'admin' (из глобальной роли, не
    # из UOA), а это тот самый случай, которому весь штат не положен.
    from app.auth.permissions import _resolve_role_for_org
    effective_role = await _resolve_role_for_org(current_user, db, org_id)
    if effective_role in ("account_owner", "admin", "org_admin") and current_user.role != "admin":
        return staff

    # Персональная роль ИМЕННО на ЭТУ субсидию (user_subsidy_access, привязка
    # к subsidy.id, а не к организации) уровня org_admin/admin/account_owner —
    # весь штат, как обычному org_admin/admin (Фикс 15.10.2026, Правило №6:
    # не второй механизм, а дополнительная ветка той же функции).
    from app.models.user_subsidy_access import UserSubsidyAccess
    subsidy_role = (await db.execute(
        select(UserSubsidyAccess.role).where(
            UserSubsidyAccess.user_id == current_user.id,
            UserSubsidyAccess.subsidy_id == subsidy.id,
        )
    )).scalar_one_or_none()
    if subsidy_role in ("account_owner", "admin", "org_admin"):
        return staff

    # Остальные (manager/employee/org_admin другой орг) — сам + подчинённые,
    # пересечённые со штатом. Вне штата выбирающий не может выбрать даже себя.
    from app.routers.task_visibility import _get_visible_user_ids
    visible = await _get_visible_user_ids(current_user, db)
    if visible is None:
        return staff
    visible = set(visible)
    visible.add(current_user.id)
    return visible & staff
