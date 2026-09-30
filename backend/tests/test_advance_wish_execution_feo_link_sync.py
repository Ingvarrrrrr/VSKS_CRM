# -*- coding: utf-8 -*-
"""Прод-инцидент (заявка №88 / закупка РЕЕ-2026-00962, 2026-09-30): владелец в
карточке заявки-компаньона авансового отчёта при согласовании создал новые
плановые позиции и перепривязал к ним строки ЗАЯВКИ (PATCH /wishes/{id}/
execution, wish_transitions.py::patch_wish_execution, WishItemFeoPatch), но
purchase_items связанной закупки остались привязаны к СТАРЫМ плановым
позициям — правка в заявке-компаньоне не долетала до закупки, а следующий
PUT закупки эту рассинхронизацию только закреплял бы (заявка-двойник — ЗЕРКАЛО
закупки, источник истины — purchase_items, см. app/services/advance_wish_sync.py).

Итоговое решение (сессия 2026-09-30): НЕ заводить новую колонку под связь
WishItem↔PurchaseItem — она уже есть (`purchase_items.wish_item_id`, миграция
g1h2i3j4k5l6 — тот же hard link, которым уже пользуются wish_distribution.py/
wish_multi_sync.py для обычных заявок). Компаньон авансового отчёта этот link
просто никогда не проставлял, потому что create_purchase/update_purchase
удаляли и пересоздавали WishItems при КАЖДОМ сохранении закупки без обратной
ссылки. Правки (ПРАВИЛО №6, один источник для каждого поля/связи):
  1. purchases.py (create_purchase is_advance-блок и update_purchase
     авансовый sync-блок) теперь проставляют `PurchaseItem.wish_item_id` при
     каждой пересборке WishItems — позиции сопоставляются ПОЗИЦИОННО, т.к.
     покупка и заявка строятся из ОДНОГО и того же списка `items_data` в
     ОДНОМ и том же порядке.
  2. wish_transitions.py::patch_wish_execution зеркалит feo_category_id/
     feo_planned_item_id/over_plan из затронутой WishItem в связанный
     PurchaseItem (найденный по wish_item_id) через общий хелпер
     app/services/advance_wish_sync.py::apply_wish_item_feo_link_to_purchase_item
     — единственное место, которое пишет эти поля со стороны заявки.

Тест покрывает ровно сценарий инцидента: авансовый с ДВУМЯ одноимёнными
строками из разных чеков (одинаковое item_name, разная unit_price — как в
инциденте «Мешки 180л» ×2 с разных чеков), перепривязка ВТОРОЙ строки к новой
плановой позиции через заявку-компаньон → purchase_item тоже перепривязан;
затем обычный PUT закупки (пересобирает purchase_items И wish_items целиком)
не должен откатить/потерять эту привязку.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase_item import PurchaseItem
from app.models.permission import UserOrgPermissionOverride
from app.models.user_org_access import UserOrgAccess


async def _make_subsidy(db_session, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",  # assert_subsidy_approved_for_binding гейтит create/update_purchase
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        budget=kwargs.pop("budget", Decimal("1000000")),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=kwargs.pop("name", "Мешки 180л"),
        quantity=kwargs.pop("quantity", Decimal("6")),
        unit=kwargs.pop("unit", "шт"),
        amount=kwargs.pop("amount", Decimal("600")),
        **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _grant_wish_edit_feo(db_session, user, org):
    """Персональный override wish.edit_feo=True — тот же приём, что и в
    test_wish_execution_feo_patch_gate.py (не зависит от засеянных RolePermission)."""
    uoa = UserOrgAccess(user_id=user.id, org_id=org.id, role=user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_wish_execution_feo_rebind_propagates_to_purchase_item_and_survives_put(
    client, auth_headers, db_session, test_org, make_user,
):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    # amount с запасом (2000) — обе строки (600 + 1200 = 1800) изначально висят
    # на old_fpi, иначе create_purchase уткнётся в 409 «ТЗ над плановой позицией»
    # ДО того, как дойти до сценария теста (assert_tz_batch_not_over_plan).
    old_fpi = await _make_planned_item(db_session, cat.id, name="Мешки 180л (старый чек)", amount=Decimal("2000"))
    new_fpi = await _make_planned_item(db_session, cat.id, name="Мешки 180л (новый чек)", amount=Decimal("2000"))

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест переприв ФЭО построчно",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Мешки 180л",
                "item_type": "товар",
                "quantity": 6,
                "unit": "шт",
                "unit_price": 100,
                "total_price": 600,
                "feo_category_id": cat.id,
                "feo_planned_item_id": old_fpi.id,
            },
            {
                # Та же позиция вторым чеком — цена другая (как в проде: две
                # одноимённые строки из разных чеков).
                "item_name": "Мешки 180л",
                "item_type": "товар",
                "quantity": 6,
                "unit": "шт",
                "unit_price": 200,
                "total_price": 1200,
                "feo_category_id": cat.id,
                "feo_planned_item_id": old_fpi.id,
            },
        ],
    }
    create_resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert create_resp.status_code in (200, 201), create_resp.text
    purchase_id = create_resp.json()["id"]
    wish_id = create_resp.json()["wish_id"]
    assert wish_id is not None

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id).order_by(WishItem.id)
    )).scalars().all()
    assert len(wish_items) == 2
    purchase_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.id)
    )).scalars().all()
    assert len(purchase_items) == 2

    # W1-фикс: hard link уже должен быть проставлен на создании компаньона —
    # без него PATCH ниже не нашёл бы, какую строку закупки обновлять.
    linked_wish_ids = {pi.wish_item_id for pi in purchase_items}
    assert linked_wish_ids == {wi.id for wi in wish_items}

    def _pi_by_price(price: int) -> PurchaseItem:
        return next(pi for pi in purchase_items if float(pi.unit_price) == price)

    def _wi_by_id(wid: int) -> WishItem:
        return next(wi for wi in wish_items if wi.id == wid)

    second_pi = _pi_by_price(200)
    second_wish_item = _wi_by_id(second_pi.wish_item_id)
    first_pi = _pi_by_price(100)

    # Заявка-компаньон рождается черновиком — patch_wish_execution требует
    # submitted/approved (прямая мутация статуса, как в
    # test_wish_execution_feo_patch_gate.py — полный submit-флоу тут не при чём).
    wish = await db_session.get(Wish, wish_id)
    wish.status = "submitted"
    await db_session.commit()

    manager = await make_user(role="manager", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, manager, test_org)
    from app.auth.jwt import create_access_token
    manager_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': manager.username, 'org_id': manager.org_id})}"
    }

    # Владелец в проде перепривязывал ВТОРУЮ строку к НОВОЙ плановой позиции.
    patch_resp = await client.patch(
        f"/api/wishes/{wish_id}/execution",
        json={"items": [{"id": second_wish_item.id, "feo_planned_item_id": new_fpi.id}]},
        headers=manager_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    await db_session.refresh(second_wish_item)
    assert second_wish_item.feo_planned_item_id == new_fpi.id

    await db_session.refresh(second_pi)
    assert second_pi.feo_planned_item_id == new_fpi.id, (
        "PATCH /wishes/{id}/execution обязан прокидывать перепривязку ФЭО в "
        "purchase_items связанной закупки (W1) — иначе следующий PUT закупки "
        "воспроизведёт прод-баг заявки №88 / РЕЕ-2026-00962"
    )
    assert second_pi.feo_category_id == cat.id
    assert second_pi.over_plan is False

    await db_session.refresh(first_pi)
    assert first_pi.feo_planned_item_id == old_fpi.id  # первая строка не тронута

    # Обычный PUT закупки (пересобирает purchase_items И wish_items целиком) —
    # payload собран из ТЕКУЩЕГО состояния БД (ре-сейв формы без правок состава).
    put_items = []
    for pi in (first_pi, second_pi):
        put_items.append({
            "item_name": pi.item_name,
            "item_type": pi.item_type,
            "quantity": float(pi.quantity),
            "unit": pi.unit,
            "unit_price": float(pi.unit_price),
            "total_price": float(pi.total_price),
            "feo_category_id": pi.feo_category_id,
            "feo_planned_item_id": pi.feo_planned_item_id,
            "over_plan": pi.over_plan,
        })
    put_payload = dict(create_payload)
    put_payload["items"] = put_items
    put_resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert put_resp.status_code == 200, put_resp.text

    new_wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id).order_by(WishItem.id)
    )).scalars().all()
    assert len(new_wish_items) == 2
    new_purchase_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.id)
    )).scalars().all()
    assert len(new_purchase_items) == 2

    new_second_wish_item = next(wi for wi in new_wish_items if float(wi.unit_price) == 200)
    assert new_second_wish_item.feo_planned_item_id == new_fpi.id, (
        "После PUT закупки привязка к новой плановой позиции в заявке-компаньоне "
        "не должна потеряться"
    )
    new_second_pi = next(pi for pi in new_purchase_items if float(pi.unit_price) == 200)
    assert new_second_pi.feo_planned_item_id == new_fpi.id
    assert new_second_pi.wish_item_id == new_second_wish_item.id, (
        "Hard link purchase_items.wish_item_id обязан восстановиться на "
        "АКТУАЛЬНЫЕ id обеих пересозданных строк после PUT"
    )

    new_first_wish_item = next(wi for wi in new_wish_items if float(wi.unit_price) == 100)
    new_first_pi = next(pi for pi in new_purchase_items if float(pi.unit_price) == 100)
    assert new_first_pi.feo_planned_item_id == old_fpi.id
    assert new_first_pi.wish_item_id == new_first_wish_item.id
