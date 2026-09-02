# -*- coding: utf-8 -*-
"""Согласование рамочной ГОЛОВЫ договора цепочкой вышестоящих (Этап D).

Владелец дословно: «рамочный договор, при его создании, должен пройти путь
как Заявка» (цепочка вышестоящих руководителей), а до согласования — быть
визуально помечен в реестре договоров.

До этой правки рамочная голова, заведённая прямо в реестре «Договоры»
(POST /api/contracts/{id}/approval-purchase, см. test_contract_approval_purchase.py),
не проходила вообще никакого согласования — approval_status оставался NULL
навсегда, никто не узнавал о новом договоре на крупную сумму.

Решение переиспользует ТОТ ЖЕ механизм построения цепочки, что и у заявок
(app.services.approval_chain.build_ascending_chain, см.
app/routers/wish_approvals.py), а не заводит второй параллельный движок —
именно так уже один раз разъехались framework_limited/framework_with_amount
(см. purchases.py::is_framework_head).

Покрытие:
  1. _framework_approval_state — чистая функция-маппер (contracts.py).
  2. _build_framework_chain_approvals — строит цепочку в PurchaseApproval,
     сама идемпотентна, не строит цепочку без руководителя организации и не
     трогает закупки, не являющиеся рамочной головой.
  3. POST /api/purchases/{pid}/approvers/cascade — HTTP-обёртка над (2).
  4. POST /api/contracts/{id}/approval-purchase — автозапуск цепочки при
     заведении рамочной головы (то самое «при создании»).
  5. GET /api/contracts/ — approval_state в выдаче реестра договоров.
"""
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.purchase_approval import PurchaseApproval
from app.routers.contracts import _framework_approval_state
from app.routers.purchases import _build_framework_chain_approvals, is_framework_head


# ---------------------------------------------------------------------------
# 1. _framework_approval_state — чистая функция, без БД
# ---------------------------------------------------------------------------

def test_framework_approval_state_mapping():
    assert _framework_approval_state("approved") == "approved"
    assert _framework_approval_state("in_progress") == "pending"
    assert _framework_approval_state("rejected") == "pending"
    assert _framework_approval_state(None) is None
    assert _framework_approval_state("") is None


# ---------------------------------------------------------------------------
# 2. _build_framework_chain_approvals — DB-backed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_chain_creates_pending_approval_for_org_head(
    db_session, test_org, make_purchase, make_user,
):
    """Автор без отдела и без явного руководителя (superior_user_id) — цепочка
    состоит из одного звена: руководителя организации. Это минимальный, но
    валидный случай (build_ascending_chain отдаёт warning, но НЕ пустую цепочку)."""
    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    subsidy = Subsidy(name="Test subsidy", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    author = await make_user(role="employee", org_id=test_org.id)
    p = await make_purchase(
        subsidy_id=subsidy.id,
        assigned_user_id=author.id,
        purchase_contract_type="framework_cumulative",
        parent_purchase_id=None,
        contract_price=Decimal("600000"),
    )
    assert is_framework_head(p)
    assert p.approval_status is None

    warning = await _build_framework_chain_approvals(p, db_session, author)
    await db_session.commit()
    await db_session.refresh(p)

    assert p.approval_status == "in_progress"
    assert p.approval_mode == "sequential"
    # Единственное звено — сам руководитель организации, поэтому build_ascending_chain
    # обязан вернуть предупреждение (см. её docstring, п.6), но не пустую цепочку.
    assert warning is not None

    rows = (await db_session.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == p.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == org_head.id
    assert rows[0].status == "pending"


@pytest.mark.asyncio
async def test_build_chain_multi_level_via_superior_chain(
    db_session, test_org, make_purchase, make_user,
):
    """Автор -> непосредственный руководитель (User.superior_user_id) -> руководитель
    организации: две ступени, order_num 0 и 1 по возрастанию (снизу вверх)."""
    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    middle_boss = await make_user(role="manager", org_id=test_org.id, superior_user_id=org_head.id)
    author = await make_user(role="employee", org_id=test_org.id, superior_user_id=middle_boss.id)

    subsidy = Subsidy(name="Test subsidy 2", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    p = await make_purchase(
        subsidy_id=subsidy.id,
        assigned_user_id=author.id,
        purchase_contract_type="framework_with_amount",
        parent_purchase_id=None,
        contract_price=Decimal("600000"),
    )

    await _build_framework_chain_approvals(p, db_session, author)
    await db_session.commit()
    await db_session.refresh(p)

    assert p.approval_status == "in_progress"
    rows = (await db_session.execute(
        select(PurchaseApproval)
        .where(PurchaseApproval.purchase_id == p.id)
        .order_by(PurchaseApproval.order_num)
    )).scalars().all()
    assert [r.user_id for r in rows] == [middle_boss.id, org_head.id]


@pytest.mark.asyncio
async def test_build_chain_noop_without_org_head(db_session, test_org, make_purchase, make_user):
    """У организации не задан head_user_id — цепочку строить не из чего;
    approval_status остаётся None, PurchaseApproval не создаётся."""
    assert test_org.head_user_id is None
    author = await make_user(role="employee", org_id=test_org.id)
    p = await make_purchase(
        assigned_user_id=author.id,
        purchase_contract_type="framework_cumulative",
        parent_purchase_id=None,
    )

    warning = await _build_framework_chain_approvals(p, db_session, author)
    await db_session.commit()
    await db_session.refresh(p)

    assert warning is None
    assert p.approval_status is None
    rows = (await db_session.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == p.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_build_chain_noop_for_non_framework_purchase(db_session, test_org, make_purchase, make_user):
    """Обычная (не рамочная) закупка не должна получать эту цепочку вообще."""
    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    author = await make_user(role="employee", org_id=test_org.id)
    p = await make_purchase(assigned_user_id=author.id, purchase_contract_type="single")
    assert not is_framework_head(p)

    warning = await _build_framework_chain_approvals(p, db_session, author)
    assert warning is None
    assert p.approval_status is None


# ---------------------------------------------------------------------------
# 3. POST /api/purchases/{pid}/approvers/cascade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cascade_endpoint_builds_chain(
    client, db_session, test_org, make_purchase, make_user, superadmin_headers,
):
    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    subsidy = Subsidy(name="Test subsidy 3", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    author = await make_user(role="employee", org_id=test_org.id)
    p = await make_purchase(
        subsidy_id=subsidy.id,
        assigned_user_id=author.id,
        purchase_contract_type="framework_cumulative",
        parent_purchase_id=None,
    )

    resp = await client.post(f"/api/purchases/{p.id}/approvers/cascade", headers=superadmin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approval_status"] == "in_progress"
    assert len(body["approvers"]) == 1
    assert body["approvers"][0]["user_id"] == org_head.id


@pytest.mark.asyncio
async def test_cascade_endpoint_rejects_non_framework_purchase(
    client, make_purchase, superadmin_headers,
):
    p = await make_purchase(purchase_contract_type="single")
    resp = await client.post(f"/api/purchases/{p.id}/approvers/cascade", headers=superadmin_headers)
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# 4. POST /api/contracts/{id}/approval-purchase — автозапуск при создании
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_purchase_endpoint_starts_chain_automatically(
    client, db_session, test_org, make_user, superadmin_headers,
):
    """Сценарий владельца: рамочный договор заведён прямо в реестре «Договоры» —
    рамочная голова должна СРАЗУ уйти на согласование, без отдельного клика."""
    from app.models.contract import Contract

    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    subsidy = Subsidy(name="Test subsidy 4", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    c = Contract(
        number="Д-100", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, subject="Поставка канцтоваров", max_amount=Decimal("600000"),
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    resp = await client.post(f"/api/contracts/{c.id}/approval-purchase", headers=superadmin_headers)
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["purchase_id"]
    assert resp.json()["created"] is True

    from app.models.purchase import Purchase
    p = await db_session.get(Purchase, purchase_id)
    assert p is not None
    assert p.approval_status == "in_progress"

    rows = (await db_session.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == purchase_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == org_head.id


# ---------------------------------------------------------------------------
# 5. GET /api/contracts/ — approval_state в реестре
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_contracts_reports_approval_state(
    client, db_session, test_org, make_purchase, make_user, superadmin_headers,
):
    from app.models.contract import Contract

    org_head = await make_user(role="manager", org_id=test_org.id)
    test_org.head_user_id = org_head.id
    await db_session.commit()

    subsidy = Subsidy(name="Test subsidy 5", year=2026, budget=1_000_000.0, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    # Договор №1: рамочная голова ожидает согласования (in_progress)
    c_pending = Contract(number="Д-201", contract_type="framework_cumulative", subsidy_id=subsidy.id)
    db_session.add(c_pending)
    await db_session.commit()
    await db_session.refresh(c_pending)
    p_pending = await make_purchase(
        contract_id=c_pending.id, subsidy_id=subsidy.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
        approval_status="in_progress",
    )

    # Договор №2: рамочная голова уже согласована
    c_approved = Contract(number="Д-202", contract_type="framework_with_amount", subsidy_id=subsidy.id)
    db_session.add(c_approved)
    await db_session.commit()
    await db_session.refresh(c_approved)
    p_approved = await make_purchase(
        contract_id=c_approved.id, subsidy_id=subsidy.id,
        purchase_contract_type="framework_with_amount", parent_purchase_id=None,
        approval_status="approved",
    )

    # Договор №3: обычный (не рамочный) — approval_state всегда None
    c_single = Contract(number="Д-203", contract_type="single", subsidy_id=subsidy.id)
    db_session.add(c_single)
    await db_session.commit()

    resp = await client.get("/api/contracts/", headers=superadmin_headers)
    assert resp.status_code == 200, resp.text
    by_number = {row["number"]: row for row in resp.json()}

    assert by_number["Д-201"]["approval_state"] == "pending"
    assert by_number["Д-202"]["approval_state"] == "approved"
    assert by_number["Д-203"]["approval_state"] is None
