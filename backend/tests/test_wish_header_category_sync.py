# -*- coding: utf-8 -*-
"""Прод-баг (закупка РЕЕ-2026-04252, заявка №206, 20.10.2026): согласующий
сменил категорию ФЭО шапки заявки (feo_per_item=False — «одна категория на
всю заявку»), а feo_category_id всех 14 WishItem остался со старой. При
конвертации заявки в закупку auto_assign_planned_items заводил новые плановые
позиции в протухшей категории ТОВАРА, а не в категории ШАПКИ — закупка
получала «Расхождение категории ФЭО» по всем товарам.

Два места фикса, оба покрыты здесь:
1. app/routers/wish_transitions.py::patch_wish_execution (PATCH /execution) —
   смена категории шапки теперь сразу переносит позиции (и их плановые
   позиции, если это auto_created строки без других владельцев) — тест HTTP.
2. app/services/plan_autoassign.py::auto_assign_planned_items(per_item_mode=False) —
   даже если позиция ОСТАЛАСЬ со старой категорией (например, другой путь не
   прошёл через sync_items_to_header_category), автозаведение/подбор плана
   обязано взять fallback (категорию шапки), а не протухшую свою, — юнит-тест
   сервиса напрямую.
"""
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import UserOrgPermissionOverride
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.wish import Wish
from app.models.wish_item import WishItem


async def _grant_wish_edit_feo(db_session, user, org):
    """См. test_wish_execution_feo_patch_gate.py::_grant_wish_edit_feo — тот же
    приём (override независим от RolePermission-сидов)."""
    uoa = UserOrgAccess(user_id=user.id, org_id=org.id, role=user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_patch_execution_header_category_change_moves_items_and_plan(
    client, db_session, test_org, test_user, make_user,
):
    """feo_per_item=False, категория A → B через PATCH /execution (без items в
    теле — только шапка, ровно как смог бы сделать согласующий): позиция БЕЗ
    плановой позиции переезжает в B вместе с шапкой; позиция С
    feo_planned_item_id остаётся в своей категории (A) вместе со своим
    планом — владелец (22.10.2026, заявка №209) развернул прежнее поведение
    (позиция по плану раньше переезжала за шапкой и теряла привязку к плану
    при чужом владении — именно это рождало ложные «дубли», см.
    app/services/wish_item_category_guard.py)."""
    subsidy = Subsidy(name=f"TestHeaderSync-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=1, name="Орг. расходы")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=1, name="Ремонт техники")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка №206", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id,
        feo_per_item=False,
    )
    db_session.add(w)
    await db_session.flush()

    fpi = FeoPlannedItem(
        feo_category_id=cat_a.id, name="Запчасть для трактора",
        quantity=Decimal("1"), amount=Decimal("5000.00"),
        is_active=True, auto_created=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    item_with_plan = WishItem(
        wish_id=w.id, item_name="Запчасть для трактора",
        quantity=1, unit_price=5000, total_price=5000,
        feo_category_id=cat_a.id, feo_planned_item_id=fpi.id,
    )
    item_without_plan = WishItem(
        wish_id=w.id, item_name="Канцтовары",
        quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_a.id,
    )
    db_session.add_all([item_with_plan, item_without_plan])
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(item_with_plan)
    await db_session.refresh(item_without_plan)

    manager = await make_user(role="manager", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, manager, test_org)
    from app.auth.jwt import create_access_token
    manager_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': manager.username, 'org_id': manager.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"feo_category_id": cat_b.id},
        headers=manager_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(w)
    await db_session.refresh(item_with_plan)
    await db_session.refresh(item_without_plan)
    await db_session.refresh(fpi)

    assert w.feo_category_id == cat_b.id
    assert item_with_plan.feo_category_id == cat_a.id, "позиция с feo_planned_item_id не переезжает за шапкой"
    assert item_without_plan.feo_category_id == cat_b.id, "позиция без плановой позиции следует за шапкой, как раньше"
    # План не трогается — он не был пропущен через move_or_detach вовсе.
    assert fpi.feo_category_id == cat_a.id
    assert item_with_plan.feo_planned_item_id == fpi.id, "привязка к плану не трогается"


@pytest.mark.asyncio
async def test_auto_assign_per_item_mode_false_uses_header_category(db_session, test_org):
    """Юнит на plan_autoassign.auto_assign_planned_items: позиция с ПРОТУХШЕЙ
    собственной категорией (старая, до смены шапки) — при per_item_mode=False
    эффективная категория всё равно категория шапки (fallback_category_id):
    новая плановая позиция заводится в категории шапки, а не в протухшей
    категории товара, и собственная feo_category_id позиции самоисправляется."""
    subsidy = Subsidy(name=f"TestAutoAssignPerItem-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat_stale = FeoCategory(subsidy_id=subsidy.id, level=1, name="Орг. расходы (протухшая)")
    cat_header = FeoCategory(subsidy_id=subsidy.id, level=1, name="Ремонт техники (шапка)")
    db_session.add_all([cat_stale, cat_header])
    await db_session.flush()

    wish = Wish(
        title="Заявка №206 (юнит)", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=cat_header.id, feo_per_item=False,
    )
    db_session.add(wish)
    await db_session.flush()

    wish_item = WishItem(
        wish_id=wish.id, item_name="Запчасть для комбайна",
        quantity=1, unit_price=3000, total_price=3000,
        feo_category_id=cat_stale.id,  # протухшая — не синхронизирована с шапкой
    )
    db_session.add(wish_item)
    await db_session.commit()
    await db_session.refresh(wish_item)

    from app.services.plan_autoassign import auto_assign_planned_items
    await auto_assign_planned_items(
        [wish_item], wish.feo_category_id, db_session,
        note="тестом per_item_mode=False", per_item_mode=False,
    )
    await db_session.commit()
    await db_session.refresh(wish_item)

    assert wish_item.feo_category_id == cat_header.id, "собственная категория позиции самоисправлена на категорию шапки"
    assert wish_item.feo_planned_item_id is not None
    new_fpi = await db_session.get(FeoPlannedItem, wish_item.feo_planned_item_id)
    assert new_fpi.feo_category_id == cat_header.id, "новая плановая позиция заведена в категории ШАПКИ, не в протухшей категории товара"


@pytest.mark.asyncio
async def test_auto_assign_per_item_mode_true_keeps_old_behavior(db_session, test_org):
    """Контроль отсутствия регресса: per_item_mode=True (по умолчанию) — позиция
    со своей категорией остаётся в НЕЙ, план заводится в категории позиции,
    а не в фолбэке/шапке (ровно старое поведение до этой правки)."""
    subsidy = Subsidy(name=f"TestAutoAssignPerItemTrue-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat_own = FeoCategory(subsidy_id=subsidy.id, level=1, name="Своя категория позиции")
    cat_fallback = FeoCategory(subsidy_id=subsidy.id, level=1, name="Фолбэк/шапка")
    db_session.add_all([cat_own, cat_fallback])
    await db_session.flush()

    wish = Wish(
        title="Заявка per_item=True", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=cat_fallback.id, feo_per_item=True,
    )
    db_session.add(wish)
    await db_session.flush()

    wish_item = WishItem(
        wish_id=wish.id, item_name="Своя позиция",
        quantity=1, unit_price=2000, total_price=2000,
        feo_category_id=cat_own.id,
    )
    db_session.add(wish_item)
    await db_session.commit()
    await db_session.refresh(wish_item)

    from app.services.plan_autoassign import auto_assign_planned_items
    await auto_assign_planned_items(
        [wish_item], wish.feo_category_id, db_session,
        note="тестом per_item_mode=True", per_item_mode=True,
    )
    await db_session.commit()
    await db_session.refresh(wish_item)

    assert wish_item.feo_category_id == cat_own.id, "per_item_mode=True — собственная категория позиции не трогается"
    new_fpi = await db_session.get(FeoPlannedItem, wish_item.feo_planned_item_id)
    assert new_fpi.feo_category_id == cat_own.id
