# -*- coding: utf-8 -*-
"""Дефект (2026-09-14): ЕГРЮЛ-обогащение разносило ФИО директора по полям
неправильно. contractors_lookup.py вызывал split_position_and_fio(row.get("g"),
signatory_position) — то есть передавал СЫРУЮ строку "ДОЛЖНОСТЬ: ФИО" целиком
И уже вычлененную должность одновременно. Первая же ветка split_position_and_fio
(`if position:`) считала, что raw уже чистое ФИО, и звала split_fio на ВСЕЙ
строке: "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Широков Владимир Константинович" резалась как
фамилия "ГЕНЕРАЛЬНЫЙ", имя "ДИРЕКТОР:", отчество "Широков Владимир Константинович".

Исправлено в двух местах (Правило №6 — один разборщик, не плодим второй):
  1. app/routers/contractors_lookup.py — больше не зовёт split_position_and_fio
     повторно; last/first/middle берутся через split_fio(_signatory), где
     _signatory уже очищен от должности внутри _split_signatory.
  2. app/services/fio.py::split_position_and_fio — сама функция стала устойчивой:
     если position передана И raw начинается с неё (с двоеточием после или без),
     префикс отрезается перед split_fio. Так что даже другой вызывающий,
     наступивший на те же грабли, не развалит ФИО.

Offline, синхронно, без БД — прямой импорт чистых функций.
"""
from app.services.fio import split_position_and_fio, split_fio


def test_position_prefix_with_colon_is_stripped_when_position_passed():
    # Тот самый случай из дефекта: raw — сырая строка ЕГРЮЛ целиком,
    # position — уже вычлененная должность.
    last, first, middle, position = split_position_and_fio(
        "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Широков Владимир Константинович",
        "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
    )
    assert last == "Широков"
    assert first == "Владимир"
    assert middle == "Константинович"
    assert position == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"


def test_same_string_without_position_argument():
    # Без переданной должности — идёт по ветке ":" и разбирает так же верно.
    last, first, middle, position = split_position_and_fio(
        "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Широков Владимир Константинович"
    )
    assert last == "Широков"
    assert first == "Владимир"
    assert middle == "Константинович"
    assert position == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"


def test_position_prefix_without_colon():
    last, first, middle, position = split_position_and_fio(
        "ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ Иванов Иван Иванович",
        "ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ",
    )
    assert last == "Иванов"
    assert first == "Иван"
    assert middle == "Иванович"
    assert position == "ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ"


def test_clean_fio_three_words_no_position_prefix_present():
    # position передана, но raw УЖЕ является чистым ФИО (не начинается с
    # должности) — старый рабочий путь для прочих вызывающих (напр.
    # contractor_lookup.py::_split_signatory на уже сохранённых записях БД)
    # не должен сломаться: raw используется как есть.
    last, first, middle, position = split_position_and_fio(
        "Петров Пётр Петрович", "Директор"
    )
    assert last == "Петров"
    assert first == "Пётр"
    assert middle == "Петрович"
    assert position == "Директор"


def test_double_surname_and_compound_middle_name_not_broken():
    last, first, middle, position = split_position_and_fio(
        "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Иванов-Петров Пётр Абрам-Ибрагимович",
        "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
    )
    assert last == "Иванов-Петров"
    assert first == "Пётр"
    assert middle == "Абрам-Ибрагимович"
    assert position == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"


def test_empty_string_returns_none_tuple_with_position_kept():
    last, first, middle, position = split_position_and_fio("", "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР")
    assert (last, first, middle) == (None, None, None)
    assert position == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"

    last, first, middle, position = split_position_and_fio(None)
    assert (last, first, middle, position) == (None, None, None, None)


def test_split_fio_still_used_directly_matches_signatory_reuse():
    # Ровно то, что теперь делает contractors_lookup.py: _signatory уже без
    # должности (composed FIO), разбирается напрямую через split_fio.
    last, first, middle = split_fio("Широков Владимир Константинович")
    assert (last, first, middle) == ("Широков", "Владимир", "Константинович")
