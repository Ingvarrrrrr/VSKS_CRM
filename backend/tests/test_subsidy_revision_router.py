# -*- coding: utf-8 -*-
"""Корректировка утверждённой субсидии через проверку — приёмка 02.10.2026,
дефекты HTTP-слоя (app/routers/subsidy_revisions.py): POST /bundles и
submit, который обязан звать ТОТ ЖЕ check_floor/preview, что и GET /preview
(ПРАВИЛО №6 — не вторая, более слабая копия проверки порога).

Вызывает роутер НАПРЯМУЮ (минуя FastAPI DI), по образцу
test_feo_item_write_wish_path.py — current_user/revision_id/body передаются
явными keyword-аргументами.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.routers import subsidy_revisions as rev_router
from app.services import subsidy_revision_ops as ops_svc


async def _make_subsidy(db_session, org_id, budget=200000):
    subsidy = Subsidy(
        name=f"RevRouterTest-{uuid.uuid4().hex[:8]}", year=2026,
        org_id=org_id, status="approved", budget=budget,
    )
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def _make_category(db_session, subsidy_id, name="Категория", **kw):
    cat = FeoCategory(subsidy_id=subsidy_id, level=1, name=name, **kw)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_item(db_session, cat_id, name="Позиция", amount=100000, quantity=10, unit_price=10000):
    item = FeoPlannedItem(
        feo_category_id=cat_id, name=name, amount=amount, quantity=quantity,
        unit_price=unit_price, unit="шт", is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _commit_item(db_session, subsidy_id, item, amount, quantity=1):
    """Делает плановую позицию «законтрактованной» — та же фикстура, что и в
    test_subsidy_revision_ops.py (ПРАВИЛО №6, второй способ не заводим)."""
    purchase = Purchase(subsidy_id=subsidy_id, status="contracted", contract_price=amount)
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    pi = PurchaseItem(
        purchase_id=purchase.id, item_name=item.name, quantity=quantity,
        total_price=amount, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    return purchase


@pytest.fixture
def revision_user(test_user):
    return test_user


# ── POST /{revision_id}/bundles ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bundles_endpoint_assigns_new_bundle_no(monkeypatch, db_session, test_org, revision_user):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    spoons = await _make_item(db_session, cat.id, name="Ложки")
    cups = await _make_item(db_session, cat.id, name="Чашки")

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op1 = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": spoons.id,
        "field_group": "qty_price", "after": {"amount": 150000},
    })
    op2 = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": cups.id,
        "field_group": "qty_price", "after": {"amount": 50000},
    })
    await db_session.commit()

    result = await rev_router.set_bundle_endpoint(
        revision.id, {"op_ids": [op1.id, op2.id], "free_money": True},
        db=db_session, current_user=revision_user,
    )
    assert result["bundle_no"] == 1
    assert sorted(result["op_ids"]) == sorted([op1.id, op2.id])
    assert result["free_money"] is True

    await db_session.refresh(op1)
    await db_session.refresh(op2)
    assert op1.bundle_no == 1
    assert op2.bundle_no == 1

    # Второй вызов с теми же строками — НОВАЯ связка (max+1), не ошибка.
    result2 = await rev_router.set_bundle_endpoint(
        revision.id, {"op_ids": [op1.id]}, db=db_session, current_user=revision_user,
    )
    assert result2["bundle_no"] == 2


@pytest.mark.asyncio
async def test_bundles_endpoint_unknown_op_id_is_422(monkeypatch, db_session, test_org, revision_user):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")
    subsidy = await _make_subsidy(db_session, test_org.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await rev_router.set_bundle_endpoint(
            revision.id, {"op_ids": [999999]}, db=db_session, current_user=revision_user,
        )
    assert exc_info.value.status_code == 422


# ── POST /{revision_id}/submit — обязан звать тот же check_floor, что /preview ──

@pytest.mark.asyncio
async def test_submit_blocks_position_below_committed(monkeypatch, db_session, test_org, revision_user):
    """Позиция уводится ниже уже законтрактованного по договорам — submit
    обязан отказать 422 revision_problems (а не пропустить, как пропускал бы
    старый submit через ops_svc.simulate(), не знающий про check_floor)."""
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")
    subsidy = await _make_subsidy(db_session, test_org.id, budget=200000)
    cat = await _make_category(db_session, subsidy.id, budget=100000)
    item = await _make_item(db_session, cat.id, amount=100000, quantity=10, unit_price=10000)
    await _commit_item(db_session, subsidy.id, item, amount=85000, quantity=8)

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "field_group": "qty_price", "after": {"amount": 50000},
    })
    await db_session.commit()
    await db_session.refresh(revision)

    with pytest.raises(HTTPException) as exc_info:
        await rev_router.submit_revision(
            revision.id, {"comment": None}, db=db_session, current_user=revision_user,
        )
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "revision_problems"
    assert any(p.get("code") == "below_committed" for p in detail["problems"])

    await db_session.refresh(revision)
    assert revision.status == "draft"  # не ушла на проверку
