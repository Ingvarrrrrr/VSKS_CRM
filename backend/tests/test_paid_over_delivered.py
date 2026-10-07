"""Тесты «Оплачено больше, чем поставлено» (владелец, 07.10.2026, прод id=74
«ЛНР»: карточки «Поставлено» 3 381 872,26 / «Поставлено, не оплачено» 0,00 /
«Оплачено» 3 385 009,26 — оплачено больше поставленного, РЕЕ-2026-03421
work_in_progress, оплата по отметке 3 137, договора нет). excess = max(0,
оплачено − поставлено) ПО ЗАКУПКЕ (поставлено=0 для статуса ниже delivered/
paid), drill (GET /api/dashboard/paid-over-delivered-drill) отдаёт ТОЛЬКО
закупки с excess > 0 и ту же сумму, что карточка (GET /api/dashboard/charts,
widgets.paid_over_delivered / subsidy_stats[].paid_over_delivered).
"""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"ExcessSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_purchase(db_session, subsidy_id, *, status, items=None, **kwargs):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    p = Purchase(subsidy_id=subsidy_id, status=status, item_name=f"Purchase-{uuid.uuid4().hex[:6]}", **kwargs)
    db_session.add(p)
    await db_session.flush()
    for item_type, amount in (items or []):
        db_session.add(PurchaseItem(
            purchase_id=p.id, item_name="item", item_type=item_type,
            quantity=Decimal("1"), unit_price=Decimal(str(amount)), total_price=Decimal(str(amount)),
        ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


@pytest.mark.asyncio
class TestPaidOverDelivered:
    async def test_work_in_progress_declared_payment_is_fully_excess(self, client, superadmin_headers, db_session):
        """Прод-кейс: work_in_progress + payment_amount_declared=3137, нет
        contract_price/acceptance — «поставлено» = 0, весь платёж сверх."""
        subsidy = await _make_subsidy(db_session)
        p = await _make_purchase(
            db_session, subsidy.id, status="work_in_progress",
            payment_amount_declared=Decimal("3137"),
            items=[("товар", 3137)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        assert charts.status_code == 200
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["paid_over_delivered"] == pytest.approx(3137.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/paid-over-delivered-drill",
            params={"scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill.status_code == 200
        body = drill.json()
        assert body["total"] == pytest.approx(3137.0, abs=0.01)
        assert {r["purchase_id"] for r in body["rows"]} == {p.id}
        row_out = body["rows"][0]
        assert row_out["excess"] == pytest.approx(3137.0, abs=0.01)
        assert row_out["is_prepayment"] is False
        assert "оплачено, но не поставлено" in row_out["reason"]
        assert "«Ведётся работа»" in row_out["reason"]

    async def test_paid_fully_delivered_purchase_has_no_excess(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        await _make_purchase(
            db_session, subsidy.id, status="paid",
            contract_price=Decimal("100"), payment_amount=Decimal("100"),
            items=[("товар", 100)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["paid_over_delivered"] == pytest.approx(0.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/paid-over-delivered-drill",
            params={"scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body = drill.json()
        assert body["total"] == pytest.approx(0.0, abs=0.01)
        assert body["rows"] == []

    async def test_prepayment_marked_separately(self, client, superadmin_headers, db_session):
        """is_prepayment=True (аванс, статус ordered) с оплатой — попадает в
        список, помечена «аванс», и отдельно в prepayment_total."""
        subsidy = await _make_subsidy(db_session)
        p = await _make_purchase(
            db_session, subsidy.id, status="ordered", is_prepayment=True,
            payment_amount_declared=Decimal("200"),
            items=[("товар", 200)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["paid_over_delivered"] == pytest.approx(200.0, abs=0.01)
        assert row["paid_over_delivered_prepayment"] == pytest.approx(200.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/paid-over-delivered-drill",
            params={"scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body = drill.json()
        assert body["prepayment_total"] == pytest.approx(200.0, abs=0.01)
        row_out = next(r for r in body["rows"] if r["purchase_id"] == p.id)
        assert row_out["is_prepayment"] is True
        assert row_out["reason"] == "аванс (оплата до поставки)"

    async def test_overpaid_purchase_does_not_offset_underpaid_purchase(self, client, superadmin_headers, db_session):
        """Две закупки одной субсидии: одна переплачена на 50 (delivered,
        поставлено 100, оплачено 150), другая недоплачена на 50 (delivered,
        поставлено 100, оплачено 50 — т.е. НЕ excess, а остаток поставки,
        другой показатель). Σ excess по субсидии = 50, не 0 (переплата одной
        не гасится недоплатой другой — та же логика, что delivered_unpaid
        residual, зеркально)."""
        subsidy = await _make_subsidy(db_session)
        p_over = await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("100"), payment_amount=Decimal("150"),
            items=[("товар", 100)],
        )
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("100"), payment_amount=Decimal("50"),
            items=[("товар", 100)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["paid_over_delivered"] == pytest.approx(50.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/paid-over-delivered-drill",
            params={"scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body = drill.json()
        assert body["total"] == pytest.approx(50.0, abs=0.01)
        assert {r["purchase_id"] for r in body["rows"]} == {p_over.id}
        assert body["rows"][0]["excess"] == pytest.approx(50.0, abs=0.01)
