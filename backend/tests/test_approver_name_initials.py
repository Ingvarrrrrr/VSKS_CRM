# -*- coding: utf-8 -*-
"""Лист согласования обязан печатать ФИО согласующих сокращённо: «Фамилия
И.О.», а не целиком (владелец: «сколько раз говорил: Фамилия целиком, имя и
отчество — инициалы»).

`_format_initials_safe` — обёртка над `_format_initials`, которая НЕ ломает
уже сокращённое имя (реальный путь: для роли «Ответственный исполнитель» в
approvers_list подставляется значение, уже прошедшее через
`_format_initials` один раз — повторное сокращение не должно откусывать
инициал отчества).

Offline, синхронно, без БД — прямой импорт чистой функции.
"""
from app.routers.documents import _format_initials_safe


def test_full_fio_female():
    assert _format_initials_safe("Маркодеева Анастасия Олеговна") == "Маркодеева А.О."


def test_full_fio_male():
    assert _format_initials_safe("Борисов Александр Алексеевич") == "Борисов А.А."


def test_idempotent_already_two_initials():
    # Повторное применение НЕ должно откусывать инициал отчества
    # (баг _format_initials("Иванов И.В.") -> "Иванов И.").
    assert _format_initials_safe("Иванов И.В.") == "Иванов И.В."
    # Прогон второй раз ничего не меняет.
    once = _format_initials_safe("Иванов И.В.")
    assert _format_initials_safe(once) == "Иванов И.В."


def test_idempotent_single_initial():
    assert _format_initials_safe("Иванов И.") == "Иванов И."


def test_placeholder_untouched():
    assert _format_initials_safe("_________________") == "_________________"


def test_empty_string():
    assert _format_initials_safe("") == ""


def test_whitespace_only():
    assert _format_initials_safe("   ") == ""


def test_single_word_surname_only():
    assert _format_initials_safe("Иванов") == "Иванов"


def test_four_words_drops_fourth_part():
    # Третья часть («оглы») отбрасывается — так работает существующий
    # _format_initials, зафиксировано намеренно.
    assert _format_initials_safe("Алиев Рашид Гейдар оглы") == "Алиев Р.Г."
