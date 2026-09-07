# -*- coding: utf-8 -*-
"""Регресс: UnboundLocalError('art') на авансовой закупке без НДС.

stages_amounts.resolve_vat_exemption_article() и compute_amounts_and_vat()
раньше оставляли локальную `art` неприсвоенной, когда vat_applicable=False
и purchase_method='advance' — рендер order_purchase (и любого другого
документа, читающего эти функции) падал 500-й на закупках вроде id=886.

Offline, синхронно, на SimpleNamespace — по образцу
test_purchase_method_required.py.
"""
from types import SimpleNamespace

from app.services.documents.stages_amounts import (
    compute_amounts_and_vat,
    resolve_vat_exemption_article,
)


def _mk_advance_purchase_no_vat(**overrides):
    base = dict(
        purchase_method="advance",
        vat_applicable=False,
        vat_rate=None,
        vat_exemption_article=None,
        contractor=None,
        contract_form=None,
        items=[],
        contract_items=[],
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


def test_resolve_vat_exemption_article_advance_no_vat_does_not_raise():
    """Раньше: UnboundLocalError('art'). Теперь — как и без advance, пустая
    строка при отсутствии оснований (ручных/самозанятый/ГПХ)."""
    art = resolve_vat_exemption_article(SimpleNamespace(
        vat_exemption_article=None, contractor=None, contract_form=None,
    ), vat_app=False, is_advance=True)
    assert art == ""


def test_resolve_vat_exemption_article_advance_with_manual_basis():
    art = resolve_vat_exemption_article(SimpleNamespace(
        vat_exemption_article="ст. 346.11 НК РФ", contractor=None, contract_form=None,
    ), vat_app=False, is_advance=True)
    assert art == "ст. 346.11 НК РФ"


def test_resolve_vat_exemption_article_vat_applicable_short_circuits():
    """vat_app=True — art не резолвится вовсе, возвращается ''."""
    assert resolve_vat_exemption_article(
        SimpleNamespace(vat_exemption_article=None, contractor=None, contract_form=None),
        vat_app=True, is_advance=False,
    ) == ""


def test_compute_amounts_and_vat_advance_no_vat_does_not_raise():
    """Юнит-тест на compute_amounts_and_vat напрямую воспроизводит путь
    generate_document('order_purchase') для закупки-аванса без НДС."""
    p = _mk_advance_purchase_no_vat()
    result = compute_amounts_and_vat(p, "order_purchase")
    assert result["is_advance"] is True
    assert result["vat_app"] is False
    assert result["vat_info_line"] == ""  # нет items с vat_rate — не придумываем


def test_compute_amounts_and_vat_advance_no_vat_with_item_rates():
    it = SimpleNamespace(total_price=500, vat_rate="20")
    p = _mk_advance_purchase_no_vat(items=[it])
    result = compute_amounts_and_vat(p, "order_purchase")
    assert "20" in result["vat_info_line"]
