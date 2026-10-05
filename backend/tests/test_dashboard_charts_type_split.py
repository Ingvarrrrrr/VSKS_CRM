"""Тесты GET /api/dashboard/charts?type_split=true (план ancient-prancing-music.md,
раздел B/1). Одна субсидия с закупками разных типов в разных статусах — сумма
goods+services+unspecified обязана РОВНО совпадать со значением этапа без
флага (Правило №6 — раскладка тех же денег, не второй расчёт), закупка без
позиций попадает в unspecified целиком, а без флага в ответе НЕТ новых полей.
"""
import uuid
from decimal import Decimal

import pytest

STAGE_KEYS = ("plan_schedule", "work", "ordered", "contracts", "delivered", "delivered_unpaid", "paid")


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TypeSplitSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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
    from app.models.contract import Contract
    subsidy = await _make_subsidy(db_session)

    # p1: plan_schedule, mixed goods/services
    await _make_purchase(
        db_session, subsidy.id, status="plan_schedule",
        planned_total_price=Decimal("1000"),
        items=[("товар", 600), ("услуга", 400)],
    )
    # p2: work_in_progress, services only
    await _make_purchase(
        db_session, subsidy.id, status="work_in_progress",
        planned_total_price=Decimal("500"),
        items=[("услуга", 500)],
    )
    # p3: ordered, goods only
    await _make_purchase(
        db_session, subsidy.id, status="ordered",
        contract_price=Decimal("800"),
        items=[("товар", 800)],
    )
    # p4: delivered, NO items — целиком «без типа»
    await _make_purchase(
        db_session, subsidy.id, status="delivered",
        contract_price=Decimal("300"),
        items=[],
    )
    # p5: paid, mixed goods/services
    await _make_purchase(
        db_session, subsidy.id, status="paid",
        payment_amount=Decimal("200"),
        items=[("товар", 100), ("услуга", 100)],
    )
    # p6: contracted, linked to an active framework_cumulative Contract — тестирует
    # обычные бакеты (plan_schedule/work), но по решению владельца 02.10.2026
    # (committed_amounts.py, PLAN.md money-redistribution шаг 1) рамочная ГОЛОВА
    # сама по себе денег НЕ занимает — в widget "contracts" эта закупка больше
    # НЕ входит, пока по ней нет размещённого заказа (ordered/delivered/paid).
    contract = Contract(
        number=f"C-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, status="active",
    )
    db_session.add(contract)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_price=Decimal("1000"), contract_id=contract.id,
        items=[("товар", 1000)],
    )
    # p7: ordered под тем же рамочным договором — ЭТА закупка и есть
    # «размещённый заказ», который по новому правилу занимает деньги и
    # единственная формирует widget "contracts" (400, goods) для этого договора.
    await _make_purchase(
        db_session, subsidy.id, status="ordered",
        contract_price=Decimal("400"), contract_id=contract.id,
        items=[("товар", 400)],
    )

    return subsidy


EXPECTED = {
    # +400 (p7, ordered/товар) во всех бакетах, куда входит статус "ordered":
    # plan_schedule/work/ordered — см. _stage_contributions (dashboard_type_split.py).
    "plan_schedule": {"amount": 4200.0, "goods": 2900.0, "services": 1000.0, "unspecified": 300.0},
    "work": {"amount": 3200.0, "goods": 2300.0, "services": 600.0, "unspecified": 300.0},
    "ordered": {"amount": 1700.0, "goods": 1300.0, "services": 100.0, "unspecified": 300.0},
    # "contracts" (владелец 02.10.2026): рамочная ГОЛОВА (p6, contracted) НЕ
    # занимает деньги — только размещённый заказ (p7, ordered, 400, goods).
    "contracts": {"amount": 400.0, "goods": 400.0, "services": 0.0, "unspecified": 0.0},
    "delivered": {"amount": 500.0, "goods": 100.0, "services": 100.0, "unspecified": 300.0},
    "delivered_unpaid": {"amount": 300.0, "goods": 0.0, "services": 0.0, "unspecified": 300.0},
    "paid": {"amount": 200.0, "goods": 100.0, "services": 100.0, "unspecified": 0.0},
}


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


@pytest.mark.asyncio
class TestDashboardChartsTypeSplit:
    async def test_type_split_matches_existing_totals_exactly(self, client, superadmin_headers, db_session):
        subsidy = await _build_fixture_subsidy(db_session)

        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        row = _find_subsidy_row(payload, subsidy.id)

        for stage in STAGE_KEYS:
            widget = row["widget"][stage]
            exp = EXPECTED[stage]
            assert widget["amount"] == pytest.approx(exp["amount"]), stage
            g = widget[f"{stage}_goods"]
            s = widget[f"{stage}_services"]
            u = widget[f"{stage}_unspecified"]
            assert g == pytest.approx(exp["goods"]), stage
            assert s == pytest.approx(exp["services"]), stage
            assert u == pytest.approx(exp["unspecified"]), stage
            # Инвариант (Правило №6): сумма трёх частей РОВНО значение этапа.
            assert g + s + u == pytest.approx(widget["amount"]), stage

    async def test_purchase_without_items_is_fully_unspecified(self, client, superadmin_headers, db_session):
        subsidy = await _build_fixture_subsidy(db_session)
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        row = _find_subsidy_row(resp.json(), subsidy.id)
        # p4 (delivered, без позиций, 300) — единственный вклад в delivered_unpaid.
        du = row["widget"]["delivered_unpaid"]
        assert du["delivered_unpaid_unspecified"] == pytest.approx(300.0)
        assert du["delivered_unpaid_goods"] == pytest.approx(0.0)
        assert du["delivered_unpaid_services"] == pytest.approx(0.0)

    async def test_global_widgets_invariant_holds_regardless_of_dataset(self, client, superadmin_headers, db_session):
        # Не привязано к конкретной субсидии — сумма частей глобального виджета
        # обязана совпадать с его "amount" независимо от того, что ещё есть в БД.
        await _build_fixture_subsidy(db_session)
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        widgets = resp.json()["widgets"]
        for stage in STAGE_KEYS:
            w = widgets[stage]
            total = w[f"{stage}_goods"] + w[f"{stage}_services"] + w[f"{stage}_unspecified"]
            assert total == pytest.approx(w["amount"]), stage

    async def test_no_flag_means_no_new_keys_and_unchanged_shape(self, client, superadmin_headers, db_session):
        subsidy = await _build_fixture_subsidy(db_session)
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        for stage in STAGE_KEYS:
            for key in payload["widgets"][stage]:
                assert not key.endswith("_goods") and not key.endswith("_services") and not key.endswith("_unspecified")
        row = _find_subsidy_row(payload, subsidy.id)
        for key in ("budget_goods", "budget_services", "budget_unspecified",
                    "planned_goods", "planned_services", "planned_unspecified"):
            assert key not in row
        for key in ("budget_goods", "budget_services", "budget_unspecified",
                    "planned_goods", "planned_services", "planned_unspecified"):
            assert key not in payload
        for stage in STAGE_KEYS:
            for key in row["widget"][stage]:
                assert not key.endswith("_goods") and not key.endswith("_services") and not key.endswith("_unspecified")

    async def test_type_split_budget_and_planned_fields_present(self, client, superadmin_headers, db_session):
        subsidy = await _build_fixture_subsidy(db_session)
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        row = _find_subsidy_row(resp.json(), subsidy.id)
        for key in ("budget_goods", "budget_services", "budget_unspecified",
                    "planned_goods", "planned_services", "planned_unspecified"):
            assert key in row

    async def test_subsidy_without_tree_puts_fallback_budget_in_unspecified(self, client, superadmin_headers, db_session):
        """Исправление 2026-09-21 (боевой замер, субсидия «Тестовая» id 59):
        субсидия БЕЗ единой FeoCategory — compute_feo_plan_tree не возвращает
        ни одного узла, split (budget_goods/services/unspecified) у неё 0 по
        построению. Но effective_budget (карточка «Бюджет (ФЭО)») в этом
        случае берёт fallback — subsidies.budget (calculate_budgets_bulk дал
        0, дерева нет) — а не 0. Fallback типа не имеет -> целиком в
        budget_unspecified, иначе Σ(goods+services+unspecified) разойдётся с
        feo_budget_total (100000 vs 0)."""
        from app.models.subsidy import Subsidy
        subsidy = Subsidy(
            name=f"NoTreeSubsidy-{uuid.uuid4().hex[:8]}", year=2026,
            require_planned_dates=False, budget=Decimal("100000"),
        )
        db_session.add(subsidy)
        await db_session.commit()
        await db_session.refresh(subsidy)

        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        row = _find_subsidy_row(resp.json(), subsidy.id)

        assert row["feo_filled"] is False, "дерева нет -> calculate_budgets_bulk дал 0 -> fallback"
        assert row["feo_budget_total"] == pytest.approx(100_000.0)
        assert row["budget_goods"] == pytest.approx(0.0)
        assert row["budget_services"] == pytest.approx(0.0)
        assert row["budget_unspecified"] == pytest.approx(100_000.0)
        split_sum = row["budget_goods"] + row["budget_services"] + row["budget_unspecified"]
        assert split_sum == pytest.approx(row["feo_budget_total"]), "Правило №6: split обязан суммироваться в scalar"


@pytest.mark.asyncio
class TestDeliveredUnpaidDeclared:
    """Карточка «Поставлено, не оплачено» (владелец, 05.10.2026) = «Поставлено»
    минус «Оплачено по отметке сотрудников» (paid_declared), не ниже 0, по
    типам тоже — см. dashboard_charts.py total_delivered_unpaid /
    delivered_unpaid_declared_by_kind. Сценарий владельца: поставлено 1000
    (товар 600 / услуга 400), отмечено оплаченным 700 (товар 600 / услуга 100)
    -> не оплачено 300 (товар 0 / услуга 300). widget["delivered_unpaid"]
    (старый смысл: status='delivered' без paid) НЕ трогается — проверяем
    отдельно, что он остался прежним.
    """

    async def test_delivered_unpaid_declared_matches_owner_scenario(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        # p1: delivered, товар 600, отмечено оплаченным целиком (600)
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("600"), payment_amount_declared=Decimal("600"),
            items=[("товар", 600)],
        )
        # p2: delivered, услуга 400, отмечено оплаченным частично (100)
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("400"), payment_amount_declared=Decimal("100"),
            items=[("услуга", 400)],
        )

        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        row = _find_subsidy_row(resp.json(), subsidy.id)

        # «Поставлено» = 1000, «Оплачено по отметке» = 700
        assert row["total_delivered"] == pytest.approx(1000.0)
        assert row["paid_declared"] == pytest.approx(700.0)
        # Новая карточка: 1000 − 700 = 300
        assert row["total_delivered_unpaid"] == pytest.approx(300.0)
        by_kind = row["delivered_unpaid_declared_by_kind"]
        assert by_kind["goods"] == pytest.approx(0.0)
        assert by_kind["services"] == pytest.approx(300.0)
        assert by_kind["unspecified"] == pytest.approx(0.0)

        # Старое поле widget["delivered_unpaid"] (status='delivered' без paid)
        # остаётся прежним смыслом — ВСЯ сумма (ни одна из этих закупок не
        # перешла в статус 'paid'), читается дашбордом (useDashboardData.ts).
        assert row["widget"]["delivered_unpaid"]["amount"] == pytest.approx(1000.0)

    async def test_delivered_unpaid_declared_floors_at_zero(self, client, superadmin_headers, db_session):
        """Отмечено оплаченным больше, чем поставлено (частичная предоплата
        задним числом/округление) — не уходим в минус."""
        subsidy = await _make_subsidy(db_session)
        await _make_purchase(
            db_session, subsidy.id, status="delivered",
            contract_price=Decimal("100"), payment_amount_declared=Decimal("150"),
            items=[("товар", 100)],
        )
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        row = _find_subsidy_row(resp.json(), subsidy.id)
        assert row["total_delivered_unpaid"] == pytest.approx(0.0)
        by_kind = row["delivered_unpaid_declared_by_kind"]
        assert by_kind["goods"] == pytest.approx(0.0)
        assert by_kind["services"] == pytest.approx(0.0)
        assert by_kind["unspecified"] == pytest.approx(0.0)
