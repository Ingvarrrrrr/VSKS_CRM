"""Перф-задача владельца (21.10.2026): GET /api/purchases/ (реестр) больше не
считает значок «Стоит: план субсидии выше ФЭО» (compute_purchase_ceiling_block
+ compute_feo_plan_tree стоили ~1,6 с на каждый вызов списка) — значок
догружается отдельной лёгкой ручкой GET /api/purchases/ceiling-badges.

Проверяет:
  (а) список (с ?with_feo_excess=true и без) отдаёт ceiling_blocked=False/
      ceiling_over_amount=None ВСЕГДА — не строит дерево ФЭО под значок;
  (б) ceiling-badges отдаёт ТУ ЖЕ сумму (over_amount), что раньше отдавал бы
      список (сверка с прямым вызовом compute_purchase_ceiling_block —
      ПРАВИЛО №6, один источник);
  (в) закупка субсидии БЕЗ превышения потолка не попадает в ответ ceiling-badges
      (ручка отдаёт только закупки СО значком — {} для пустого случая);
  (г) закупка вне видимости пользователя (чужая орг, без granted-доступа) не
      попадает в ceiling-badges — та же видимость, что у списка.

Приём создания subsidy/category/planned_item скопирован из
tests/test_plan_excess_ceiling_gate.py (та же механика потолка).
"""
import uuid
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.purchase_ceiling_block import compute_purchase_ceiling_block, PRE_CONTRACT_STATUSES
from app.services.feo_plan import compute_feo_plan_tree


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    s = Subsidy(
        name=f"CeilingBadge-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026, budget=budget, org_id=org_id, require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget):
    cat = FeoCategory(
        subsidy_id=subsidy_id, parent_id=None, level=1,
        name=f"Cat-{uuid.uuid4().hex[:8]}", budget=Decimal(str(budget)),
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount):
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id, name="Позиция плана",
        quantity=Decimal("1"), unit="шт", amount=Decimal(str(amount)), is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _over_ceiling_subsidy(db_session, org_id):
    """Субсидия, у которой план (150) уже выше её единственного потолка ФЭО
    (бюджет категории 100) — та же механика, что в test_plan_excess_ceiling_gate."""
    subsidy = await _make_subsidy(db_session, org_id)
    cat = await _make_category(db_session, subsidy.id, budget=100)
    await _make_planned_item(db_session, cat.id, amount=150)
    return subsidy


@pytest.mark.asyncio
async def test_list_never_returns_ceiling_badge(client, db_session, admin_headers, test_admin_user, test_org):
    subsidy = await _over_ceiling_subsidy(db_session, test_org.id)
    p = Purchase(
        item_name="Закупка под потолком", subject="Тест",
        status="plan_schedule", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.commit()

    for qs in ("", "?with_feo_excess=true"):
        resp = await client.get(f"/api/purchases/{qs}", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        row = next(r for r in resp.json() if r["id"] == p.id)
        assert row["ceiling_blocked"] is False, row
        assert row["ceiling_over_amount"] is None, row


@pytest.mark.asyncio
async def test_ceiling_badges_matches_direct_compute(client, db_session, admin_headers, test_admin_user, test_org):
    subsidy = await _over_ceiling_subsidy(db_session, test_org.id)
    p = Purchase(
        item_name="Закупка над потолком", subject="Тест",
        status="plan_schedule", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    # Прямой вызов той же формулы (как и раньше делал list_purchases) — эталон.
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    direct = await compute_purchase_ceiling_block(db_session, [p], tree=tree)
    expected_over = direct[p.id]["ceiling_over_amount"]
    assert direct[p.id]["ceiling_blocked"] is True, direct

    resp = await client.get("/api/purchases/ceiling-badges", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(p.id) in body, body
    assert body[str(p.id)] == pytest.approx(expected_over), body


@pytest.mark.asyncio
async def test_ceiling_badges_empty_when_no_excess(client, db_session, admin_headers, test_admin_user, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=1000)
    await _make_planned_item(db_session, cat.id, amount=10)  # план << потолок
    p = Purchase(
        item_name="Закупка без превышения", subject="Тест",
        status="plan_schedule", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.commit()

    resp = await client.get("/api/purchases/ceiling-badges", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert str(p.id) not in resp.json(), resp.json()


@pytest.mark.asyncio
async def test_ceiling_badges_respects_visibility(client, db_session, admin_headers, test_admin_user, test_org, make_user):
    """Закупка чужой организации (без granted-доступа и без иерархии) не
    должна попасть в ceiling-badges — та же видимость, что и у списка."""
    import uuid as _uuid
    from app.models.organization import Organization

    other_org = Organization(name=f"OtherOrg-{_uuid.uuid4().hex[:6]}")
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    other_subsidy = await _over_ceiling_subsidy(db_session, other_org.id)
    other_user = await make_user(role="manager", org_id=other_org.id)
    foreign_p = Purchase(
        item_name="Чужая закупка над потолком", subject="Тест",
        status="plan_schedule", assigned_user_id=other_user.id, subsidy_id=other_subsidy.id,
    )
    db_session.add(foreign_p)
    await db_session.commit()
    await db_session.refresh(foreign_p)

    resp = await client.get("/api/purchases/ceiling-badges", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert str(foreign_p.id) not in resp.json(), (
        f"Закупка чужой организации {foreign_p.id} не должна быть видна admin_headers: {resp.json()}"
    )
