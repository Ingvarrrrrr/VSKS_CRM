# -*- coding: utf-8 -*-
"""Владелец (2026-09-02), этапы 2-3 плана исправления расхождения категорий ФЭО.

До этой правки расхождение «категория позиции закупки ≠ категория привязанной
плановой позиции» было НЕИСПРАВИМЫМ:
  - PATCH /purchases/{pid}/items/{item_id} (явный выбор плановой позиции)
    отказывал 409-кой ВСЕМ без исключения при малейшем несовпадении категорий
    (даже потомку) и без обхода для суперадмина;
  - POST /feo-planned-items/map, наоборот, вообще не проверял совпадение и
    молча ПЕРЕНОСИЛ позицию закупки в категорию плановой позиции — это само
    создавало расхождение «категория позиции ≠ категория шапки», которое PATCH
    выше как раз запрещает. Два пути жили по разным правилам.

Новое правило — ОДНО, в app.services.plan_autoassign.check_planned_item_category_link,
и вызывается из ОБОИХ мест:
  - совпадение категории (или потомок, через _category_within) — разрешено
    любому, без уведомления;
  - несовпадение — обычному пользователю 409 с detail={code, message},
    суперадмину — разрешено, но согласовавшим закупку (PurchaseApproval,
    status='approved') и ответственному (purchase.assigned_user_id) уходит
    уведомление;
  - при этом POST /feo-planned-items/map больше НЕ переносит категорию позиции
    закупки следом за плановой — привязка живёт поверх существующей категории,
    как и у PATCH.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace) + лёгкая FakeDB с .get()/.execute(),
по образцу test_feo_change_resets_item_links.py. Реальные роутер-функции
(patch_purchase_item, map_purchase_item_to_planned) вызываются НАПРЯМУЮ как
обычные корутины — Depends(...) в их сигнатурах это просто значения по
умолчанию, при прямом вызове передаём db/current_user сами и полностью
обходим FastAPI DI, `_has_purchase_write_access` замокан (не имеет отношения
к проверяемому правилу)."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import app.notifications as notifications
from app.routers import purchases as pr
from app.routers import feo_planned_items as fpi_router
from app.services.plan_autoassign import check_planned_item_category_link
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.purchase_approval import PurchaseApproval
from app.models.wish_item import WishItem
from app.models.user import User


# ---------------------------------------------------------------------------
# Подставные объекты — то же дерево категорий, что в test_feo_change_resets_item_links.py
# ---------------------------------------------------------------------------
#   10 "Организация мероприятий" (root)
#     11 "Закупка комплекта форменной одежды"  <- категория ПОЗИЦИИ ЗАКУПКИ
#       12 "Пошив по индивидуальным меркам"     <- потомок 11
#   20 "Техническое оснащение деятельности штаба" (root)
#     21 "Закупка канцелярских принадлежностей"  <- ЧУЖАЯ категория (плана)

def _mk_categories():
    return {
        10: SimpleNamespace(id=10, parent_id=None, name="Организация мероприятий"),
        11: SimpleNamespace(id=11, parent_id=10, name="Закупка комплекта форменной одежды"),
        12: SimpleNamespace(id=12, parent_id=11, name="Пошив по индивидуальным меркам"),
        20: SimpleNamespace(id=20, parent_id=None, name="Техническое оснащение деятельности штаба"),
        21: SimpleNamespace(id=21, parent_id=20, name="Закупка канцелярских принадлежностей"),
    }


def _mk_user(role: str, uid: int = 1) -> SimpleNamespace:
    # telegram_id/max_chat_id намеренно None — notify_user() тогда честный no-op
    # (см. app/notifications.py), реальных сетевых вызовов не будет ни разу, но
    # для теста «уведомление отправлено» notify_user всё равно подменяется шпионом.
    return SimpleNamespace(id=uid, role=role, full_name=f"Тестовый {role}", username=role,
                            telegram_id=None, max_chat_id=None)


EMPLOYEE = _mk_user("employee", uid=1)
SUPERADMIN = _mk_user("superadmin", uid=2)
APPROVER = _mk_user("manager", uid=3)
ASSIGNEE = _mk_user("manager", uid=4)


class _FakeResult:
    """Универсальная обёртка результата execute(): tests хранят РОВНО одну строку
    на таблицу (или список для approvals) — фильтрацию по WHERE не выполняет,
    как и _FakeDB в test_feo_change_resets_item_links.py."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows
        return SimpleNamespace(all=lambda: list(rows))

    def one(self):
        return self._rows[0]

    def all(self):
        return self._rows


class _FakeDB:
    """db.get()/db.execute() по типу таблицы (dispatch по __tablename__/подстроке
    компилированного SQL) — ровно тот минимум, который проходят
    patch_purchase_item (явный выбор плановой позиции) и
    map_purchase_item_to_planned. Не СУБД: одна запись на тип на тест."""

    def __init__(self, *, categories=None, planned_items=None, purchase_items=None,
                 purchases=None, wish_items=None, approved_user_ids=None):
        self._by_table = {
            "feo_categories": categories or {},
            "feo_planned_items": planned_items or {},
            "purchase_items": purchase_items or {},
            "purchases": purchases or {},
            "wish_items": wish_items or {},
        }
        self._approved_user_ids = approved_user_ids or []
        self.added = []
        self.flushed = False
        self.committed = False

    async def get(self, model, id_):
        if id_ is None:
            return None
        return self._by_table.get(getattr(model, "__tablename__", None), {}).get(id_)

    async def execute(self, stmt):
        sql = str(stmt).lower()
        if "sum(" in sql or "coalesce(" in sql:
            # _recalc_purchase_totals — сумма позиций закупки, тестам безразлична.
            return _FakeResult([Decimal("0")])
        if "purchase_approvals" in sql:
            return _FakeResult(self._approved_user_ids)
        for table in ("purchase_items", "feo_planned_items", "purchases", "wish_items", "feo_categories"):
            if table in sql:
                return _FakeResult(list(self._by_table[table].values()))
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


def _mk_purchase(**kw):
    base = dict(id=100, purchase_number="З-100", feo_category_id=11, assigned_user_id=None,
                subsidy_id=None, status="plan_schedule", total_nmck=None, planned_total_price=None,
                contract_price=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _mk_purchase_item(**kw):
    base = dict(id=200, purchase_id=100, wish_item_id=None, feo_category_id=None,
                feo_planned_item_id=None, item_name="Футболка поло", over_plan=False,
                quantity=Decimal("10"), unit="шт.", unit_price=Decimal("500"),
                total_price=Decimal("5000"), planned_quantity=None, planned_unit_price=None,
                planned_total=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _swap_notify_user(fn):
    """Подменяет app.notifications.notify_user на fn, возвращает функцию восстановления.
    Лениво импортируемый (`from app.notifications import notify_user` внутри тела
    check_planned_item_category_link) забирает АКТУАЛЬНОЕ значение атрибута модуля
    на момент вызова — подмена атрибута модуля работает без monkeypatch-фикстуры."""
    original = notifications.notify_user
    notifications.notify_user = fn
    return lambda: setattr(notifications, "notify_user", original)


# ---------------------------------------------------------------------------
# 1) check_planned_item_category_link — прямая проверка общего хелпера
# ---------------------------------------------------------------------------

def test_helper_rejects_mismatch_for_regular_user():
    db = _FakeDB(categories=_mk_categories())
    purchase = _mk_purchase()
    item = _mk_purchase_item()

    async def run():
        await check_planned_item_category_link(
            db, purchase=purchase, item=item,
            item_category_id=11, planned_category_id=21,  # чужая ветка
            planned_item_name="Скрепки канцелярские", current_user=EMPLOYEE,
        )

    try:
        asyncio.run(run())
        assert False, "ожидался HTTPException 409"
    except Exception as e:
        assert getattr(e, "status_code", None) == 409
        detail = e.detail
        assert detail["code"] == "PLANNED_ITEM_CATEGORY_MISMATCH"
        # Сообщение обязано вести к решению, а не просто констатировать факт.
        assert "категории закупки" in detail["message"]
        assert "Создать в плане закупок" in detail["message"]


def test_helper_allows_superadmin_and_notifies_approvers_and_assignee():
    db = _FakeDB(categories=_mk_categories(), approved_user_ids=[APPROVER.id])
    purchase = _mk_purchase(assigned_user_id=ASSIGNEE.id)
    item = _mk_purchase_item()
    users_by_id = {APPROVER.id: APPROVER, ASSIGNEE.id: ASSIGNEE}

    sent = []

    async def fake_notify_user(user, text, **kw):
        sent.append((user.id, text))

    restore = _swap_notify_user(fake_notify_user)

    async def fake_db_get(model, id_):
        if model is User:
            return users_by_id.get(id_)
        return await _FakeDB.get(db, model, id_)
    db.get = fake_db_get  # type: ignore[assignment]

    try:
        async def run():
            await check_planned_item_category_link(
                db, purchase=purchase, item=item,
                item_category_id=11, planned_category_id=21,
                planned_item_name="Скрепки канцелярские", current_user=SUPERADMIN,
            )
        asyncio.run(run())  # не должно бросить
    finally:
        restore()

    # Ровно 2 получателя (согласовавший + ответственный), без дублей.
    recipient_ids = {uid for uid, _ in sent}
    assert recipient_ids == {APPROVER.id, ASSIGNEE.id}
    for _, text in sent:
        assert "Скрепки канцелярские" in text
        assert "Тестовый superadmin" in text


def test_helper_no_duplicate_notification_when_approver_is_also_assignee():
    db = _FakeDB(categories=_mk_categories(), approved_user_ids=[APPROVER.id])
    purchase = _mk_purchase(assigned_user_id=APPROVER.id)  # тот же человек
    item = _mk_purchase_item()

    sent = []

    async def fake_notify_user(user, text, **kw):
        sent.append(user.id)

    restore = _swap_notify_user(fake_notify_user)

    async def fake_db_get(model, id_):
        if model is User:
            return APPROVER if id_ == APPROVER.id else None
        return await _FakeDB.get(db, model, id_)
    db.get = fake_db_get  # type: ignore[assignment]

    try:
        async def run():
            await check_planned_item_category_link(
                db, purchase=purchase, item=item,
                item_category_id=11, planned_category_id=21,
                planned_item_name="Скрепки канцелярские", current_user=SUPERADMIN,
            )
        asyncio.run(run())
    finally:
        restore()

    assert sent == [APPROVER.id]  # один раз, не дважды


def test_helper_allows_exact_match_without_notification():
    db = _FakeDB(categories=_mk_categories())
    purchase = _mk_purchase()
    item = _mk_purchase_item()
    sent = []
    restore = _swap_notify_user(lambda *a, **kw: sent.append(1))
    try:
        async def run():
            await check_planned_item_category_link(
                db, purchase=purchase, item=item,
                item_category_id=11, planned_category_id=11,  # та же категория
                planned_item_name="Футболка поло", current_user=EMPLOYEE,
            )
        asyncio.run(run())  # не бросает
    finally:
        restore()
    assert sent == []


def test_helper_allows_descendant_category_without_notification():
    db = _FakeDB(categories=_mk_categories())
    purchase = _mk_purchase()
    item = _mk_purchase_item()
    sent = []
    restore = _swap_notify_user(lambda *a, **kw: sent.append(1))
    try:
        async def run():
            await check_planned_item_category_link(
                db, purchase=purchase, item=item,
                item_category_id=11, planned_category_id=12,  # потомок 11
                planned_item_name="Пошив на заказ", current_user=EMPLOYEE,
            )
        asyncio.run(run())  # не бросает
    finally:
        restore()
    assert sent == []


def test_helper_skips_when_item_has_no_category_at_all():
    """У закупки нет ни своей категории позиции, ни категории шапки — сравнивать
    не с чем, проверка не блокирует (это отдельная проблема — «нет категории»,
    не «расхождение категорий»)."""
    db = _FakeDB(categories=_mk_categories())
    purchase = _mk_purchase(feo_category_id=None)
    item = _mk_purchase_item()

    async def run():
        await check_planned_item_category_link(
            db, purchase=purchase, item=item,
            item_category_id=None, planned_category_id=21,
            planned_item_name="Скрепки канцелярские", current_user=EMPLOYEE,
        )
    asyncio.run(run())  # не бросает


# ---------------------------------------------------------------------------
# 2) Оба реальных роутера — PATCH /purchases/{id}/items/{id} (явный выбор) и
#    POST /feo-planned-items/map — вызываются НАПРЯМУЮ (обходя FastAPI DI) на
#    ОДИНАКОВЫХ данных и должны давать ОДИНАКОВЫЙ результат. Это и есть
#    главная проверка того, что общий хелпер не разъехался по двум копиям.
# ---------------------------------------------------------------------------

def _patch_wall(monkeypatch_write_access=True):
    """_has_purchase_write_access не имеет отношения к проверяемому правилу —
    подменяем на всегда-True, восстанавливаем после теста."""
    original = pr._has_purchase_write_access

    async def _always_true(user, db):
        return True
    pr._has_purchase_write_access = _always_true
    return lambda: setattr(pr, "_has_purchase_write_access", original)


def test_patch_items_endpoint_rejects_mismatch_for_regular_user():
    db = _FakeDB(
        categories=_mk_categories(),
        planned_items={21: SimpleNamespace(id=21, feo_category_id=21, name="Скрепки", is_active=True)},
        purchase_items={200: _mk_purchase_item(feo_category_id=None)},
        purchases={100: _mk_purchase(feo_category_id=11)},
    )
    restore_wall = _patch_wall()
    body = pr._ItemPatchBody(feo_planned_item_id=21)
    try:
        async def run():
            await pr.patch_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=EMPLOYEE)
        try:
            asyncio.run(run())
            assert False, "ожидался HTTPException 409"
        except Exception as e:
            assert getattr(e, "status_code", None) == 409
            assert e.detail["code"] == "PLANNED_ITEM_CATEGORY_MISMATCH"
    finally:
        restore_wall()


def test_map_endpoint_rejects_mismatch_for_regular_user():
    db = _FakeDB(
        categories=_mk_categories(),
        planned_items={21: SimpleNamespace(id=21, feo_category_id=21, name="Скрепки", is_active=True)},
        purchase_items={200: _mk_purchase_item(feo_category_id=None)},
        purchases={100: _mk_purchase(feo_category_id=11)},
    )

    async def run():
        await fpi_router.map_purchase_item_to_planned(
            purchase_item_id=200, planned_item_id=21, db=db, current_user=EMPLOYEE,
        )
    try:
        asyncio.run(run())
        assert False, "ожидался HTTPException 409"
    except Exception as e:
        assert getattr(e, "status_code", None) == 409
        assert e.detail["code"] == "PLANNED_ITEM_CATEGORY_MISMATCH"

    # Категория позиции закупки НЕ должна была измениться (раньше /map молча
    # переносил её в категорию плановой позиции — этап 3 это убирает).
    assert db._by_table["purchase_items"][200].feo_category_id is None


def test_both_endpoints_allow_superadmin_on_identical_mismatch_and_leave_category_untouched():
    sent = []

    async def fake_notify_user(user, text, **kw):
        sent.append(user.id)
    restore_notify = _swap_notify_user(fake_notify_user)

    users_by_id = {APPROVER.id: APPROVER}

    def _mk_db():
        db = _FakeDB(
            categories=_mk_categories(),
            planned_items={21: SimpleNamespace(id=21, feo_category_id=21, name="Скрепки", is_active=True)},
            purchase_items={200: _mk_purchase_item(feo_category_id=None)},
            purchases={100: _mk_purchase(feo_category_id=11)},
            approved_user_ids=[APPROVER.id],
        )

        async def fake_get(model, id_):
            if model is User:
                return users_by_id.get(id_)
            return await _FakeDB.get(db, model, id_)
        db.get = fake_get  # type: ignore[assignment]
        return db

    restore_wall = _patch_wall()
    db_patch = _mk_db()
    body = pr._ItemPatchBody(feo_planned_item_id=21)
    try:
        async def run_patch():
            return await pr.patch_purchase_item(pid=100, item_id=200, body=body, db=db_patch, current_user=SUPERADMIN)
        result_patch = asyncio.run(run_patch())
    finally:
        restore_wall()

    db_map = _mk_db()

    async def run_map():
        return await fpi_router.map_purchase_item_to_planned(
            purchase_item_id=200, planned_item_id=21, db=db_map, current_user=SUPERADMIN,
        )
    result_map = asyncio.run(run_map())

    restore_notify()

    # Оба пути: разрешили привязку суперадмину...
    assert result_patch["feo_planned_item_id"] == 21
    assert result_map["planned_item_id"] == 21
    # ...НЕ тронули собственную категорию позиции закупки (главное отличие от
    # старого поведения /map, которое молча переносило её)...
    assert db_patch._by_table["purchase_items"][200].feo_category_id is None
    assert db_map._by_table["purchase_items"][200].feo_category_id is None
    # ...и оба отправили РОВНО ОДНО уведомление одному и тому же согласовавшему
    # (assigned_user_id не задан в этой фикстуре -> получатель только APPROVER).
    assert sent == [APPROVER.id, APPROVER.id]


def test_both_endpoints_allow_matching_category_silently():
    sent = []
    restore_notify = _swap_notify_user(lambda *a, **kw: sent.append(1))

    def _mk_db():
        return _FakeDB(
            categories=_mk_categories(),
            planned_items={11: SimpleNamespace(id=11, feo_category_id=11, name="Футболки", is_active=True)},
            purchase_items={200: _mk_purchase_item(feo_category_id=None)},
            purchases={100: _mk_purchase(feo_category_id=11)},
        )

    restore_wall = _patch_wall()
    db_patch = _mk_db()
    body = pr._ItemPatchBody(feo_planned_item_id=11)
    try:
        async def run_patch():
            return await pr.patch_purchase_item(pid=100, item_id=200, body=body, db=db_patch, current_user=EMPLOYEE)
        result_patch = asyncio.run(run_patch())
    finally:
        restore_wall()

    db_map = _mk_db()

    async def run_map():
        return await fpi_router.map_purchase_item_to_planned(
            purchase_item_id=200, planned_item_id=11, db=db_map, current_user=EMPLOYEE,
        )
    result_map = asyncio.run(run_map())
    restore_notify()

    assert result_patch["feo_planned_item_id"] == 11
    assert result_map["planned_item_id"] == 11
    assert sent == []  # ни то, ни другое несовпадением не было — уведомлений нет
