"""Тест build_order_substitution_economy (economy_preview.py) — правка
12.10.2026, план lazy-swimming-hollerith.md п.4б: «экономия видна» при
импорте факта, формула — та же _order_substituted_plan, что у дерева ФЭО.
"""
from decimal import Decimal

from app.services.historical_fact_import.economy_preview import build_order_substitution_economy
from app.services.feo_plan_common import _order_substituted_plan


def test_haval_example_matches_owner_text():
    """Боевой пример владельца: план позиции 25 000,00, заказано одной
    строкой 8 826,23 — экономия 16 173,77, новый план = заказанной сумме."""
    r = build_order_substitution_economy(
        planned_qty=1, planned_amount=25000,
        already_ordered_qty=0, already_ordered_sum=0,
        row_qty=1, row_amount=8826.23,
        planned_item_name="Haval Dargo Р937ХУ 180",
    )
    assert r is not None
    assert r["amount"] == Decimal("16173.77")
    assert r["new_plan"] == Decimal("8826.23")
    assert "16 173,77" in r["message"]
    assert "Haval Dargo Р937ХУ 180" in r["message"]
    assert "25 000,00" in r["message"]
    assert "8 826,23" in r["message"]


def test_no_economy_when_quantity_not_fully_covered():
    """Строка не доводит количество до плана целиком — не экономия, ещё
    нет сигнала (частичный заказ не замещает план, см. _order_substituted_plan)."""
    r = build_order_substitution_economy(
        planned_qty=2, planned_amount=50000,
        already_ordered_qty=0, already_ordered_sum=0,
        row_qty=1, row_amount=10000,
        planned_item_name="x",
    )
    assert r is None


def test_no_economy_when_already_fully_ordered_before_this_row():
    """Количество уже набрано ДО этой строки — не её заслуга, предупреждение
    не повторяется на каждой следующей строке той же позиции."""
    r = build_order_substitution_economy(
        planned_qty=1, planned_amount=25000,
        already_ordered_qty=1, already_ordered_sum=8826.23,
        row_qty=1, row_amount=500,
        planned_item_name="x",
    )
    assert r is None


def test_no_economy_when_order_not_cheaper_than_plan():
    """Заказ дороже или равен плану — замещение плана заказом всё равно
    происходит (формула дерева), но экономии (plan - new_plan > 0) нет."""
    r = build_order_substitution_economy(
        planned_qty=1, planned_amount=10000,
        already_ordered_qty=0, already_ordered_sum=0,
        row_qty=1, row_amount=12000,
        planned_item_name="x",
    )
    assert r is None


def test_matches_tree_formula_directly():
    """ПРАВИЛО №6 — new_plan здесь совпадает с _order_substituted_plan,
    зовём напрямую с теми же числами и сравниваем (не вторая формула)."""
    planned_qty, planned_amount = 1, 25000.0
    ordered_qty, ordered_sum = 1, 8826.23
    expected_plan = Decimal(str(_order_substituted_plan(planned_qty, ordered_sum, ordered_qty, planned_amount)))
    r = build_order_substitution_economy(
        planned_qty=planned_qty, planned_amount=planned_amount,
        already_ordered_qty=0, already_ordered_sum=0,
        row_qty=ordered_qty, row_amount=ordered_sum,
        planned_item_name="x",
    )
    assert r["new_plan"] == expected_plan.quantize(Decimal("0.01"))
