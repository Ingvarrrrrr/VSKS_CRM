# -*- coding: utf-8 -*-
"""НДС «для каждой позиции» (Purchase.vat_mode == 'per_item') — документы.

Владелец (закупка РЕЕ-2026-00918, 2026-09-16): проставил всем позициям 5%
вручную (режим «для каждой позиции»), но лист согласования отказал
VAT_EXEMPTION_ARTICLE_REQUIRED — проверка читала ТОЛЬКО шапку закупки
(vat_applicable/vat_rate/vat_exemption_article), построчные ставки
(PurchaseItem.vat_rate) игнорировались.

Offline, синхронно, на SimpleNamespace — по образцу
test_advance_vat_exemption_article.py / test_purchase_method_required.py.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.documents.templates import _require_vat_rate_for_doc
from app.services.documents.stages_amounts import compute_amounts_and_vat


def _mk_item(name="Товар", vat_rate=None, total_price=1000):
    return SimpleNamespace(item_name=name, vat_rate=vat_rate, total_price=total_price)


def _mk_purchase(**overrides):
    base = dict(
        vat_mode="per_item",
        vat_applicable=False,
        vat_rate=None,
        vat_exemption_article=None,
        contractor=None,
        contract_form=None,
        items=[],
        contract_items=[],
        purchase_method=None,
        planned_total_price=1000,
        contract_price=None,
        payment_amount=None,
        payment_amount_declared=None,
        status=None,
        purchase_contract_type=None,
        parent_purchase_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Гейт: _require_vat_rate_for_doc ветвится на per_item по vat_mode
# ---------------------------------------------------------------------------

def test_per_item_all_rates_filled_does_not_raise():
    p = _mk_purchase(items=[_mk_item(vat_rate="5%"), _mk_item(vat_rate="20%")])
    _require_vat_rate_for_doc(p, "approval_sheet")  # не должно бросать


def test_per_item_ignores_empty_header_vat_fields():
    """Ключевой регресс: шапка пустая (vat_applicable=False, vat_exemption_article=None),
    но режим per_item и все позиции со ставкой — документ формируется."""
    p = _mk_purchase(
        vat_applicable=False, vat_rate=None, vat_exemption_article=None,
        items=[_mk_item(vat_rate="5%")],
    )
    _require_vat_rate_for_doc(p, "approval_sheet")  # не должно бросать


def test_per_item_missing_rate_on_one_item_raises_422():
    p = _mk_purchase(items=[_mk_item(name="A", vat_rate="5%"), _mk_item(name="B", vat_rate=None)])
    with pytest.raises(HTTPException) as exc_info:
        _require_vat_rate_for_doc(p, "approval_sheet")
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "VAT_RATE_REQUIRED"
    assert detail["missing_fields"] == ["items.vat_rate"]
    assert "1" in detail["message"]


def test_per_item_missing_rate_counts_only_named_items():
    """Пустые (безымянные) строки не считаются «позицией без ставки»."""
    p = _mk_purchase(items=[_mk_item(name="", vat_rate=None), _mk_item(name="Товар", vat_rate="10%")])
    _require_vat_rate_for_doc(p, "approval_sheet")  # не должно бросать


def test_per_item_no_items_does_not_raise():
    p = _mk_purchase(items=[])
    _require_vat_rate_for_doc(p, "approval_sheet")  # не должно бросать


def test_per_item_multiple_missing_pluralizes_message():
    p = _mk_purchase(items=[_mk_item(name="A"), _mk_item(name="B"), _mk_item(name="C", vat_rate="20%")])
    with pytest.raises(HTTPException) as exc_info:
        _require_vat_rate_for_doc(p, "approval_sheet")
    detail = exc_info.value.detail
    assert "2" in detail["message"]
    assert "позиций" in detail["message"]


def test_uniform_mode_unaffected_by_items_vat_rate():
    """vat_mode='uniform' (default) — старое поведение по шапке, построчные
    ставки не читаются вовсе."""
    p = _mk_purchase(
        vat_mode="uniform", vat_applicable=False, vat_exemption_article=None,
        items=[_mk_item(vat_rate="5%")],
    )
    with pytest.raises(HTTPException) as exc_info:
        _require_vat_rate_for_doc(p, "approval_sheet")
    assert exc_info.value.detail["code"] == "VAT_EXEMPTION_ARTICLE_REQUIRED"


def test_doc_type_not_printing_vat_skips_check_entirely():
    p = _mk_purchase(items=[_mk_item(name="A", vat_rate=None)])
    _require_vat_rate_for_doc(p, "tech_spec_request")  # не в VAT_RATE_PRINTED_DOC_TYPES


# ---------------------------------------------------------------------------
# compute_amounts_and_vat: агрегация построчного НДС в контекст документа
# ---------------------------------------------------------------------------

def test_compute_amounts_per_item_single_rate_sums_correctly():
    it1 = _mk_item(vat_rate="20%", total_price=1200)  # НДС = 200
    it2 = _mk_item(vat_rate="20%", total_price=600)   # НДС = 100
    p = _mk_purchase(items=[it1, it2])
    result = compute_amounts_and_vat(p, "approval_sheet")
    assert result["vat_app"] is True
    assert result["vat_rate_val"] == 20
    assert result["vat_amount_val"] == pytest.approx(300.0)
    assert "20%" in result["vat_info_line"]


def test_compute_amounts_per_item_mixed_rates_reports_breakdown():
    it1 = _mk_item(vat_rate="5%", total_price=1050)   # НДС = 50
    it2 = _mk_item(vat_rate="20%", total_price=1200)  # НДС = 200
    p = _mk_purchase(items=[it1, it2])
    result = compute_amounts_and_vat(p, "approval_sheet")
    assert result["vat_app"] is True
    assert result["vat_rate_val"] is None
    assert result["vat_amount_val"] == pytest.approx(250.0)
    assert "по позициям" in result["vat_info_line"]
    assert "5%" in result["vat_info_line"] and "20%" in result["vat_info_line"]


def test_compute_amounts_per_item_no_priced_items_reports_no_vat():
    p = _mk_purchase(items=[])
    result = compute_amounts_and_vat(p, "approval_sheet")
    assert result["vat_app"] is False
    assert result["vat_amount_val"] == 0.0
    assert result["vat_info_line"] == "НДС не облагается"
