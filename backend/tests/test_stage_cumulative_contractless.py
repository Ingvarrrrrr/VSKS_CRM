"""stage_cumulative.committed_without_contract_by_subsidy — решение владельца
05.10.2026: «любая оплата = был договор, хоть упрощённый по чеку/счёту» —
закупка БЕЗ формального Contract, но дошедшая до committed-статуса, должна
попадать в «Заключено договоров» (dashboard_charts.py::contracts_map/
total_contracts/widget.contracts)."""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"Contractless-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_purchase(db_session, subsidy_id, *, status, **kwargs):
    from app.models.purchase import Purchase
    p = Purchase(subsidy_id=subsidy_id, status=status, item_name=f"P-{uuid.uuid4().hex[:6]}", **kwargs)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_contractless_paid_purchase_counts_in_contracts_card(client, superadmin_headers, db_session):
    subsidy = await _make_subsidy(db_session)
    # Закупка оплачена «по чеку» — НЕТ ни Contract, ни contract_id.
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("500"))
    # plan_schedule — контроль, что НЕ попадает (статус не committed).
    await _make_purchase(db_session, subsidy.id, status="plan_schedule", planned_total_price=Decimal("1000"))

    resp = await client.get(
        "/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    row = next(r for r in payload["subsidy_stats"] if r["id"] == subsidy.id)
    assert row["total_contracts"] == pytest.approx(500.0)
    assert row["widget"]["contracts"]["amount"] == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_purchase_with_real_contract_not_double_counted(client, superadmin_headers, db_session):
    from app.models.contract import Contract
    subsidy = await _make_subsidy(db_session)
    contract = Contract(
        number=f"C-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("700"),
    )
    db_session.add(contract)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_price=Decimal("700"), contract_id=contract.id,
    )

    resp = await client.get(
        "/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    row = next(r for r in payload["subsidy_stats"] if r["id"] == subsidy.id)
    # Ровно 700 — не 1400 (single-договор уже даёт max_amount=700 через
    # contract_single_q, contract_id НЕ NULL — contractless-слагаемое её не видит).
    assert row["total_contracts"] == pytest.approx(700.0)


@pytest.mark.asyncio
async def test_single_contract_null_max_amount_topped_up(client, superadmin_headers, db_session):
    """Находка (стенд, субсидия «ХО», 05.10.2026): Contract(contract_type=
    'single', status='active') с max_amount IS NULL — cs_rows (dashboard_
    charts.py) буквально суммирует Contract.max_amount, SQL SUM молча теряет
    NULL-строки целиком, «Заключено договоров» показывал 0 для таких
    закупок, хотя они дошли до «Оплачено». single_contract_topup_by_subsidy
    обязана добавить реальную Σ закупки."""
    from app.models.contract import Contract
    subsidy = await _make_subsidy(db_session)
    contract = Contract(
        number=f"C-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=None,
    )
    db_session.add(contract)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="paid",
        payment_amount=Decimal("1500"), contract_id=contract.id,
    )

    resp = await client.get(
        "/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    row = next(r for r in payload["subsidy_stats"] if r["id"] == subsidy.id)
    assert row["total_contracts"] == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_contracted_ge_ordered_ge_delivered_invariant(client, superadmin_headers, db_session):
    """Правило владельца (05.10.2026) ПО ПОСТРОЕНИЮ: «Заключён договор» ⊇
    «Заказано» ⊇ «Поставлено» для КАЖДОЙ субсидии, на смешанном наборе
    закупок (с и без Contract, single с NULL max_amount, рамочный, аванс)."""
    from app.models.contract import Contract
    subsidy = await _make_subsidy(db_session)

    # Без Contract вовсе.
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("500"))
    # single, max_amount=NULL.
    c1 = Contract(number=f"C-{uuid.uuid4().hex[:6]}", contract_type="single", subsidy_id=subsidy.id, status="active", max_amount=None)
    db_session.add(c1)
    await db_session.flush()
    await _make_purchase(db_session, subsidy.id, status="delivered", contract_price=Decimal("777"), contract_id=c1.id)
    # рамочный (framework_cumulative), заказ.
    c2 = Contract(number=f"C-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative", subsidy_id=subsidy.id, status="active")
    db_session.add(c2)
    await db_session.flush()
    await _make_purchase(db_session, subsidy.id, status="ordered", contract_price=Decimal("300"), contract_id=c2.id)
    # Контракт НЕактивный (расторгнут) — закупка всё равно committed.
    c3 = Contract(number=f"C-{uuid.uuid4().hex[:6]}", contract_type="single", subsidy_id=subsidy.id, status="closed", max_amount=Decimal("999"))
    db_session.add(c3)
    await db_session.flush()
    await _make_purchase(db_session, subsidy.id, status="contracted", contract_price=Decimal("900"), contract_id=c3.id)

    resp = await client.get(
        "/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    row = next(r for r in payload["subsidy_stats"] if r["id"] == subsidy.id)
    contracted = row["total_contracts"]
    ordered = row["total_ordered"]
    delivered = row["total_delivered"]
    paid = row.get("paid_declared", row.get("total_paid", 0))
    assert contracted + 0.01 >= ordered, (contracted, ordered)
    assert ordered + 0.01 >= delivered, (ordered, delivered)
    assert delivered + 0.01 >= paid, (delivered, paid)
    # Числа по построению: 500(без контракта)+777(single NULL)+300(framework)+900(неактивный) = 2477
    assert contracted == pytest.approx(2477.0)
