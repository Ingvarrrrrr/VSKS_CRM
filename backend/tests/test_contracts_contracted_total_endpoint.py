"""GET /api/contracts/contracted-total — итог вкладки «Договоры» для ОДНОЙ
субсидии (найдено 2026-10-06, ФАДМ 2026_2, прод id=88): вкладка «Договоры»
(frontend/src/composables/contracts/useContractsFilters.ts::filteredSum)
раньше суммировала голый Contract.max_amount и расходилась с карточкой
«Заключено договоров» на странице субсидии (dashboard_charts.py::
total_contracts/widget.contracts), которая применяет greatest()/топ-апы/
framework_cumulative (app.services.stage_cumulative.contracted_total_by_subsidy,
ПРАВИЛО №6 — единая функция для обоих мест).

Этот тест строит ровно тот сценарий, который давал разницу на проде: single-
договор с max_amount=NULL (топ-ап по факту закупки) + framework_with_amount,
чьи заказы превысили лимит головы (greatest побеждает лимит) — наивная Σ
max_amount даёт меньше, чем единый расчёт."""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"ContractedTotal-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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
async def test_contracted_total_endpoint_matches_subsidy_kpi_card(client, superadmin_headers, db_session):
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)

    # single, max_amount=NULL — наивная Σ Contract.max_amount даёт 0 для этого
    # договора; единый расчёт обязан топ-апнуть реальной Σ закупки (1500).
    c1 = Contract(
        number=f"C-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=None,
    )
    db_session.add(c1)
    await db_session.flush()
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("1500"), contract_id=c1.id)

    # framework_with_amount: лимит головы 1000, но заказы-дети уже на 1800 —
    # greatest() обязан показать 1800, не застрявший лимит; наивная Σ
    # max_amount взяла бы только 1000 (голову).
    c2 = Contract(
        number=f"C-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("1000"),
    )
    db_session.add(c2)
    await db_session.flush()
    head = await _make_purchase(db_session, subsidy.id, status="contracted", contract_id=c2.id)
    await _make_purchase(
        db_session, subsidy.id, status="ordered", contract_price=Decimal("1800"),
        contract_id=c2.id, parent_purchase_id=head.id,
    )

    # Наивная Σ Contract.max_amount (старое поведение вкладки «Договоры»):
    naive_sum = 0.0 + float(c2.max_amount)  # c1.max_amount is None -> 0

    resp_charts = await client.get(
        "/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers,
    )
    assert resp_charts.status_code == 200
    chart_row = next(r for r in resp_charts.json()["subsidy_stats"] if r["id"] == subsidy.id)
    official_total = chart_row["total_contracts"]

    resp_tab = await client.get(
        "/api/contracts/contracted-total", params={"subsidy_id": subsidy.id}, headers=superadmin_headers,
    )
    assert resp_tab.status_code == 200
    tab_total = resp_tab.json()["amount"]

    # Единый источник (ПРАВИЛО №6): итог вкладки «Договоры» == карточка
    # «Заключено договоров» — и оба СТРОГО больше наивной Σ max_amount.
    assert tab_total == pytest.approx(official_total)
    assert tab_total == pytest.approx(1500.0 + 1800.0)
    assert tab_total > naive_sum
