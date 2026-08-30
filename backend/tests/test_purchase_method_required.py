# -*- coding: utf-8 -*-
"""Способ закупки — обязательный пункт приказа и листа согласования.

Владелец дословно: «"Запрос цен" — это вариант конкурсной процедуры, так же
как и Аукцион — он же редукцион, а также Конкурс. Необходимо требовать
заполнения способа закупки для формирования приказа, так же для листа
согласования наверное тоже надо».

Без purchase_method приказ печатает пустой п.2 распорядительной части
(«2. Определить способ закупки: .») — документ юридически бессмысленный.
Массовость: 376 из 449 закупок в базе на момент задачи не имеют
purchase_method.

Offline, синхронно, без БД/HTTP — на подставных объектах (SimpleNamespace),
по образцу test_contract_documents_use_contract_items.py.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import documents as docs


def _mk_purchase(purchase_method=None, competitive_form=None):
    return SimpleNamespace(
        purchase_method=purchase_method,
        competitive_form=competitive_form,
    )


# ---------------------------------------------------------------------------
# Гейт: пустой purchase_method → 422 PURCHASE_METHOD_REQUIRED
# ---------------------------------------------------------------------------

def test_order_purchase_without_method_raises_422():
    p = _mk_purchase(purchase_method=None)
    with pytest.raises(HTTPException) as exc_info:
        docs._require_purchase_method_for_doc(p, "order_purchase")
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "PURCHASE_METHOD_REQUIRED"
    assert detail["message"] == "Не выбран способ закупки"
    assert detail["missing_fields"] == ["purchase_method"]
    assert detail["doc_type"] == "order_purchase"


def test_approval_sheet_without_method_raises_422():
    p = _mk_purchase(purchase_method=None)
    with pytest.raises(HTTPException) as exc_info:
        docs._require_purchase_method_for_doc(p, "approval_sheet")
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "PURCHASE_METHOD_REQUIRED"
    assert detail["doc_type"] == "approval_sheet"


def test_order_purchase_with_method_does_not_raise():
    p = _mk_purchase(purchase_method="single")
    docs._require_purchase_method_for_doc(p, "order_purchase")  # не должно бросать


def test_approval_sheet_with_method_does_not_raise():
    p = _mk_purchase(purchase_method="competitive")
    docs._require_purchase_method_for_doc(p, "approval_sheet")  # не должно бросать


def test_empty_string_method_still_raises():
    """Пустая строка — тоже "не выбран", не только None."""
    p = _mk_purchase(purchase_method="")
    with pytest.raises(HTTPException) as exc_info:
        docs._require_purchase_method_for_doc(p, "order_purchase")
    assert exc_info.value.status_code == 422


def test_non_order_doc_types_do_not_require_method():
    """service_note_payment и прочие не-приказные типы — способ закупки не обязателен."""
    p = _mk_purchase(purchase_method=None)
    for doc_type in ("service_note_payment", "tech_spec_request", "contract"):
        docs._require_purchase_method_for_doc(p, doc_type)  # не должно бросать


# ---------------------------------------------------------------------------
# Подпись способа закупки: конкретная форма конкурентной процедуры
# ---------------------------------------------------------------------------

def test_competitive_with_price_request_form_label():
    p = _mk_purchase(purchase_method="competitive", competitive_form="price_request")
    assert docs._purchase_method_label(p) == "Запрос цен"


def test_competitive_with_auction_form_label():
    p = _mk_purchase(purchase_method="competitive", competitive_form="auction")
    assert docs._purchase_method_label(p) == "Аукцион (редукцион)"


def test_competitive_with_tender_form_label():
    p = _mk_purchase(purchase_method="competitive", competitive_form="tender")
    assert docs._purchase_method_label(p) == "Конкурс"


def test_competitive_without_form_falls_back_to_generic_label():
    p = _mk_purchase(purchase_method="competitive", competitive_form=None)
    assert docs._purchase_method_label(p) == "Конкурсная процедура"


def test_single_method_label_unaffected():
    p = _mk_purchase(purchase_method="single")
    assert docs._purchase_method_label(p) == "Единственный поставщик"
