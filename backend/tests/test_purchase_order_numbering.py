"""assign_procurement_order_number_if_missing (владелец, 28.10.2026): номер
приказа о закупке — ручной ввод приоритетнее авто; авто-номер
последовательный в пределах организации и года."""
import uuid
from datetime import date

import pytest

from app.models.purchase import Purchase
from app.services.purchase_order_numbering import assign_procurement_order_number_if_missing


async def _make_subsidy(db_session, org_id=None, **kw):
    from app.models.subsidy import Subsidy
    defaults = dict(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=1_000_000,
        require_planned_dates=False, status="approved", org_id=org_id,
    )
    defaults.update(kw)
    s = Subsidy(**defaults)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_purchase(db_session, **kwargs) -> Purchase:
    defaults = dict(status="wishes")
    defaults.update(kwargs)
    p = Purchase(**defaults)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _make_org(db_session, **kw):
    from app.models.organization import Organization
    defaults = dict(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    defaults.update(kw)
    o = Organization(**defaults)
    db_session.add(o)
    await db_session.commit()
    await db_session.refresh(o)
    return o


@pytest.mark.asyncio
async def test_first_purchase_in_org_year_gets_number_one(db_session):
    org = await _make_org(db_session)
    sub = await _make_subsidy(db_session, org_id=org.id)
    p = await _make_purchase(db_session, subsidy_id=sub.id, purchase_number=1)

    await assign_procurement_order_number_if_missing(db_session, p)

    assert p.procurement_order_number == "1"
    assert p.procurement_order_date == date.today()


@pytest.mark.asyncio
async def test_sequential_within_same_org_and_year(db_session):
    org = await _make_org(db_session)
    sub = await _make_subsidy(db_session, org_id=org.id)
    p1 = await _make_purchase(db_session, subsidy_id=sub.id, purchase_number=1)
    p2 = await _make_purchase(db_session, subsidy_id=sub.id, purchase_number=2)

    await assign_procurement_order_number_if_missing(db_session, p1)
    await assign_procurement_order_number_if_missing(db_session, p2)

    assert p1.procurement_order_number == "1"
    assert p2.procurement_order_number == "2"


@pytest.mark.asyncio
async def test_other_org_starts_its_own_sequence(db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    sub_a = await _make_subsidy(db_session, org_id=org_a.id)
    sub_b = await _make_subsidy(db_session, org_id=org_b.id)
    p_a = await _make_purchase(db_session, subsidy_id=sub_a.id, purchase_number=1)
    p_b = await _make_purchase(db_session, subsidy_id=sub_b.id, purchase_number=1)

    await assign_procurement_order_number_if_missing(db_session, p_a)
    await assign_procurement_order_number_if_missing(db_session, p_b)

    assert p_a.procurement_order_number == "1"
    assert p_b.procurement_order_number == "1"  # своя организация — своя последовательность


@pytest.mark.asyncio
async def test_manual_number_is_never_overwritten(db_session):
    org = await _make_org(db_session)
    sub = await _make_subsidy(db_session, org_id=org.id)
    p = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=1,
        procurement_order_number="РУЧНОЙ-7",
    )

    await assign_procurement_order_number_if_missing(db_session, p)

    assert p.procurement_order_number == "РУЧНОЙ-7"
    assert p.procurement_order_date is None  # дата не подставляется, номер ручной


@pytest.mark.asyncio
async def test_manual_date_without_number_still_gets_auto_number_keeps_date(db_session):
    org = await _make_org(db_session)
    sub = await _make_subsidy(db_session, org_id=org.id)
    manual_date = date(2025, 3, 1)
    p = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=1,
        procurement_order_date=manual_date,
    )

    await assign_procurement_order_number_if_missing(db_session, p)

    assert p.procurement_order_number == "1"
    assert p.procurement_order_date == manual_date
