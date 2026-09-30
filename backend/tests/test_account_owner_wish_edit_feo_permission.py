"""Баг (проверено на проде 2026-09-30, владелец аккаунта id=5): account_owner
не имел action-права 'wish.edit_feo' — app.auth.permissions.get_effective_actions
не возвращал этот ключ для владельца аккаунта, хотя по иерархии ролей
(employee < manager < org_admin < admin < account_owner < superadmin,
см. app/auth/permissions.py ROLE_RANK) он выше admin, которому право дано.

Причина — app/startup/permission_seeds.py::_wish_edit_feo_action ROLE_DEFAULTS
не содержал account_owner (сид написан до появления роли). Исправлено:
1) ROLE_DEFAULTS сида дополнен ('account_owner', True);
2) data-backfill миграция a3c5e7g9i1k3 закрыла разрыв на накопленных данных
   (INSERT ... SELECT admin's granted=True keys для account_owner, где строки
   не было вообще).

Тест фиксирует итоговое поведение через get_effective_actions — ровно ту
функцию, за которой стоит фронтовый canEditWishFeo (useWishForm.ts) и кнопка
«Создать в плане закупок» в карточке заявки."""
import pytest
from sqlalchemy import select

from app.auth.permissions import get_effective_actions
from app.models.permission import RolePermission


@pytest.mark.asyncio
async def test_account_owner_role_permission_row_exists(db_session):
    """Строка ('account_owner', 'wish.edit_feo', granted=True) должна существовать
    в role_permissions — либо от сида (свежая БД), либо от миграции-бэкфилла
    a3c5e7g9i1k3 (уже накопленная БД, где сида ещё не было при первой выдаче
    admin)."""
    res = await db_session.execute(
        select(RolePermission).where(
            RolePermission.role_name == "account_owner",
            RolePermission.key == "wish.edit_feo",
        )
    )
    row = res.scalar_one_or_none()
    assert row is not None, "account_owner лишён строки wish.edit_feo в role_permissions"
    assert row.granted is True


@pytest.mark.asyncio
async def test_account_owner_gets_wish_edit_feo_action(db_session, test_org, make_user):
    """get_effective_actions для account_owner-пользователя обязана содержать
    'wish.edit_feo' — именно это проверяет фронт (canEditWishFeo) для показа
    кнопки «Создать в плане закупок» и правки ФЭО в карточке заявки."""
    owner = await make_user(role="account_owner", org_id=test_org.id)

    actions = await get_effective_actions(owner, db_session, org_id=test_org.id)

    assert "wish.edit_feo" in actions
