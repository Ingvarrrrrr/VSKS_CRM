# -*- coding: utf-8 -*-
"""Рамочный договор без своей закупки не может пройти согласование/печать.

Владелец дословно: создал рамочный договор в реестре «Договоры» — нет кнопки
отправить на согласование необходимости, вывести на печать договор и лист
согласования.

Диагноз: согласование необходимости, печать договора и лист согласования
живут на Purchase (см. /api/purchases/{pid}/documents/{doc_type},
purchase_transitions.py), НЕ на Contract. Реестр «Договоры» — отдельная
сущность (contracts.py) без своего документооборота. У рамочных договоров,
заведённых прямо в реестре «Договоры», закупка не создаётся автоматически —
поэтому вся уже готовая машинерия до них не дотягивается.

Решение — POST /api/contracts/{contract_id}/approval-purchase: находит уже
привязанную рамочную голову или заводит новую, копируя поля из договора.
НЕ дублирует генерацию документов — только связывает Contract → Purchase.

Offline, синхронно, без БД/HTTP — на подставных объектах (SimpleNamespace) и
чистой функции-хелпере _build_approval_purchase_fields, по образцу
test_framework_contract_documents.py / test_purchase_method_required.py (см.
project_pytest_asyncio_loop_flake — async-тесты в этом проекте флакуют при
параллельном запуске).
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.routers.contracts import _build_approval_purchase_fields
from app.routers.purchases import is_framework_head


def _mk_contract(number="Д-42", date_=None, contract_type="framework_cumulative",
                  contractor_id=7, subsidy_id=3, subject="Поставка канцтоваров",
                  max_amount=Decimal("600000"), purchase_method="competitive"):
    return SimpleNamespace(
        id=99,
        number=number,
        date=date_ if date_ is not None else date(2026, 1, 15),
        contract_type=contract_type,
        contractor_id=contractor_id,
        subsidy_id=subsidy_id,
        subject=subject,
        max_amount=max_amount,
        purchase_method=purchase_method,
    )


def _mk_purchase(id_, contract_id, purchase_contract_type=None, parent_purchase_id=None):
    return SimpleNamespace(
        id=id_,
        contract_id=contract_id,
        purchase_contract_type=purchase_contract_type,
        parent_purchase_id=parent_purchase_id,
    )


# ---------------------------------------------------------------------------
# _build_approval_purchase_fields — маппинг полей Contract → Purchase kwargs
# ---------------------------------------------------------------------------

def test_fields_are_copied_from_contract():
    c = _mk_contract()
    fields = _build_approval_purchase_fields(c, assigned_user_id=11)

    assert fields["contract_id"] == 99
    assert fields["contractor_id"] == 7
    assert fields["subsidy_id"] == 3
    assert fields["subject"] == "Поставка канцтоваров"
    assert fields["contract_number"] == "Д-42"
    assert fields["contract_date"] == date(2026, 1, 15)
    assert fields["contract_price"] == Decimal("600000")  # = max_amount
    assert fields["purchase_contract_type"] == "framework_cumulative"  # = contract_type
    assert fields["purchase_method"] == "competitive"
    assert fields["parent_purchase_id"] is None
    assert fields["assigned_user_id"] == 11


def test_initial_status_matches_new_purchase_default():
    """Статус — начальный, как у обычной новой закупки (Purchase.status /
    PurchaseCreate.status оба по умолчанию 'wishes')."""
    c = _mk_contract()
    fields = _build_approval_purchase_fields(c, assigned_user_id=1)
    assert fields["status"] == "wishes"


def test_empty_contract_number_stays_empty_not_fabricated():
    """Пустой номер договора (''} → None у закупки, НЕ подставляем что-то
    своё. Это открывает дорогу уже готовой логике временного номера
    «ВРЕМ-…» (_generate_temp_contract_number в purchases.py) при первом
    формировании документа."""
    c = _mk_contract(number="")
    fields = _build_approval_purchase_fields(c, assigned_user_id=1)
    assert fields["contract_number"] is None


def test_none_contract_number_stays_none():
    c = _mk_contract(number=None)
    fields = _build_approval_purchase_fields(c, assigned_user_id=1)
    assert fields["contract_number"] is None


def test_framework_with_amount_type_is_copied_too():
    c = _mk_contract(contract_type="framework_with_amount")
    fields = _build_approval_purchase_fields(c, assigned_user_id=1)
    assert fields["purchase_contract_type"] == "framework_with_amount"


# ---------------------------------------------------------------------------
# Идемпотентность — поиск уже существующей рамочной головы через
# is_framework_head() (единый источник истины, используемый и endpoint'ом
# get_or_create_approval_purchase, и documents.py/purchase_transitions.py).
# ---------------------------------------------------------------------------

def test_existing_framework_head_is_found_not_recreated():
    """Ровно то, что делает endpoint: select Purchase WHERE contract_id=...,
    затем первая, для которой is_framework_head() истинно. Если такая уже
    есть — id возвращается, вторая закупка НЕ создаётся."""
    linked = [
        _mk_purchase(101, contract_id=99, purchase_contract_type="framework_cumulative", parent_purchase_id=None),
    ]
    existing = next((p for p in linked if is_framework_head(p)), None)
    assert existing is not None
    assert existing.id == 101

    # Повторный вызов той же логики над тем же списком — тот же результат,
    # вторая закупка не появляется (список не растёт).
    existing_again = next((p for p in linked if is_framework_head(p)), None)
    assert existing_again is existing
    assert len(linked) == 1


def test_child_purchase_of_framework_is_not_reused_as_head():
    """Дочерняя закупка рамочного (parent_purchase_id заполнен) — НЕ голова,
    её нельзя перепутать с искомой рамочной головой."""
    linked = [
        _mk_purchase(101, contract_id=99, purchase_contract_type="framework_cumulative", parent_purchase_id=55),
    ]
    existing = next((p for p in linked if is_framework_head(p)), None)
    assert existing is None


def test_no_linked_purchases_means_none_found():
    linked = []
    existing = next((p for p in linked if is_framework_head(p)), None)
    assert existing is None


def test_single_type_contract_purchase_not_treated_as_framework_head():
    """Явная защита от смешения: закупка с purchase_contract_type='single' на
    том же contract_id не должна считаться рамочной головой."""
    linked = [
        _mk_purchase(101, contract_id=99, purchase_contract_type="single", parent_purchase_id=None),
    ]
    existing = next((p for p in linked if is_framework_head(p)), None)
    assert existing is None
