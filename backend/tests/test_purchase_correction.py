# -*- coding: utf-8 -*-
"""Офлайн юнит-тесты для очистки/сохранения auto_created-позиций при откате,
права purchase.correct, контроля превышения сумм и возврата в черновик заявки."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.sql.dml import Update as _SqlUpdate

from app.models.event import Event
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish


def test_replace_auto_planned_items_on_draft_wish_moves_to_new_category():
    """При смене категории ФЭО даже в черновике старая auto_created позиция
    отвязывается и деактивируется, а в новой категории создаётся новая."""
    from app.services.feo_effective_category import replace_wish_auto_planned_items_on_category_change
    from app.services import feo_history, plan_autoassign

    old_fpi = SimpleNamespace(id=501, feo_category_id=10, auto_created=True, is_active=True)
    new_fpi = SimpleNamespace(id=502, feo_category_id=20, auto_created=True, is_active=True)
    wi = SimpleNamespace(
        id=1, wish_id=264, from_plan=False, item_name="Ноутбук",
        feo_category_id=20, feo_planned_item_id=501, planned_item=old_fpi, over_plan=False,
    )
    wish = SimpleNamespace(
        id=264, status="draft", feo_per_item=False, feo_category_id=20, items=[wi],
    )

    class _EmptyRes:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])
        def all(self):
            return []

    class _DraftFakeDB:
        async def execute(self, stmt):
            return _EmptyRes()

        async def get(self, model, id_):
            if model is FeoPlannedItem:
                return {501: old_fpi, 502: new_fpi}.get(id_)
            return None

        async def flush(self):
            return None

    called_auto = []
    orig_auto = plan_autoassign.auto_assign_planned_items
    orig_record = feo_history.record_updated

    async def _fake_auto(items, fallback_cat, db, **kwargs):
        called_auto.append((items, fallback_cat))
        for it in items:
            it.feo_planned_item_id = 502

    async def _fake_record(*args, **kwargs):
        return None

    plan_autoassign.auto_assign_planned_items = _fake_auto
    feo_history.record_updated = _fake_record
    try:
        asyncio.run(replace_wish_auto_planned_items_on_category_change(
            _DraftFakeDB(), wish, {1: (10, 501)},
        ))
    finally:
        plan_autoassign.auto_assign_planned_items = orig_auto
        feo_history.record_updated = orig_record

    assert old_fpi.is_active is False
    assert len(called_auto) == 1
    assert wi.feo_planned_item_id == 502
    assert wi.planned_item is new_fpi


def test_cleanup_wish_auto_planned_items_detaches_and_deactivates():
    """cleanup_wish_auto_planned_items (stop_wish) отвязывает auto_created (from_plan=False)
    и деактивирует осиротевшие FeoPlannedItem, не трогая ручные привязки."""
    from app.services import feo_history, plan_autoassign

    fpi_auto = SimpleNamespace(id=701, auto_created=True, is_active=True, feo_category_id=11)
    fpi_manual = SimpleNamespace(id=702, auto_created=False, is_active=True, feo_category_id=11)

    wi_auto = SimpleNamespace(id=11, from_plan=False, feo_planned_item_id=701, over_plan=False, planned_item=fpi_auto)
    wi_manual = SimpleNamespace(id=12, from_plan=True, feo_planned_item_id=701, over_plan=False, planned_item=fpi_auto)
    wi_human_plan = SimpleNamespace(id=13, from_plan=False, feo_planned_item_id=702, over_plan=False, planned_item=fpi_manual)

    p_wishes = SimpleNamespace(id=90, status="wishes", stopped_at=None)
    pi_auto = SimpleNamespace(id=31, wish_item_id=11, from_plan=False, feo_planned_item_id=701, over_plan=False)

    class _FakeRes:
        def __init__(self, rows):
            self._rows = rows
        def scalars(self):
            return SimpleNamespace(all=lambda: self._rows)
        def all(self):
            return self._rows

    class _CleanupDB:
        async def execute(self, stmt):
            text = str(stmt)
            if "FROM wish_items" in text and "JOIN wishes" not in text:
                return _FakeRes([wi_auto, wi_manual, wi_human_plan])
            if "FROM purchases" in text:
                return _FakeRes([p_wishes])
            if "FROM purchase_items" in text and "JOIN purchases" not in text:
                return _FakeRes([pi_auto])
            if "FROM feo_planned_items" in text:
                return _FakeRes([fpi_auto, fpi_manual])
            if "JOIN purchases" in text or "JOIN wishes" in text:
                return _FakeRes([])
            return _FakeRes([])

        async def flush(self):
            return None

    orig_record = feo_history.record_updated

    async def _noop_record(*args, **kwargs):
        return None

    feo_history.record_updated = _noop_record
    try:
        asyncio.run(plan_autoassign.cleanup_wish_auto_planned_items(_CleanupDB(), wish_id=264))
    finally:
        feo_history.record_updated = orig_record

    assert wi_auto.feo_planned_item_id is None
    assert pi_auto.feo_planned_item_id is None
    assert wi_manual.feo_planned_item_id == 701
    assert wi_human_plan.feo_planned_item_id == 702
    assert fpi_auto.is_active is False
    assert fpi_manual.is_active is True


def test_ensure_can_correct_respects_purchase_correct_permission():
    """Право purchase.correct управляет доступом к корректировке: при False -> 403, при True -> ok."""
    from app.services import purchase_correction_service as pcs

    p = SimpleNamespace(id=1, status="work_in_progress", subsidy_id=5)
    user = SimpleNamespace(id=7, role="manager")

    class _NoPermDB:
        async def get(self, model, id_):
            return SimpleNamespace(org_id=10)

    orig_vis = pcs.ensure_purchase_visible
    orig_key = pcs.has_org_key

    async def _ok_vis(*args, **kwargs):
        return None

    async def _deny_key(u, db, org_id, key, **kwargs):
        assert key == "purchase.correct"
        return False

    async def _allow_key(u, db, org_id, key, **kwargs):
        assert key == "purchase.correct"
        return True

    pcs.ensure_purchase_visible = _ok_vis
    pcs.has_org_key = _deny_key
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pcs.ensure_can_correct(p, user, _NoPermDB()))
        assert exc_info.value.status_code == 403

        pcs.has_org_key = _allow_key
        asyncio.run(pcs.ensure_can_correct(p, user, _NoPermDB()))
    finally:
        pcs.ensure_purchase_visible = orig_vis
        pcs.has_org_key = orig_key


def test_return_purchase_to_draft_wish_preserves_planned_items():
    """Возврат закупки в черновик заявки через Корректировку переводит закупку в 'wishes',
    заявку в 'draft' и НЕ очищает feo_planned_item_id позиций."""
    from app.services import purchase_correction_service as pcs, wish_distribution as wd

    wish = SimpleNamespace(id=264, status="converted", rejected_by=9, rejected_at=datetime.now(timezone.utc), rejection_reason="x")
    p = SimpleNamespace(id=500, registry_number="РЕЕ-2026-00500", status="work_in_progress", approval_status="pending", wish_id=264)
    user = SimpleNamespace(id=7, role="manager", org_id=1, full_name="Цыганов И.И.", username="tsyganov")
    wi = SimpleNamespace(id=1, feo_planned_item_id=777)
    pi = SimpleNamespace(id=2, wish_item_id=1, feo_planned_item_id=777)
    added_events = []

    class _RetDB:
        def __init__(self):
            self.committed = False
        async def get(self, model, id_):
            if model is Wish and id_ == 264:
                return wish
            return None
        def add(self, obj):
            added_events.append(obj)
        async def commit(self):
            self.committed = True

    orig_reset_pa = pcs.reset_purchase_approvals
    orig_reset_wa = wd._reset_approvals

    async def _noop(*args, **kwargs):
        return None

    pcs.reset_purchase_approvals = _noop
    wd._reset_approvals = _noop
    db = _RetDB()
    try:
        res = asyncio.run(pcs.return_purchase_to_draft_wish_core(p, "Пересмотреть суммы", db, user))
    finally:
        pcs.reset_purchase_approvals = orig_reset_pa
        wd._reset_approvals = orig_reset_wa

    assert db.committed is True
    assert res["wish_status"] == "draft"
    assert res["purchase_status"] == "wishes"
    assert p.status == "wishes"
    assert p.approval_status is None
    assert wish.status == "draft"
    assert wish.rejected_by is None
    assert wi.feo_planned_item_id == 777
    assert pi.feo_planned_item_id == 777
    assert len(added_events) == 1


def test_check_correction_excess_raises_409_and_rolls_back():
    """При превышении бюджета категории check_correction_excess откатывает транзакцию и отдаёт 409."""
    from app.services import purchase_correction_service as pcs, wish_distribution as wd

    p = SimpleNamespace(id=1, registry_number="РЕЕ-2026-00001", subsidy_id=5, wish_id=266, feo_category_id=20, feo_per_item=False)
    pi = SimpleNamespace(id=1, item_name="Товар", total_price=10000, feo_category_id=20, feo_planned_item_id=200)
    user = SimpleNamespace(id=7, role="manager")

    class _ExDB:
        def __init__(self):
            self.rolled_back = False
        async def rollback(self):
            self.rolled_back = True

    orig_ew = wd._collect_excess_warnings
    orig_tz = pcs.collect_tz_over_plan_violations
    orig_tp = pcs.collect_type_excess_violations

    async def _fake_ew(*args, **kwargs):
        return [{"category_id": 20, "category_name": "4.2. Спорт", "plan_after": 60000.0, "budget": 50000.0, "excess_amount": 10000.0}]

    async def _empty(*args, **kwargs):
        return []

    wd._collect_excess_warnings = _fake_ew
    pcs.collect_tz_over_plan_violations = _empty
    pcs.collect_type_excess_violations = _empty
    db = _ExDB()
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pcs.check_correction_excess(db, p, [pi], {20}, False, user))
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CORRECTION_CAUSES_EXCESS"
        assert exc_info.value.detail["wish_id"] == 266
        assert db.rolled_back is True
    finally:
        wd._collect_excess_warnings = orig_ew
        pcs.collect_tz_over_plan_violations = orig_tz
        pcs.collect_type_excess_violations = orig_tp


def test_purchase_correction_updates_category_event_and_history():
    """POST /correction меняет категорию ФЭО и мероприятие действующей закупки
    на стадии contracted без сброса статуса, отвязывает/деактивирует старую
    auto_created позицию, создаёт новую и отдаёт историю корректировок."""
    from app.routers import purchase_correction as pc
    from app.services import feo_history, purchase_correction_service as pcs

    cat_old = SimpleNamespace(
        id=10, parent_id=None, name="4.1. Просвещение", subsidy_id=5,
        planned_quantity=None, planned_amount=None,
    )
    cat_new = SimpleNamespace(
        id=20, parent_id=None, name="4.2. Спорт", subsidy_id=5,
        planned_quantity=None, planned_amount=None,
    )
    ev_old = SimpleNamespace(id=1, name="Слёт ВСКС", subsidy_id=5)
    ev_new = SimpleNamespace(id=2, name="Спартакиада", subsidy_id=5)
    fpi_old = SimpleNamespace(id=100, feo_category_id=10, name="Бумага А4", auto_created=True, is_active=True)

    purchase = SimpleNamespace(
        id=4894, registry_number="РЕЕ-2026-04894", status="contracted", approval_status="approved",
        subsidy_id=5, feo_category_id=10, feo_per_item=False, event_id=1, wish_id=266,
        assigned_user_id=7, service_note_to_user_id=None, service_note_by=None,
    )
    pi = SimpleNamespace(
        id=901, purchase_id=4894, wish_item_id=801, item_name="Бумага А4",
        quantity=2, unit="Штука", total_price=836, item_type="Товар",
        feo_category_id=10, feo_planned_item_id=100, from_plan=False, over_plan=False,
    )
    wish = SimpleNamespace(id=266, feo_category_id=10, feo_per_item=False, event_id=1)
    wi = SimpleNamespace(id=801, wish_id=266, feo_category_id=10, feo_planned_item_id=100, from_plan=False, over_plan=False)
    user = SimpleNamespace(id=7, role="manager", org_id=1, full_name="Цыганов И.И.", username="tsyganov")

    events_store: list[PurchaseEvent] = []
    fpi_store: dict[int, object] = {100: fpi_old}
    next_fpi_id = [200]

    class _Res:
        def __init__(self, rows):
            self._rows = rows
        def scalars(self):
            return SimpleNamespace(all=lambda: self._rows)
        def all(self):
            return self._rows
        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    class _FakeCorrectionDB:
        def __init__(self):
            self.committed = False

        async def get(self, model, id_):
            if model is Purchase and id_ == 4894:
                return purchase
            if model is FeoCategory:
                return {10: cat_old, 20: cat_new}.get(id_)
            if model is Event:
                return {1: ev_old, 2: ev_new}.get(id_)
            if model is FeoPlannedItem:
                return fpi_store.get(id_)
            if model is Wish and id_ == 266:
                return wish
            return None

        async def execute(self, stmt):
            if isinstance(stmt, _SqlUpdate):
                return _Res([])
            text = str(stmt)
            if "FROM purchase_items" in text and "JOIN purchases" not in text:
                return _Res([pi])
            if "FROM wish_items" in text and "JOIN wishes" not in text:
                return _Res([wi])
            if "FROM feo_categories" in text:
                return _Res([cat_old, cat_new])
            if "FROM feo_planned_items" in text:
                if text.startswith("SELECT feo_planned_items.id, feo_planned_items.name"):
                    return _Res([(f.id, f.name) for f in fpi_store.values()])
                return _Res([])
            if "FROM purchase_events" in text:
                return _Res(list(events_store))
            if "FROM users" in text:
                return _Res([(7, "Цыганов И.И.", "tsyganov")])
            return _Res([])

        def add(self, obj):
            if isinstance(obj, PurchaseEvent):
                obj.id = len(events_store) + 1
                obj.created_at = datetime(2026, 11, 16, 22, 55, tzinfo=timezone.utc)
                events_store.append(obj)
            elif getattr(obj, "name", None) and getattr(obj, "feo_category_id", None):
                obj.id = next_fpi_id[0]
                next_fpi_id[0] += 1
                fpi_store[obj.id] = obj

        async def flush(self):
            return None

        async def commit(self):
            self.committed = True

    orig_visible = pcs.ensure_purchase_visible
    orig_key = pcs.has_org_key
    orig_payroll = pc.assert_no_goods_in_payroll
    orig_excess = pc.check_correction_excess
    orig_rec_upd = feo_history.record_updated
    orig_rec_crt = feo_history.record_created

    async def _noop(*args, **kwargs):
        return None

    async def _ok_key(*args, **kwargs):
        return True

    async def _no_excess(*args, **kwargs):
        return [], [], []

    pcs.ensure_purchase_visible = _noop
    pcs.has_org_key = _ok_key
    pc.assert_no_goods_in_payroll = _noop
    pc.check_correction_excess = _no_excess
    feo_history.record_updated = _noop
    feo_history.record_created = _noop
    db = _FakeCorrectionDB()
    try:
        body = pc.PurchaseCorrectionIn(
            feo_category_id=20,
            feo_per_item=False,
            event_id=2,
            comment="Исправление ФЭО без сброса",
            items=[pc.PurchaseItemCorrectionIn(id=901, feo_category_id=20, feo_planned_item_id=None)],
        )
        res = asyncio.run(pc.apply_purchase_correction(4894, body, db=db, current_user=user))
    finally:
        pcs.ensure_purchase_visible = orig_visible
        pcs.has_org_key = orig_key
        pc.assert_no_goods_in_payroll = orig_payroll
        pc.check_correction_excess = orig_excess
        feo_history.record_updated = orig_rec_upd
        feo_history.record_created = orig_rec_crt

    assert db.committed is True
    assert purchase.status == "contracted"
    assert purchase.approval_status == "approved"
    assert purchase.feo_category_id == 20
    assert purchase.event_id == 2
    assert pi.feo_category_id == 20
    assert pi.feo_planned_item_id == 200
    assert wi.feo_category_id == 20
    assert wi.feo_planned_item_id == 200
    assert wish.feo_category_id == 20
    assert wish.event_id == 2
    assert fpi_old.is_active is False

    assert res["category_corrected"] is True
    assert res["event_corrected"] is True
    assert res["initial_feo_category_name"] == "4.1. Просвещение"
    assert res["current_feo_category_name"] == "4.2. Спорт"
    assert res["initial_event_name"] == "Слёт ВСКС"
    assert res["current_event_name"] == "Спартакиада"
    assert len(res["history"]) == 1
    assert res["history"][0]["user_name"] == "Цыганов И.И."
    assert res["history"][0]["comment"] == "Исправление ФЭО без сброса"
