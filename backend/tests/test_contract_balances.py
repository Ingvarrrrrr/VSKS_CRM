"""contract_balances.py (владелец 08.10.2026, прод ФАДМ 2026_2) — ЕДИНАЯ
точка «остаток на договоре» (сумма договора минус заказано)."""
import uuid

import pytest

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.services.contract_balances import contract_balances


async def _make_subsidy(db_session, budget=5_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
        require_planned_dates=False, status="approved",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_contract(db_session, **kwargs):
    defaults = dict(number="ДОГ-1", contract_type="framework_with_amount")
    defaults.update(kwargs)
    c = Contract(**defaults)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _make_purchase(db_session, **kwargs) -> Purchase:
    defaults = dict(
        status="ordered", purchase_contract_type=None, parent_purchase_id=None,
        contract_id=None, contract_number=None, feo_category_id=None,
    )
    defaults.update(kwargs)
    p = Purchase(**defaults)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_framework_head_remaining_is_contract_sum_minus_orders(db_session):
    sub = await _make_subsidy(db_session)
    contract = await _make_contract(db_session, max_amount=1000)
    head = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=1,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        contract_number=contract.number, status="ordered",
    )
    order1 = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=2, order_number="1",
        parent_purchase_id=head.id, status="paid", planned_total_price=300,
    )
    order2 = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=3, order_number="2",
        parent_purchase_id=head.id, status="delivered", planned_total_price=200,
    )
    # Отменённая заявка — не должна попасть в "заказано".
    cancelled = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=4, order_number="3",
        parent_purchase_id=head.id, status="cancelled", planned_total_price=400,
    )

    result = await contract_balances(db_session, sub.id)

    head_entry = result["by_purchase"][head.id]
    assert head_entry["contract_sum"] == 1000.0
    assert head_entry["ordered"] == pytest.approx(500.0)
    assert head_entry["remaining"] == pytest.approx(500.0)

    # Заказы получают ТУ ЖЕ запись группы (одно и то же remaining).
    assert result["by_purchase"][order1.id]["remaining"] == pytest.approx(500.0)
    assert result["by_purchase"][order2.id]["remaining"] == pytest.approx(500.0)
    assert cancelled.id not in result["by_purchase"]

    groups = result["groups"]
    assert len(groups) == 1
    assert groups[0]["ordered"] == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_single_purchase_remaining_is_zero(db_session):
    sub = await _make_subsidy(db_session)
    p = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=10, status="paid",
        contract_number="ДОГ-10", planned_total_price=80000,
    )
    result = await contract_balances(db_session, sub.id)
    entry = result["by_purchase"][p.id]
    assert entry["contract_sum"] == pytest.approx(80000.0)
    assert entry["ordered"] == pytest.approx(80000.0)
    assert entry["remaining"] == 0.0


@pytest.mark.asyncio
async def test_wishes_status_with_contract_number_excluded(db_session):
    """Владелец 09.10.2026, прод ФАДМ 2026_2 — «Остаток на договорах» у
    «Без типа» в Сводной был ложно 600 000: закупка в статусе wishes/
    plan_schedule/work_in_progress с заполненным № договора раньше ВСЁ РАВНО
    попадала в contract_balances (contract_number.isnot(None) в OR). Теперь
    contract_scope_predicate требует статус от «Договор» и выше, ИЛИ голову
    рамочного — заполненный № договора при статусе wishes не достаточен."""
    sub = await _make_subsidy(db_session)
    p = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=20, status="wishes",
        contract_number="ДОГ-20", contract_id=None, planned_total_price=600000,
    )
    result = await contract_balances(db_session, sub.id)
    assert p.id not in result["by_purchase"]
    assert result["groups"] == []


@pytest.mark.asyncio
async def test_framework_head_wishes_status_excluded_even_with_max_amount(db_session):
    """Владелец 09.10.2026, прод ФАДМ 2026_2, 2-й заход — РЕЕ-2026-03218
    (ООО «АДС-АВТО», 600 000, статус 'wishes' «Желания сотрудников», договор
    не заключён) попадала в contract_balances/реестр, потому что голова
    рамочного раньше проходила предикат при ЛЮБОМ статусе. Теперь голова
    требует ТОТ ЖЕ статус-пол (contracted/ordered/delivered/paid), что и
    любая другая закупка."""
    sub = await _make_subsidy(db_session)
    contract = await _make_contract(db_session, max_amount=600000)
    head = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=218, status="wishes",
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        contract_number=contract.number,
    )
    result = await contract_balances(db_session, sub.id)
    assert head.id not in result["by_purchase"]
    assert result["groups"] == []


@pytest.mark.asyncio
async def test_framework_head_without_orders_treated_as_single(db_session):
    """Владелец 09.10.2026, прод ФАДМ 2026_2, 3-й заход — РЕЕ-2026-03110:
    purchase_contract_type='framework_cumulative', parent_purchase_id NULL,
    status='paid', 3500 ₽, но заявок под ней нет (формальная "голова" без
    заявок) — должна считаться разовой закупкой: contract_sum=ordered=3500,
    remaining=0 (не пустой факт головы без орденов)."""
    sub = await _make_subsidy(db_session)
    p = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=3110, status="paid",
        purchase_contract_type="framework_cumulative", contract_id=None,
        contract_number="ДОГ-1168", planned_total_price=3500,
    )
    result = await contract_balances(db_session, sub.id)
    entry = result["by_purchase"][p.id]
    assert entry["contract_sum"] == pytest.approx(3500.0)
    assert entry["ordered"] == pytest.approx(3500.0)
    assert entry["remaining"] == 0.0
