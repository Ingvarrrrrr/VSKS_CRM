"""Регрессия (владелец, 15.10.2026, ФАДМ 2026_2 id=7320): карточка «Ведётся
работа» (GET /api/dashboard/charts?type_split=true → subsidy_stats[].
total_work / widget.work.amount) и окно-расшифровка по клику
(GET /api/dashboard/type-drill?kind=all) обязаны давать ОДНО число (ПРАВИЛО
№6) для ЛЮБОЙ стадии (plan_schedule/work/ordered/delivered/paid — "contracts"
покрыта ниже отдельным тестом (своя, более сложная формула — single_fwa_rows_
by_contract_subsidy + framework_cumulative + committed_uncounted); "delivered_
unpaid" считается отдельной функцией, см. её собственные тесты).

Прод-находка: рамочная голова (framework_with_amount/framework_cumulative,
parent_purchase_id IS NULL) с РЕАЛЬНО существующим заказом-ребёнком обязана
исключаться из статусных сумм (её деньги несут сами заказы, см. докстринг
app.services.purchase_amounts.aggregate_scope_expr) — subsidy_q в
dashboard_charts.py это делает через JOIN-условие, а base_q в
app.services.dashboard_type_split (compute_type_split_raw/
compute_type_split_detail) этот фильтр не применял: голова считалась ЕЩЁ РАЗ
поверх уже посчитанных заказов-детей → drill(kind=all) > карточки ровно на
Σ эффективных сумм голов с детьми.

Тест создаёт framework_with_amount-голову (max_amount=1 400 000, статус
'contracted' — попадает в work/plan_schedule) с одним реальным заказом-
ребёнком (status='ordered', 300 000) и проверяет на каждой из 5 стадий:
Σ type-drill(kind=all).rows == карточке (subsidy_stats/widget), и
goods+services+unspecified (kind=all расклад по chip) == тому же числу.
"""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"StageDrillCard-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


async def _build_framework_head_fixture(db_session, subsidy_id):
    """Рамочная голова framework_with_amount (max_amount=1 400 000,
    status='contracted' — несёт work/plan_schedule) + один реальный
    заказ-ребёнок (status='ordered', 300 000, товар) — голова ОБЯЗАНА
    исчезнуть из статусных сумм, её долю несёт ребёнок."""
    from app.models.contract import Contract
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    contract = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy_id, status="active", max_amount=Decimal("1400000"),
    )
    db_session.add(contract)
    await db_session.flush()

    head = Purchase(
        subsidy_id=subsidy_id, status="contracted", item_name="FWA head",
        contract_id=contract.id, purchase_contract_type="framework_with_amount",
        parent_purchase_id=None, planned_total_price=Decimal("1400000"),
    )
    db_session.add(head)
    await db_session.flush()

    child = Purchase(
        subsidy_id=subsidy_id, status="ordered", item_name="FWA child order",
        contract_id=contract.id, purchase_contract_type="framework_with_amount",
        parent_purchase_id=head.id, planned_total_price=Decimal("300000"),
        contract_price=Decimal("300000"),
    )
    db_session.add(child)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=child.id, item_name="товар", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("300000"), total_price=Decimal("300000"),
    ))
    await db_session.commit()
    await db_session.refresh(head)
    await db_session.refresh(child)
    return contract, head, child


@pytest.mark.asyncio
class TestStageDrillMatchesCard:
    async def test_framework_head_with_child_not_double_counted(
        self, client, superadmin_headers, db_session,
    ):
        subsidy = await _make_subsidy(db_session)
        await _build_framework_head_fixture(db_session, subsidy.id)

        charts_resp = await client.get(
            "/api/dashboard/charts",
            params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert charts_resp.status_code == 200
        charts_payload = charts_resp.json()
        subsidy_row = _find_subsidy_row(charts_payload, subsidy.id)

        for stage in ("plan_schedule", "work", "ordered", "delivered", "paid"):
            card_amount = subsidy_row["widget"][stage]["amount"]

            drill_all = await client.get(
                "/api/dashboard/type-drill",
                params={
                    "stage": stage, "kind": "all", "scope": "dashboard",
                    "subsidy_ids": str(subsidy.id),
                },
                headers=superadmin_headers,
            )
            assert drill_all.status_code == 200
            drill_body = drill_all.json()
            rows_total = sum(r["stage_amount"] for r in drill_body["rows"])

            assert rows_total == pytest.approx(drill_body["total"], abs=0.01), stage
            assert drill_body["total"] == pytest.approx(card_amount, abs=0.01), (
                stage, "drill kind=all must equal card", drill_body["total"], card_amount,
            )

            kind_sum = 0.0
            for kind in ("goods", "services", "unspecified"):
                r = await client.get(
                    "/api/dashboard/type-drill",
                    params={
                        "stage": stage, "kind": kind, "scope": "dashboard",
                        "subsidy_ids": str(subsidy.id),
                    },
                    headers=superadmin_headers,
                )
                assert r.status_code == 200
                kind_sum += r.json()["total"]
            assert kind_sum == pytest.approx(card_amount, abs=0.01), (
                stage, "goods+services+unspecified must equal card",
            )
            # Карточка тоже обязана сойтись chip-в-chip (reconcile_split).
            chip_sum = sum(
                subsidy_row["widget"][stage].get(f"{stage}_{k}", 0.0)
                for k in ("goods", "services", "unspecified")
            )
            assert chip_sum == pytest.approx(card_amount, abs=0.01), (stage, "card chips")

    async def test_contracts_stage_single_fwa_plus_uncounted_matches_card(
        self, client, superadmin_headers, db_session,
    ):
        """Регрессия (15.10.2026, прод id=51/ДНР id=7): при переводе этапа
        "contracts" на ЕДИНЫЙ источник (stage_cumulative.
        single_fwa_rows_by_contract_subsidy) окно теряло слагаемое
        «committed-закупка без активного контракта известного типа»
        (committed_uncounted_expr) — drill оказался МЕНЬШЕ карточки ровно на
        сумму такой закупки (54 318 / 341 565 на проде). Фикстура: single-
        договор с max_amount=200000 и привязанной закупкой на 200000
        (committed) + отдельная закупка БЕЗ контракта, статус 'contracted'
        (тоже committed, но contract_id IS NULL — «неучтённая»)."""
        subsidy = await _make_subsidy(db_session)
        from app.models.contract import Contract
        from app.models.purchase import Purchase
        from app.models.purchase_item import PurchaseItem

        contract = Contract(
            number=f"SGL-{uuid.uuid4().hex[:6]}", contract_type="single",
            subsidy_id=subsidy.id, status="active", max_amount=Decimal("200000"),
        )
        db_session.add(contract)
        await db_session.flush()
        linked = Purchase(
            subsidy_id=subsidy.id, status="contracted", item_name="Single linked",
            contract_id=contract.id, purchase_contract_type="single",
            contract_price=Decimal("200000"),
        )
        db_session.add(linked)
        await db_session.flush()
        db_session.add(PurchaseItem(
            purchase_id=linked.id, item_name="товар", item_type="товар",
            quantity=Decimal("1"), unit_price=Decimal("200000"), total_price=Decimal("200000"),
        ))
        uncounted = Purchase(
            subsidy_id=subsidy.id, status="contracted", item_name="No contract",
            contract_id=None, planned_total_price=Decimal("75000"),
        )
        db_session.add(uncounted)
        await db_session.flush()
        db_session.add(PurchaseItem(
            purchase_id=uncounted.id, item_name="услуга", item_type="услуга",
            quantity=Decimal("1"), unit_price=Decimal("75000"), total_price=Decimal("75000"),
        ))
        await db_session.commit()

        charts_resp = await client.get(
            "/api/dashboard/charts",
            params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert charts_resp.status_code == 200
        subsidy_row = _find_subsidy_row(charts_resp.json(), subsidy.id)
        card_amount = subsidy_row["total_contracts"]
        assert card_amount == pytest.approx(275000.0, abs=0.01)

        drill = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "contracts", "kind": "all", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill.status_code == 200
        body = drill.json()
        rows_total = sum(r["stage_amount"] for r in body["rows"])
        assert rows_total == pytest.approx(body["total"], abs=0.01)
        assert body["total"] == pytest.approx(card_amount, abs=0.01)

    async def test_global_widget_matches_per_subsidy_sum(
        self, client, superadmin_headers, db_session,
    ):
        """Σ per-subsidy widget.work.amount по видимым субсидиям обязана
        совпадать с глобальным widgets.work.amount (basket_q) — тот же
        aggregate_scope_expr() фильтр теперь применён в обоих местах."""
        subsidy = await _make_subsidy(db_session)
        await _build_framework_head_fixture(db_session, subsidy.id)

        drill_global = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "work", "kind": "all", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill_global.status_code == 200
        # 1 400 000 (голова) + 300 000 (ребёнок) было бы ДО фикса; корректно —
        # голова исключена (есть реальный ребёнок), считается только ребёнок.
        assert drill_global.json()["total"] == pytest.approx(300000.0, abs=0.01)
