# -*- coding: utf-8 -*-
"""scripts/fadm_sheet_load/sheet_v2_enrich.py — пересборка «ФАДМ 2026_2»,
шаги 2-4 плана sleepy-fluttering-walrus.md (15.10.2026).

find_pairs/match_category_by_path/build_purchase_key — чистые функции без БД.
transfer_pair/move_purchase_to_subsidy/transfer_paid_confirmation трогают
реальную локальную dev-БД (как и tests/test_fadm_restore_items.py — scripts/
не смонтирован через conftest.db_session) — очистка руками в finally.
"""
from decimal import Decimal

import pytest

from scripts.fadm_sheet_load.feo_path_resolve import CategoryNode, FeoTree
from scripts.fadm_sheet_load.sheet_v2_enrich import (
    PurchaseKey,
    find_pairs,
    match_category_by_path,
)


# ---------------------------------------------------------------------------
# find_pairs — чистая логика сопоставления (без БД)
# ---------------------------------------------------------------------------
def _key(pid, inn, supplier, amount):
    return PurchaseKey(purchase_id=pid, registry_number=f"REG-{pid}", inn=inn, supplier_key=supplier, amount=Decimal(amount))


def test_find_pairs_exact_match_one_to_one():
    listed = [_key(1, "7705513090", "contractor:10", "1000.00")]
    source = [_key(101, "7705513090", "contractor:10", "1000.00")]
    result = find_pairs(listed, source)
    assert len(result.pairs) == 1
    assert result.pairs[0].listed_purchase_id == 1
    assert result.pairs[0].source_purchase_id == 101
    assert result.ambiguous == []
    assert result.unmatched_source_ids == []


def test_find_pairs_amount_mismatch_is_not_a_pair():
    listed = [_key(1, "7705513090", "contractor:10", "1000.00")]
    source = [_key(101, "7705513090", "contractor:10", "1000.01")]
    result = find_pairs(listed, source)
    assert result.pairs == []
    assert result.unmatched_source_ids == [101]


def test_find_pairs_ambiguous_two_candidates_not_merged():
    listed = [_key(1, "7705513090", "contractor:10", "1000.00")]
    source = [
        _key(101, "7705513090", "contractor:10", "1000.00"),
        _key(102, "7705513090", "contractor:10", "1000.00"),
    ]
    result = find_pairs(listed, source)
    assert result.pairs == []
    assert len(result.ambiguous) == 1
    assert result.ambiguous[0].listed_purchase_id == 1
    assert sorted(result.ambiguous[0].candidate_source_ids) == [101, 102]
    # Найдено прогоном на 7320 (15.10.2026): кандидаты неоднозначной пары
    # НЕ считаются "без пары" и НЕ попадают в unmatched_source_ids — иначе
    # шаг C молча переносит их как превышение, хотя один из них МОЖЕТ быть
    # настоящей парой (владелец должен решить сам, run_enrich их не трогает
    # вовсе — ни merge, ни перенос).
    assert 101 not in result.unmatched_source_ids and 102 not in result.unmatched_source_ids


def test_find_pairs_advance_matches_by_employee_not_inn():
    # авансовые: inn пустой у обеих сторон, "поставщик" = сотрудник-получатель
    listed = [_key(1, "", "employee:42", "500.00")]
    source = [
        _key(101, "", "employee:42", "500.00"),
        _key(102, "", "employee:43", "500.00"),  # другой сотрудник — не пара
    ]
    result = find_pairs(listed, source)
    assert len(result.pairs) == 1
    assert result.pairs[0].source_purchase_id == 101
    assert result.unmatched_source_ids == [102]


def test_find_pairs_each_source_used_at_most_once():
    # два листа с одинаковым ключом, один источник-кандидат — пара только одна,
    # второй лист остаётся без пары (unmatched_source не включает уже занятых)
    listed = [_key(1, "inn", "contractor:5", "100"), _key(2, "inn", "contractor:5", "100")]
    source = [_key(101, "inn", "contractor:5", "100")]
    result = find_pairs(listed, source)
    assert len(result.pairs) == 1
    assert result.unmatched_source_ids == []


# ---------------------------------------------------------------------------
# match_category_by_path — чистая логика (переиспользует names_match/
# normalize_feo_name, тестируется через собранные вручную деревья)
# ---------------------------------------------------------------------------
def _tree(nodes):
    return FeoTree([CategoryNode(id=n[0], parent_id=n[1], name=n[2], level=n[3]) for n in nodes])


def test_match_category_by_path_full_match():
    source = _tree([
        (1, None, "Форменная одежда", 1),
        (2, 1, "Головные уборы", 2),
    ])
    target = _tree([
        (10, None, "Форменная одежда", 1),
        (11, 10, "Головные уборы", 2),
        (12, 10, "Обувь", 2),
    ])
    assert match_category_by_path(source, target, 2) == 11


def test_match_category_by_path_no_match_anywhere_returns_none():
    source = _tree([(1, None, "Совсем другое направление", 1)])
    target = _tree([(10, None, "Форменная одежда", 1)])
    assert match_category_by_path(source, target, 1) is None


def test_match_category_by_path_root_matches_but_child_does_not_returns_none():
    # владелец: "нет совпадения -> «Не определена»" — частичный путь (только
    # корень совпал) НЕ считается совпадением, функция обязана вернуть None
    # целиком, а не id найденного корня.
    source = _tree([
        (1, None, "Форменная одежда", 1),
        (2, 1, "Нет такой категории у получателя", 2),
    ])
    target = _tree([
        (10, None, "Форменная одежда", 1),
        (11, 10, "Головные уборы", 2),
    ])
    assert match_category_by_path(source, target, 2) is None


def test_match_category_by_path_none_category_id_returns_none():
    target = _tree([(10, None, "X", 1)])
    source = _tree([(1, None, "Y", 1)])
    assert match_category_by_path(source, target, None) is None


# ---------------------------------------------------------------------------
# Интеграционные тесты на локальной БД (НЕ на проде, см. app.config для
# проверки — тот же приём, что test_fadm_restore_items.py).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transfer_pair_moves_executor_items_and_stops_source():
    from sqlalchemy import delete, select

    from app.database import async_session
    from app.models.feo_category import FeoCategory
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseEvent, PurchaseMember
    from app.models.purchase_item import PurchaseItem
    from app.models.subsidy import Subsidy
    from app.models.user import User
    from scripts.fadm_sheet_load.sheet_v2_enrich import pair_already_transferred, transfer_pair

    created_subsidy_ids = []
    created_user_ids = []
    try:
        async with async_session() as db:
            src = Subsidy(name="test_enrich_src", year=2026)
            dst = Subsidy(name="test_enrich_dst", year=2026)
            db.add_all([src, dst])
            await db.flush()
            created_subsidy_ids = [src.id, dst.id]

            executor = User(username="test_enrich_exec", password_hash="x", role="employee")
            member_user = User(username="test_enrich_member", password_hash="x", role="employee")
            db.add_all([executor, member_user])
            await db.flush()
            created_user_ids = [executor.id, member_user.id]

            cat = FeoCategory(subsidy_id=dst.id, name="cat", level=1)
            db.add(cat)
            await db.flush()

            # status ДО 'contracted' (STATUS_ORDER) — иначе can_stop_purchase
            # (граница той же, что и штатная кнопка «Остановить») откажет.
            old = Purchase(subsidy_id=src.id, status="work_in_progress", registry_number="OLD-1",
                            assigned_user_id=executor.id)
            new = Purchase(subsidy_id=dst.id, status="work_in_progress", registry_number="NEW-1")
            db.add_all([old, new])
            await db.flush()

            db.add(PurchaseMember(purchase_id=old.id, user_id=member_user.id, role="viewer"))
            for amt in (Decimal("60.00"), Decimal("40.00")):
                db.add(PurchaseItem(purchase_id=old.id, item_name="old item", quantity=Decimal("1"),
                                     total_price=amt, unit_price=amt, item_type="товар"))
            db.add(PurchaseItem(purchase_id=new.id, item_name="агрегат", quantity=Decimal("1"),
                                 total_price=Decimal("100.00"), unit_price=Decimal("100.00"),
                                 item_type="услуга", feo_category_id=cat.id))
            await db.commit()

        async with async_session() as db:
            old = (await db.execute(select(Purchase).where(Purchase.registry_number == "OLD-1"))).scalars().one()
            new = (await db.execute(select(Purchase).where(Purchase.registry_number == "NEW-1"))).scalars().one()
            assert not await pair_already_transferred(db, new.id)
            result = await transfer_pair(db, old, new)
            await db.commit()

        assert result.members_added == 1
        assert result.items_transferred is True
        assert result.stopped is True

        async with async_session() as db:
            old = await db.get(Purchase, old.id)
            new = await db.get(Purchase, new.id)
            assert new.assigned_user_id == executor.id
            assert old.stopped_at is not None
            assert "ФАДМ 2026_2" in (old.stopped_reason or "")

            new_items = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == new.id))).scalars().all()
            assert len(new_items) == 2
            assert all(it.item_type == "услуга" for it in new_items)  # тип взят у получателя, не у источника
            assert all(it.feo_category_id == cat.id for it in new_items)
            assert sum((it.total_price for it in new_items), Decimal("0")) == Decimal("100.00")

            members = (await db.execute(select(PurchaseMember).where(PurchaseMember.purchase_id == new.id))).scalars().all()
            assert any(m.user_id == member_user.id for m in members)

            # идемпотентность: второй прогон не трогает уже перенесённую пару
            assert await pair_already_transferred(db, new.id)
    finally:
        async with async_session() as db:
            await db.execute(delete(PurchaseEvent).where(
                PurchaseEvent.purchase_id.in_(select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            ))
            await db.execute(delete(PurchaseMember).where(
                PurchaseMember.purchase_id.in_(select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            ))
            await db.execute(delete(PurchaseItem).where(
                PurchaseItem.purchase_id.in_(select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            ))
            await db.execute(delete(Purchase).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(FeoCategory).where(FeoCategory.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(Subsidy).where(Subsidy.id.in_(created_subsidy_ids)))
            if created_user_ids:
                await db.execute(delete(User).where(User.id.in_(created_user_ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_move_purchase_to_subsidy_sets_category_by_path_and_marks_na_on_miss():
    from sqlalchemy import delete, select

    from app.database import async_session
    from app.models.feo_category import FeoCategory
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseEvent
    from app.models.subsidy import Subsidy
    from scripts.fadm_sheet_load.feo_path_resolve import load_feo_tree
    from scripts.fadm_sheet_load.sheet_v2_enrich import find_na_category_id, move_purchase_to_subsidy

    created_subsidy_ids = []
    try:
        async with async_session() as db:
            src = Subsidy(name="test_enrich_move_src", year=2026, status="approved")
            dst = Subsidy(name="test_enrich_move_dst", year=2026, status="approved")
            db.add_all([src, dst])
            await db.flush()
            created_subsidy_ids = [src.id, dst.id]

            src_root = FeoCategory(subsidy_id=src.id, name="Форменная одежда", level=1)
            db.add(src_root)
            await db.flush()
            src_child = FeoCategory(subsidy_id=src.id, name="Головные уборы", level=2, parent_id=src_root.id)
            src_unmatched_root = FeoCategory(subsidy_id=src.id, name="Совсем другое", level=1)
            db.add_all([src_child, src_unmatched_root])

            dst_root = FeoCategory(subsidy_id=dst.id, name="Форменная одежда", level=1)
            dst_na = FeoCategory(subsidy_id=dst.id, name="Не определена", level=1)
            db.add_all([dst_root, dst_na])
            await db.flush()
            dst_child = FeoCategory(subsidy_id=dst.id, name="Головные уборы", level=2, parent_id=dst_root.id)
            db.add(dst_child)
            await db.flush()

            p_match = Purchase(subsidy_id=src.id, status="paid", registry_number="MOVE-1", feo_category_id=src_child.id)
            p_miss = Purchase(subsidy_id=src.id, status="paid", registry_number="MOVE-2", feo_category_id=src_unmatched_root.id)
            db.add_all([p_match, p_miss])
            await db.commit()
            src_child_id, dst_child_id, dst_na_id = src_child.id, dst_child.id, dst_na.id

        async with async_session() as db:
            source_tree = await load_feo_tree(db, src.id)
            target_tree = await load_feo_tree(db, dst.id)
            na_id = await find_na_category_id(db, dst.id)
            assert na_id == dst_na_id

            p1 = await db.get(Purchase, p_match.id)
            r1 = await move_purchase_to_subsidy(
                db, p1, target_subsidy_id=dst.id, source_tree=source_tree, target_tree=target_tree, na_category_id=na_id,
            )
            p2 = await db.get(Purchase, p_miss.id)
            r2 = await move_purchase_to_subsidy(
                db, p2, target_subsidy_id=dst.id, source_tree=source_tree, target_tree=target_tree, na_category_id=na_id,
            )
            await db.commit()

        assert r1.moved is True and r1.category_matched is True
        assert r2.moved is True and r2.category_matched is False

        async with async_session() as db:
            p1 = await db.get(Purchase, p_match.id)
            p2 = await db.get(Purchase, p_miss.id)
            assert p1.subsidy_id == dst.id and p1.feo_category_id == dst_child_id
            assert p2.subsidy_id == dst.id and p2.feo_category_id == dst_na_id

            events = (await db.execute(
                select(PurchaseEvent).where(PurchaseEvent.purchase_id == p1.id, PurchaseEvent.event_type == "fadm_enrich_moved_no_pair")
            )).scalars().all()
            assert len(events) == 1

            # идемпотентность: уже перенесённая закупка не трогается повторно
            r1_again = await move_purchase_to_subsidy(
                db, p1, target_subsidy_id=dst.id, source_tree=source_tree, target_tree=target_tree, na_category_id=na_id,
            )
            assert r1_again.moved is False
    finally:
        async with async_session() as db:
            await db.execute(delete(PurchaseEvent).where(
                PurchaseEvent.purchase_id.in_(select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            ))
            await db.execute(delete(Purchase).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(FeoCategory).where(FeoCategory.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(Subsidy).where(Subsidy.id.in_(created_subsidy_ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_transfer_paid_confirmation_walks_to_paid_and_records_old_user_and_date():
    from datetime import datetime, timezone
    from sqlalchemy import delete, select

    from app.database import async_session
    from app.models.purchase import Purchase
    from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
    from app.models.subsidy import Subsidy
    from app.models.user import User
    from scripts.fadm_sheet_load.sheet_v2_enrich import ConfirmationSnapshotEntry, transfer_paid_confirmation

    created_subsidy_ids = []
    created_user_ids = []
    try:
        async with async_session() as db:
            dst = Subsidy(name="test_enrich_confirm_dst", year=2026, status="approved")
            db.add(dst)
            await db.flush()
            created_subsidy_ids = [dst.id]

            old_confirmer = User(username="test_enrich_confirmer", password_hash="x", role="account_owner")
            db.add(old_confirmer)
            await db.flush()
            created_user_ids = [old_confirmer.id]

            # delivered с закрывающими документами не гарантирован в этом тесте
            # (гейты _walk_to_paid могут заблокировать на реальных данных) —
            # поэтому проверяем УЖЕ paid закупку: подтверждение пишется без
            # перехода статуса, что и есть ветка "уже оплачена" в коде.
            new_p = Purchase(subsidy_id=dst.id, status="paid", registry_number="CONF-1")
            db.add(new_p)
            await db.commit()
            new_p_id = new_p.id

        old_dt = datetime(2026, 8, 10, tzinfo=timezone.utc)
        entry = ConfirmationSnapshotEntry(
            inn="7705513090", purchase_no="12", order_no="3",
            user_id=old_confirmer.id, confirmed_at=old_dt, bank_payment_id=None, amount=Decimal("500.00"),
        )

        async with async_session() as db:
            new_p = await db.get(Purchase, new_p_id)
            result = await transfer_paid_confirmation(db, entry, new_p)
            await db.commit()

        assert result.transferred is True

        async with async_session() as db:
            conf = (await db.execute(
                select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == new_p_id)
            )).scalars().one()
            assert conf.status == "confirmed"
            assert conf.decided_by == old_confirmer.id
            assert conf.decided_at == old_dt
            assert conf.amount_confirmed == Decimal("500.00")

            # идемпотентность: повторный перенос той же пары не плодит вторую запись
            new_p = await db.get(Purchase, new_p_id)
            result_again = await transfer_paid_confirmation(db, entry, new_p)
            assert result_again.transferred is False
    finally:
        async with async_session() as db:
            await db.execute(delete(PurchasePaidConfirmation).where(
                PurchasePaidConfirmation.purchase_id.in_(
                    select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids))
                )
            ))
            await db.execute(delete(Purchase).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(Subsidy).where(Subsidy.id.in_(created_subsidy_ids)))
            if created_user_ids:
                await db.execute(delete(User).where(User.id.in_(created_user_ids)))
            await db.commit()
