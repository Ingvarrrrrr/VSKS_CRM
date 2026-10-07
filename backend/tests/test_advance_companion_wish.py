# -*- coding: utf-8 -*-
"""Бэкфилл заявок-компаньонов для старых авансовых отчётов без заявки
(владелец, 2026-10-07): 44 закупки purchase_method='advance' на проде без
Wish-компаньона (заведены импортом/до 16.09). Покрывает:

  1. app/services/advance_companion_wish.py::create_advance_companion_wish —
     единая функция, которой звонит и роутер (создание), и бэкфилл-скрипт.
  2. backend/scripts/backfill_advance_wishes.py::run_backfill — пропуск уже
     привязанных закупок, статус 'draft'/'converted' по статусу закупки.
  3. do_rollback — откат возвращает как было.
"""
import json

import pytest
from sqlalchemy import select

from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.advance_companion_wish import create_advance_companion_wish
from scripts.backfill_advance_wishes import (
    companion_status_for_purchase,
    run_backfill,
    do_rollback,
)


@pytest.mark.asyncio
async def test_create_advance_companion_wish_builds_wish_and_links(
    db_session, test_org, test_user, make_purchase_with_items,
):
    purchase = await make_purchase_with_items(status="wishes", items_count=2)
    purchase.purchase_method = "advance"
    purchase.registry_number = "РЕЕ-TEST-0001"
    db_session.add(purchase)
    await db_session.flush()

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id).order_by(PurchaseItem.id)
    )).scalars().all()
    assert len(items) == 2

    wish = await create_advance_companion_wish(
        db_session, purchase, items,
        created_by=test_user.id, org_id=test_org.id, status="draft",
        creator=test_user,
    )
    await db_session.commit()
    await db_session.refresh(purchase)

    assert wish.source == "advance_report"
    assert wish.status == "draft"
    assert "РЕЕ-TEST-0001" in wish.title
    assert purchase.wish_id == wish.id

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish.id)
    )).scalars().all()
    assert len(wish_items) == 2
    assert {wi.item_name for wi in wish_items} == {i.item_name for i in items}

    await db_session.refresh(items[0])
    await db_session.refresh(items[1])
    assert items[0].wish_item_id is not None
    assert items[1].wish_item_id is not None


def test_companion_status_for_purchase_rules():
    assert companion_status_for_purchase("wishes") == "draft"
    assert companion_status_for_purchase("paid") == "converted"
    assert companion_status_for_purchase("work_in_progress") == "converted"


@pytest.mark.asyncio
async def test_backfill_skips_purchase_with_existing_wish_id(
    db_session, test_org, test_user, make_purchase_with_items,
):
    purchase = await make_purchase_with_items(status="wishes", items_count=1)
    purchase.purchase_method = "advance"
    purchase.registry_number = "РЕЕ-TEST-0002"
    purchase.reimbursement_user_id = test_user.id

    other_wish = Wish(source="advance_report", status="draft", title="уже есть", created_by=test_user.id, org_id=test_org.id)
    db_session.add(other_wish)
    await db_session.flush()
    purchase.wish_id = other_wish.id
    db_session.add(purchase)
    await db_session.commit()

    rows, rollback_entries, created, skipped = await run_backfill(db_session, purchase_ids=[purchase.id], apply=True)

    # wish_id IS NOT NULL → не попадает в кандидаты (фильтр _candidates).
    assert rows == []
    assert created == 0
    assert skipped == 0
    await db_session.rollback()


@pytest.mark.asyncio
async def test_backfill_creates_draft_for_wishes_status_and_converted_for_paid(
    db_session, test_org, test_user, make_purchase_with_items,
):
    p_draft = await make_purchase_with_items(status="wishes", items_count=1)
    p_draft.purchase_method = "advance"
    p_draft.registry_number = "РЕЕ-TEST-0003"
    p_draft.reimbursement_user_id = test_user.id

    p_paid = await make_purchase_with_items(status="paid", items_count=1)
    p_paid.purchase_method = "advance"
    p_paid.registry_number = "РЕЕ-TEST-0004"
    p_paid.assigned_user_id = test_user.id

    db_session.add_all([p_draft, p_paid])
    await db_session.commit()

    rows, rollback_entries, created, skipped = await run_backfill(
        db_session, purchase_ids=[p_draft.id, p_paid.id], apply=True,
    )
    await db_session.commit()

    assert created == 2
    assert skipped == 0
    by_id = {r["purchase_id"]: r for r in rows}
    assert by_id[p_draft.id]["wish_status"] == "draft"
    assert by_id[p_paid.id]["wish_status"] == "converted"

    await db_session.refresh(p_draft)
    await db_session.refresh(p_paid)
    assert p_draft.wish_id is not None
    assert p_paid.wish_id is not None

    return rollback_entries


@pytest.mark.asyncio
async def test_backfill_skips_purchase_without_any_creator_candidate(
    db_session, test_org, make_purchase_with_items,
):
    purchase = await make_purchase_with_items(status="wishes", items_count=1)
    purchase.purchase_method = "advance"
    purchase.registry_number = "РЕЕ-TEST-0005"
    # reimbursement_user_id/assigned_user_id/service_note_by все пустые
    db_session.add(purchase)
    await db_session.commit()

    rows, rollback_entries, created, skipped = await run_backfill(db_session, purchase_ids=[purchase.id], apply=True)

    assert created == 0
    assert skipped == 1
    assert "skip" in rows[0]
    await db_session.rollback()


@pytest.mark.asyncio
async def test_rollback_restores_previous_state(
    db_session, test_org, test_user, make_purchase_with_items, tmp_path,
):
    purchase = await make_purchase_with_items(status="wishes", items_count=2)
    purchase.purchase_method = "advance"
    purchase.registry_number = "РЕЕ-TEST-0006"
    purchase.reimbursement_user_id = test_user.id
    db_session.add(purchase)
    await db_session.commit()

    rows, rollback_entries, created, skipped = await run_backfill(db_session, purchase_ids=[purchase.id], apply=True)
    await db_session.commit()
    assert created == 1
    wish_id = rollback_entries[0]["wish_id"]

    payload_path = tmp_path / "rollback.json"
    payload_path.write_text(json.dumps(rollback_entries, ensure_ascii=False), encoding="utf-8")

    await do_rollback(db_session, str(payload_path))
    await db_session.commit()

    assert await db_session.get(Wish, wish_id) is None
    await db_session.refresh(purchase)
    assert purchase.wish_id is None
    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )).scalars().all()
    assert all(i.wish_item_id is None for i in items)
