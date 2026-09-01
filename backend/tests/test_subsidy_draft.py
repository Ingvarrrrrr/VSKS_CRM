# -*- coding: utf-8 -*-
"""План C1/C2/C3 (владелец, 2026-09-01): черновые субсидии.

«Должна быть возможность у любого сотрудника создавать субсидию и вносить в
неё корректировки, так же подключать к этой субсидии других людей для
совместной работы (как с заявкой). Но это будет черновая субсидия, которую
надо будет утвердить у администратора, чтобы она могла пойти в работу...
Это такая же субсидия, не надо там ничего изобретать; к ней не прикрепляются
заявки, договора и прочее — это просто смета.»

Один флаг состояния (Subsidy.status: 'draft' | 'approved'), без цепочек
согласования. Offline, синхронно (asyncio.run внутри def test_...), без
реального БД/HTTP — на подставных объектах (SimpleNamespace/фейковый db),
по образцу test_feo_category_write_gate.py / test_purchase_method_required.py.
has_org_key монкипатчится на самом модуле app.auth.permissions — проверяемый
код делает `from app.auth.permissions import has_org_key` ВНУТРИ функции при
каждом вызове, поэтому патч атрибута модуля подхватывается.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import permissions as perm_module
from app.routers import subsidies
from app.models.subsidy import Subsidy as SubsidyModel
from app.schemas.schemas import SubsidyCreate
from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding


# ---------------------------------------------------------------------------
# Подставные объекты
# ---------------------------------------------------------------------------

def _mk_user(role="employee", id=1, org_id=10, **kw):
    base = dict(role=role, id=id, org_id=org_id, full_name="Тест Тестов", username="test")
    base.update(kw)
    return SimpleNamespace(**base)


def _mk_subsidy_obj(**kw):
    """Настоящий Subsidy() ORM-инстанс (не SimpleNamespace) — approve_subsidy/
    create_subsidy строят ответ через `s.__table__.columns`, которого у
    SimpleNamespace нет."""
    defaults = dict(
        id=1, org_id=10, status="draft", created_by=5,
        approved_by=None, approved_at=None, contractor_id=None,
        name="Тест", year=2026, budget=1000.0,
    )
    defaults.update(kw)
    s = SubsidyModel()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


class _FakeResult:
    def __init__(self, obj=None):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def first(self):
        return self._obj

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._obj, list):
            return self._obj
        return [self._obj] if self._obj is not None else []


class _FakeDB:
    """Отдаёт канонные результаты по очереди на каждый db.execute(), не глядя
    в сам запрос — как _QueueDB в test_feo_category_write_gate.py."""

    def __init__(self, results=None):
        self._queue = list(results or [])
        self.added = []
        self.deleted = []

    async def execute(self, stmt):
        return self._queue.pop(0) if self._queue else _FakeResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self.deleted.append(obj)

    async def get(self, model, id):
        return None


# ---------------------------------------------------------------------------
# C1/C2 — создание субсидии: автор + черновик по умолчанию
# ---------------------------------------------------------------------------

def test_create_subsidy_sets_draft_status_and_author(monkeypatch):
    async def _fake_ceiling(db, subsidy_id):
        return {}
    monkeypatch.setattr(subsidies, "calculate_ceiling_forecast", _fake_ceiling)

    user = _mk_user("employee", id=42, org_id=10)
    db = _FakeDB(results=[_FakeResult(None)])  # dup-name check → нет дубля
    body = SubsidyCreate(name="Субсидия C1", year=2026, budget=1000)

    out = asyncio.run(subsidies.create_subsidy(body, db, user))

    assert out["status"] == "draft"
    assert out["created_by"] == 42


# ---------------------------------------------------------------------------
# C2 — авторизация правки черновика: автор / участник / посторонний
# ---------------------------------------------------------------------------

def test_draft_edit_allowed_for_author():
    user = _mk_user("employee", id=5)
    sub = _mk_subsidy_obj(created_by=5)
    db = _FakeDB()  # created_by совпадает — до БД дело не доходит
    assert asyncio.run(subsidies._can_edit_draft_subsidy(sub, user, db)) is True


def test_draft_edit_allowed_for_member():
    user = _mk_user("employee", id=7)
    sub = _mk_subsidy_obj(created_by=5)
    db = _FakeDB(results=[_FakeResult(1)])  # SubsidyMember найден
    assert asyncio.run(subsidies._can_edit_draft_subsidy(sub, user, db)) is True


def test_draft_edit_denied_for_stranger():
    user = _mk_user("employee", id=9)
    sub = _mk_subsidy_obj(created_by=5)
    db = _FakeDB(results=[_FakeResult(None)])  # не участник
    assert asyncio.run(subsidies._can_edit_draft_subsidy(sub, user, db)) is False


def test_update_subsidy_endpoint_403_for_stranger_on_draft():
    """Интеграционно через сам PUT-хендлер: гейт бросает 403 РАНЬШЕ, чем
    хендлер дойдёт до подсчёта бюджета/commit — поэтому фейковой БД достаточно
    отдать саму субсидию, а затем «не участник»."""
    user = _mk_user("employee", id=9)
    sub = _mk_subsidy_obj(created_by=5, status="draft")
    db = _FakeDB(results=[_FakeResult(sub), _FakeResult(None)])
    body = SubsidyCreate(name="Субсидия C1", year=2026, budget=1000)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(subsidies.update_subsidy(1, body, db, user))
    assert exc_info.value.status_code == 403


def test_delete_subsidy_endpoint_403_for_stranger_on_draft():
    user = _mk_user("employee", id=9)
    sub = _mk_subsidy_obj(created_by=5, status="draft")
    db = _FakeDB(results=[_FakeResult(sub), _FakeResult(None)])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(subsidies.delete_subsidy(1, db, user))
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# C2 — утверждение: переводит в рабочее состояние, проставляет утвердившего,
# идемпотентно
# ---------------------------------------------------------------------------

def test_approve_subsidy_requires_subsidy_edit(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee", id=9)
    sub = _mk_subsidy_obj(status="draft")
    db = _FakeDB(results=[_FakeResult(sub)])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(subsidies.approve_subsidy(1, db, user))
    assert exc_info.value.status_code == 403


def test_approve_subsidy_moves_to_approved_and_stamps_approver(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "subsidy.edit"
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    async def _fake_calc_budget(db, subsidy_id):
        return 0.0
    monkeypatch.setattr(subsidies, "calculate_budget_from_categories", _fake_calc_budget)

    async def _fake_ceiling(db, subsidy_id):
        return {}
    monkeypatch.setattr(subsidies, "calculate_ceiling_forecast", _fake_ceiling)

    admin = _mk_user("manager", id=2)
    sub = _mk_subsidy_obj(status="draft", created_by=5, approved_by=None, approved_at=None)
    db = _FakeDB(results=[_FakeResult(sub)])

    out = asyncio.run(subsidies.approve_subsidy(1, db, admin))

    assert out["status"] == "approved"
    assert out["approved_by"] == 2
    assert out["approved_at"] is not None


def test_approve_subsidy_idempotent_second_call_is_noop(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "subsidy.edit"
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    async def _fake_calc_budget(db, subsidy_id):
        return 0.0
    monkeypatch.setattr(subsidies, "calculate_budget_from_categories", _fake_calc_budget)

    async def _fake_ceiling(db, subsidy_id):
        return {}
    monkeypatch.setattr(subsidies, "calculate_ceiling_forecast", _fake_ceiling)

    admin = _mk_user("manager", id=2)
    # Уже утверждена кем-то другим ранее — повторное утверждение НЕ переписывает.
    sub = _mk_subsidy_obj(status="approved", approved_by=99, approved_at="2026-01-01T00:00:00+00:00")
    db = _FakeDB(results=[_FakeResult(sub)])

    out = asyncio.run(subsidies.approve_subsidy(1, db, admin))

    assert out["status"] == "approved"
    assert out["approved_by"] == 99  # не перезаписано текущим пользователем


# ---------------------------------------------------------------------------
# C3 — запрет привязок к черновой субсидии (единый хелпер
# assert_subsidy_approved_for_binding, используется в wishes/purchases/contracts)
# ---------------------------------------------------------------------------

def test_binding_blocked_for_draft_subsidy():
    db = _FakeDB(results=[_FakeResult("draft")])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(assert_subsidy_approved_for_binding(db, 1))
    assert exc_info.value.status_code == 409


def test_binding_allowed_for_approved_subsidy():
    db = _FakeDB(results=[_FakeResult("approved")])
    asyncio.run(assert_subsidy_approved_for_binding(db, 1))  # не должно бросать


def test_binding_noop_when_no_subsidy_id():
    db = _FakeDB()  # если бы код полез в БД без причины — execute() отдал бы None и упал бы дальше
    asyncio.run(assert_subsidy_approved_for_binding(db, None))  # не должно бросать
    asyncio.run(assert_subsidy_approved_for_binding(db, 0))  # 0 — тоже «нет привязки»


# ---------------------------------------------------------------------------
# C3 — статическая проверка: хелпер реально вызван в местах создания/правки
# заявки/закупки/договора (не три копии проверки, а общий хелпер).
# По образцу test_publications_router_has_no_inline_can_publish.
# ---------------------------------------------------------------------------

def test_wishes_router_calls_binding_guard():
    src = Path("/app/app/routers/wishes.py").read_text(encoding="utf-8")
    assert src.count("assert_subsidy_approved_for_binding") >= 2  # create_wish + update_wish


def test_purchases_router_calls_binding_guard():
    src = Path("/app/app/routers/purchases.py").read_text(encoding="utf-8")
    assert src.count("assert_subsidy_approved_for_binding") >= 2  # create_purchase + update_purchase


def test_contracts_router_calls_binding_guard():
    src = Path("/app/app/routers/contracts.py").read_text(encoding="utf-8")
    assert src.count("assert_subsidy_approved_for_binding") >= 2  # create_contract + update_contract
