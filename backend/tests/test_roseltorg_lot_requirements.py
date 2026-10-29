# -*- coding: utf-8 -*-
"""Требования площадки Росэлторг.Бизнес к лоту, проверенные разработчиком
живьём 29.10.2026 (13 размещённых процедур ДНР): единицы измерения ОКЕИ,
условия оплаты (lot.payment), населённый пункт доставки (lot.region).

Покрывает app/services/units_okei.py, app/services/roseltorg/lot_requirements.py
и app/services/roseltorg/items.py (полное название единицы в payload, не
исходное сокращение). Сетевых вызовов нет — все функции чистые.
"""
from app.services.units_okei import normalize_unit, okei_for_unit, is_okei_unit
from app.services.roseltorg.items import build_roseltorg_item_payloads, find_items_with_unknown_unit
from app.services.roseltorg.lot_requirements import (
    find_delivery_city,
    extract_city_from_text,
    build_lot_payment,
    resolve_roseltorg_region,
)


# ── units_okei.py: normalize_unit ───────────────────────────────────────────

def test_normalize_unit_legacy_spellings():
    assert normalize_unit("шт.") == "Штука"
    assert normalize_unit("шт") == "Штука"
    assert normalize_unit("ШТ.") == "Штука"
    assert normalize_unit("л") == "Литр; кубический дециметр"
    assert normalize_unit("компл") == "Комплект"
    assert normalize_unit("усл.") == "Условная единица"
    assert normalize_unit("кв.м") == "Квадратный метр"
    assert normalize_unit("т") == "Тонна; метрическая тонна (1000 кг)"


def test_normalize_unit_exact_canonical_passes_through():
    assert normalize_unit("Штука") == "Штука"
    assert normalize_unit("Литр; кубический дециметр") == "Литр; кубический дециметр"


def test_normalize_unit_unknown_returns_none():
    """«коробка», «канистра», «1» и т.п. — не выдумываем, фронт подсвечивает сам."""
    assert normalize_unit("коробка") is None
    assert normalize_unit("канистра") is None
    assert normalize_unit("1") is None
    assert normalize_unit("") is None
    assert normalize_unit(None) is None


def test_normalize_unit_rejects_not_accepted_forms():
    """«Литр», «Тонна», «Километр», «Миллилитр» (без дополнения) —
    площадка такие НЕ принимает, в списке только составные названия."""
    assert is_okei_unit("Литр") is False
    assert is_okei_unit("Тонна") is False
    assert is_okei_unit("Километр") is False
    assert is_okei_unit("Миллилитр") is False


def test_okei_code_for_canonical_names():
    assert okei_for_unit("шт.") == ("Штука", "796")
    assert okei_for_unit("Условная единица") == ("Условная единица", "876")
    assert okei_for_unit("коробка") == (None, None)


# ── items.py: build_roseltorg_item_payloads — отдаёт ПОЛНОЕ название ───────

def test_item_payload_sends_full_canonical_unit_name():
    rows = [{"name": "Товар", "quantity": 1, "unit": "шт.", "unit_price": 10, "description": ""}]
    out = build_roseltorg_item_payloads(rows)
    assert out[0]["unit"] == "Штука"
    assert out[0]["okeiId"] == "796"
    assert out[0]["isArbitraryUnit"] is False


def test_item_payload_compound_unit_name_sent_as_is():
    rows = [{"name": "Бензин", "quantity": 1, "unit": "л", "unit_price": 10, "description": ""}]
    out = build_roseltorg_item_payloads(rows)
    assert out[0]["unit"] == "Литр; кубический дециметр"
    assert out[0]["okeiId"] == "112"


def test_find_items_with_unknown_unit():
    rows = [
        {"name": "Коробки", "quantity": 1, "unit": "коробка", "unit_price": 1, "description": ""},
        {"name": "Болты", "quantity": 1, "unit": "шт.", "unit_price": 1, "description": ""},
        {"name": "Без единицы", "quantity": 1, "unit": "", "unit_price": 1, "description": ""},
    ]
    bad = find_items_with_unknown_unit(rows)
    assert bad == ["Коробки", "Без единицы"]


# ── lot_requirements.py: условия оплаты (lot.payment) ───────────────────────

def test_build_lot_payment_postpayment_default():
    payment = build_lot_payment(None, None, None, None)
    assert payment["type"] == "fact"
    assert payment["postpone_days"] is None
    assert payment["other_terms"] is None


def test_build_lot_payment_postponement():
    payment = build_lot_payment("postponement", 15, "calendar", None)
    assert payment["type"] == "postponement"
    assert payment["postpone_days"] == 15
    assert payment["typePostponeDays"] == "calendarDays"

    payment_work = build_lot_payment("postponement", 10, "work", None)
    assert payment_work["typePostponeDays"] == "workDays"


def test_build_lot_payment_prepayment():
    payment = build_lot_payment("prepayment", None, None, None)
    assert payment["type"] == "prepayment"


def test_build_lot_payment_other():
    payment = build_lot_payment("other", None, None, "Оплата при подписании акта")
    assert payment["type"] == "other"
    assert payment["other_terms"] == "Оплата при подписании акта"


# ── lot_requirements.py: поиск города (lot.region) ──────────────────────────

def test_find_delivery_city_donetsk_dnr():
    """Донецк, ДНР — ровно случай, проверенный живьём 29.10.2026."""
    row = find_delivery_city("Донецк", "Донецкая Народная Республика")
    assert row is not None
    assert row["id"] == "5f492efc-feef-4888-ba7e-e7d16928f800"
    assert "Донецк" in row["name"]


def test_find_delivery_city_donetsk_rostov_different_guid():
    """Второй Донецк — Ростовская область — другой guid, не перепутан с ДНР."""
    dnr = find_delivery_city("Донецк", "Донецкая Народная Республика")
    rostov = find_delivery_city("Донецк", "Ростовская область")
    assert rostov is not None
    assert rostov["id"] != dnr["id"]


def test_find_delivery_city_subject_abbreviation_matches():
    """Справочник площадки хранит «Ростовская обл» (сокращение) — должно
    совпасть с полным «Ростовская область» из ru_regions.json проекта."""
    row = find_delivery_city("Донецк", "Ростовская обл")
    assert row is not None


def test_find_delivery_city_unknown_city_returns_none():
    assert find_delivery_city("Город-которого-нет-12345", "Москва") is None


def test_extract_city_from_text():
    assert extract_city_from_text("344000, г. Донецк, ул. Ленина, д. 1") == "Донецк"
    assert extract_city_from_text(None) is None
    assert extract_city_from_text("без города тут") is None


def test_resolve_roseltorg_region_uses_delivery_city_raw_first():
    payload = {"delivery_city_raw": "Донецк", "delivery_region_raw": "Донецкая Народная Республика"}
    row = resolve_roseltorg_region(payload)
    assert row is not None
    assert row["id"] == "5f492efc-feef-4888-ba7e-e7d16928f800"


def test_resolve_roseltorg_region_falls_back_to_address_extraction():
    payload = {
        "delivery_city_raw": None,
        "delivery_region_raw": "Ростовская область",
        "delivery_address": "344000, г. Донецк, ул. Ленина, д. 1",
    }
    row = resolve_roseltorg_region(payload)
    assert row is not None


def test_resolve_roseltorg_region_none_when_no_city():
    assert resolve_roseltorg_region({}) is None
