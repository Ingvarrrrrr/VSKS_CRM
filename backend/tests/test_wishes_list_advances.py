# -*- coding: utf-8 -*-
"""Задача владельца (16.10.2026, «Авансовые видны в Заявках»): авансовый отчёт
(Purchase.purchase_method='advance') без заявки-компаньона (wish_id IS NULL) —
28 таких у субсидии «ФАДМ 2026_3», созданных загрузчиком, не находились в
«Заявках» вовсе. Покрывает app/services/standalone_advances.py и GET
/api/wishes/standalone-advances (app/routers/wish_lists.py).
"""
import pytest
from sqlalchemy import select

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.standalone_advances import list_standalone_advances


async def _make_subsidy(db_session, test_org):
    s = Subsidy(name="ФАДМ 2026_3 (тест)", year=2026, org_id=test_org.id)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest.mark.asyncio
async def test_advance_without_wish_is_listed_and_found_by_registry_number(
    db_session, test_org, test_user, make_purchase_with_items,
):
    subsidy = await _make_subsidy(db_session, test_org)
    purchase = await make_purchase_with_items(status="wishes", items_count=1)
    purchase.purchase_method = "advance"
    purchase.wish_id = None
    purchase.subsidy_id = subsidy.id
    purchase.assigned_user_id = test_user.id
    purchase.reimbursement_user_id = test_user.id
    purchase.registry_number = "РЕЕ-2026-04233"
    db_session.add(purchase)
    await db_session.commit()

    rows = await list_standalone_advances(db_session, test_user)
    assert any(r.id == purchase.id for r in rows)

    found = await list_standalone_advances(db_session, test_user, search="04233")
    assert [r.id for r in found] == [purchase.id]

    not_found = await list_standalone_advances(db_session, test_user, search="99999")
    assert not_found == []


@pytest.mark.asyncio
async def test_advance_with_wish_is_not_duplicated(
    db_session, test_org, test_user, make_purchase_with_items,
):
    """Авансовый с уже привязанной заявкой (обычный путь создания — см.
    app/services/advance_companion_wish.py) не должен попадать в этот список:
    он УЖЕ виден в «Заявках» через Purchase.wish_id, второй раз показывать не надо."""
    from app.models.wish import Wish

    subsidy = await _make_subsidy(db_session, test_org)
    purchase = await make_purchase_with_items(status="wishes", items_count=1)
    purchase.purchase_method = "advance"
    purchase.subsidy_id = subsidy.id
    purchase.assigned_user_id = test_user.id
    purchase.reimbursement_user_id = test_user.id
    purchase.registry_number = "РЕЕ-2026-04999"

    wish = Wish(
        title="Авансовый отчёт (компаньон)",
        org_id=test_org.id,
        created_by=test_user.id,
        status="draft",
        source="advance_report",
    )
    db_session.add(wish)
    await db_session.flush()
    purchase.wish_id = wish.id
    db_session.add(purchase)
    await db_session.commit()

    rows = await list_standalone_advances(db_session, test_user)
    assert all(r.id != purchase.id for r in rows)


@pytest.mark.asyncio
async def test_mine_only_filters_by_reimbursement_or_assigned_user(
    db_session, test_org, test_user, make_user, make_purchase_with_items,
):
    subsidy = await _make_subsidy(db_session, test_org)
    other_user = await make_user(role="employee", org_id=test_org.id)

    mine = await make_purchase_with_items(status="wishes", items_count=1)
    mine.purchase_method = "advance"
    mine.subsidy_id = subsidy.id
    mine.assigned_user_id = test_user.id
    mine.reimbursement_user_id = test_user.id
    mine.registry_number = "РЕЕ-2026-05001"

    theirs = await make_purchase_with_items(status="wishes", items_count=1)
    theirs.purchase_method = "advance"
    theirs.subsidy_id = subsidy.id
    theirs.assigned_user_id = other_user.id
    theirs.reimbursement_user_id = other_user.id
    theirs.registry_number = "РЕЕ-2026-05002"
    db_session.add_all([mine, theirs])
    await db_session.commit()

    rows = await list_standalone_advances(db_session, test_user, mine_only=True)
    ids = {r.id for r in rows}
    assert mine.id in ids
    assert theirs.id not in ids
