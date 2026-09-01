# -*- coding: utf-8 -*-
"""Рамочная голова договора без закупок внутри — печатается без позиций договора.

Владелец дословно: «Когда создаются рамочные договора, у них может ещё не
быть закупок внутри него, но договор уже заключили, к примеру на 600 000, но
чтобы его подписать, тоже надо согласовать его нужность, сформировать
договор, сделать лист согласования для него».

У рамочной головы (purchase_contract_type in ('framework_cumulative',
'framework_with_amount') AND parent_purchase_id IS NULL) вместо списка
ContractItem — общая сумма (Purchase.contract_price). Требование
CONTRACT_ITEMS_REQUIRED на неё не распространяется; PURCHASE_METHOD_REQUIRED —
распространяется (способ закупки к позициям не относится, см.
test_purchase_method_required.py — не тронут этой задачей).

До фикса код проверял несуществующее в данных значение 'framework_limited'
(в БД реально встречаются только 'framework_cumulative' и
'framework_with_amount') — из-за этого рамочная голова НЕ распознавалась как
рамочная нигде (recalc contract_price, гейт позиций договора), и:
  - contract_price затирался суммой ContractItem при переходе в «Заключён
    договор» (purchase_transitions.py);
  - формирование договора/листа согласования требовало позиций договора,
    которых у головы в принципе не бывает (documents.py).

Offline, синхронно, без БД/HTTP — на подставных объектах (SimpleNamespace), по
образцу test_contract_documents_use_contract_items.py /
test_purchase_method_required.py (см. project_pytest_asyncio_loop_flake —
async-тесты в этом проекте флакуют при параллельном запуске).
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import documents as docs
from app.routers.purchases import is_framework_head


def _mk_purchase(purchase_contract_type=None, parent_purchase_id=None,
                  contract_items=None, contract_price=None, items=None,
                  total_nmck=None, nmck=None, planned_total_price=None):
    return SimpleNamespace(
        purchase_contract_type=purchase_contract_type,
        parent_purchase_id=parent_purchase_id,
        contract_items=contract_items if contract_items is not None else [],
        contract_price=contract_price,
        items=items if items is not None else [],
        total_nmck=total_nmck,
        nmck=nmck,
        planned_total_price=planned_total_price,
    )


# ---------------------------------------------------------------------------
# is_framework_head — единый хелпер (purchases.py), переиспользуется
# purchase_transitions.py и documents.py, чтобы значения больше не разъезжались
# ---------------------------------------------------------------------------

def test_is_framework_head_true_for_framework_cumulative():
    p = _mk_purchase(purchase_contract_type="framework_cumulative", parent_purchase_id=None)
    assert is_framework_head(p) is True


def test_is_framework_head_true_for_framework_with_amount():
    p = _mk_purchase(purchase_contract_type="framework_with_amount", parent_purchase_id=None)
    assert is_framework_head(p) is True


def test_is_framework_head_false_for_single():
    p = _mk_purchase(purchase_contract_type="single", parent_purchase_id=None)
    assert is_framework_head(p) is False


def test_is_framework_head_false_for_framework_child():
    """Дочерняя закупка рамочного (parent_purchase_id заполнен) — НЕ голова."""
    p = _mk_purchase(purchase_contract_type="framework_cumulative", parent_purchase_id=42)
    assert is_framework_head(p) is False

    p2 = _mk_purchase(purchase_contract_type="framework_with_amount", parent_purchase_id=7)
    assert is_framework_head(p2) is False


def test_is_framework_head_false_for_nonexistent_framework_limited():
    """'framework_limited' в реальных данных НЕТ (framework_cumulative — 11
    закупок, framework_with_amount — 1, framework_limited — 0). Не должен
    считаться рамочной головой — старая проверка на это значение и была
    причиной бага (contract_price затирался суммой позиций)."""
    p = _mk_purchase(purchase_contract_type="framework_limited", parent_purchase_id=None)
    assert is_framework_head(p) is False


# ---------------------------------------------------------------------------
# _require_contract_items_for_doc — рамочная голова исключена из требования
# ---------------------------------------------------------------------------

def test_framework_cumulative_head_without_items_does_not_raise():
    p = _mk_purchase(purchase_contract_type="framework_cumulative", parent_purchase_id=None,
                      contract_items=[], contract_price=Decimal("600000"))
    docs._require_contract_items_for_doc(p, "contract_tz")  # не должно бросать


def test_framework_with_amount_head_without_items_does_not_raise():
    p = _mk_purchase(purchase_contract_type="framework_with_amount", parent_purchase_id=None,
                      contract_items=[], contract_price=Decimal("600000"))
    docs._require_contract_items_for_doc(p, "approval_sheet")  # не должно бросать


def test_regular_purchase_without_items_still_raises():
    """Обычная (не рамочная) закупка без позиций договора — гейт не тронут."""
    p = _mk_purchase(purchase_contract_type="single", parent_purchase_id=None,
                      contract_items=[])
    with pytest.raises(HTTPException) as exc_info:
        docs._require_contract_items_for_doc(p, "contract_tz")
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "CONTRACT_ITEMS_REQUIRED"


def test_framework_child_without_items_still_raises():
    """Дочерняя закупка рамочного (parent_purchase_id заполнен) — НЕ голова,
    позиции договора для неё по-прежнему обязательны."""
    p = _mk_purchase(purchase_contract_type="framework_cumulative", parent_purchase_id=42,
                      contract_items=[])
    with pytest.raises(HTTPException) as exc_info:
        docs._require_contract_items_for_doc(p, "contract_tz")
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "CONTRACT_ITEMS_REQUIRED"


# ---------------------------------------------------------------------------
# _resolve_doc_amount — сумма документа рамочной головы = contract_price
# ---------------------------------------------------------------------------

def test_framework_head_doc_amount_uses_contract_price():
    p = _mk_purchase(purchase_contract_type="framework_with_amount", parent_purchase_id=None,
                      contract_items=[], contract_price=Decimal("600000"))
    amount, is_planned = docs._resolve_doc_amount(p, "approval_sheet")
    assert amount == 600000.0
    assert is_planned is False
