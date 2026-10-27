"""Тесты app/services/documents/org_name_case.py — чистые функции, без БД.

Владелец (27.10.2026): полное наименование организации из ЕГРЮЛ лежит
КАПСОМ и в документах должно превращаться в обычный регистр, с
исключениями из карточки организации (аббревиатуры/устойчивые фразы).
"""
import pytest

from app.services.documents.org_name_case import (
    doc_case_org_name,
    doc_case_org_name_case,
    doc_quotes_only,
    org_name_exceptions,
)

NAME_1 = (
    'ВСЕРОССИЙСКАЯ ОБЩЕСТВЕННАЯ МОЛОДЕЖНАЯ ОРГАНИЗАЦИЯ '
    '"ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ"'
)
NAME_2 = (
    'АВТОНОМНАЯ НЕКОММЕРЧЕСКАЯ ОРГАНИЗАЦИЯ '
    '"ЦЕНТР ПОДГОТОВКИ ПОИСКОВИКОВ ДОБРОВОЛЬЦЕВ"'
)
NAME_3 = (
    'ЗАПОРОЖСКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ '
    'МОЛОДЕЖНОЙ ОРГАНИЗАЦИИ "ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ"'
)


def test_name1_default_case():
    assert doc_case_org_name(NAME_1, []) == (
        'Всероссийская общественная молодежная организация '
        '«Всероссийский студенческий корпус спасателей»'
    )


def test_name2_default_case():
    assert doc_case_org_name(NAME_2, []) == (
        'Автономная некоммерческая организация '
        '«Центр подготовки поисковиков добровольцев»'
    )


def test_name3_default_case():
    assert doc_case_org_name(NAME_3, []) == (
        'Запорожское региональное отделение всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )


def test_name3_dative_case():
    assert doc_case_org_name_case(NAME_3, [], 'datv') == (
        'Запорожскому региональному отделению всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )


def test_name3_with_phrase_exception():
    # Исключение задаёт собственное написание фразы — побеждает в любой позиции.
    result = doc_case_org_name(
        NAME_3, ['Всероссийской общественной молодежной организации']
    )
    assert 'Всероссийской общественной молодежной организации' in result
    assert result == (
        'Запорожское региональное отделение Всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )


def test_abbreviation_exception():
    name = 'ЗАПОРОЖСКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ "ВСКС"'
    assert doc_case_org_name(name, ['ВСКС']) == (
        'Запорожское региональное отделение «ВСКС»'
    )


def test_normal_case_not_touched():
    # В строке есть строчные буквы — регистр не трогаем (кавычки всё равно конвертируются).
    name = 'Автономная некоммерческая организация "Пример"'
    assert doc_case_org_name(name, []) == 'Автономная некоммерческая организация «Пример»'


@pytest.mark.parametrize('value', [None, ''])
def test_empty_input(value):
    assert doc_case_org_name(value, []) == (value or '')
    assert doc_case_org_name_case(value, [], 'gent') == (value or '')
    assert doc_quotes_only(value) == (value or '')


def test_doc_quotes_only_keeps_case():
    assert doc_quotes_only('АНО "ВСКС"') == 'АНО «ВСКС»'
    assert doc_quotes_only('АНО «ВСКС»') == 'АНО «ВСКС»'


def test_builtin_exceptions_rf_inn_ogrn():
    name = 'ОТДЕЛЕНИЕ РФ ПО ВОПРОСАМ ИНН И ОГРН'
    result = doc_case_org_name(name, [])
    assert 'РФ' in result
    assert 'ИНН' in result
    assert 'ОГРН' in result


def test_roman_numerals_and_digits_not_lowered():
    name = 'ОТДЕЛЕНИЕ № 1 ОКРУГ IV'
    result = doc_case_org_name(name, [])
    assert '1' in result
    assert 'IV' in result


class _FakeOrg:
    def __init__(self, doc_name_exceptions=None):
        self.doc_name_exceptions = doc_name_exceptions


def test_org_name_exceptions_parses_lines():
    org = _FakeOrg("ВСКС\n МЧС \n\nРоссийской Федерации\n")
    assert org_name_exceptions(org) == ['ВСКС', 'МЧС', 'Российской Федерации']


def test_org_name_exceptions_none_org():
    assert org_name_exceptions(None) == []


def test_org_name_exceptions_empty_field():
    assert org_name_exceptions(_FakeOrg(None)) == []
    assert org_name_exceptions(_FakeOrg("")) == []
