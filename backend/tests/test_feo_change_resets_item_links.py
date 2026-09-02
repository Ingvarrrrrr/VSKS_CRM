# -*- coding: utf-8 -*-
"""Владелец (2026-09-02), баг с прода: суперадмин поменял категорию ФЭО в
шапке закупки («Организация мероприятий → Закупка комплекта форменной
одежды»), но плановая позиция, привязанная к товару (PurchaseItem.
feo_planned_item_id), осталась от старой категории («Техническое оснащение
деятельности штаба → Закупка канцелярских принадлежностей»). Лист
согласования печатает путь ФЭО от ПЛАНОВОЙ ПОЗИЦИИ — документ показывал
старую ветку, противоречащую шапке.

Требование владельца: «при изменении категории ФЭО выше привязка позиций
должна сбрасываться и требовать заново переопределения».

Проверяем app.routers.purchases._reset_incompatible_item_feo_links (+
вспомогательный _category_within) — общая точка, вызываемая и из PATCH
(autosave), и из PUT (явный Save), по образцу test_feo_change_after_approval.py:
  - смена категории шапки -> привязка к плановой позиции ЧУЖОЙ категории
    сбрасывается;
  - привязка к плановой позиции НОВОЙ категории (или её ПОТОМКА) сохраняется;
  - feo_per_item=False -> feo_category_id позиций подтягивается к новой
    категории шапки;
  - feo_per_item=True -> feo_category_id позиций НЕ трогаем, но
    feo_planned_item_id всё равно сбрасывается, если плановая позиция не
    принадлежит категории САМОЙ ПОЗИЦИИ (не шапки);
  - категория не менялась (old == new) -> ничего не сбрасывается, БД не
    трогаем.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace), как test_feo_change_after_approval.py.
"""
import asyncio
from types import SimpleNamespace

from app.routers import purchases as pr
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


# ---------------------------------------------------------------------------
# Подставные объекты
# ---------------------------------------------------------------------------

# Дерево категорий:
#   10 "Организация мероприятий" (root)
#     11 "Закупка комплекта форменной одежды"  <- НОВАЯ категория шапки
#       12 "Пошив по индивидуальным меркам"     <- потомок новой
#   20 "Техническое оснащение деятельности штаба" (root)
#     21 "Закупка канцелярских принадлежностей"  <- СТАРАЯ/чужая категория

def _mk_categories():
    return {
        10: SimpleNamespace(id=10, parent_id=None, name="Организация мероприятий"),
        11: SimpleNamespace(id=11, parent_id=10, name="Закупка комплекта форменной одежды"),
        12: SimpleNamespace(id=12, parent_id=11, name="Пошив по индивидуальным меркам"),
        20: SimpleNamespace(id=20, parent_id=None, name="Техническое оснащение деятельности штаба"),
        21: SimpleNamespace(id=21, parent_id=20, name="Закупка канцелярских принадлежностей"),
    }


def _mk_planned_items():
    return {
        1: SimpleNamespace(id=1, feo_category_id=21),  # чужая (старая) категория
        2: SimpleNamespace(id=2, feo_category_id=11),  # ровно новая категория
        3: SimpleNamespace(id=3, feo_category_id=12),  # потомок новой категории
    }


def _mk_item(feo_category_id=None, feo_planned_item_id=None):
    return SimpleNamespace(feo_category_id=feo_category_id, feo_planned_item_id=feo_planned_item_id)


class _FakeDB:
    """db.get() отдаёт FeoCategory/FeoPlannedItem по словарю."""

    def __init__(self, categories=None, planned_items=None):
        self._categories = categories or {}
        self._planned_items = planned_items or {}

    async def get(self, model, id_):
        if id_ is None:
            return None
        if model is FeoCategory:
            return self._categories.get(id_)
        if model is FeoPlannedItem:
            return self._planned_items.get(id_)
        return None


# ---------------------------------------------------------------------------
# _category_within — обход дерева вверх (совпадение или потомок)
# ---------------------------------------------------------------------------

def test_category_within_same_id():
    db = _FakeDB(categories=_mk_categories())
    assert asyncio.run(pr._category_within(db, 11, 11)) is True


def test_category_within_descendant():
    db = _FakeDB(categories=_mk_categories())
    assert asyncio.run(pr._category_within(db, 12, 11)) is True  # 12 потомок 11


def test_category_within_foreign_branch():
    db = _FakeDB(categories=_mk_categories())
    assert asyncio.run(pr._category_within(db, 21, 11)) is False  # 21 в другой ветке


def test_category_within_ancestor_is_not_within():
    db = _FakeDB(categories=_mk_categories())
    # 10 — родитель 11, но НЕ потомок; "новая категория или её потомок" не выполняется
    assert asyncio.run(pr._category_within(db, 10, 11)) is False


# ---------------------------------------------------------------------------
# _reset_incompatible_item_feo_links — сброс несогласованных привязок позиций
# ---------------------------------------------------------------------------

def test_link_to_foreign_category_planned_item_is_reset():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=None, feo_planned_item_id=1)  # план из чужой категории 21

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 1
    assert item.feo_planned_item_id is None


def test_link_to_new_category_planned_item_is_preserved():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    # feo_category_id уже = новая категория шапки -> pull-to-header не триггерится,
    # изолированно проверяем именно сохранение привязки плановой позиции.
    item = _mk_item(feo_category_id=11, feo_planned_item_id=2)  # план ровно новой категории

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 0
    assert item.feo_planned_item_id == 2


def test_link_to_descendant_of_new_category_is_preserved():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=11, feo_planned_item_id=3)  # план потомка новой категории

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 0
    assert item.feo_planned_item_id == 3


def test_link_preserved_even_when_own_category_pulled_to_header():
    """feo_per_item=False, feo_category_id позиции ещё не проставлена (None) —
    подтягивается к новой категории шапки (count==1 из-за этого), но привязка
    к плановой позиции НОВОЙ категории всё равно сохраняется, а не сбрасывается
    заодно с категорией."""
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=None, feo_planned_item_id=2)

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 1
    assert item.feo_category_id == 11
    assert item.feo_planned_item_id == 2  # НЕ сброшена


def test_per_item_off_pulls_item_category_to_new_header_category():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=21, feo_planned_item_id=None)  # своя категория осталась старой

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 1
    assert item.feo_category_id == 11  # подтянулась к новой категории шапки


def test_per_item_on_does_not_touch_item_category():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=21, feo_planned_item_id=None)  # своя категория — 21

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=True, db=db,
    ))

    assert count == 0
    assert item.feo_category_id == 21  # НЕ тронута — режим "своя категория на позицию"


def test_per_item_on_still_resets_link_foreign_to_items_own_category():
    """feo_per_item=True: категория позиции (21) не про шапку (11), но привязанная
    плановая позиция (2, категория 11) не принадлежит СОБСТВЕННОЙ категории
    позиции (21) -> сбрасываем feo_planned_item_id, категорию не трогаем."""
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=21, feo_planned_item_id=2)

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=True, db=db,
    ))

    assert count == 1
    assert item.feo_category_id == 21  # своя категория не тронута
    assert item.feo_planned_item_id is None  # но привязка сброшена


def test_per_item_on_preserves_link_matching_items_own_category():
    """feo_per_item=True: плановая позиция (1, категория 21) принадлежит
    СОБСТВЕННОЙ категории позиции (21, никак не связана со сменой шапки) ->
    сохраняем, несмотря на смену категории шапки."""
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item = _mk_item(feo_category_id=21, feo_planned_item_id=1)

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=True, db=db,
    ))

    assert count == 0
    assert item.feo_planned_item_id == 1


def test_category_unchanged_resets_nothing():
    db = _FakeDB(categories=_mk_categories(), planned_items=_mk_planned_items())
    item_foreign = _mk_item(feo_category_id=21, feo_planned_item_id=1)
    item_stale_own_cat = _mk_item(feo_category_id=20, feo_planned_item_id=None)

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item_foreign, item_stale_own_cat],
        old_category_id=11, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 0
    assert item_foreign.feo_planned_item_id == 1
    assert item_stale_own_cat.feo_category_id == 20


def test_dangling_planned_item_reference_is_reset():
    """Плановая позиция удалена (FK SET NULL ещё не отработал / db.get вернул
    None) — привязку тоже надо сбросить, а не оставлять висящей."""
    db = _FakeDB(categories=_mk_categories(), planned_items={})
    item = _mk_item(feo_category_id=None, feo_planned_item_id=999)

    count = asyncio.run(pr._reset_incompatible_item_feo_links(
        [item], old_category_id=20, new_category_id=11, per_item_mode=False, db=db,
    ))

    assert count == 1
    assert item.feo_planned_item_id is None
