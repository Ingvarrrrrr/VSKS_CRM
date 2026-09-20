# -*- coding: utf-8 -*-
"""Владелец (2026-09-21), POST /api/purchases/{pid}/items/{item_id}/split
(app/routers/purchase_items_edit.py::split_purchase_item).

Два новых правила:

1. Позиция, пришедшая из заявки/плана (feo_planned_item_id и/или
   wish_item_id уже проставлены), — категория ФЭО зафиксирована планом (тот
   же принцип, что и у patch_purchase_item, см. test_purchase_feo_category_guard.py).
   Разбивка по РАЗНЫМ категориям для такой позиции запрещена — 422
   ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN (общий хелпер _raise_item_feo_category_locked,
   текст не копируется). Разбивка на части В ТОЙ ЖЕ категории допускается,
   только если КАЖДАЯ часть остаётся в текущей категории И привязана к той
   же плановой позиции — иначе тоже отказ.

2. Позиция БЕЗ привязок к заявке/плану — часть разбивки может нести флаг
   create_planned_item: true, чтобы сразу завести недостающую плановую
   позицию в своей категории (переиспользует POST /feo-planned-items/
   ::create_planned_item — тот же эндпоинт, что и «Создать в плане закупок»
   у заявки) и привязаться к ней. Ответ несёт created_planned_item_ids.

Первый блок (лок) — offline, синхронно, на подставных объектах (SimpleNamespace)
+ лёгкая FakeDB, по образцу test_purchase_feo_category_guard.py — лок срабатывает
ДО любого обращения к БД. Второй блок (создание плановых позиций) — на реальной
db_session/test_org (create_planned_item делает настоящие SELECT/INSERT/commit,
подделывать смысла нет) с current_user=superadmin (обходит матрицу доступа
_check_planned_item_write_access — она сама не предмет этого теста, уже
покрыта в другом месте) — split_purchase_item вызывается НАПРЯМУЮ как обычная
корутина (Depends(...) в сигнатуре — просто дефолты, см. test_planned_item_link_rules.py).
"""
import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import purchase_items_edit as pie
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase


# ---------------------------------------------------------------------------
# 1) Лок категории для позиции, привязанной к плану/заявке — offline.
# ---------------------------------------------------------------------------

def _mk_item(id_=200, purchase_id=100, **kw):
    base = dict(
        id=id_, purchase_id=purchase_id, wish_item_id=None, feo_category_id=1,
        feo_planned_item_id=None, item_name="Огнетушитель ОУ-2", over_plan=False,
        quantity=Decimal("66"), unit="шт", unit_price=Decimal("500"), total_price=Decimal("33000"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _mk_purchase(id_=100, **kw):
    base = dict(id=id_, purchase_number="З-100", status="plan_schedule", subsidy_id=None, feo_category_id=1)
    base.update(kw)
    return SimpleNamespace(**base)


def _mk_user(role="employee", id_=1):
    return SimpleNamespace(role=role, id=id_, full_name="Тестовый", username="tester")


class _FakeLockDB:
    """Лок обязан бросить ДО любого обращения к БД, кроме db.get() исходных
    item/purchase — та же идея, что и _FakeItemsDB в test_purchase_feo_category_guard.py."""

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
        raise AssertionError("лок обязан бросить до обращения к БД")


def _split_body(parts):
    return pie._ItemSplitBody(parts=[pie._ItemSplitPart(**p) for p in parts])


def test_split_locked_item_rejects_different_category():
    """(1) позиция с feo_planned_item_id -> split в другую категорию -> 422
    ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN."""
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    p = _mk_purchase()
    db = _FakeLockDB(it, p)
    body = _split_body([
        {"quantity": Decimal("41"), "feo_category_id": 1, "feo_planned_item_id": 77},
        {"quantity": Decimal("25"), "feo_category_id": 2, "feo_planned_item_id": None},
    ])
    user = _mk_user()

    async def run():
        await pie.split_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_split_locked_item_rejects_same_category_different_planned_item():
    """Та же категория у обеих частей, но одна часть отвязана от плановой
    позиции (feo_planned_item_id=None) — тоже отказ: «привязаны к той же
    плановой позиции», не только «та же категория»."""
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    p = _mk_purchase()
    db = _FakeLockDB(it, p)
    body = _split_body([
        {"quantity": Decimal("41"), "feo_category_id": 1, "feo_planned_item_id": 77},
        {"quantity": Decimal("25"), "feo_category_id": 1, "feo_planned_item_id": None},
    ])
    user = _mk_user()

    async def run():
        await pie.split_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_split_locked_item_rejects_create_planned_item_flag():
    """Заблокированная позиция + create_planned_item=true на части -> тоже
    отказ (нельзя заводить второй, независимый план рядом с уже
    существующим)."""
    it = _mk_item(feo_planned_item_id=77, feo_category_id=1)
    p = _mk_purchase()
    db = _FakeLockDB(it, p)
    body = _split_body([
        {"quantity": Decimal("41"), "feo_category_id": 1, "feo_planned_item_id": 77},
        {"quantity": Decimal("25"), "feo_category_id": 1, "feo_planned_item_id": 77, "create_planned_item": True},
    ])
    user = _mk_user()

    async def run():
        await pie.split_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


def test_split_locked_by_wish_item_id_alone_rejects_different_category():
    """Тот же лок работает и по wish_item_id без собственной feo_planned_item_id
    (см. докстринг _guard_item_feo_category_locked_from_plan — «или»)."""
    it = _mk_item(feo_planned_item_id=None, wish_item_id=321, feo_category_id=1)
    p = _mk_purchase()
    db = _FakeLockDB(it, p)
    body = _split_body([
        {"quantity": Decimal("41"), "feo_category_id": 1, "feo_planned_item_id": None},
        {"quantity": Decimal("25"), "feo_category_id": 2, "feo_planned_item_id": None},
    ])
    user = _mk_user()

    async def run():
        await pie.split_purchase_item(pid=100, item_id=200, body=body, db=db, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.detail["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"


# ---------------------------------------------------------------------------
# 2) create_planned_item на части позиции БЕЗ привязок — реальная БД
#    (create_planned_item делает настоящие SELECT/INSERT/commit).
# ---------------------------------------------------------------------------

async def _make_subsidy(db_session, org_id, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase_with_item(db_session, subsidy_id, feo_category_id, quantity, unit_price, **item_kw):
    p = Purchase(
        item_name="Тестовая закупка split-planned",
        status="plan_schedule",
        subsidy_id=subsidy_id,
    )
    db_session.add(p)
    await db_session.flush()
    it = PurchaseItem(
        purchase_id=p.id,
        item_name="Футболки поло",
        quantity=quantity,
        unit="шт",
        unit_price=unit_price,
        total_price=quantity * unit_price,
        feo_category_id=feo_category_id,
        **item_kw,
    )
    db_session.add(it)
    await db_session.commit()
    await db_session.refresh(p)
    await db_session.refresh(it)
    return p, it


@pytest.mark.asyncio
async def test_split_creates_and_links_planned_items_for_flagged_parts(db_session, test_org, superadmin_user):
    """(2) позиция без привязок + create_planned_item на ДВУХ частях -> две
    плановые позиции реально созданы (в СВОИХ категориях частей) и привязаны
    (part.feo_planned_item_id стал их id), ответ несёт оба id в
    created_planned_item_ids."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория A", budget=Decimal("1000000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Категория B", budget=Decimal("1000000"))
    p, it = await _make_purchase_with_item(
        db_session, subsidy.id, feo_category_id=cat_a.id,
        quantity=Decimal("66"), unit_price=Decimal("823"),
    )

    body = pie._ItemSplitBody(parts=[
        pie._ItemSplitPart(quantity=Decimal("41"), feo_category_id=cat_a.id, create_planned_item=True),
        pie._ItemSplitPart(quantity=Decimal("25"), feo_category_id=cat_b.id, create_planned_item=True),
    ])

    result = await pie.split_purchase_item(
        pid=p.id, item_id=it.id, body=body, db=db_session, current_user=superadmin_user,
    )

    assert result["ok"] is True
    assert len(result["created_planned_item_ids"]) == 2
    assert len(set(result["created_planned_item_ids"])) == 2  # два разных id

    from app.models.feo_planned_item import FeoPlannedItem
    fpi_a = await db_session.get(FeoPlannedItem, result["created_planned_item_ids"][0])
    fpi_b = await db_session.get(FeoPlannedItem, result["created_planned_item_ids"][1])
    assert fpi_a is not None and fpi_b is not None
    assert fpi_a.feo_category_id == cat_a.id
    assert fpi_b.feo_category_id == cat_b.id
    assert fpi_a.is_internal_plan is True
    assert fpi_b.is_internal_plan is True
    assert fpi_a.quantity == Decimal("41")
    assert fpi_b.quantity == Decimal("25")
    assert fpi_a.name == "Футболки поло"

    parts_by_qty = {float(pt["quantity"]): pt for pt in result["parts"]}
    assert parts_by_qty[41.0]["feo_planned_item_id"] == fpi_a.id
    assert parts_by_qty[25.0]["feo_planned_item_id"] == fpi_b.id


@pytest.mark.asyncio
async def test_split_without_flag_keeps_previous_behavior(db_session, test_org, superadmin_user):
    """(3) без флага create_planned_item — прежнее поведение: части без
    feo_planned_item_id остаются без плана, created_planned_item_ids пуст, ни
    одной новой FeoPlannedItem не заведено."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория A", budget=Decimal("1000000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Категория B", budget=Decimal("1000000"))
    p, it = await _make_purchase_with_item(
        db_session, subsidy.id, feo_category_id=cat_a.id,
        quantity=Decimal("66"), unit_price=Decimal("823"),
    )

    from sqlalchemy import select
    from app.models.feo_planned_item import FeoPlannedItem
    before_count = len((await db_session.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_([cat_a.id, cat_b.id]))
    )).all())

    body = pie._ItemSplitBody(parts=[
        pie._ItemSplitPart(quantity=Decimal("41"), feo_category_id=cat_a.id),
        pie._ItemSplitPart(quantity=Decimal("25"), feo_category_id=cat_b.id),
    ])

    result = await pie.split_purchase_item(
        pid=p.id, item_id=it.id, body=body, db=db_session, current_user=superadmin_user,
    )

    assert result["ok"] is True
    assert result["created_planned_item_ids"] == []
    for part in result["parts"]:
        assert part["feo_planned_item_id"] is None

    after_count = len((await db_session.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_([cat_a.id, cat_b.id]))
    )).all())
    assert after_count == before_count


@pytest.mark.asyncio
async def test_split_create_planned_item_rejects_with_explicit_feo_planned_item_id(db_session, test_org, superadmin_user):
    """create_planned_item=true ВМЕСТЕ с явным feo_planned_item_id на той же
    части -> 400 (нельзя и привязать к существующей, и создать новую)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория A", budget=Decimal("1000000"))
    p, it = await _make_purchase_with_item(
        db_session, subsidy.id, feo_category_id=cat_a.id,
        quantity=Decimal("66"), unit_price=Decimal("823"),
    )

    body = pie._ItemSplitBody(parts=[
        pie._ItemSplitPart(quantity=Decimal("41"), feo_category_id=cat_a.id, feo_planned_item_id=999, create_planned_item=True),
        pie._ItemSplitPart(quantity=Decimal("25"), feo_category_id=cat_a.id),
    ])

    with pytest.raises(HTTPException) as exc_info:
        await pie.split_purchase_item(pid=p.id, item_id=it.id, body=body, db=db_session, current_user=superadmin_user)
    assert exc_info.value.status_code == 400
