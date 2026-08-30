# -*- coding: utf-8 -*-
"""Путь ФЭО на листе согласования обязан идти от ДОГОВОРНЫХ позиций, а не
от плановых purchase_items (владелец, 2026-08-30).

Лист согласования уже переведён на договорные позиции (ContractItem, см.
CONTRACT_FAMILY_DOC_TYPES) — цены в нём договорные. У ContractItem своего
поля ФЭО нет, поэтому категория берётся у плановой PurchaseItem, из которой
договорная позиция скопирована (``source_item_id``). Владелец: «договорные
категории должны совпадать с плановыми» — это выполняется по построению,
т.к. категория физически та же запись.

Договорная позиция без ``source_item_id`` (заведена вручную, не копированием
из плана) не должна унаследовать чужую категорию — путь для неё остаётся
явно «не определён», не пустым молчанием и не подменой.

Offline, синхронно, без БД — на подставных объектах (SimpleNamespace).
"""
from decimal import Decimal
from types import SimpleNamespace

from app.routers.documents import (
    FEO_PATH_UNRESOLVED_LABEL,
    _build_contract_item_feo_paths,
)


def _feo_category(id_, name, parent_id=None):
    return SimpleNamespace(id=id_, name=name, parent_id=parent_id)


def _feo_path_nodes_factory(categories: dict):
    """Тот же алгоритм root→leaf, что используется в documents.py."""

    def _feo_path_nodes(node_id):
        path_nodes = []
        visited = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            cat = categories.get(node_id)
            if not cat:
                break
            path_nodes.append(cat)
            node_id = cat.parent_id
        path_nodes.reverse()
        return path_nodes

    return _feo_path_nodes


def _plan_item(id_, feo_category_id):
    return SimpleNamespace(id=id_, feo_category_id=feo_category_id)


def _contract_item(source_item_id, total):
    return SimpleNamespace(source_item_id=source_item_id, total=total)


def test_feo_path_taken_from_source_plan_item_category():
    """Договорная позиция со ссылкой на плановую → путь берётся из категории
    ТОЙ плановой позиции (не пересчитывается заново, не эвристика)."""
    categories = {
        1: _feo_category(1, "Административные расходы"),
        2: _feo_category(2, "Канцелярия", parent_id=1),
    }
    feo_path_nodes = _feo_path_nodes_factory(categories)

    plan_items = [_plan_item(101, feo_category_id=2)]
    contract_items = [_contract_item(source_item_id=101, total=Decimal("5000.00"))]

    result = _build_contract_item_feo_paths(contract_items, plan_items, feo_path_nodes)

    assert result == [("Административные расходы → Канцелярия", Decimal("5000.00"))]


def test_contract_item_without_source_gets_no_borrowed_category():
    """Договорная позиция БЕЗ source_item_id → путь пуст/«не определена»,
    чужая категория НЕ подставляется, даже если рядом есть позиции с
    известной категорией."""
    categories = {
        1: _feo_category(1, "Административные расходы"),
    }
    feo_path_nodes = _feo_path_nodes_factory(categories)

    plan_items = [_plan_item(101, feo_category_id=1)]
    contract_items = [
        _contract_item(source_item_id=101, total=Decimal("1000.00")),
        _contract_item(source_item_id=None, total=Decimal("777.00")),  # заведена вручную
    ]

    result = _build_contract_item_feo_paths(contract_items, plan_items, feo_path_nodes)

    assert ("Административные расходы", Decimal("1000.00")) in result
    unresolved = [r for r in result if r[0] == FEO_PATH_UNRESOLVED_LABEL]
    assert unresolved == [(FEO_PATH_UNRESOLVED_LABEL, Decimal("777.00"))]
    # Ни одна строка не выдаёт "Административные расходы" для позиции без source_item_id
    assert len(result) == 2


def test_order_and_count_follow_contract_items_not_plan_items():
    """Плановых позиций больше, чем договорных — подмена источника была бы
    видна по количеству/набору строк. Договорных категорий должно быть
    ровно столько, сколько различается среди ДОГОВОРНЫХ позиций."""
    categories = {
        1: _feo_category(1, "Категория А"),
        2: _feo_category(2, "Категория Б"),
        3: _feo_category(3, "Категория В"),
    }
    feo_path_nodes = _feo_path_nodes_factory(categories)

    # 5 плановых позиций, 3 разные категории — если бы путь строился из
    # плана (старое поведение), в результате были бы все 3 категории.
    plan_items = [
        _plan_item(1, feo_category_id=1),
        _plan_item(2, feo_category_id=2),
        _plan_item(3, feo_category_id=3),
        _plan_item(4, feo_category_id=1),
        _plan_item(5, feo_category_id=2),
    ]
    # Но в договор попали только 2 позиции, из категорий А и В (Б выпала —
    # например, позицию не стали заказывать).
    contract_items = [
        _contract_item(source_item_id=1, total=Decimal("100.00")),
        _contract_item(source_item_id=3, total=Decimal("300.00")),
    ]

    result = _build_contract_item_feo_paths(contract_items, plan_items, feo_path_nodes)

    paths = [r[0] for r in result]
    assert paths == ["Категория А", "Категория В"]
    assert "Категория Б" not in paths
    assert len(result) == 2


def test_multiple_contract_items_same_category_are_summed():
    """Несколько договорных позиций с одной унаследованной категорией
    складываются в одну строку с суммой (как и было для плановых)."""
    categories = {1: _feo_category(1, "Категория А")}
    feo_path_nodes = _feo_path_nodes_factory(categories)

    plan_items = [_plan_item(1, feo_category_id=1), _plan_item(2, feo_category_id=1)]
    contract_items = [
        _contract_item(source_item_id=1, total=Decimal("100.00")),
        _contract_item(source_item_id=2, total=Decimal("50.00")),
    ]

    result = _build_contract_item_feo_paths(contract_items, plan_items, feo_path_nodes)

    assert result == [("Категория А", Decimal("150.00"))]


def test_empty_contract_items_returns_empty_list():
    result = _build_contract_item_feo_paths([], [], _feo_path_nodes_factory({}))
    assert result == []
