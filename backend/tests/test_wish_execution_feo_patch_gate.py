"""Жалоба владельца (2026-09-16): «Я согласующий заявку — не могу одной кнопкой
создать всем позициям в заявке плановую позицию». Причина оказалась чисто
фронтовой (canEditWishFeo не учитывал MANAGER_ROLES, см. useWishForm.ts) —
бэкендовый гейт PATCH /wishes/{id}/execution (wish_transitions.py::
patch_wish_execution) уже пускает менеджера+ ДО этой сессии. Тест фиксирует
именно это правило доступа к построчной правке ФЭО заявки (WishItemFeoPatch),
чтобы дальнейшие правки фронта/бэка не разъехались с ним (Правило №6):

  manager+ (MANAGER_ROLES) ИЛИ assigned_to ИЛИ участник цепочки согласования
  (wish_approvals) — пропускается; любой другой (employee не из цепочки,
  не автор, не назначенный) — 403.

Менеджер в тесте НЕ в цепочке согласования, НЕ автор, НЕ assigned_to — ровно
случай владельца («руководитель по иерархии одобряет по MANAGER_ROLES, но не
числится в явной цепочке»).
"""
import pytest
from app.models.feo_category import FeoCategory
from app.models.permission import UserOrgPermissionOverride
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.wish import Wish
from app.models.wish_item import WishItem


async def _seed_submitted_wish(db_session, test_org, author):
    """Отправленная заявка с одной позицией и категорией ФЭО — минимум, нужный
    PATCH /execution, чтобы патчить body.items[].feo_category_id."""
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория A")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория B")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    w = Wish(
        org_id=test_org.id,
        title="Заявка на согласовании",
        status="submitted",
        created_by=author.id,
        subsidy_id=subsidy.id,
        feo_category_id=cat_a.id,
    )
    db_session.add(w)
    await db_session.flush()

    item = WishItem(
        wish_id=w.id, item_name="Позиция 1",
        quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_a.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(item)
    return w, item, cat_b


async def _grant_wish_edit_feo(db_session, user, org):
    """Персональный override wish.edit_feo=True для (user, org) — не зависит от
    того, засеян ли уже RolePermission('manager', 'wish.edit_feo') в БД теста
    (см. app/startup/permission_seeds.py::_wish_edit_feo_action, дефолт
    manager=True — override здесь гарантирует право детерминированно, без
    попытки INSERT в role_permissions и риска нарваться на uq_role_perm)."""
    uoa = UserOrgAccess(user_id=user.id, org_id=org.id, role=user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_manager_not_in_chain_can_patch_wish_feo(client, db_session, test_org, test_user, make_user):
    """Менеджер+, НЕ в цепочке согласования, НЕ автор, НЕ assigned_to — вправе
    перераспределить позицию заявки по категории ФЭО (тот же круг, что уже
    пускают POST /approve и /reject, wish_transitions.py MANAGER_ROLES)."""
    from app.auth.jwt import create_access_token

    w, item, cat_b = await _seed_submitted_wish(db_session, test_org, test_user)

    manager = await make_user(role="manager", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, manager, test_org)
    manager_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': manager.username, 'org_id': manager.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"items": [{"id": item.id, "feo_category_id": cat_b.id}]},
        headers=manager_headers,
    )

    assert resp.status_code == 200, resp.text
    await db_session.refresh(item)
    assert item.feo_category_id == cat_b.id


@pytest.mark.asyncio
async def test_employee_not_in_chain_cannot_patch_wish_feo(client, db_session, test_org, test_user, make_user):
    """Сотрудник — НЕ автор, НЕ assigned_to, НЕ участник цепочки согласования —
    получает 403, даже с выданным wish.edit_feo (право есть, но круг решающих
    по заявке уже, см. patch_wish_execution: MANAGER_ROLES/assigned_to/in_chain)."""
    from app.auth.jwt import create_access_token

    w, item, cat_b = await _seed_submitted_wish(db_session, test_org, test_user)

    outsider = await make_user(role="employee", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, outsider, test_org)
    outsider_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': outsider.username, 'org_id': outsider.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"items": [{"id": item.id, "feo_category_id": cat_b.id}]},
        headers=outsider_headers,
    )

    assert resp.status_code == 403, resp.text
    await db_session.refresh(item)
    assert item.feo_category_id != cat_b.id
