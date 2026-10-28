"""Тесты сборки/разбора адреса по частям (app/services/address_compose.py).

Покрывает баг владельца (28.10.2026): «г.о. Бердянск» разбиралось как
«о.Бердянск»/«о. Бердянск» — регэксп искал префикс «г.» и не отличал его от
сокращения «г.о.» (городской округ)."""
import pytest

from app.services.address_compose import compose_address, parse_address, extract_settlement_name


# --- extract_settlement_name: баг г.о. -------------------------------------

def test_okrug_berdyansk_with_space_not_truncated():
    # Реальная строка из прода (contractors.id=54101)
    addr = "обл. Запорожская, г.о. Бердянск, пер. Металлистов, д. 5"
    assert extract_settlement_name(addr) == "Бердянск"
    assert extract_settlement_name(addr) != "о. Бердянск"
    assert extract_settlement_name(addr) != "о.Бердянск"


def test_okrug_berdyansk_without_space_not_truncated():
    addr = "Запорожская обл., г.о.Бердянск, пер. Металлистов, д. 5"
    assert extract_settlement_name(addr) == "Бердянск"
    assert extract_settlement_name(addr) != "о.Бердянск"


def test_okrug_plus_explicit_city_prefers_explicit_city():
    addr = "Запорожская обл., г.о. Бердянск, г. Бердянск, ул. Дружбы, д. 1"
    assert extract_settlement_name(addr) == "Бердянск"


# --- extract_settlement_name: старые кейсы (не регрессировать) ------------

@pytest.mark.parametrize("addr,expected", [
    ("г. Донецк, ул. Артёма, д. 1", "Донецк"),
    ("г.Донецк, ул. Артёма, д. 1", "Донецк"),
    ("город Москва, Тверская ул., д. 1", "Москва"),
    ("140100, Московская обл., г. Раменское, ул. Чугунова", "Раменское"),
    ("Санкт-Петербург, Невский пр-т, д. 1", "Санкт-Петербург"),
    ("ул. Ленина, д. 5", ""),
    ("", ""),
    (None, ""),
])
def test_extract_settlement_name_classic_cases(addr, expected):
    assert extract_settlement_name(addr) == expected


# --- parse_address -----------------------------------------------------

def test_parse_address_berdyansk_okrug_only():
    addr = "обл. Запорожская, г.о. Бердянск, пер. Металлистов, д. 5"
    parts = parse_address(addr)
    assert parts["settlement"] == "Бердянск"
    assert parts["settlement_type"] == "г.о."
    assert parts["street"].lower().startswith("пер")
    assert parts["house"] == "5"


def test_parse_address_full_example():
    addr = "140100, Московская область, г. Раменское, ул. Чугунова, д. 10, корп. 2, оф. 305"
    parts = parse_address(addr)
    assert parts["postal_code"] == "140100"
    assert parts["region"] == "Московская область"
    assert parts["settlement"] == "Раменское"
    assert parts["settlement_type"] == "г."
    assert parts["house"] == "10"
    assert parts["building"] == "2"
    assert parts["office"] == "305"


def test_parse_address_empty():
    parts = parse_address("")
    assert all(v == "" for v in parts.values())
    parts = parse_address(None)
    assert all(v == "" for v in parts.values())


# --- compose_address -----------------------------------------------------

def test_compose_address_basic():
    parts = {
        "postal_code": "140100",
        "region": "Московская область",
        "district": "",
        "settlement_type": "г.",
        "settlement": "Раменское",
        "street": "ул. Чугунова",
        "house": "10",
        "building": "2",
        "office": "305",
    }
    s = compose_address(parts)
    assert s == "140100, Московская область, г. Раменское, ул. Чугунова, д. 10, корп. 2, оф. 305"


def test_compose_address_skips_empty_parts():
    assert compose_address({"region": "Москва"}) == "Москва"
    assert compose_address({}) == ""
    assert compose_address(None) == ""


# --- Идемпотентность: собрал -> разобрал -> собрал снова = та же строка ---

@pytest.mark.parametrize("parts", [
    {
        "postal_code": "140100",
        "region": "Московская область",
        "settlement_type": "г.",
        "settlement": "Раменское",
        "street": "ул. Чугунова",
        "house": "10",
        "building": "2",
        "office": "305",
    },
    {
        "region": "Московская область",
        "settlement_type": "г.",
        "settlement": "Раменское",
        "street": "ул. Ленина",
        "house": "1",
    },
])
def test_compose_parse_compose_idempotent(parts):
    composed_once = compose_address(parts)
    reparsed = parse_address(composed_once)
    composed_twice = compose_address(reparsed)
    assert composed_twice == composed_once


# --- building_prefix: адрес доставки закупки (внешний API Фабриканта) -----
#
# publications_payload.py::_build_delivery_address() раньше собирал строку
# ВТОРЫМ независимым механизмом (конкатенация delivery_region/city/street/
# house/building), нарушая ПРАВИЛО №6. Теперь это тот же compose_address(),
# но с коротким префиксом корпуса "к." (а не "корп.", как у юр. адреса
# контрагента) — формат уходит во внешний API и его менять нельзя.

def test_compose_address_building_prefix_default_is_korp():
    assert compose_address({"settlement": "Москва", "building": "2"}) == "Москва, корп. 2"


def test_compose_address_building_prefix_override_for_delivery():
    parts = {"settlement": "Москва", "street": "ул. Ленина", "house": "1", "building": "2"}
    assert compose_address(parts) == "Москва, ул. Ленина, д. 1, корп. 2"
    assert compose_address(parts, building_prefix="к.") == "Москва, ул. Ленина, д. 1, к. 2"


def _old_build_delivery_address(postcode, region, city, street, house, building):
    """Точная копия СТАРОЙ (до рефакторинга) логики
    publications_payload.py::_build_delivery_address — используется только
    тут, чтобы доказать, что новая реализация через compose_address даёт
    побайтово ту же строку на реалистичных наборах данных."""
    parts = []
    if (postcode or "").strip():
        parts.append(postcode.strip())
    if (region or "").strip():
        parts.append(region.strip())
    if (city or "").strip():
        parts.append(city.strip())
    if (street or "").strip():
        parts.append(street.strip())
    if (house or "").strip():
        parts.append("д. " + house.strip())
    if (building or "").strip():
        parts.append("к. " + building.strip())
    return ", ".join(parts) if parts else None


@pytest.mark.parametrize("postcode,region,city,street,house,building", [
    ("190000", "Санкт-Петербург", "Санкт-Петербург", "Невский пр-т", "1", "2"),
    ("", "Московская область", "Раменское", "ул. Чугунова", "10", ""),
    ("", "", "Донецк", "ул. Артёма", "1", ""),
    ("", "Ростовская область", "", "", "", ""),
    ("140100", "", "", "", "", ""),
    ("", "", "", "", "", ""),
])
def test_build_delivery_address_matches_compose_address(postcode, region, city, street, house, building):
    old = _old_build_delivery_address(postcode, region, city, street, house, building)
    new = compose_address(
        {
            "postal_code": postcode,
            "region": region,
            "settlement": city,
            "street": street,
            "house": house,
            "building": building,
        },
        building_prefix="к.",
    ) or None
    assert new == old
