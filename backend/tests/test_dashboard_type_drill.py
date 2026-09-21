"""Тесты GET /api/dashboard/type-drill (расшифровка строки «товары/услуги/без
типа» карточки этапа дашборда, владелец 21.09: карточка «План-график·товары»
24 559 275 vs диалог 36,7 млн — диалог считал сумму САМ на клиенте, расходился
с карточкой).

Инвариант (Правило №6): Σ stage_amount по rows с kind=K ОБЯЗАНА совпадать с
widgets[stage][f"{stage}_{K}"] (глобально) и с widget[stage][f"{stage}_{K}"]
конкретной субсидии (per-subsidy) из GET /api/dashboard/charts?type_split=true
— обе точки читают одну и ту же формулу
(app.services.dashboard_type_split.compute_type_split_raw /
compute_type_split_detail), просто одна агрегирует в 3 числа, другая отдаёт
построчно. purchases_count — число РАЗЛИЧНЫХ закупок среди rows.
"""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TypeDrillSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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


async def _build_fixture_subsidy(db_session):
    """3 закупки (владелец, план задачи): типизированные позиции (товар) +
    закупка без позиций (без типа) + работа (считается услугой, kind_of)."""
    subsidy = await _make_subsidy(db_session)

    # p1: plan_schedule, товар — попадает ТОЛЬКО в этап plan_schedule.
    p1 = await _make_purchase(
        db_session, subsidy.id, status="plan_schedule",
        planned_total_price=Decimal("1000"),
        items=[("товар", 1000)],
    )
    # p2: paid, работа (= услуга по kind_of) — попадает в plan_schedule И paid
    # (накопительные корзины).
    p2 = await _make_purchase(
        db_session, subsidy.id, status="paid",
        payment_amount=Decimal("500"),
        items=[("работа", 500)],
    )
    # p3: paid, БЕЗ позиций — целиком «без типа», тоже в plan_schedule И paid.
    p3 = await _make_purchase(
        db_session, subsidy.id, status="paid",
        payment_amount=Decimal("300"),
        items=[],
    )

    return subsidy, p1, p2, p3


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


@pytest.mark.asyncio
class TestDashboardTypeDrill:
    async def test_plan_schedule_rows_match_kind_and_purchases(self, client, superadmin_headers, db_session):
        subsidy, p1, p2, p3 = await _build_fixture_subsidy(db_session)

        resp_goods = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "plan_schedule", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert resp_goods.status_code == 200
        body = resp_goods.json()
        assert body["stage"] == "plan_schedule"
        assert body["kind"] == "goods"
        assert body["total"] == pytest.approx(1000.0, abs=0.01)
        assert body["purchases_count"] == 1
        assert {r["purchase_id"] for r in body["rows"]} == {p1.id}
        for r in body["rows"]:
            assert r["kind"] == "goods"
            assert r["item_type"] == "товар"

        resp_services = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "plan_schedule", "kind": "services", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body_s = resp_services.json()
        assert body_s["total"] == pytest.approx(500.0, abs=0.01)
        assert body_s["purchases_count"] == 1
        assert {r["purchase_id"] for r in body_s["rows"]} == {p2.id}

        resp_unspec = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "plan_schedule", "kind": "unspecified", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body_u = resp_unspec.json()
        assert body_u["total"] == pytest.approx(300.0, abs=0.01)
        assert body_u["purchases_count"] == 1
        assert {r["purchase_id"] for r in body_u["rows"]} == {p3.id}
        assert body_u["rows"][0]["item_name"] == "— (без позиции)"

    async def test_paid_rows_match_kind_and_purchases(self, client, superadmin_headers, db_session):
        subsidy, p1, p2, p3 = await _build_fixture_subsidy(db_session)

        resp_goods = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "paid", "kind": "goods", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body_g = resp_goods.json()
        assert body_g["total"] == pytest.approx(0.0, abs=0.01)
        assert body_g["purchases_count"] == 0
        assert body_g["rows"] == []

        resp_services = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "paid", "kind": "services", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body_s = resp_services.json()
        assert body_s["total"] == pytest.approx(500.0, abs=0.01)
        assert body_s["purchases_count"] == 1
        assert {r["purchase_id"] for r in body_s["rows"]} == {p2.id}

        resp_unspec = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "paid", "kind": "unspecified", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        body_u = resp_unspec.json()
        assert body_u["total"] == pytest.approx(300.0, abs=0.01)
        assert body_u["purchases_count"] == 1
        assert {r["purchase_id"] for r in body_u["rows"]} == {p3.id}

    async def test_invariant_matches_charts_widget_global_and_per_subsidy(self, client, superadmin_headers, db_session):
        subsidy, p1, p2, p3 = await _build_fixture_subsidy(db_session)

        charts_resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert charts_resp.status_code == 200
        charts_payload = charts_resp.json()
        global_widgets = charts_payload["widgets"]
        subsidy_row = _find_subsidy_row(charts_payload, subsidy.id)

        for stage in ("plan_schedule", "paid"):
            for kind in ("goods", "services", "unspecified"):
                drill_global = await client.get(
                    "/api/dashboard/type-drill",
                    params={"stage": stage, "kind": kind, "scope": "dashboard"},
                    headers=superadmin_headers,
                )
                assert drill_global.status_code == 200
                drill_body = drill_global.json()
                rows_total = sum(r["stage_amount"] for r in drill_body["rows"])
                assert rows_total == pytest.approx(drill_body["total"], abs=0.01), (stage, kind)
                assert drill_body["total"] == pytest.approx(
                    global_widgets[stage][f"{stage}_{kind}"], abs=0.01
                ), (stage, kind, "global")
                assert drill_body["purchases_count"] == len({r["purchase_id"] for r in drill_body["rows"] if r["purchase_id"] is not None})

                drill_scoped = await client.get(
                    "/api/dashboard/type-drill",
                    params={"stage": stage, "kind": kind, "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
                    headers=superadmin_headers,
                )
                scoped_body = drill_scoped.json()
                assert scoped_body["total"] == pytest.approx(
                    subsidy_row["widget"][stage][f"{stage}_{kind}"], abs=0.01
                ), (stage, kind, "per_subsidy")

    async def test_unknown_stage_or_kind_rejected(self, client, superadmin_headers, db_session):
        resp = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "not_a_stage", "kind": "goods", "scope": "dashboard"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 422

        resp2 = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "paid", "kind": "not_a_kind", "scope": "dashboard"},
            headers=superadmin_headers,
        )
        assert resp2.status_code == 422
