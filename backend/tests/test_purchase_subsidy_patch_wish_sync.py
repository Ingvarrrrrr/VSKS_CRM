# -*- coding: utf-8 -*-
"""Прод-инцидент (авансовый РЕЕ-2026-00973 / заявка №95, 2026-09-30): владелец
при создании авансового отчёта выбрал субсидию в карточке закупки, но
subsidy_id закупки остался NULL — фронт автосохраняет карточку ТОЛЬКО через
PATCH /api/purchases/{id} (CreateOrderView.vue::serializeFormForAutosave), а
subsidy_id не входил ни в этот payload, ни в PATCHABLE_FIELDS бэкенда
(routers/purchases.py::patch_purchase) — поле терялось молча по двум причинам
сразу. feo_category_id при этом сохранялся (уже был в обоих местах), поэтому
закупка осталась с категорией без субсидии — ровно воспроизводимый здесь
сценарий.

Правки (ПРАВИЛО №6, общий хелпер в app/services/advance_wish_sync.py):
  1. patch_purchase теперь принимает subsidy_id (пока закупка не при
     договоре — SUBSIDY_PATCHABLE_STATUSES), с теми же проверками, что PUT/
     create (assert_subsidy_approved_for_binding + согласованность выбранной
     feo_category_id с новой субсидией), и зеркалит шапку
     (subsidy_id/feo_category_id/event_id) в заявку-компаньона авансового
     отчёта (sync_wish_header_from_purchase) — заявка ЗЕРКАЛО закупки, тот
     же принцип, что уже применён к содержимому/цене/названию.
  2. Обратное направление: согласующий с правом wish.edit_feo меняет
     subsidy_id заявки-компаньона через PATCH /wishes/{id}/execution
     (WishExecutionPatch.subsidy_id, новое поле) — зеркалится в связанную
     закупку (apply_wish_header_to_purchase).

Тест покрывает оба направления одним прогоном на одной паре закупка/заявка,
плюс проверку, что PATCH больше не отбрасывает непатчабельные поля молча
(ignored_fields в ответе).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.purchase import Purchase
from app.models.permission import UserOrgPermissionOverride
from app.models.user_org_access import UserOrgAccess


async def _make_subsidy(db_session, **kwargs):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=kwargs.pop("name", f"TestSubsidy-{uuid.uuid4().hex[:8]}"),
        year=2026,
        budget=kwargs.pop("budget", 8_000_000),
        require_planned_dates=False,
        status="approved",  # assert_subsidy_approved_for_binding гейтит смену субсидии
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


async def _grant_wish_edit_feo(db_session, user, org):
    """Персональный override wish.edit_feo=True (тот же приём, что и в
    test_advance_wish_execution_feo_link_sync.py / test_wish_execution_feo_patch_gate.py)."""
    uoa = UserOrgAccess(user_id=user.id, org_id=org.id, role=user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_patch_advance_purchase_subsidy_id_saved_and_synced_to_wish_companion(
    client, auth_headers, db_session, test_org,
):
    """Воспроизводит ровно прод-сценарий: авансовый создаётся С категорией
    ФЭО, но БЕЗ субсидии (как это реально произошло — subsidy_id не долетал).
    Категория уже принадлежит субсидии, которую пользователь добавит следующим
    PATCH — согласованность категория/субсидия при этом не нарушается."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест PATCH subsidy_id",
        "feo_category_id": cat.id,
        "items": [{
            "item_name": "Такси", "item_type": "услуга",
            "quantity": 1, "unit": "усл.", "unit_price": 500, "total_price": 500,
        }],
    }
    create_resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert create_resp.status_code in (200, 201), create_resp.text
    purchase_id = create_resp.json()["id"]
    wish_id = create_resp.json()["wish_id"]
    assert wish_id is not None

    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.subsidy_id is None  # воспроизводим инцидент
    assert purchase.feo_category_id == cat.id
    wish = await db_session.get(Wish, wish_id)
    assert wish.subsidy_id is None  # компаньон родился с тем же расхождением

    # Автосейв формы: PATCH шлёт subsidy_id вместе с прочими полями шапки.
    patch_resp = await client.patch(
        f"/api/purchases/{purchase_id}",
        json={"subsidy_id": subsidy.id, "feo_category_id": cat.id, "subject": "Авансовый — тест PATCH subsidy_id"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert "subsidy_id" in body["changed"]
    # Непатчабельные поля больше не пропадают молча — список пуст, т.к. все
    # поля этого запроса патчабельны/специально обработаны.
    assert body.get("ignored_fields") == []

    await db_session.refresh(purchase)
    assert purchase.subsidy_id == subsidy.id, (
        "PATCH обязан сохранять subsidy_id закупки — раньше поле отсутствовало "
        "и в PATCHABLE_FIELDS, и в автосейве фронта (заявка №95, 2026-09-30)"
    )

    await db_session.refresh(wish)
    assert wish.subsidy_id == subsidy.id, (
        "Заявка-компаньон авансового отчёта обязана зеркалить subsidy_id "
        "закупки при PATCH (sync_wish_header_from_purchase)"
    )
    assert wish.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_patch_purchase_ignores_stale_field_and_reports_it(
    client, auth_headers, db_session, test_org,
):
    """Контроль: поле, которого нет в PATCHABLE_FIELDS и которое не входит в
    заведомо-игнорируемый legacy-набор, теперь возвращается в ignored_fields,
    а не пропадает без следа."""
    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест ignored_fields",
        "items": [{
            "item_name": "Канцтовары", "item_type": "товар",
            "quantity": 1, "unit": "шт", "unit_price": 300, "total_price": 300,
        }],
    }
    create_resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert create_resp.status_code in (200, 201), create_resp.text
    purchase_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/purchases/{purchase_id}",
        json={"subject": "обновлено", "totally_unknown_field": "x"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert "totally_unknown_field" in body.get("ignored_fields", []), (
        "Поле вне PATCHABLE_FIELDS обязано попасть в ignored_fields ответа, "
        "а не молча исчезать (ровно так потерялся subsidy_id в инциденте 30.09)"
    )


@pytest.mark.asyncio
async def test_wish_execution_subsidy_patch_propagates_to_advance_purchase(
    client, auth_headers, db_session, test_org, make_user,
):
    """Обратное направление: согласующий с правом wish.edit_feo меняет
    субсидию заявки-компаньона через PATCH /wishes/{id}/execution — правка
    обязана долететь до связанной закупки (apply_wish_header_to_purchase)."""
    old_subsidy = await _make_subsidy(db_session, name="OldSubsidy")
    old_cat = await _make_category(db_session, old_subsidy.id, name="OldCat")
    new_subsidy = await _make_subsidy(db_session, name="NewSubsidy")
    new_cat = await _make_category(db_session, new_subsidy.id, name="NewCat")

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый — тест execution subsidy_id",
        "subsidy_id": old_subsidy.id,
        "feo_category_id": old_cat.id,
        "items": [{
            "item_name": "ГСМ", "item_type": "товар",
            "quantity": 1, "unit": "л", "unit_price": 1000, "total_price": 1000,
            "feo_category_id": old_cat.id,
        }],
    }
    create_resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert create_resp.status_code in (200, 201), create_resp.text
    purchase_id = create_resp.json()["id"]
    wish_id = create_resp.json()["wish_id"]
    assert wish_id is not None

    # Заявка-компаньон рождается черновиком — execution-PATCH требует
    # submitted/approved (та же прямая мутация статуса, что в
    # test_advance_wish_execution_feo_link_sync.py).
    wish = await db_session.get(Wish, wish_id)
    wish.status = "submitted"
    await db_session.commit()

    manager = await make_user(role="manager", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, manager, test_org)
    from app.auth.jwt import create_access_token
    manager_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': manager.username, 'org_id': manager.org_id})}"
    }

    patch_resp = await client.patch(
        f"/api/wishes/{wish_id}/execution",
        json={"subsidy_id": new_subsidy.id, "feo_category_id": new_cat.id},
        headers=manager_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    await db_session.refresh(wish)
    assert wish.subsidy_id == new_subsidy.id
    assert wish.feo_category_id == new_cat.id

    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.subsidy_id == new_subsidy.id, (
        "Смена субсидии согласующим в карточке заявки-компаньона обязана "
        "долетать до закупки (apply_wish_header_to_purchase)"
    )
    assert purchase.feo_category_id == new_cat.id
