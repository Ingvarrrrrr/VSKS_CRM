"""Тесты «Поставлено, не оплачено» = Σ остатков ПО ЗАКУПКЕ (владелец,
06.10.2026, ФАДМ 2026_2) — переплата по одной закупке не гасит долг другой,
drill (GET /api/dashboard/type-drill, stage=delivered_unpaid) отдаёт ТОЛЬКО
закупки с остатком > 0 и ту же сумму, что карточка (GET /api/dashboard/charts,
subsidy_stats[].total_delivered_unpaid / delivered_unpaid_declared_by_kind).
"""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"ResidualSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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
class TestDeliveredUnpaidResidual:
    async def test_fully_paid_purchase_has_no_residual(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        # delivered, оплачено ПОЛНОСТЬЮ (payment_amount == contract_price) — не
        # должна попасть ни в карточку, ни в drill.
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("1000"), payment_amount=Decimal("1000"),
            items=[("товар", 1000)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        assert charts.status_code == 200
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["total_delivered_unpaid"] == pytest.approx(0.0, abs=0.01)
        assert row["delivered_unpaid_declared_by_kind"]["goods"] == pytest.approx(0.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered_unpaid", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill.status_code == 200
        body = drill.json()
        assert body["total"] == pytest.approx(0.0, abs=0.01)
        assert body["rows"] == []

    async def test_partial_payment_gives_residual_not_full_amount(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        p = await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("1000"), payment_amount=Decimal("400"),
            items=[("товар", 1000)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["total_delivered_unpaid"] == pytest.approx(600.0, abs=0.01)
        assert row["delivered_unpaid_declared_by_kind"]["goods"] == pytest.approx(600.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered_unpaid", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body = drill.json()
        assert body["total"] == pytest.approx(600.0, abs=0.01)
        assert {r["purchase_id"] for r in body["rows"]} == {p.id}
        assert body["rows"][0]["stage_amount"] == pytest.approx(600.0, abs=0.01)

    async def test_overpaid_purchase_does_not_offset_another_purchase_debt(self, client, superadmin_headers, db_session):
        """Жалоба владельца: прежняя формула вычитала Σ«оплачено» из Σ«поставлено»
        СУБСИДИИ целиком — переплата по p_over гасила долг p_unpaid. Теперь
        остаток считается ПО ЗАКУПКЕ: p_over даёт 0 (не отрицательное число,
        переносимое на соседа), p_unpaid — полным долгом."""
        subsidy = await _make_subsidy(db_session)
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("1000"), payment_amount=Decimal("1500"),  # переплата
            items=[("товар", 1000)],
        )
        p_unpaid = await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("500"),  # без оплаты вовсе
            items=[("товар", 500)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        # Правильно: 0 (переплата) + 500 (неоплачено) = 500, НЕ max(0, 1500-1500)=0.
        assert row["total_delivered_unpaid"] == pytest.approx(500.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered_unpaid", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body = drill.json()
        assert body["total"] == pytest.approx(500.0, abs=0.01)
        assert {r["purchase_id"] for r in body["rows"]} == {p_unpaid.id}

    async def test_drill_matches_card_total_by_kind(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("1000"), payment_amount=Decimal("200"),
            items=[("товар", 1000)],
        )
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("300"), payment_amount=Decimal("100"),
            items=[("работа", 300)],
        )

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        by_kind = row["delivered_unpaid_declared_by_kind"]
        assert row["total_delivered_unpaid"] == pytest.approx(1000.0, abs=0.01)
        assert by_kind["goods"] == pytest.approx(800.0, abs=0.01)
        assert by_kind["services"] == pytest.approx(200.0, abs=0.01)

        drill_goods = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered_unpaid", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        drill_services = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered_unpaid", "kind": "services", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill_goods.json()["total"] == pytest.approx(by_kind["goods"], abs=0.01)
        assert drill_services.json()["total"] == pytest.approx(by_kind["services"], abs=0.01)
