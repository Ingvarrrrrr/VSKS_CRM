# -*- coding: utf-8 -*-
"""Пакет 2 (владелец, 22.10.2026, заявка №209): «если всё создано из плана —
категория не меняется; менять можно только у каждой дополнительно добавленной
позиции по отдельности».

Единственный гейт — app/services/wish_item_category_guard.py
(assert_wish_item_category_from_plan + MSG_HEADER_LOCKED/wish_items_all_plan_linked,
владелец 20.09 + поправка 22.10.2026: подключён и к patch_wish_execution) —
второй механизм не заводим (правка после ревью: исходная версия этого пакета
содержала отдельный app/services/wish_plan_category_lock.py, удалён).

Покрывает:
  (a) PATCH /execution: смена категории шапки у заявки, где ВСЕ позиции по
      плану → 422 (MSG_HEADER_LOCKED), категории позиций не изменились,
      привязки к плану на месте.
  (b) смешанная заявка (одна позиция по плану, одна ручная): шапка меняется,
      позиция по плану остаётся в своей категории/привязке, ручная переезжает.
  (c) PATCH /execution body.items: смена feo_category_id ОДНОЙ позиции по
      плану (без переприсылки feo_planned_item_id) → 422, категория в БД не
      изменилась, привязка к плану на месте.
  (d) ложный дубль устранён: категория С активными FeoPlannedItem не даёт
      категорийного фолбэка позиции без feo_planned_item_id (нет предупреждения),
      а позиция С feo_planned_item_id, чей план занят чужой закупкой, — даёт
      предупреждение со структурированным purchases[0].registry_number.
  (e) PATCH /execution contract_form сохраняется; недопустимое значение → 400.

Приёмы — по образцу test_wish_header_category_sync.py (client + manager +
wish.edit_feo override) и test_plan_position_duplicate_warning.py (прямой
вызов collect_plan_duplicate_warnings)."""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import UserOrgPermissionOverride
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from app.models.wish import Wish
from app.models.wish_item import WishItem


async def _grant_wish_edit_feo(db_session, user, org):
    uoa = UserOrgAccess(user_id=user.id, org_id=org.id, role=user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()


async def _manager_headers(db_session, test_org, make_user):
    from app.auth.jwt import create_access_token
    manager = await make_user(role="manager", org_id=test_org.id)
    await _grant_wish_edit_feo(db_session, manager, test_org)
    return {"Authorization": f"Bearer {create_access_token({'sub': manager.username, 'org_id': manager.org_id})}"}


async def _make_subsidy(db_session, org_id, name="TestPlanLock"):
    s = Subsidy(name=f"{name}-{uuid.uuid4().hex[:8]}", year=2026, budget=0, org_id=org_id, require_planned_dates=False, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest.mark.asyncio
async def test_header_category_locked_when_all_items_on_plan(client, db_session, test_org, test_user, make_user):
    """(a) ВСЕ позиции заявки по плану → смена категории шапки через PATCH
    /execution отклоняется 400, ничего в БД не меняется."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория A")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория B")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    fpi = FeoPlannedItem(feo_category_id=cat_a.id, name="Перчатки", quantity=Decimal("10"), amount=Decimal("1000"), is_active=True)
    db_session.add(fpi)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка по плану", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id, feo_per_item=False,
    )
    db_session.add(w)
    await db_session.flush()
    wi = WishItem(
        wish_id=w.id, item_name="Перчатки", quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_a.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(wi)

    headers = await _manager_headers(db_session, test_org, make_user)
    resp = await client.patch(f"/api/wishes/{w.id}/execution", json={"feo_category_id": cat_b.id}, headers=headers)
    assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"
    assert "план" in resp.text.lower(), resp.text

    await db_session.refresh(w)
    await db_session.refresh(wi)
    assert w.feo_category_id == cat_a.id
    assert wi.feo_category_id == cat_a.id
    assert wi.feo_planned_item_id == fpi.id


@pytest.mark.asyncio
async def test_mixed_wish_header_change_keeps_plan_item_category(client, db_session, test_org, test_user, make_user):
    """(b) Смешанная заявка: шапка меняется (manual item следует), позиция по
    плану остаётся в своей категории/со своей привязкой."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория A")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория B")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    fpi = FeoPlannedItem(feo_category_id=cat_a.id, name="Перчатки", quantity=Decimal("10"), amount=Decimal("1000"), is_active=True)
    db_session.add(fpi)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка смешанная", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id, feo_per_item=False,
    )
    db_session.add(w)
    await db_session.flush()
    item_plan = WishItem(
        wish_id=w.id, item_name="Перчатки", quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_a.id, feo_planned_item_id=fpi.id,
    )
    item_manual = WishItem(
        wish_id=w.id, item_name="Канцтовары", quantity=1, unit_price=500, total_price=500,
        feo_category_id=cat_a.id,
    )
    db_session.add_all([item_plan, item_manual])
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(item_plan)
    await db_session.refresh(item_manual)

    headers = await _manager_headers(db_session, test_org, make_user)
    resp = await client.patch(f"/api/wishes/{w.id}/execution", json={"feo_category_id": cat_b.id}, headers=headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(w)
    await db_session.refresh(item_plan)
    await db_session.refresh(item_manual)
    assert w.feo_category_id == cat_b.id
    assert item_plan.feo_category_id == cat_a.id, "позиция по плану не переезжает"
    assert item_plan.feo_planned_item_id == fpi.id
    assert item_manual.feo_category_id == cat_b.id, "ручная позиция следует за шапкой"


@pytest.mark.asyncio
async def test_patch_execution_item_category_change_rejected_for_plan_item(
    client, db_session, test_org, test_user, make_user,
):
    """(c) PATCH /execution body.items: смена feo_category_id ОДНОЙ позиции по
    плану (без переприсылки feo_planned_item_id) → 422 (тот же единственный
    гейт — assert_wish_item_category_from_plan, app/services/
    wish_item_category_guard.py), категория и привязка к плану в БД не
    изменились. Раньше здесь тихо переезжала/отвязывалась плановая позиция
    (move_or_detach_planned_item) — владелец (22.10.2026, заявка №209) это
    отменил."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_plan = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория плана")
    cat_other = FeoCategory(subsidy_id=subsidy.id, level=1, name="Другая категория")
    db_session.add_all([cat_plan, cat_other])
    await db_session.flush()

    fpi = FeoPlannedItem(feo_category_id=cat_plan.id, name="Перчатки", quantity=Decimal("10"), amount=Decimal("1000"), is_active=True)
    db_session.add(fpi)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id, title="Заявка построчный гейт", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_per_item=True,
    )
    db_session.add(w)
    await db_session.flush()
    item = WishItem(
        wish_id=w.id, item_name="Перчатки", quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_plan.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(item)

    headers = await _manager_headers(db_session, test_org, make_user)
    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"items": [{"id": item.id, "feo_category_id": cat_other.id}]},
        headers=headers,
    )
    assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"

    await db_session.refresh(item)
    assert item.feo_category_id == cat_plan.id, "категория позиции по плану не изменилась"
    assert item.feo_planned_item_id == fpi.id, "привязка к плану на месте"


@pytest.mark.asyncio
async def test_put_wish_non_draft_item_category_change_rejected_for_plan_item(
    client, db_session, test_org, test_user, auth_headers,
):
    """PUT /api/wishes/{id} (non-draft, update in-place по id, как это делает
    фронт при пересохранении заявки) — смена feo_category_id позиции по плану
    без переприсылки feo_planned_item_id → 422, в БД категория и привязка не
    изменились (QA после ревью: этот же молчаливый перенос/отвязка жил и в
    update_wish non-draft ветке, не только в patch_wish_execution)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_plan = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория плана (PUT)")
    cat_other = FeoCategory(subsidy_id=subsidy.id, level=1, name="Другая категория (PUT)")
    db_session.add_all([cat_plan, cat_other])
    await db_session.flush()

    fpi = FeoPlannedItem(feo_category_id=cat_plan.id, name="Перчатки", quantity=Decimal("10"), amount=Decimal("1000"), is_active=True)
    db_session.add(fpi)
    await db_session.flush()

    # status=submitted — иначе update_wish уйдёт в draft-ветку (delete+recreate,
    # уже покрыта test_wish_item_category_guard.py); нужна именно non-draft
    # ветка (update in-place по id). auth_headers/test_user — автор заявки.
    w = Wish(
        org_id=test_org.id, title="Заявка non-draft PUT", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_per_item=True,
    )
    db_session.add(w)
    await db_session.flush()
    item = WishItem(
        wish_id=w.id, item_name="Перчатки", quantity=1, unit_price=1000, total_price=1000,
        feo_category_id=cat_plan.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(item)

    resp = await client.put(
        f"/api/wishes/{w.id}",
        json={"items": [{"id": item.id, "feo_category_id": cat_other.id}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"

    await db_session.refresh(item)
    assert item.feo_category_id == cat_plan.id, "категория позиции по плану не изменилась"
    assert item.feo_planned_item_id == fpi.id, "привязка к плану на месте"


@pytest.mark.asyncio
async def test_duplicate_warning_skips_category_with_active_planned_items(db_session, test_org):
    """(d1) Категория С активными FeoPlannedItem — категорийный фолбэк для
    позиции без feo_planned_item_id НЕ применяется (иначе ложный дубль, как в
    заявке №209), даже если в этой категории есть чужая закупка (но на другую
    плановую позицию)."""
    from app.services.plan_duplicate_warning import collect_plan_duplicate_warnings

    subsidy = await _make_subsidy(db_session, test_org.id, name="TestDupSkip")
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="ЗП")
    db_session.add(cat)
    await db_session.flush()

    fpi_other = FeoPlannedItem(feo_category_id=cat.id, name="Другая плановая позиция", quantity=Decimal("1"), amount=Decimal("8200000"), is_active=True)
    db_session.add(fpi_other)
    await db_session.flush()

    # Чужая закупка, привязанная к fpi_other (другая плановая позиция ТОЙ ЖЕ категории).
    foreign_purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="ЗП другая",
        registry_number="РЕЕ-2026-04286", status="paid",
        planned_quantity=Decimal("1"), planned_total_price=Decimal("8200000"),
        total_nmck=Decimal("8200000"), nmck=Decimal("8200000"),
    )
    db_session.add(foreign_purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=foreign_purchase.id, item_name="ЗП другая", quantity=1, unit="шт",
        unit_price=Decimal("8200000"), total_price=Decimal("8200000"),
        feo_category_id=cat.id, feo_planned_item_id=fpi_other.id,
    ))
    await db_session.commit()

    # Своя заявка: позиция БЕЗ feo_planned_item_id (была отвязана), в ТОЙ ЖЕ категории.
    wish = Wish(org_id=test_org.id, title="Заявка №209-подобная", status="submitted", subsidy_id=subsidy.id)
    db_session.add(wish)
    await db_session.flush()
    wi = WishItem(
        wish_id=wish.id, item_name="Своя позиция", quantity=1, unit_price=500, total_price=500,
        feo_category_id=cat.id, feo_planned_item_id=None,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)

    warnings = await collect_plan_duplicate_warnings(db_session, [wi], exclude_wish_id=wish.id)
    assert warnings == [], "категория с активными FeoPlannedItem не даёт категорийного фолбэка — ложный дубль устранён"


@pytest.mark.asyncio
async def test_duplicate_warning_includes_structured_purchases(db_session, test_org):
    """(d2) Позиция С feo_planned_item_id, план которой занят чужой закупкой —
    предупреждение есть, purchases[0].registry_number заполнен структурно."""
    from app.services.plan_duplicate_warning import collect_plan_duplicate_warnings

    subsidy = await _make_subsidy(db_session, test_org.id, name="TestDupStruct")
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование")
    db_session.add(cat)
    await db_session.flush()

    fpi = FeoPlannedItem(feo_category_id=cat.id, name="Принтер", quantity=Decimal("1"), amount=Decimal("50000"), is_active=True)
    db_session.add(fpi)
    await db_session.flush()

    foreign_purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Принтер",
        registry_number="РЕЕ-2026-09999", status="paid",
        planned_quantity=Decimal("1"), planned_total_price=Decimal("50000"),
        total_nmck=Decimal("50000"), nmck=Decimal("50000"),
    )
    db_session.add(foreign_purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=foreign_purchase.id, item_name="Принтер", quantity=1, unit="шт",
        unit_price=Decimal("50000"), total_price=Decimal("50000"),
        feo_category_id=cat.id, feo_planned_item_id=fpi.id,
    ))
    await db_session.commit()

    wish = Wish(org_id=test_org.id, title="Заявка-дубль", status="submitted", subsidy_id=subsidy.id)
    db_session.add(wish)
    await db_session.flush()
    wi = WishItem(
        wish_id=wish.id, item_name="Принтер", quantity=1, unit_price=50000, total_price=50000,
        feo_category_id=cat.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)

    warnings = await collect_plan_duplicate_warnings(db_session, [wi], exclude_wish_id=wish.id)
    assert len(warnings) == 1
    w = warnings[0]
    assert w["purchases"], "структурированный список закупок обязан быть заполнен"
    assert w["purchases"][0]["registry_number"] == "РЕЕ-2026-09999"


@pytest.mark.asyncio
async def test_patch_execution_contract_form(client, db_session, test_org, test_user, make_user):
    """(e) PATCH /execution contract_form сохраняется; недопустимое значение → 400."""
    subsidy = await _make_subsidy(db_session, test_org.id, name="TestContractForm")
    w = Wish(
        org_id=test_org.id, title="Заявка форма договора", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    headers = await _manager_headers(db_session, test_org, make_user)

    resp_bad = await client.patch(f"/api/wishes/{w.id}/execution", json={"contract_form": "not_a_real_form"}, headers=headers)
    assert resp_bad.status_code == 400, resp_bad.text

    resp_ok = await client.patch(f"/api/wishes/{w.id}/execution", json={"contract_form": "services"}, headers=headers)
    assert resp_ok.status_code == 200, resp_ok.text

    await db_session.refresh(w)
    assert w.contract_form == "services"
