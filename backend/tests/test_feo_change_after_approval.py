# -*- coding: utf-8 -*-
"""Владелец (2026-09-01): «Закупки после согласования есть возможность
поменять категорию ФЭО, но это неправильно. Да, я суперадмин, но в данном
случае это должно быть уведомление, плюс остальным пользователям не должна
предоставляться возможность менять после согласования».

Проверяем app.routers.purchases._guard_feo_category_change_after_approval —
общий гейт, вызываемый и из PATCH (autosave, реальный вектор бага: фронт
шлёт feo_category_id в каждом autosave-запросе), и из PUT (явный Save):
  - approval_status == 'approved' + смена категории + обычный пользователь
    -> 422 с понятным текстом;
  - тот же случай + superadmin -> проходит, но уведомляет согласовавших
    (purchase_approvals.status == 'approved') и ответственного
    (assigned_user_id), без дублей;
  - значение не меняется (то же самое или None/отсутствует) -> ничего не
    происходит, в БД не лезем;
  - закупка НЕ согласована (None/in_progress/rejected) -> без ограничений
    для кого угодно.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace), по образцу
test_feo_category_write_gate.py. notify_user патчится на самом модуле
app.notifications — проверяемый код делает локальный `from app.notifications
import notify_user` ВНУТРИ функции при каждом вызове, поэтому патч атрибута
модуля подхватывается.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import purchases as pr
from app import notifications as notif_module
from app.models.feo_category import FeoCategory
from app.models.user import User


# ---------------------------------------------------------------------------
# Подставные объекты
# ---------------------------------------------------------------------------

def _mk_purchase(feo_category_id=1, approval_status="approved", assigned_user_id=None,
                  purchase_number=42, id_=99):
    return SimpleNamespace(
        id=id_, purchase_number=purchase_number,
        feo_category_id=feo_category_id, approval_status=approval_status,
        assigned_user_id=assigned_user_id,
    )


def _mk_user(role="employee", id_=1, full_name="Иван Иванов", username="ivan"):
    return SimpleNamespace(role=role, id=id_, full_name=full_name, username=username)


class _ApprovalRow:
    """Заглушка scalars()-результата запроса user_id согласовавших
    (PurchaseApproval.status == 'approved')."""

    def __init__(self, ids):
        self._ids = ids

    def scalars(self):
        return self

    def all(self):
        return self._ids


class _FakeDB:
    """db.get() отдаёт FeoCategory/User по словарю; db.execute() всегда
    отдаёт список user_id согласовавших — гейт всегда делает ровно один
    такой запрос (или ноль, если раньше бросил/вышел)."""

    def __init__(self, categories=None, users=None, approver_ids=None):
        self._categories = categories or {}
        self._users = users or {}
        self._approver_ids = approver_ids or []
        self.execute_calls = 0

    async def get(self, model, id_):
        if id_ is None:
            return None
        if model is FeoCategory:
            return self._categories.get(id_)
        if model is User:
            return self._users.get(id_)
        return None

    async def execute(self, stmt):
        self.execute_calls += 1
        return _ApprovalRow(self._approver_ids)


def _notify_spy(monkeypatch):
    calls = []

    async def _fake_notify_user(user, text, task_id=None, button_url=None,
                                 button_label=None, reply_markup_override=None):
        calls.append((user, text))

    monkeypatch.setattr(notif_module, "notify_user", _fake_notify_user)
    return calls


# ---------------------------------------------------------------------------
# Обычный пользователь — запрет
# ---------------------------------------------------------------------------

def test_regular_user_cannot_change_feo_category_after_approval(monkeypatch):
    calls = _notify_spy(monkeypatch)
    p = _mk_purchase(feo_category_id=1, approval_status="approved")
    user = _mk_user(role="manager")
    db = _FakeDB()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "FEO_CATEGORY_LOCKED_AFTER_APPROVAL"
    assert "согласована" in detail["message"]
    assert "менять категорию ФЭО нельзя" in detail["message"]
    assert "снимите согласование" in detail["message"]
    assert "обратитесь к администратору" in detail["message"]
    assert calls == []  # уведомление не шлётся — действие отклонено
    assert db.execute_calls == 0  # гейт бросает ДО обращения к согласованиям


def test_org_admin_also_blocked_not_just_employee(monkeypatch):
    """org_admin — тоже НЕ суперадмин, отказ применяется как к рядовому
    сотруднику (владелец: «остальным пользователям» — без исключений)."""
    calls = _notify_spy(monkeypatch)
    p = _mk_purchase(feo_category_id=1, approval_status="approved")
    user = _mk_user(role="org_admin")
    db = _FakeDB()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))

    assert exc_info.value.status_code == 422
    assert calls == []


# ---------------------------------------------------------------------------
# Суперадмин — разрешено, но с уведомлением
# ---------------------------------------------------------------------------

def test_superadmin_can_change_and_triggers_notification(monkeypatch):
    calls = _notify_spy(monkeypatch)
    p = _mk_purchase(feo_category_id=1, approval_status="approved",
                      assigned_user_id=5, purchase_number=777)
    user = _mk_user(role="superadmin", id_=99, full_name="Суперадмин Суперадминов")
    categories = {
        1: SimpleNamespace(id=1, name="Канцелярия"),
        2: SimpleNamespace(id=2, name="Транспорт"),
    }
    approver = SimpleNamespace(id=10, full_name="Согласующий Согласующев")
    assignee = SimpleNamespace(id=5, full_name="Ответственный Ответственнов")
    db = _FakeDB(categories=categories, users={10: approver, 5: assignee}, approver_ids=[10])

    asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))  # не бросает

    notified_ids = {u.id for u, _ in calls}
    assert notified_ids == {10, 5}  # согласовавший + ответственный, без дублей
    for _, text in calls:
        assert "777" in text  # номер закупки
        assert "Канцелярия" in text  # старая категория
        assert "Транспорт" in text  # новая категория
        assert "Суперадмин Суперадминов" in text  # кто поменял


def test_superadmin_no_duplicate_notification_when_approver_is_also_assignee(monkeypatch):
    calls = _notify_spy(monkeypatch)
    p = _mk_purchase(feo_category_id=1, approval_status="approved", assigned_user_id=10)
    user = _mk_user(role="superadmin")
    categories = {1: SimpleNamespace(id=1, name="A"), 2: SimpleNamespace(id=2, name="B")}
    same_person = SimpleNamespace(id=10, full_name="Тот же человек")
    db = _FakeDB(categories=categories, users={10: same_person}, approver_ids=[10])

    asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))

    assert len(calls) == 1  # один и тот же человек в обоих списках — уведомление одно


# ---------------------------------------------------------------------------
# Значение не меняется — ничего не происходит
# ---------------------------------------------------------------------------

def test_no_op_when_category_unchanged(monkeypatch):
    calls = _notify_spy(monkeypatch)
    p = _mk_purchase(feo_category_id=1, approval_status="approved")
    user = _mk_user(role="employee")
    db = _FakeDB()

    asyncio.run(pr._guard_feo_category_change_after_approval(p, 1, user, db))  # то же значение

    assert calls == []
    assert db.execute_calls == 0


def test_no_op_when_new_value_is_none():
    p = _mk_purchase(feo_category_id=1, approval_status="approved")
    user = _mk_user(role="employee")
    db = _FakeDB()
    # None -> поле не передано в патче/пейлоаде, гейт не должен трогать БД
    asyncio.run(pr._guard_feo_category_change_after_approval(p, None, user, db))
    assert db.execute_calls == 0


# ---------------------------------------------------------------------------
# Закупка не согласована — без ограничений вообще
# ---------------------------------------------------------------------------

def test_unapproved_purchase_no_restriction_for_regular_user(monkeypatch):
    calls = _notify_spy(monkeypatch)
    for status in (None, "in_progress", "rejected"):
        p = _mk_purchase(feo_category_id=1, approval_status=status)
        user = _mk_user(role="employee")
        db = _FakeDB()
        asyncio.run(pr._guard_feo_category_change_after_approval(p, 2, user, db))  # не бросает
        assert db.execute_calls == 0
    assert calls == []  # уведомления не при чём — только гейт после approved
