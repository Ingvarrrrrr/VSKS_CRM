# -*- coding: utf-8 -*-
"""Корректировка утверждённой субсидии через проверку, волна 1 (2026-10-02):
тест гейта app.services.subsidy_revision_guard.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace), по образцу
test_feo_category_write_gate.py. has_org_key монкипатчится на самом модуле
app.auth.permissions — проверяемый код делает локальный
`from app.auth.permissions import has_org_key` ВНУТРИ функции при каждом
вызове, поэтому патч атрибута модуля подхватывается.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import permissions as perm_module
from app.services import subsidy_revision_guard as guard


def _mk_user(role="employee", id=1):
    return SimpleNamespace(role=role, id=id)


def _mk_subsidy(status="approved", org_id=10):
    return SimpleNamespace(status=status, org_id=org_id)


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    """Отдаёт один и тот же Subsidy-объект на любой db.execute() — гейту
    достаточно одного лукапа по subsidy_id до вызова has_org_key."""

    def __init__(self, subsidy=None):
        self._subsidy = subsidy

    async def execute(self, stmt):
        return _FakeResult(self._subsidy)


# ---------------------------------------------------------------------------
# Флаг выключен (SUBSIDY_REVISION_ENABLED не '1') -> всегда 'direct', has_org_key
# не вызывается вообще (поведение не меняется, пока функция не принята).
# ---------------------------------------------------------------------------

def test_flag_disabled_always_direct(monkeypatch):
    monkeypatch.delenv("SUBSIDY_REVISION_ENABLED", raising=False)

    async def _boom(*a, **kw):
        raise AssertionError("has_org_key не должен вызываться при выключенном флаге")
    monkeypatch.setattr(perm_module, "has_org_key", _boom)

    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="approved"))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_DIRECT
    asyncio.run(guard.assert_direct_edit(db, user, 111))  # не бросает


def test_flag_disabled_assert_direct_edit_does_not_raise(monkeypatch):
    monkeypatch.delenv("SUBSIDY_REVISION_ENABLED", raising=False)
    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="approved"))
    asyncio.run(guard.assert_direct_edit(db, user, 111))  # не бросает


# ---------------------------------------------------------------------------
# Флаг включён, но субсидия ЧЕРНОВИК (status != 'approved') -> всегда 'direct'.
# ---------------------------------------------------------------------------

def test_draft_subsidy_always_direct(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _boom(*a, **kw):
        raise AssertionError("has_org_key не должен вызываться для черновика")
    monkeypatch.setattr(perm_module, "has_org_key", _boom)

    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="draft"))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_DIRECT


# ---------------------------------------------------------------------------
# Флаг включён, субсидия approved, subsidy_id=None -> 'direct' без обращения к БД.
# ---------------------------------------------------------------------------

def test_subsidy_id_none_always_direct(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _boom(*a, **kw):
        raise AssertionError("не должен обращаться к БД/has_org_key при subsidy_id=None")
    monkeypatch.setattr(perm_module, "has_org_key", _boom)

    user = _mk_user("employee")

    class _BoomDB:
        async def execute(self, stmt):
            raise AssertionError("не должен обращаться к БД при subsidy_id=None")

    mode = asyncio.run(guard.subsidy_edit_mode(_BoomDB(), user, None))
    assert mode == guard.MODE_DIRECT


# ---------------------------------------------------------------------------
# Флаг включён, субсидия approved, superadmin -> 'direct' без вызова has_org_key.
# ---------------------------------------------------------------------------

def test_superadmin_always_direct(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _boom(*a, **kw):
        raise AssertionError("has_org_key не должен вызываться для superadmin")
    monkeypatch.setattr(perm_module, "has_org_key", _boom)

    user = _mk_user("superadmin")
    db = _FakeDB(_mk_subsidy(status="approved"))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_DIRECT


# ---------------------------------------------------------------------------
# Флаг включён, субсидия approved, есть subsidy.edit -> 'direct'.
# ---------------------------------------------------------------------------

def test_approved_with_subsidy_edit_is_direct(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "subsidy.edit" and org_id == 10 and subsidy_id == 111
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="approved", org_id=10))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_DIRECT
    asyncio.run(guard.assert_direct_edit(db, user, 111))  # не бросает


# ---------------------------------------------------------------------------
# Флаг включён, субсидия approved, только subsidy.correct (без subsidy.edit)
# -> 'revision' и 409 с нужным code/message.
# ---------------------------------------------------------------------------

def test_approved_with_only_subsidy_correct_is_revision(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "subsidy.correct" and org_id == 10 and subsidy_id == 111
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="approved", org_id=10))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_REVISION

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(guard.assert_direct_edit(db, user, 111))
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["code"] == "subsidy_revision_required"
    assert "корректировку" in detail["message"]


# ---------------------------------------------------------------------------
# Флаг включён, субсидия approved, нет ни subsidy.edit, ни subsidy.correct
# -> 'forbidden' и 403.
# ---------------------------------------------------------------------------

def test_approved_without_any_right_is_forbidden(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee")
    db = _FakeDB(_mk_subsidy(status="approved", org_id=10))
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 111))
    assert mode == guard.MODE_FORBIDDEN

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(guard.assert_direct_edit(db, user, 111))
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["code"] == "subsidy_correct_required"
    assert "Корректировать субсидию" in detail["message"]


def test_subsidy_not_found_is_direct(monkeypatch):
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    async def _boom(*a, **kw):
        raise AssertionError("has_org_key не должен вызываться, если субсидия не найдена")
    monkeypatch.setattr(perm_module, "has_org_key", _boom)

    user = _mk_user("employee")
    db = _FakeDB(None)
    mode = asyncio.run(guard.subsidy_edit_mode(db, user, 999))
    assert mode == guard.MODE_DIRECT
