# -*- coding: utf-8 -*-
"""Чистые функции (без БД) для новых переменных шаблонов документов
(владелец, 20.10.2026): город из адреса Заказчика, падежи названия
организации, родительный падеж сокращённых инициалов ФИО.

ПРАВИЛО №6: _extract_city_from_address — единственный разбор города из
адреса (formatting.py); _to_gen_org_name/_to_dat_org_name — тонкие обёртки
над единственным разбором головной группы фразы (morphology._to_case_position,
уже используется для должностей); _to_gen_fio_initials — тонкая обёртка над
обобщённым _to_case_fio_initials (раньше была только дательная версия)."""
from app.services.documents.formatting import _extract_city_from_address
from app.services.documents.contexts_org_people import _to_gen_org_name, _to_dat_org_name
from app.services.documents.morphology import _to_gen_fio_initials, _to_dat_fio_initials


# ── customer_city ────────────────────────────────────────────────────────

def test_extract_city_g_dot_space():
    assert _extract_city_from_address("г. Донецк, ул. Артёма, д. 1") == "Донецк"


def test_extract_city_g_dot_no_space():
    assert _extract_city_from_address("г.Донецк, ул. Артёма, д. 1") == "Донецк"


def test_extract_city_word_gorod():
    assert _extract_city_from_address("город Москва, Тверская ул., д. 1") == "Москва"


def test_extract_city_g_not_first_segment():
    assert _extract_city_from_address(
        "140100, Московская обл., г. Раменское, ул. Чугунова"
    ) == "Раменское"


def test_extract_city_federal_without_prefix():
    assert _extract_city_from_address("Санкт-Петербург, Невский пр-т, д. 1") == "Санкт-Петербург"


def test_extract_city_not_found():
    assert _extract_city_from_address("ул. Ленина, д. 5") == ""


def test_extract_city_empty():
    assert _extract_city_from_address("") == ""
    assert _extract_city_from_address(None) == ""


# ── customer_full_name_genitive / _dative ───────────────────────────────

def test_org_name_genitive_ano():
    assert _to_gen_org_name(
        "Автономная некоммерческая организация «ВСКС»"
    ) == "Автономной некоммерческой организации «ВСКС»"


def test_org_name_dative_ano():
    assert _to_dat_org_name(
        "Автономная некоммерческая организация «ВСКС»"
    ) == "Автономной некоммерческой организации «ВСКС»"


def test_org_name_genitive_tail_not_declined():
    assert _to_gen_org_name(
        "Региональное отделение Общероссийской общественной организации «Х»"
    ) == "Регионального отделения Общероссийской общественной организации «Х»"


def test_org_name_abbreviation_unchanged():
    assert _to_gen_org_name("АНО «ВСКС»") == "АНО «ВСКС»"
    assert _to_dat_org_name("АНО «ВСКС»") == "АНО «ВСКС»"


def test_org_name_starting_with_quote_unchanged():
    assert _to_gen_org_name("«Ромашка»") == "«Ромашка»"


def test_org_name_empty():
    assert _to_gen_org_name("") == ""
    assert _to_dat_org_name(None) == ""


# ── responsible_initials_gen / chief_accountant_initials_genitive ───────

def test_fio_initials_genitive_classic():
    assert _to_gen_fio_initials("Петрова Полина Петровна") == "Петровой П.П."


def test_fio_initials_dative_classic():
    assert _to_dat_fio_initials("Петрова Полина Петровна") == "Петровой П.П."


def test_fio_initials_genitive_non_classic_returns_nominative_initials():
    # 2 слова — не классическое ФИО для petrovich, возвращаем инициалы без падежа.
    assert _to_gen_fio_initials("Мадонна") == "Мадонна"
