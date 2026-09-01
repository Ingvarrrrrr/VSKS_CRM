# -*- coding: utf-8 -*-
"""B2/B3 (план владельца, 2026-09-01): настоящий гейт ЗАПИСИ дерева категорий ФЭО.

B2 — feo_category.edit (заведено этапом B1, коммит 208d848) как write-гейт на
create/import-preview/import/import-mapped/PUT/DELETE/move/reorder в
feo_categories.py, ПОВЕРХ существующего require_tab('feo_categories') (тот
остаётся гейтом ВИДИМОСТИ, не заменяется). Для правки/удаления/переноса/
переупорядочивания субсидия для проверки права обязана браться из УЖЕ
ЗАГРУЖЕННОЙ из БД категории, а не из тела запроса — иначе право обходится
подменой поля.

B3 — POST /unallocated («Не определена») дёргает рядовой сотрудник из формы
заявки/закупки, поэтому там своя (мягче) матрица доступа:
feo_category.edit ИЛИ wish.edit_feo (обе — по субсидии) ИЛИ вкладка
wishes/purchases.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace), по образцу
test_purchase_method_required.py. has_org_key/_has_key_in_any_org
монкипатчатся на самом модуле app.auth.permissions — проверяемый код делает
локальный `from app.auth.permissions import ...` ВНУТРИ функции при каждом
вызове, поэтому патч атрибута модуля подхватывается.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import permissions as perm_module
from app.routers import feo_categories as fc


# ---------------------------------------------------------------------------
# Подставные объекты
# ---------------------------------------------------------------------------

def _mk_user(role="employee", active_org_id=10, uoa_org_ids=None):
    return SimpleNamespace(
        role=role, id=1, org_id=active_org_id,
        _active_org_id=active_org_id, _uoa_org_ids=uoa_org_ids or [],
    )


def _mk_subsidy(org_id=10):
    return SimpleNamespace(org_id=org_id)


def _mk_category(id=1, subsidy_id=111, **kw):
    base = dict(
        id=id, subsidy_id=subsidy_id, parent_id=None, level=1, name="x",
        code=None, appendix=None, is_active=True, description=None,
        budget=None, feo_quantity=None, feo_unit=None, feo_amount=None,
        planned_quantity=None, planned_amount=None, unit=None,
        plan_source="planned_items", manual_plan_amount=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalars(self):
        return self

    def first(self):
        return self._obj

    def all(self):
        # Список в очереди (например все Subsidy разом для .scalars().all())
        # отдаётся как есть; одиночный объект — по-старому оборачивается в [obj].
        if isinstance(self._obj, list):
            return self._obj
        return [self._obj] if self._obj is not None else []


class _QueueDB:
    """Отдаёт канонные результаты по очереди на каждый db.execute(), не глядя
    в сам запрос — для этих тестов достаточно, т.к. гейт всегда бросает
    HTTPException раньше, чем handler дойдёт до второго/третьего execute()."""

    def __init__(self, *objs):
        self._queue = list(objs)

    async def execute(self, stmt):
        obj = self._queue.pop(0) if self._queue else None
        return _FakeResult(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _spy_require_write():
    """Заглушка _require_feo_category_write, которая ЗАПИСЫВАЕТ переданный
    subsidy_id и всегда бросает 403 — используется, чтобы поймать, ЧТО именно
    передал вызывающий handler, не прогоняя реальную has_org_key-логику."""
    calls = []

    async def _spy(current_user, db, subsidy_id=None):
        calls.append(subsidy_id)
        raise HTTPException(status_code=403, detail={"code": "spy", "message": "spy"})

    return calls, _spy


# ---------------------------------------------------------------------------
# B2: _require_feo_category_write — базовая матрица прав
# ---------------------------------------------------------------------------

def test_write_gate_employee_without_right_denied(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee")
    db = _QueueDB(_mk_subsidy(org_id=10))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fc._require_feo_category_write(user, db, 111))
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["code"] == "feo_category_edit_required"
    assert "редактировать справочник категорий ФЭО" in detail["message"]
    assert "Просмотр остаётся доступен" in detail["message"]


def test_write_gate_user_with_right_by_subsidy_passes(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "feo_category.edit" and org_id == 10 and subsidy_id == 111
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee")
    db = _QueueDB(_mk_subsidy(org_id=10))
    asyncio.run(fc._require_feo_category_write(user, db, 111))  # не должно бросать


def test_write_gate_superadmin_passes_without_touching_db():
    user = _mk_user("superadmin")
    db = _QueueDB()  # пустая очередь — если бы код полез в БД, execute() вернул бы None и упал бы дальше
    asyncio.run(fc._require_feo_category_write(user, db, 111))  # не должно бросать


def test_write_gate_no_subsidy_checks_any_available_org(monkeypatch):
    """import-preview/import: subsidy_id=None -> право по ЛЮБОЙ доступной пользователю орге."""
    seen_orgs = []

    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        seen_orgs.append(org_id)
        return org_id == 20

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    user = _mk_user("employee", active_org_id=10, uoa_org_ids=[20])
    db = _QueueDB()
    asyncio.run(fc._require_feo_category_write(user, db, None))
    assert seen_orgs == [10, 20]  # сначала активная орга, потом UOA-орги


def test_write_gate_no_subsidy_denied_when_no_org_has_right(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    user = _mk_user("employee")
    db = _QueueDB()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fc._require_feo_category_write(user, db, None))
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# B2: create — субсидия ЗАКОННО берётся из тела (объекта ещё не существует)
# ---------------------------------------------------------------------------

def test_create_category_gate_uses_body_subsidy(monkeypatch):
    calls, spy = _spy_require_write()
    monkeypatch.setattr(fc, "_require_feo_category_write", spy)
    user = _mk_user("employee")
    db = _QueueDB()
    category_data = SimpleNamespace(subsidy_id=777, planned_quantity=None, planned_amount=None)
    with pytest.raises(HTTPException):
        asyncio.run(fc.create_category(category_data, db, user))
    assert calls == [777]


# ---------------------------------------------------------------------------
# B2: PUT/DELETE/move/reorder — субсидия ИЗ ЗАГРУЖЕННОЙ КАТЕГОРИИ, а не из тела
# (защита от обхода подменой поля в запросе)
# ---------------------------------------------------------------------------

def test_update_category_gate_uses_loaded_category_subsidy_not_body(monkeypatch):
    calls, spy = _spy_require_write()
    monkeypatch.setattr(fc, "_require_feo_category_write", spy)
    user = _mk_user("employee")
    cat = _mk_category(id=5, subsidy_id=111)
    db = _QueueDB(cat)  # первый (и единственный, т.к. spy бросает раньше) execute() отдаёт cat
    # Тело запроса указывает ДРУГУЮ субсидию (999) — если бы код читал её отсюда,
    # атакующий мог бы подставить субсидию, где у него есть право.
    category_data = SimpleNamespace(subsidy_id=999, planned_quantity=None, planned_amount=None)
    with pytest.raises(HTTPException):
        asyncio.run(fc.update_category(5, category_data, db, user))
    assert calls == [111]  # subsidy_id категории из БД, НЕ 999 из тела


def test_delete_category_gate_uses_loaded_category_subsidy(monkeypatch):
    calls, spy = _spy_require_write()
    monkeypatch.setattr(fc, "_require_feo_category_write", spy)
    user = _mk_user("employee")
    cat = _mk_category(id=5, subsidy_id=222)
    db = _QueueDB(cat)
    with pytest.raises(HTTPException):
        asyncio.run(fc.delete_category(5, db, user))
    assert calls == [222]


def test_move_category_gate_uses_loaded_category_subsidy(monkeypatch):
    calls, spy = _spy_require_write()
    monkeypatch.setattr(fc, "_require_feo_category_write", spy)
    user = _mk_user("employee")
    cat = _mk_category(id=5, subsidy_id=333)
    db = _QueueDB(cat)
    with pytest.raises(HTTPException):
        asyncio.run(fc.move_category(5, {"parent_id": None}, db, user))
    assert calls == [333]


def test_reorder_category_gate_uses_loaded_category_subsidy(monkeypatch):
    calls, spy = _spy_require_write()
    monkeypatch.setattr(fc, "_require_feo_category_write", spy)
    user = _mk_user("employee")
    cat = _mk_category(id=5, subsidy_id=444)
    db = _QueueDB(cat)
    with pytest.raises(HTTPException):
        asyncio.run(fc.reorder_category(5, {"direction": "up"}, db, user))
    assert calls == [444]


# ---------------------------------------------------------------------------
# B2: _require_feo_import_write — дыра импорта (закрыта 2026-09-01).
# _do_feo_import (общий код /import и /import-mapped) определяет субсидию
# НЕ единым subsidy_id запроса, а построчно (колонка «Субсидия» файла +
# default_subsidy_id как фолбэк) — файл может затрагивать несколько субсидий
# сразу. Раньше вызывающие ручки проверяли право только «в любой доступной
# пользователю орге» (subsidy_id=None), вообще не глядя на субсидии, которые
# реально резолвятся построчно, — пользователь с правом только в организации A
# мог импортом писать категории в субсидию организации B. Ниже — прямая
# проверка новой функции: она обязана проверить КАЖДУЮ субсидию из
# touched_subsidies через уже существующий _require_feo_category_write
# (subsidy_id=...), тот же код, что и для create/PUT/DELETE одной категории.
# ---------------------------------------------------------------------------

def _mk_subsidy_row(id, name, org_id):
    return SimpleNamespace(id=id, name=name, org_id=org_id)


def test_import_write_gate_org_a_right_subsidy_in_org_b_denied(monkeypatch):
    """Право есть только в организации A (org_id=10); единственная целевая
    субсидия файла (111) принадлежит организации B (org_id=20) → отказ."""
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "feo_category.edit" and org_id == 10  # право только в орге A
    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee", active_org_id=10)
    sub_111 = _mk_subsidy_row(id=111, name="Субсидия Б (орг. B)", org_id=20)
    db = _QueueDB(sub_111)  # запрос Subsidy.id==111 внутри _require_feo_category_write

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fc._require_feo_import_write(user, db, {111}, [sub_111]))
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["subsidy_id"] == 111
    assert "Субсидия Б (орг. B)" in detail["message"]


def test_import_write_gate_right_on_both_subsidies_passes(monkeypatch):
    """Право есть по КАЖДОЙ из двух субсидий файла (111 в орге A, 222 в орге B) →
    гейт пропускает молча, обе субсидии реально проверены."""
    checked_subsidy_ids = []

    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        checked_subsidy_ids.append(subsidy_id)
        return key == "feo_category.edit"  # право есть в обеих организациях

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee", active_org_id=10, uoa_org_ids=[20])
    sub_111 = _mk_subsidy_row(id=111, name="Субсидия А", org_id=10)
    sub_222 = _mk_subsidy_row(id=222, name="Субсидия Б", org_id=20)
    db = _QueueDB(sub_111, sub_222)  # по одному Subsidy-лукапу на каждую проверяемую субсидию

    asyncio.run(fc._require_feo_import_write(user, db, {111, 222}, [sub_111, sub_222]))  # не должно бросать
    assert checked_subsidy_ids == [111, 222]  # обе субсидии реально дошли до проверки права


def test_import_write_gate_right_on_only_one_of_two_denied_names_it(monkeypatch):
    """Право есть только по субсидии 111 (орг. A), но НЕ по 222 (орг. B) →
    отказ с явным указанием, какая именно субсидия недоступна (222, орг. B)."""
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "feo_category.edit" and org_id == 10  # только орга A (субсидия 111)

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)

    user = _mk_user("employee", active_org_id=10, uoa_org_ids=[20])
    sub_111 = _mk_subsidy_row(id=111, name="Субсидия А (доступна)", org_id=10)
    sub_222 = _mk_subsidy_row(id=222, name="Субсидия Б (недоступна)", org_id=20)
    db = _QueueDB(sub_111, sub_222)  # 111 проверится и пройдёт, 222 — проверится и упадёт

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fc._require_feo_import_write(user, db, {111, 222}, [sub_111, sub_222]))
    detail = exc_info.value.detail
    assert detail["subsidy_id"] == 222
    assert "Субсидия Б (недоступна)" in detail["message"]
    assert "Субсидия А (доступна)" not in detail["message"]


def test_import_write_gate_none_user_skips_silently():
    """current_user=None (тот же контракт, что и снимок версии дерева в
    _do_feo_import) — гейт не лезет в БД и не бросает."""
    db = _QueueDB()  # пустая очередь — если бы код полез в БД, execute() отдал бы None
    asyncio.run(fc._require_feo_import_write(None, db, {111, 222}, []))  # не должно бросать


# ---------------------------------------------------------------------------
# B3: _check_unallocated_write_access — своя (мягче) матрица для POST /unallocated
# ---------------------------------------------------------------------------

def test_unallocated_gate_employee_without_right_denied(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False

    async def _fake_has_key_in_any_org(user, db, key):
        return False

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(perm_module, "_has_key_in_any_org", _fake_has_key_in_any_org)
    user = _mk_user("employee")
    db = _QueueDB()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "unallocated_category_access_required"


def test_unallocated_gate_feo_category_edit_by_subsidy_passes(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "feo_category.edit" and subsidy_id == 111

    async def _fake_has_key_in_any_org(user, db, key):
        return False

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(perm_module, "_has_key_in_any_org", _fake_has_key_in_any_org)
    user = _mk_user("employee")
    db = _QueueDB()
    asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))  # не должно бросать


def test_unallocated_gate_wish_edit_feo_by_subsidy_passes(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return key == "wish.edit_feo" and subsidy_id == 111

    async def _fake_has_key_in_any_org(user, db, key):
        return False

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(perm_module, "_has_key_in_any_org", _fake_has_key_in_any_org)
    user = _mk_user("employee")
    db = _QueueDB()
    asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))  # не должно бросать


def test_unallocated_gate_wishes_tab_passes(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False

    async def _fake_has_key_in_any_org(user, db, key):
        return key == "wishes"

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(perm_module, "_has_key_in_any_org", _fake_has_key_in_any_org)
    user = _mk_user("employee")
    db = _QueueDB()
    asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))  # не должно бросать


def test_unallocated_gate_purchases_tab_passes(monkeypatch):
    async def _fake_has_org_key(user, db, org_id, key, subsidy_id=None):
        return False

    async def _fake_has_key_in_any_org(user, db, key):
        return key == "purchases"

    monkeypatch.setattr(perm_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(perm_module, "_has_key_in_any_org", _fake_has_key_in_any_org)
    user = _mk_user("employee")
    db = _QueueDB()
    asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))  # не должно бросать


def test_unallocated_gate_superadmin_passes_without_touching_db():
    user = _mk_user("superadmin")
    db = _QueueDB()
    asyncio.run(fc._check_unallocated_write_access(user, db, 10, 111))  # не должно бросать


# ---------------------------------------------------------------------------
# B4 (2026-09-01): грант на КОНКРЕТНУЮ субсидию не должен вливаться в
# ГЛОБАЛЬНЫЙ набор прав пользователя. До фикса _subsidy_grant_keys() вливал
# ВСЕ ключи роли гранта (включая action-ключи типа feo_category.edit) прямо
# в _get_effective_simple(), а _has_key_in_any_org()/require_action() потом
# пропускали пользователя в ЛЮБОЙ орге. SUBSIDY_GRANT_NON_GLOBAL вычитает
# такие action-ключи из глобального пути; ключи-вкладки (видимость) обязаны
# остаться нетронутыми, иначе мы отбираем чтение, а не режем запись.
# ---------------------------------------------------------------------------

class _FakeExecResult:
    """Минимальная заглушка Result для _get_effective_simple: пустые
    RolePermission/override выборки (роль-матрица и org-overrides не
    участвуют в этом тесте — интересует только union по субсидия-гранту)."""

    def __init__(self, items=None):
        self._items = items or []

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._items)

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return None


class _FakeEmptyDB:
    async def execute(self, stmt):
        return _FakeExecResult([])


def test_subsidy_grant_action_key_excluded_from_global_effective(monkeypatch):
    """feo_category.edit, выданный ГРАНТОМ на субсидию, НЕ попадает в
    глобальный набор _get_effective_simple(include_subsidy_grants=True)."""
    async def _fake_subsidy_grant_keys(user_id, db):
        return {"feo_category.edit", "feo_categories"}

    monkeypatch.setattr(perm_module, "_subsidy_grant_keys", _fake_subsidy_grant_keys)

    user = _mk_user("employee")
    db = _FakeEmptyDB()
    effective = asyncio.run(
        perm_module._get_effective_simple(user, db, org_id=None, include_subsidy_grants=True)
    )
    assert "feo_category.edit" not in effective


def test_subsidy_grant_tab_key_still_reaches_global_effective(monkeypatch):
    """Ключ-ВКЛАДКА (видимость), выданный тем же грантом, В глобальный набор
    попадает — иначе у грант-пользователей пропадают пункты меню/данные."""
    async def _fake_subsidy_grant_keys(user_id, db):
        return {"feo_category.edit", "feo_categories"}

    monkeypatch.setattr(perm_module, "_subsidy_grant_keys", _fake_subsidy_grant_keys)

    user = _mk_user("employee")
    db = _FakeEmptyDB()
    effective = asyncio.run(
        perm_module._get_effective_simple(user, db, org_id=None, include_subsidy_grants=True)
    )
    assert "feo_categories" in effective


def test_has_org_key_with_subsidy_id_still_passes_by_grant(monkeypatch):
    """has_org_key(..., subsidy_id=...) обязан по-прежнему пропускать по
    гранту на конкретную субсидию — SUBSIDY_GRANT_NON_GLOBAL действует ТОЛЬКО
    на глобальный путь (_get_effective_simple), не на per-subsidy проверку."""
    async def _fake_get_subsidy_effective(user_id, subsidy_id, db):
        assert subsidy_id == 111
        return {"feo_category.edit"}

    monkeypatch.setattr(perm_module, "get_subsidy_effective", _fake_get_subsidy_effective)

    user = _mk_user("employee")
    db = _FakeEmptyDB()
    allowed = asyncio.run(
        perm_module.has_org_key(user, db, org_id=10, key="feo_category.edit", subsidy_id=111)
    )
    assert allowed is True
