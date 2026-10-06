"""app.services.dashboard_contracts_drill — расшифровка карточки «Заключено
договоров» по ДОГОВОРАМ (план sleepy-fluttering-walrus.md, п.2, владелец
06.10.2026).

Контрольный пример: один разовый договор, один framework_with_amount с
неиспользованным остатком (та же ситуация, что «Предрейсовый» на проде id=89:
лимит 584 032 − заказано 338 903 = остаток 245 129), один framework_cumulative
— Σ amount строк ОБЯЗАНА совпасть с contracted_total_by_subsidy (ПРАВИЛО №6,
единый источник карточки)."""
import uuid
from decimal import Decimal

import pytest

from app.services.dashboard_contracts_drill import contracts_drill_rows
from app.services.stage_cumulative import contracted_total_by_subsidy


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"ContractsDrill-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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
async def test_contracts_drill_sums_match_card(db_session, test_org):
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)

    # 1) Разовый договор — одна committed-закупка на всю сумму.
    single = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("100000"),
    )
    db_session.add(single)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_price=Decimal("100000"), contract_id=single.id,
    )

    # 2) Рамочный с суммой — лимит 584 032, заказано (дочерние закупки) 338 903
    #    → остаток 245 129 (контрольный пример владельца, «Предрейсовый»).
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("584032"),
    )
    db_session.add(fwa)
    await db_session.flush()
    parent = await _make_purchase(db_session, subsidy.id, status="contracted", contract_id=fwa.id)
    await _make_purchase(
        db_session, subsidy.id, status="ordered", contract_price=Decimal("338903"),
        contract_id=fwa.id, parent_purchase_id=parent.id,
    )

    # 3) Рамочный накопительный — Σ привязанных закупок.
    cumulative = Contract(
        number=f"FC-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, status="active",
    )
    db_session.add(cumulative)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="ordered",
        contract_price=Decimal("50000"), contract_id=cumulative.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="delivered",
        contract_price=Decimal("30000"), contract_id=cumulative.id,
    )

    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])
    assert len(rows) == 3

    by_type = {r["contract_type"]: r for r in rows}
    assert by_type["single"]["contract_amount"] == pytest.approx(100_000.0)
    assert by_type["single"]["remaining"] == pytest.approx(0.0)

    assert by_type["framework_with_amount"]["contract_amount"] == pytest.approx(584_032.0)
    assert by_type["framework_with_amount"]["ordered_amount"] == pytest.approx(338_903.0)
    assert by_type["framework_with_amount"]["remaining"] == pytest.approx(245_129.0)

    assert by_type["framework_cumulative"]["contract_amount"] == pytest.approx(80_000.0)
    assert by_type["framework_cumulative"]["remaining"] == pytest.approx(0.0)

    total = sum(r["contract_amount"] for r in rows)
    card_map = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert total == pytest.approx(card_map[subsidy.id]["amount"])


@pytest.mark.asyncio
async def test_contracts_drill_includes_contractless_committed_purchase(db_session, test_org):
    """«Любая оплата = был договор» (владелец 05.10.2026) — committed-закупка
    БЕЗ Contract попадает в drill отдельной строкой «Без договора», и её
    сумма входит в общий итог наравне с карточкой (ПРАВИЛО №6, тот же приём,
    что test_stage_cumulative_contractless.py для самой карточки)."""
    subsidy = await _make_subsidy(db_session)
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("500"))

    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])
    assert len(rows) == 1
    assert rows[0]["contract_id"] is None
    assert rows[0]["contract_amount"] == pytest.approx(500.0)

    card_map = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert rows[0]["contract_amount"] == pytest.approx(card_map[subsidy.id]["amount"])
