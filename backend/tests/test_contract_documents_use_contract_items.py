# -*- coding: utf-8 -*-
"""Договорные документы обязаны брать позиции и суммы ТОЛЬКО из ContractItem
(«Как в договоре»), без отката на плановые purchase_items / НМЦК / план.

Требование владельца дословно: «В договор должны попадать только те
названия и та сумма, которая уже "Как в договоре", иначе бессмысленно. И
соответственно лист согласования можно делать только на основании позиций
"Как в договоре", оттуда берутся цены и суммы. Плановые не равно Договор».

Покрытие НЕ end-to-end: реальная БД/HTTP-эндпоинты здесь не поднимаются —
тестируются напрямую синхронные функции построения контекста из
backend/app/routers/documents.py (_build_items_list_from_contract_items,
_build_items_list_from_purchase_items, _resolve_doc_amount,
_require_contract_items_for_doc) на подставных объектах (SimpleNamespace).
Причина: асинхронные тесты в этом проекте страдают от flake «different
loop» при параллельном запуске (см. project_pytest_asyncio_loop_flake), а
сама async-обёртка generate_document() смешивает построение контекста с
кучей независимых DB-запросов (согласующие, подписанты и т.д.), которые к
предмету теста не относятся. Логика распределения источника данных (план
vs договор) вынесена в чистые синхронные функции специально, чтобы её
можно было проверить так.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import documents as docs


PLAN_NAME = "ПЛАНОВОЕ-НАЗВАНИЕ"
PLAN_PRICE = Decimal("100")
CONTRACT_NAME = "ДОГОВОРНОЕ-НАЗВАНИЕ"
CONTRACT_PRICE = Decimal("250")


def _mk_purchase_item(name, price, qty=1, unit="шт", item_type="товар", product=None):
    qty_d = Decimal(str(qty))
    price_d = Decimal(str(price))
    return SimpleNamespace(
        item_name=name,
        item_type=item_type,
        unit=unit,
        unit_price=price_d,
        quantity=qty_d,
        total_price=price_d * qty_d,
        product_id=getattr(product, "id", None),
        product=product,
        country_origin=None,
        vat_rate=None,
        feo_category_id=None,
        feo_planned_item_id=None,
    )


def _mk_contract_item(name, price, qty=1, unit="шт", product=None):
    qty_d = Decimal(str(qty))
    price_d = Decimal(str(price))
    return SimpleNamespace(
        name=name,
        quantity=qty_d,
        unit=unit,
        unit_price=price_d,
        total=price_d * qty_d,
        product=product,
    )


def _mk_purchase(items, contract_items, contract_price=None, total_nmck=None,
                  nmck=None, planned_total_price=None):
    return SimpleNamespace(
        items=items,
        contract_items=contract_items,
        contract_price=contract_price,
        total_nmck=total_nmck,
        nmck=nmck,
        planned_total_price=planned_total_price,
    )


def _make_test_purchase(**overrides):
    """Закупка с ДРУГИМИ плановыми и договорными позициями/ценами."""
    plan_items = [_mk_purchase_item(PLAN_NAME, PLAN_PRICE)]
    contract_items = [_mk_contract_item(CONTRACT_NAME, CONTRACT_PRICE)]
    return _mk_purchase(plan_items, contract_items, **overrides)


# ---------------------------------------------------------------------------
# CONTRACT_FAMILY_DOC_TYPES — состав константы
# ---------------------------------------------------------------------------

def test_contract_family_includes_required_types():
    expected = {
        "contract_services_large", "contract_services_small", "contract_services_food",
        "contract_goods_single", "contract_gph_individual", "contract_gph_individual_rid",
        "contract_repair_vehicle", "contract_repair_framework",
        "contract", "contract_tz", "tech_spec_contract", "approval_sheet",
    }
    assert expected <= docs.CONTRACT_FAMILY_DOC_TYPES


def test_contract_family_excludes_planned_and_other_types():
    excluded = (
        "tech_spec_request",  # ТЗ для ЗАПРОСА цен — плановый по смыслу
        "service_note_delivery", "service_note_payment",
        "service_note_procurement", "service_note_advance",
        "fabrikant_instruction", "fabrikant_application_form",
        "fabrikant_documentation", "fabrikant_contract_project",
        "order_purchase",
    )
    for doc_type in excluded:
        assert doc_type not in docs.CONTRACT_FAMILY_DOC_TYPES, doc_type


# ---------------------------------------------------------------------------
# Позиции договорного документа — только ContractItem, плановые НЕ фигурируют
# ---------------------------------------------------------------------------

def test_contract_items_list_uses_contract_values_not_plan():
    p = _make_test_purchase()
    items_list = docs._build_items_list_from_contract_items(p)

    names = [it["name"] for it in items_list]
    assert CONTRACT_NAME in names
    assert PLAN_NAME not in names

    # Цена в позиции — договорная (250), не плановая (100)
    prices = [it["unit_price"] for it in items_list]
    assert any("250" in price for price in prices)
    assert not any("100" in price for price in prices)

    # Поля шаблона сохранены (num/name/quantity/unit/unit_price/total_price/total)
    row = items_list[0]
    for key in ("num", "name", "quantity", "unit", "unit_price", "total_price", "total"):
        assert key in row


def test_plan_items_list_unaffected_uses_purchase_items():
    """tech_spec_request (плановый тип) — поведение НЕ должно измениться."""
    p = _make_test_purchase()
    items_list = docs._build_items_list_from_purchase_items(p)

    names = [it["name"] for it in items_list]
    assert PLAN_NAME in names
    assert CONTRACT_NAME not in names


# ---------------------------------------------------------------------------
# Деньги — договорной документ не откатывается на НМЦК/план
# ---------------------------------------------------------------------------

def test_contract_doc_amount_ignores_plan_and_nmck_fallback():
    p = _make_test_purchase(total_nmck=Decimal("999999"), nmck=Decimal("888888"))
    amount, is_planned = docs._resolve_doc_amount(p, "contract_tz")
    assert amount == 250.0
    assert is_planned is False


def test_contract_doc_amount_prefers_explicit_contract_price():
    """Если p.contract_price уже проставлен — берём его, а не сумму позиций."""
    p = _make_test_purchase(contract_price=Decimal("777"))
    amount, _ = docs._resolve_doc_amount(p, "approval_sheet")
    assert amount == 777.0


def test_plan_doc_amount_still_falls_back_to_plan_and_items_sum():
    """tech_spec_request (плановый тип) — старое поведение (план/НМЦК/сумма позиций)."""
    p = _make_test_purchase()
    amount, is_planned = docs._resolve_doc_amount(p, "tech_spec_request")
    assert amount == 100.0  # сумма плановых позиций
    assert is_planned is True  # contract_price ещё не проставлен


# ---------------------------------------------------------------------------
# Пустые contract_items → 422, а не молчаливый откат на план
# ---------------------------------------------------------------------------

def test_contract_doc_without_contract_items_raises_422():
    p = _mk_purchase(items=[_mk_purchase_item(PLAN_NAME, PLAN_PRICE)], contract_items=[])
    with pytest.raises(HTTPException) as exc_info:
        docs._require_contract_items_for_doc(p, "contract_tz")
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "CONTRACT_ITEMS_REQUIRED"
    assert "не заполнены" in detail["message"]
    assert "нечего" in detail["hint"]  # объясняет, почему документ не сформировать
    assert "Скопировать из заявки" in detail["hint"]


def test_plan_doc_without_contract_items_does_not_raise():
    p = _mk_purchase(items=[_mk_purchase_item(PLAN_NAME, PLAN_PRICE)], contract_items=[])
    docs._require_contract_items_for_doc(p, "tech_spec_request")  # не должно бросать
