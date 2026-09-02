# -*- coding: utf-8 -*-
"""Владелец (2026-09-02): «должно быть уведомление глобально, если позиция
категории ФЭО вверху и в каждом товаре не соответствует друг другу — об этом
должен быть алярм прям стоять».

Это ПРО ДРУГОЕ, чем _reset_incompatible_item_feo_links (см.
test_feo_change_resets_item_links.py) — та функция сбрасывает несогласованные
привязки ПРИ смене категории шапки. Здесь проверяем расхождения, которые УЖЕ
накоплены и которые сброс не тронет, потому что категорию шапки никто не
менял (например, руками поправили feo_category_id позиции в обход шапки).

Проверяем app.routers.purchases._item_feo_mismatch — считает расхождение по
ОДНОЙ позиции закупки:
  1) позиция привязана к плановой позиции (feo_planned_item_id), категория
     которой НЕ совпадает с эффективной категорией позиции и не её потомок
     (переиспользует _category_within, см. test_feo_change_resets_item_links.py);
  2) feo_per_item ВЫКЛЮЧЕН у закупки, а feo_category_id позиции заполнен и
     отличается от категории шапки — в этом режиме позиции обязаны следовать
     за шапкой.

Offline, синхронно (asyncio.run внутри def test_...), без реального БД/HTTP —
на подставных объектах (SimpleNamespace + _FakeDB), по образцу
test_feo_change_resets_item_links.py.
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
#     11 "Закупка комплекта форменной одежды"     <- категория шапки закупки
#       12 "Пошив по индивидуальным меркам"        <- потомок категории шапки
#   20 "Техническое оснащение деятельности штаба" (root)
#     21 "Закупка канцелярских принадлежностей"    <- ЧУЖАЯ категория

CATEGORIES = {
    10: SimpleNamespace(id=10, parent_id=None, name="Организация мероприятий"),
    11: SimpleNamespace(id=11, parent_id=10, name="Закупка комплекта форменной одежды"),
    12: SimpleNamespace(id=12, parent_id=11, name="Пошив по индивидуальным меркам"),
    20: SimpleNamespace(id=20, parent_id=None, name="Техническое оснащение деятельности штаба"),
    21: SimpleNamespace(id=21, parent_id=20, name="Закупка канцелярских принадлежностей"),
}

CAT_NAMES = {cid: c.name for cid, c in CATEGORIES.items()}


def _mk_planned_items():
    return {
        1: SimpleNamespace(id=1, name="Пошив формы (чужая категория)", feo_category_id=21),
        2: SimpleNamespace(id=2, name="Пошив формы (ровно категория шапки)", feo_category_id=11),
        3: SimpleNamespace(id=3, name="Пошив формы (потомок категории шапки)", feo_category_id=12),
    }


def _mk_purchase(feo_category_id=11, feo_per_item=False):
    return SimpleNamespace(id=100, feo_category_id=feo_category_id, feo_per_item=feo_per_item)


def _mk_item(item_id=1, item_name="Позиция", feo_category_id=None, feo_planned_item_id=None):
    return SimpleNamespace(
        id=item_id, item_name=item_name,
        feo_category_id=feo_category_id, feo_planned_item_id=feo_planned_item_id,
    )


class _FakeDB:
    """db.get() отдаёт FeoCategory/FeoPlannedItem по словарю (как в
    test_feo_change_resets_item_links.py)."""

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


def _run_mismatch(purchase, item, db=None, planned_map=None):
    db = db or _FakeDB(categories=CATEGORIES, planned_items=_mk_planned_items())
    return asyncio.run(pr._item_feo_mismatch(
        db, purchase, item, cat_names=CAT_NAMES, planned_map=planned_map or _mk_planned_items(),
    ))


# ---------------------------------------------------------------------------
# Кейс 1: плановая позиция ЧУЖОЙ категории -> расхождение
# ---------------------------------------------------------------------------

def test_planned_item_foreign_category_is_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=False)
    # feo_category_id позиции не задан -> эффективная категория = категория шапки (11);
    # плановая позиция 1 из категории 21 (другая ветка) -> расхождение.
    item = _mk_item(feo_planned_item_id=1)

    result = _run_mismatch(purchase, item)

    assert result is not None
    assert result["reason"] == "planned"
    assert result["item_id"] == item.id
    assert "Пошив формы (чужая категория)" in result["message"]
    assert result["planned_category_id"] == 21
    assert result["item_category_id"] == 11


# ---------------------------------------------------------------------------
# Кейс 2: плановая позиция ТОЙ ЖЕ категории или её ПОТОМКА -> расхождения нет
# ---------------------------------------------------------------------------

def test_planned_item_same_category_no_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=False)
    item = _mk_item(feo_planned_item_id=2)  # план ровно категории 11 (= шапка)

    result = _run_mismatch(purchase, item)

    assert result is None


def test_planned_item_descendant_category_no_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=False)
    item = _mk_item(feo_planned_item_id=3)  # план категории 12 (потомок 11)

    result = _run_mismatch(purchase, item)

    assert result is None


# ---------------------------------------------------------------------------
# Кейс 3: feo_per_item=False и своя категория позиции отличается от шапки
#          -> расхождение (независимо от привязки к плановой позиции)
# ---------------------------------------------------------------------------

def test_per_item_off_own_category_diverges_from_header_is_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=False)
    item = _mk_item(feo_category_id=21, feo_planned_item_id=None)  # своя категория — 21, не 11

    result = _run_mismatch(purchase, item)

    assert result is not None
    assert result["reason"] == "header"
    assert result["header_category_id"] == 11
    assert result["item_category_id"] == 21


# ---------------------------------------------------------------------------
# Кейс 4: feo_per_item=True и своя категория отличается от шапки, но плановая
#          позиция ЕЙ соответствует -> расхождения НЕТ (per-item режим разрешает
#          позиции иметь свою категорию, отличную от шапки)
# ---------------------------------------------------------------------------

def test_per_item_on_own_category_diverges_but_planned_matches_no_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=True)
    # Своя категория позиции — 21 (не 11, но per_item=True это разрешает).
    # Плановая позиция 1 -> категория 21, совпадает с эффективной (собственной) категорией.
    item = _mk_item(feo_category_id=21, feo_planned_item_id=1)

    result = _run_mismatch(purchase, item)

    assert result is None


def test_per_item_on_own_category_diverges_and_planned_diverges_is_mismatch():
    """Контрольная проверка обратного: per_item=True, но плановая позиция НЕ
    соответствует даже собственной категории позиции -> расхождение остаётся
    (проверка 2 отключена per_item=True, но проверка 1 всё равно работает)."""
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=True)
    item = _mk_item(feo_category_id=21, feo_planned_item_id=2)  # план категории 11, не 21

    result = _run_mismatch(purchase, item)

    assert result is not None
    assert result["reason"] == "planned"


# ---------------------------------------------------------------------------
# Кейс 5: позиция БЕЗ привязки к плановой -> расхождения нет (при прочих
#          согласованных условиях)
# ---------------------------------------------------------------------------

def test_no_planned_link_no_mismatch():
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=False)
    item = _mk_item(feo_category_id=None, feo_planned_item_id=None)

    result = _run_mismatch(purchase, item)

    assert result is None


def test_no_planned_link_per_item_on_own_category_diverges_no_mismatch():
    """Без привязки к плановой позиции и per_item=True (проверка 2 отключена) —
    расхождения нет, даже если своя категория отличается от шапки."""
    purchase = _mk_purchase(feo_category_id=11, feo_per_item=True)
    item = _mk_item(feo_category_id=21, feo_planned_item_id=None)

    result = _run_mismatch(purchase, item)

    assert result is None
