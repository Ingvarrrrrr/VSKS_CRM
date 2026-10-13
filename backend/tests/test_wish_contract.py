# -*- coding: utf-8 -*-
"""Договор заявки — необязательное поле (владелец, 12.10.2026, план
lazy-swimming-hollerith.md, п.2): «В заявке должна быть возможность выбрать
Договор, к которому относится заявка». Решения владельца:
  - необязательное поле (Wish.contract_id);
  - при переводе заявки в закупку договор переносится, закупка становится
    заказом этого рамочного договора существующим механизмом
    Purchase.contract_id + framework_seq (app.routers.purchase_budget.
    _assign_framework_seq) — НЕ вторым механизмом нумерации;
  - уже заданный договор закупки не перетирается;
  - согласующий может сменить договор заявки при согласовании (PATCH
    /{wish_id}/execution — тот же гейт прав, что уже есть у event_id/
    feo_category_id, см. test_wish_execution_event_id.py).

Покрытие:
  1. Создание заявки с contract_id — сохраняется, отдаётся в карточке.
  2. Согласующий из цепочки (не автор, не assigned_to) меняет contract_id
     заявки через PATCH /execution; посторонний сотрудник — 403.
  3. Перевод заявки в закупку (/convert) — closes contract_id + framework_seq.
  4. Повторная конвертация существующей закупки с УЖЕ заданным contract_id —
     заявочный договор её не перетирает.
  5. Заявка без договора конвертируется как раньше (contract_id/framework_seq
     остаются NULL, поведение не изменилось).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_approval import WishApproval
from app.models.contract import Contract
from app.models.purchase import Purchase


async def _make_subsidy(db_session, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026, budget=budget, require_planned_dates=False, status="approved",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=5_000_000):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id, parent_id=None, level=1,
        name=f"Cat-{uuid.uuid4().hex[:8]}", budget=Decimal(str(budget)),
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_framework_contract(db_session, subsidy_id=None, contract_type="framework_cumulative"):
    c = Contract(
        number=f"РД-{uuid.uuid4().hex[:6]}",
        contract_type=contract_type,
        subsidy_id=subsidy_id,
        status="active",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.mark.asyncio
async def test_create_wish_with_contract_id(client, auth_headers, db_session, test_user):
    subsidy = await _make_subsidy(db_session)
    contract = await _make_framework_contract(db_session, subsidy_id=subsidy.id)

    resp = await client.post(
        "/api/wishes/",
        json={"title": "Заявка с договором", "subsidy_id": subsidy.id, "contract_id": contract.id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["contract_id"] == contract.id
    assert body["contract_number"] == contract.number
    assert body["contract_type"] == "framework_cumulative"


@pytest.mark.asyncio
async def test_chain_approver_can_change_wish_contract(client, db_session, test_org, test_user, make_user):
    """Согласующий из цепочки (не автор, не assigned_to) меняет договор заявки
    через PATCH /execution — тот же гейт прав, что у event_id (см.
    test_wish_execution_event_id.py::test_chain_approver_can_set_event_id)."""
    from app.auth.jwt import create_access_token

    subsidy = await _make_subsidy(db_session)
    contract_a = await _make_framework_contract(db_session, subsidy_id=subsidy.id)
    contract_b = await _make_framework_contract(db_session, subsidy_id=subsidy.id)

    w = Wish(
        org_id=test_org.id, title="Заявка на согласовании", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, contract_id=contract_a.id,
    )
    db_session.add(w)
    await db_session.flush()

    approver = await make_user(role="employee", org_id=test_org.id)
    db_session.add(WishApproval(wish_id=w.id, user_id=approver.id, order_num=0, status="pending"))
    await db_session.commit()

    approver_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': approver.username, 'org_id': approver.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"contract_id": contract_b.id},
        headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(w)
    assert w.contract_id == contract_b.id

    # Посторонний сотрудник — 403, договор не меняется.
    outsider = await make_user(role="employee", org_id=test_org.id)
    outsider_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': outsider.username, 'org_id': outsider.org_id})}"
    }
    resp2 = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"contract_id": contract_a.id},
        headers=outsider_headers,
    )
    assert resp2.status_code == 403, resp2.text
    await db_session.refresh(w)
    assert w.contract_id == contract_b.id  # не перетёрто


@pytest.mark.asyncio
async def test_convert_wish_sets_purchase_contract_and_framework_seq(client, auth_headers, db_session, test_user, test_org):
    subsidy = await _make_subsidy(db_session)
    contract = await _make_framework_contract(db_session, subsidy_id=subsidy.id)
    cat = await _make_category(db_session, subsidy.id)

    w = Wish(
        org_id=test_org.id, title="Заявка с договором", status="approved",
        created_by=test_user.id, subsidy_id=subsidy.id, contract_id=contract.id,
        feo_category_id=cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id, item_name="Товар", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("1000"), total_price=Decimal("1000"), feo_category_id=cat.id,
    ))
    await db_session.commit()

    resp = await client.post(f"/api/wishes/{w.id}/convert", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["purchase_id"]

    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.contract_id == contract.id
    assert purchase.purchase_contract_type == "framework_cumulative"
    assert purchase.framework_seq == 1

    # Вторая закупка того же договора получает следующий порядковый номер.
    w2 = Wish(
        org_id=test_org.id, title="Вторая заявка, тот же договор", status="approved",
        created_by=test_user.id, subsidy_id=subsidy.id, contract_id=contract.id,
        feo_category_id=cat.id,
    )
    db_session.add(w2)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w2.id, item_name="Товар 2", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("500"), total_price=Decimal("500"), feo_category_id=cat.id,
    ))
    await db_session.commit()
    resp2 = await client.post(f"/api/wishes/{w2.id}/convert", json={}, headers=auth_headers)
    assert resp2.status_code == 200, resp2.text
    purchase2 = await db_session.get(Purchase, resp2.json()["purchase_id"])
    assert purchase2.framework_seq == 2


@pytest.mark.asyncio
async def test_convert_does_not_overwrite_existing_purchase_contract(client, auth_headers, db_session, test_user, test_org):
    """Повторная конвертация (закупка уже существует со status='wishes') не
    перетирает contract_id, уже заданный вручную прямо в закупке."""
    subsidy = await _make_subsidy(db_session)
    wish_contract = await _make_framework_contract(db_session, subsidy_id=subsidy.id)
    manual_contract = await _make_framework_contract(db_session, subsidy_id=subsidy.id)

    w = Wish(
        org_id=test_org.id, title="Заявка, закупка уже есть", status="approved",
        created_by=test_user.id, subsidy_id=subsidy.id, contract_id=wish_contract.id,
    )
    db_session.add(w)
    await db_session.flush()

    existing_purchase = Purchase(
        wish_id=w.id, status="wishes", item_name="Уже закупка", subsidy_id=subsidy.id,
        contract_id=manual_contract.id, purchase_contract_type=manual_contract.contract_type,
    )
    db_session.add(existing_purchase)
    await db_session.commit()

    resp = await client.post(f"/api/wishes/{w.id}/convert", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(existing_purchase)
    assert existing_purchase.contract_id == manual_contract.id  # не перетёрто


@pytest.mark.asyncio
async def test_convert_without_contract_unchanged(client, auth_headers, db_session, test_user, test_org):
    """Заявка без договора конвертируется как раньше — contract_id/
    framework_seq остаются NULL, второй путь не затрагивается."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    w = Wish(
        org_id=test_org.id, title="Заявка без договора", status="approved",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id, item_name="Товар", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("100"), total_price=Decimal("100"), feo_category_id=cat.id,
    ))
    await db_session.commit()

    resp = await client.post(f"/api/wishes/{w.id}/convert", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    purchase = await db_session.get(Purchase, resp.json()["purchase_id"])
    assert purchase.contract_id is None
    assert purchase.framework_seq is None
