"""Прод-находка 15.10.2026 (владелец): две субсидии-копии «ФАДМ 2026_2» (id=89)
и «ФАДМ 2026_3» (id=100) делят ОДНИ И ТЕ ЖЕ договоры — загрузчик нашёл
существующие договоры по номеру/дате/контрагенту, Contract.subsidy_id указывает
на ОДНУ "домашнюю" субсидию, а Purchase ОБЕИХ субсидий ссылаются на тот же
Contract.id. Итог на проде: у 89 суммы договоров считали закупки ОБЕИХ
субсидий (13,9 → 19,8 млн), у 100 — только её 22 «своих» договора (7,5 млн <
«Заказано» 12,8 млн).

Правило владельца: договор входит в «Заключено» субсидии S, если к нему
привязана хотя бы одна НЕ остановленная committed-закупка субсидии S; все
суммы по договору для субсидии S считаются ТОЛЬКО по закупкам субсидии S;
лимит framework_with_amount засчитывается субсидии S, если у неё есть закупка
на этом договоре (шапка или заказ). Действующий рамочный-с-суммой БЕЗ единой
закупки вообще (ни в одной субсидии, «АДС-АВТО») — остаётся в своей домашней
субсидии как раньше.

Проверяется ЕДИНЫЙ источник атрибуции (ПРАВИЛО №6) —
app.services.stage_cumulative.single_fwa_rows_by_contract_subsidy() — через
три точки входа, которые на него опираются: contracted_total_by_subsidy()
(карточка), dashboard_contracts_drill.contracts_drill_rows() (список) и
framework_cumulative (который был корректен и раньше в stage_cumulative.py, но
НЕ в dashboard_contracts_drill.py — тоже дефект того же рода, исправлен тут
же)."""
import uuid
from decimal import Decimal

import pytest

from app.services.dashboard_contracts_drill import contracts_drill_rows
from app.services.stage_cumulative import contracted_total_by_subsidy


async def _make_subsidy(db_session, name):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"{name}-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
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
async def test_shared_contracts_do_not_double_count_between_subsidies(db_session, test_org):
    from app.models.contract import Contract

    subsidy_a = await _make_subsidy(db_session, "SharedA")
    subsidy_b = await _make_subsidy(db_session, "SharedB")

    # 1) Общий РАЗОВЫЙ договор (home = A) — по закупке в каждой субсидии.
    single = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy_a.id, status="active", max_amount=Decimal("0"),
    )
    db_session.add(single)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy_a.id, status="contracted",
        contract_price=Decimal("100000"), contract_id=single.id,
    )
    await _make_purchase(
        db_session, subsidy_b.id, status="contracted",
        contract_price=Decimal("50000"), contract_id=single.id,
    )

    # 2) Общий framework_with_amount (home = A), лимит 200000 — заказы в КАЖДОЙ
    #    субсидии.
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy_a.id, status="active", max_amount=Decimal("200000"),
    )
    db_session.add(fwa)
    await db_session.flush()
    head_a = await _make_purchase(
        db_session, subsidy_a.id, status="contracted",
        contract_id=fwa.id, purchase_contract_type="framework_with_amount",
    )
    await _make_purchase(
        db_session, subsidy_a.id, status="ordered", contract_price=Decimal("30000"),
        contract_id=fwa.id, parent_purchase_id=head_a.id,
    )
    head_b = await _make_purchase(
        db_session, subsidy_b.id, status="contracted",
        contract_id=fwa.id, purchase_contract_type="framework_with_amount",
    )
    await _make_purchase(
        db_session, subsidy_b.id, status="ordered", contract_price=Decimal("40000"),
        contract_id=fwa.id, parent_purchase_id=head_b.id,
    )

    # 3) Общий framework_cumulative (home = A) — заказы в КАЖДОЙ субсидии.
    cumulative = Contract(
        number=f"FC-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy_a.id, status="active",
    )
    db_session.add(cumulative)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy_a.id, status="delivered",
        contract_price=Decimal("5000"), contract_id=cumulative.id,
    )
    await _make_purchase(
        db_session, subsidy_b.id, status="delivered",
        contract_price=Decimal("7000"), contract_id=cumulative.id,
    )

    # 4) Действующий framework_with_amount БЕЗ единой закупки вообще (home = A,
    #    «АДС-АВТО») — остаётся только в A.
    unused_fwa = Contract(
        number=f"FWA2-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy_a.id, status="active", max_amount=Decimal("60000"),
    )
    db_session.add(unused_fwa)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy_a.id, status="wishes",
        contract_id=unused_fwa.id, purchase_contract_type="framework_with_amount",
    )

    card = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy_a.id, subsidy_b.id])
    rows_a = await contracts_drill_rows(db_session, subsidy_ids=[subsidy_a.id])
    rows_b = await contracts_drill_rows(db_session, subsidy_ids=[subsidy_b.id])

    # Карточка каждой субсидии == Σ её собственного списка.
    assert card[subsidy_a.id]["amount"] == pytest.approx(sum(r["contract_amount"] for r in rows_a))
    assert card[subsidy_b.id]["amount"] == pytest.approx(sum(r["contract_amount"] for r in rows_b))

    # Ни одна строка субсидии A не принадлежит B и наоборот.
    assert all(r["subsidy_id"] == subsidy_a.id for r in rows_a)
    assert all(r["subsidy_id"] == subsidy_b.id for r in rows_b)

    # Ключ по contract_id — в A есть ДВА framework_with_amount договора
    # (общий `fwa` и легаси `unused_fwa`), группировка по одному contract_type
    # потеряла бы один из них.
    by_contract_a = {r["contract_id"]: r for r in rows_a}
    by_contract_b = {r["contract_id"]: r for r in rows_b}

    # single — каждая субсидия видит ТОЛЬКО свою закупку (max(0, actual)).
    assert by_contract_a[single.id]["contract_amount"] == pytest.approx(100_000.0)
    assert by_contract_b[single.id]["contract_amount"] == pytest.approx(50_000.0)

    # framework_with_amount — заказы разнесены по своим субсидиям; лимит
    # (200000) учитывается ОТДЕЛЬНО для каждой субсидии, у которой есть заказ
    # на этот договор (owner-правило «лимит или факт, что больше» — ПО
    # закупкам этой субсидии).
    assert by_contract_a[fwa.id]["ordered_amount"] == pytest.approx(30_000.0)
    assert by_contract_a[fwa.id]["contract_amount"] == pytest.approx(200_000.0)
    assert by_contract_b[fwa.id]["ordered_amount"] == pytest.approx(40_000.0)
    assert by_contract_b[fwa.id]["contract_amount"] == pytest.approx(200_000.0)

    # framework_cumulative — каждая субсидия видит только свою Σ.
    assert by_contract_a[cumulative.id]["contract_amount"] == pytest.approx(5_000.0)
    assert by_contract_b[cumulative.id]["contract_amount"] == pytest.approx(7_000.0)

    # «Заключено ≥ Заказано» в каждой строке обеих субсидий.
    for r in rows_a + rows_b:
        assert r["contract_amount"] + 1e-6 >= r["ordered_amount"]

    # Действующий рамочный-с-суммой без заказов вообще — ТОЛЬКО в домашней A,
    # его нет в списке B (легаси-правило «АДС-АВТО»).
    unused_in_a = [r for r in rows_a if r["contract_id"] == unused_fwa.id]
    unused_in_b = [r for r in rows_b if r["contract_id"] == unused_fwa.id]
    assert len(unused_in_a) == 1
    assert unused_in_a[0]["contract_amount"] == pytest.approx(60_000.0)
    assert unused_in_b == []

    # Субсидия B не утекла в A и наоборот — ни одна сумма A не включает
    # закупки B (100000+30000(заказ)/200000(лимит)+5000+60000 — без 50000/40000/7000 B).
    total_a = sum(r["contract_amount"] for r in rows_a)
    total_b = sum(r["contract_amount"] for r in rows_b)
    assert total_a == pytest.approx(100_000.0 + 200_000.0 + 5_000.0 + 60_000.0)
    assert total_b == pytest.approx(50_000.0 + 200_000.0 + 7_000.0)
