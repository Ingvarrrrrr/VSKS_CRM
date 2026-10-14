"""Наследование персональных overrides для users.all_orgs_access.

Решение владельца продукта (2026-10-14): «Доступ ко всем организациям
аккаунта» должен работать ОДНОЙ галочкой — в организациях аккаунта, где у
сотрудника НЕТ СВОИХ настроек вкладок/действий (user_org_permission_overrides
пусты для этой пары user/org), действуют настройки его ОСНОВНОЙ организации
(users.org_id). Где свои настройки заданы хоть по одному ключу — остаются
свои, наследование для этой орги не применяется.

Правило №6 (один показатель — один источник истины): это ЕДИНСТВЕННОЕ место,
где решается «наследовать ли» и «overrides какой пары (user, org) читать».
Все вызывающие места обязаны спрашивать здесь, а не писать свою копию этой
проверки:
  - app/auth/permissions.py::_get_effective_simple (Step 2, расчёт
    ЭФФЕКТИВНЫХ прав для tab/action-гейтов и видимости субсидий/орг);
  - app/routers/permissions.py::list_overrides (GET — что показать в UI);
  - app/routers/permissions.py::_apply_overrides_for_org (PUT — копирует
    overrides основной орги в целевую ПЕРЕД применением правки, чтобы снятие
    одной галочки в орге без своих настроек не обнулило остальные
    унаследованные ключи).

Роль (user_org_access.role) этим модулем НЕ затрагивается и не наследуется —
роль пользователя в каждой организации по-прежнему настраивается отдельно
(см. _resolve_role_for_org в permissions.py). Наследуются только boolean-flip
overrides вкладок/действий.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride


async def org_overrides_map(user_id: int, org_id: Optional[int], db: AsyncSession) -> dict:
    """dict key->granted для пары (user_id, org_id).

    Пусто, если org_id не задан, нет UserOrgAccess для этой пары, или у
    существующего UOA нет ни одной строки override. Общий хелпер — вместо
    того чтобы каждое место само строило JOIN UserOrgPermissionOverride +
    UserOrgAccess (так было раньше только в _get_effective_simple)."""
    if not org_id:
        return {}
    rows = (await db.execute(
        select(UserOrgPermissionOverride.key, UserOrgPermissionOverride.granted)
        .join(
            UserOrgAccess,
            UserOrgPermissionOverride.user_org_access_id == UserOrgAccess.id,
        )
        .where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )).all()
    return {key: granted for (key, granted) in rows}


async def inherited_overrides_source_org(
    user: User, db: AsyncSession, org_id: Optional[int]
) -> Optional[int]:
    """Возвращает user.org_id (основную оргу) как ИСТОЧНИК overrides для
    org_id, если ВСЁ из перечисленного верно, иначе None:

    - users.all_orgs_access включён у user;
    - роль user не superadmin/account_owner (SaaS-роли не используют этот
      механизм — они и так видят весь эффективный набор ключей отдельной
      веткой в _get_effective_simple);
    - у user задана основная организация (user.org_id), и она НЕ совпадает
      с org_id (наследовать нечего — это и есть источник);
    - org_id входит в охват users.all_orgs_access
      (get_all_orgs_access_org_ids — используется кэш
      user._all_orgs_access_org_ids, выставленный jwt.get_current_user, если
      он есть на объекте; иначе считается заново, напр. для ЦЕЛЕВОГО
      пользователя в routers/permissions.py, у которого этого кэша нет);
    - у пары (user, org_id) НЕТ ни одной строки overrides — если UserOrgAccess
      для org_id существует, но overrides в ней пусты, это ТОЖЕ считается
      «своих настроек нет» (наследование применяется);
    - у ОСНОВНОЙ организации (user.org_id) есть UserOrgAccess — без неё
      наследовать нечего (копирование дало бы пустое множество, неотличимое
      от «наследования нет», поэтому явно не считаем org_id источником).
    """
    if not getattr(user, 'all_orgs_access', False):
        return None
    if user.role in ('superadmin', 'account_owner'):
        return None
    if not org_id or not user.org_id:
        return None
    if int(org_id) == int(user.org_id):
        return None

    cached = getattr(user, '_all_orgs_access_org_ids', None)
    if cached is not None:
        scope = {int(x) for x in cached}
    else:
        from app.auth.visibility import get_all_orgs_access_org_ids
        scope = await get_all_orgs_access_org_ids(user, db)
    if int(org_id) not in scope:
        return None

    own = await org_overrides_map(user.id, org_id, db)
    if own:
        return None

    primary_uoa_id = (await db.execute(
        select(UserOrgAccess.id).where(
            UserOrgAccess.user_id == user.id,
            UserOrgAccess.org_id == user.org_id,
        )
    )).scalar_one_or_none()
    if primary_uoa_id is None:
        return None

    return int(user.org_id)
