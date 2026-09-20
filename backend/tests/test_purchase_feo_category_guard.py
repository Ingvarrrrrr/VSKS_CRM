# -*- coding: utf-8 -*-
"""Владелец (2026-09-20): «когда закупка создаётся из заявки — у неё нельзя
менять категорию ФЭО; из какой взяли, в такой и должна находиться; менять —
в плане и согласовывать до формирования закупки».

Два новых замка, оба БЕЗ суперадмин-обхода (жёстче, чем существующий
FEO_CATEGORY_LOCKED_AFTER_APPROVAL, который суперадмина пускает):

1. app.routers.purchases._guard_feo_category_change_after_approval —
   расширен первой проверкой: закупка с wish_id (рождена из заявки/плана) —
   категория ФЭО зафиксирована ВСЕГДА, независимо от approval_status.
   Код ошибки FEO_CATEGORY_LOCKED_FROM_WISH. Проверяется ДО существующей
   проверки approval_status — вызывается и из PUT (:1140-1143), и из PATCH
   (:1811-1813) purchases.py, тело функции общее.

2. app.routers.purchase_items_edit._guard_item_feo_category_locked_from_plan
   — новый хелпер, вызывается из patch_purchase_item рядом с гейтом W3:
   позиция с feo_planned_item_id и/или wish_item_id — категория позиции
   зафиксирована планом. Код ошибки ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN.

3. app.routers.purchase_items_edit.assert_items_feo_category_matches_planned_items
   — добивка (2026-09-20): та же блокировка для PUT /api/purchases/{pid}
   (полная замена items, wish_item_id в схеме нет) — сверяет входящую
   feo_category_id с СОБСТВЕННОЙ категорией FeoPlannedItem, тот же код
   ошибки через общий _raise_item_feo_category_locked (не вторая копия).
   Вызывается из update_purchase сразу после `items_data = data.items or []`.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
по образцу test_feo_change_after_approval.py (гейт шапки закупки) и
test_planned_item_link_rules.py (сквозной вызов patch_purchase_item на
подставной БД).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import purchases as pr
from app.routers import purchase_items_edit as pie
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase


# ---------------------------------------------------------------------------
# 1) _guard_feo_category_change_after_approval — новая проверка wish_id
# ---------------------------------------------------------------------------

def _mk_purchase(wish_id=None, feo_category_id=1, approval_status="approved",
                  assigned_user_id=None, purchase_number=42, id_=99):
    return SimpleNamespace(
        id=id_, purchase_number=purchase_number, wish_id=wish_id,
        feo_category_id=feo_category_id, approval_status=approval_status,
        assigned_user_id=assigned_user_id,
    )


def _mk_user(role="employee", id_=1, full_name="Иван Иванов", username="ivan"):
    return SimpleNamespace(role=role, id=id_, full_name=full_name, username=username)


class _FakeDB:
    """Гейт на закупке с wish_id бросает ДО любого обращения к БД (первая
    проверка в функции) — этой заглушке достаточно не падать при создании."""

    async def get(self, model, id_):
        return None

    async def execute(self, stmt):
        raise AssertionError("wish_id-гейт обязан бросить ДО обращения к БД")


def test_purchase_from_wish_blocks_category_change_regardless_of_approval():
    """(а) закупка с wish_id, другая категория -> 422 FEO_CATEGORY_LOCKED_FROM_WISH,
    даже если закупка ЕЩЁ НЕ согласована (approval_status != 'approved') — замок
    жёстче и проверяется раньше существующего approval-гейта."""
    for status in (None, "in_progress", "approved", "rejected"):
        p = _mk_purchase(wish_id=555, feo_category_id=1, approval_status=status)
        user = _mk_user(role="employee")
        db = _FakeDB()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))

        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert detail["code"] == "FEO_CATEGORY_LOCKED_FROM_WISH"
        assert "заявки" in detail["message"]
        assert "плане" in detail["message"]


def test_purchase_from_wish_blocks_even_for_superadmin():
    """Жёсткий замок — БЕЗ суперадмин-обхода (в отличие от FEO_CATEGORY_LOCKED_AFTER_APPROVAL)."""
    p = _mk_purchase(wish_id=555, feo_category_id=1, approval_status="approved")
    user = _mk_user(role="superadmin")
    db = _FakeDB()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "FEO_CATEGORY_LOCKED_FROM_WISH"


def test_purchase_from_wish_same_category_is_idempotent_noop():
    """Идемпотентный PUT: если новая категория == текущей — гейт вообще не
    должен дойти до wish_id-проверки (return на самом первом no-op-чеке)."""
    p = _mk_purchase(wish_id=555, feo_category_id=1, approval_status="approved")
    user = _mk_user(role="employee")
    db = _FakeDB()

    asyncio.run(pr._guard_feo_category_change_after_approval(p, 1, user, db))  # не бросает


def test_purchase_without_wish_id_keeps_old_approval_behavior():
    """(б) закупка БЕЗ wish_id — прежнее поведение не тронуто:
    approved + обычный пользователь -> всё ещё FEO_CATEGORY_LOCKED_AFTER_APPROVAL;
    не согласована -> меняется свободно."""
    # Всё ещё согласованная закупка без wish_id — старый гейт продолжает работать.
    p_approved = _mk_purchase(wish_id=None, feo_category_id=1, approval_status="approved")
    user = _mk_user(role="employee")
    db = _FakeDB()  # db.execute не должен вызываться — гейт approval бросает раньше
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pr._guard_feo_category_change_after_approval(p_approved, 2, user, db))
    assert exc_info.value.detail["code"] == "FEO_CATEGORY_LOCKED_AFTER_APPROVAL"

    # Не согласованная закупка без wish_id — меняется свободно, как и раньше.
    class _FakeDBNoOp:
        async def get(self, model, id_):
            return None

        async def execute(self, stmt):
            raise AssertionError("несогласованная закупка не должна трогать БД")

    p_draft = _mk_purchase(wish_id=None, feo_category_id=1, approval_status="in_progress")
    asyncio.run(pr._guard_feo_category_change_after_approval(p_draft, 2, user, _FakeDBNoOp()))  # не бросает


# ---------------------------------------------------------------------------
# 2) _guard_item_feo_category_locked_from_plan — новый item-level хелпер
# ---------------------------------------------------------------------------

def _mk_item(feo_planned_item_id=None, wish_item_id=None, feo_category_id=None):
    return SimpleNamespace(
        feo_planned_item_id=feo_planned_item_id, wish_item_id=wish_item_id,
        feo_category_id=feo_category_id,
    )


def test_item_with_planned_item_blocks_category_change():
    """(в) позиция с feo_planned_item_id -> смена feo_category_id -> 422."""
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    with pytest.raises(HTTPException) as exc_info:
        pie._guard_item_feo_category_locked_from_plan(it, 2)
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"
    assert "плановой позиции" in detail["message"]


def test_item_with_wish_item_id_blocks_category_change():
    """Та же блокировка для позиции, пришедшей из заявки (wish_item_id),
    даже без собственной feo_planned_item_id."""
    it = _mk_item(wish_item_id=321, feo_category_id=1)
    with pytest.raises(HTTPException) as exc_info:
        pie._guard_item_feo_category_locked_from_plan(it, 2)
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_item_with_planned_item_blocks_clear_feo_category():
    """clear_feo_category тоже заблокирован для привязанной позиции."""
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    with pytest.raises(HTTPException) as exc_info:
        pie._guard_item_feo_category_locked_from_plan(it, None, clearing=True)
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_item_with_planned_item_same_category_is_idempotent_noop():
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    pie._guard_item_feo_category_locked_from_plan(it, 1)  # не бросает


def test_item_without_links_changes_freely():
    """(в) позиция без привязок к плану/заявке -> категория меняется как раньше."""
    it = _mk_item(feo_planned_item_id=None, wish_item_id=None, feo_category_id=1)
    pie._guard_item_feo_category_locked_from_plan(it, 2)  # не бросает
    pie._guard_item_feo_category_locked_from_plan(it, None, clearing=True)  # не бросает


# ---------------------------------------------------------------------------
# 3) Сквозной вызов patch_purchase_item — подтверждает, что хелпер реально
#    подключён рядом с гейтом W3, а не только протестирован изолированно.
# ---------------------------------------------------------------------------

class _FakeItemsDB:
    """Гейт бросает ДО любых расчётных проверок/commit — заглушке достаточно
    отдавать PurchaseItem/Purchase по id."""

    def __init__(self, item, purchase):
        self._item = item
        self._purchase = purchase

    async def get(self, model, id_):
        if model is PurchaseItem:
            return self._item
        if model is Purchase:
            return self._purchase
        return None

    async def execute(self, stmt):
        raise AssertionError("гейт обязан бросить до обращения к БД")


def _mk_real_item(id_=200, purchase_id=100, **kw):
    base = dict(
        id=id_, purchase_id=purchase_id, wish_item_id=None, feo_category_id=None,
        feo_planned_item_id=None, item_name="Футболка поло", over_plan=False,
        quantity=10, unit="шт.", unit_price=500, total_price=5000,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _mk_real_purchase(id_=100, **kw):
    base = dict(id=id_, purchase_number="З-100", status="plan_schedule", feo_category_id=1)
    base.update(kw)
    return SimpleNamespace(**base)


def test_patch_endpoint_rejects_category_change_for_planned_item():
    it = _mk_real_item(feo_planned_item_id=77, feo_category_id=1)
    p = _mk_real_purchase()
    db = _FakeItemsDB(it, p)
    body = pie._ItemPatchBody(feo_category_id=2)
    user = _mk_user(role="employee")

    async def run():
        await pie.patch_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_patch_endpoint_rejects_category_change_for_wish_item():
    it = _mk_real_item(wish_item_id=321, feo_category_id=1)
    p = _mk_real_purchase()
    db = _FakeItemsDB(it, p)
    body = pie._ItemPatchBody(feo_category_id=2)
    user = _mk_user(role="employee")

    async def run():
        await pie.patch_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


# ---------------------------------------------------------------------------
# 4) assert_items_feo_category_matches_planned_items — добивка PUT items-replace.
#    update_purchase (PUT /api/purchases/{pid}) зовёт эту функцию сразу после
#    `items_data = data.items or []`, ДО любых мутаций — тест бьёт по ней
#    напрямую, теми же объектами (PurchaseItemCreate), что реально приходят
#    в PUT, вместо разгона всего тяжёлого тела update_purchase офлайн.
# ---------------------------------------------------------------------------

from app.schemas.purchases import PurchaseItemCreate


def _mk_put_item(feo_planned_item_id=None, feo_category_id=None, **kw):
    return PurchaseItemCreate(
        item_name="Футболка поло", quantity=10, unit_price=500, total_price=5000,
        feo_planned_item_id=feo_planned_item_id, feo_category_id=feo_category_id,
        **kw,
    )


class _FakeFpiRowsDB:
    """Один db.execute() -> .all() отдаёт (FeoPlannedItem.id, feo_category_id)
    построчно — ровно то, что делает один SELECT в assert_items_feo_category_
    matches_planned_items (без N+1)."""

    def __init__(self, rows):
        self._rows = rows
        self.execute_calls = 0

    async def execute(self, stmt):
        self.execute_calls += 1
        return SimpleNamespace(all=lambda: self._rows)


def test_put_items_rejects_when_item_category_differs_from_planned_item_category():
    """PUT: позиция с feo_planned_item_id=77, чья плановая позиция числится в
    категории 1, приходит с feo_category_id=2 (другой) -> 422."""
    items_data = [_mk_put_item(feo_planned_item_id=77, feo_category_id=2)]
    db = _FakeFpiRowsDB(rows=[(77, 1)])  # FeoPlannedItem(id=77).feo_category_id == 1

    async def run():
        await pie.assert_items_feo_category_matches_planned_items(items_data, db)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"
    assert db.execute_calls == 1  # один SELECT на все feo_planned_item_id


def test_put_items_allows_when_item_category_matches_planned_item_category():
    """Та же плановая позиция (категория 1), позиция приходит С ТОЙ ЖЕ
    категорией -> проходит (аналог 200 для PUT)."""
    items_data = [_mk_put_item(feo_planned_item_id=77, feo_category_id=1)]
    db = _FakeFpiRowsDB(rows=[(77, 1)])

    asyncio.run(pie.assert_items_feo_category_matches_planned_items(items_data, db))  # не бросает
    assert db.execute_calls == 1


def test_put_items_with_no_planned_item_links_skips_db_entirely():
    """Ни у одной позиции нет feo_planned_item_id -> функция не должна лезть в БД."""
    items_data = [_mk_put_item(feo_planned_item_id=None, feo_category_id=5)]
    db = _FakeFpiRowsDB(rows=[])

    asyncio.run(pie.assert_items_feo_category_matches_planned_items(items_data, db))  # не бросает
    assert db.execute_calls == 0


def test_put_items_skips_item_without_own_category():
    """Позиция ссылается на плановую позицию, но СВОЮ feo_category_id не
    прислала (полагается на фолбэк категории шапки закупки) -> не блокируем,
    сравнивать нечего."""
    items_data = [_mk_put_item(feo_planned_item_id=77, feo_category_id=None)]
    db = _FakeFpiRowsDB(rows=[(77, 1)])

    asyncio.run(pie.assert_items_feo_category_matches_planned_items(items_data, db))  # не бросает


def test_put_items_batches_multiple_items_in_one_select():
    """Несколько позиций с РАЗНЫМИ feo_planned_item_id -> один SELECT на всех,
    несовпадение хотя бы у одной -> 422."""
    items_data = [
        _mk_put_item(feo_planned_item_id=77, feo_category_id=1),   # совпадает
        _mk_put_item(feo_planned_item_id=88, feo_category_id=99),  # НЕ совпадает
    ]
    db = _FakeFpiRowsDB(rows=[(77, 1), (88, 2)])

    async def run():
        await pie.assert_items_feo_category_matches_planned_items(items_data, db)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"
    assert db.execute_calls == 1
