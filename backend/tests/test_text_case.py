"""Тесты app.services.text_case.capitalize_first (ПРАВИЛО №6).

Решение владельца 14.10.2026: «где в названиях категорий аббревиатуры и всё
большими буквами — не трогать, исправлять только там, где должно быть с
большой, а написано с маленькой».
"""
from app.services.text_case import capitalize_first


def test_abbreviation_without_vowels_not_touched():
    # "лкп" — л,к,п без гласных, 3 буквы — аббревиатура, не трогаем.
    assert capitalize_first("лкп") == "лкп"


def test_ordinary_word_capitalized():
    assert capitalize_first("пожарное оборудование") == "Пожарное оборудование"


def test_already_upper_acronym_not_touched():
    # Первая буква уже заглавная — условие (а) правила не выполняется.
    assert capitalize_first("СИЗ") == "СИЗ"


def test_siz_lowercase_has_vowel_gets_capitalized():
    # "сиз" содержит гласную "и" -> по правилу это НЕ аббревиатура, поэтому
    # капитализируется как обычное слово (текущее поведение, зафиксировано
    # в задании). Отмечено владельцу в отчёте: "сиз" -> "Сиз".
    assert capitalize_first("сиз") == "Сиз"


def test_it_hyphen_word_gets_capitalized():
    # "it" содержит гласную "i" -> не аббревиатура, несмотря на то, что
    # всё слово "it-оборудование" целиком никогда не проверяется как одно
    # целое (проверяется только ведущая буквенная цепочка "it" до дефиса).
    assert capitalize_first("it-оборудование") == "It-оборудование"


def test_none_and_empty():
    assert capitalize_first(None) is None
    assert capitalize_first("") is None
    assert capitalize_first("   ") is None


def test_strips_surrounding_whitespace():
    assert capitalize_first("  мебель  ") == "Мебель"


def test_two_letter_abbreviation_without_vowels():
    assert capitalize_first("вс") == "вс"


def test_already_capitalized_word_not_touched():
    assert capitalize_first("Мебель") == "Мебель"
