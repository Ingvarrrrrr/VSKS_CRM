"""Тесты app.services.product_type_keys — ключ вида товара для автосведения
карточек пожарной безопасности без артикула производителя (владелец,
27.10.2026). Чистые функции, БД не требуется."""
from app.services.product_type_keys import type_key, keys_match


def _chars(*pairs):
    return [{"name": n, "value": v, "unit": None} for n, v in pairs]


def test_op2_not_equal_op20():
    a = type_key("Огнетушитель порошковый ОП-2-АВСЕ РИФ")
    b = type_key("Огнетушитель порошковый ОП-20-АВСЕ РИФ")
    assert a.key is not None and b.key is not None
    assert a.key != b.key
    assert keys_match(a, b) != "уверенно"


def test_ou5_vse_equals_with_capability_in_parens():
    a = type_key("Огнетушитель углекислотный ОУ-5 ВСЕ РИФ")
    b = type_key("Огнетушитель углекислотный ОУ-5-ВСЕ (55В, С, Е) РИФ")
    assert a.kind == b.kind == "огнетушитель"
    assert a.key is not None and b.key is not None
    assert a.key == b.key
    assert keys_match(a, b) == "уверенно"


def test_zpu_china_not_equal_zpu_russia():
    a = type_key("Огнетушитель порошковый ОП-4 АВСЕ ЗПУ Китай РИФ")
    b = type_key("Огнетушитель порошковый ОП-4 АВСЕ ЗПУ Россия РИФ")
    assert a.key is not None and b.key is not None
    assert a.key != b.key
    assert keys_match(a, b) != "уверенно"


def test_chromированный_not_equal_plain():
    a = type_key("Огнетушитель порошковый ОП-4 АВСЕ хромированный РИФ")
    b = type_key("Огнетушитель порошковый ОП-4 АВСЕ РИФ")
    assert a.key is not None and b.key is not None
    assert a.key != b.key
    assert keys_match(a, b) != "уверенно"


def test_sign_f01_matches_descriptive_name():
    a = type_key(
        'Знак F01 Огнетушитель на самоклеящейся плёнке, 200х200',
        _chars(("Исполнение", "Самоклеящаяся пленка"), ("Размер", "200х200")),
    )
    b = type_key(
        "Знак F01 Огнетушитель (200х200 мм, самоклеящаяся плёнка)",
    )
    assert a.kind == b.kind == "знак"
    assert a.key is not None and b.key is not None
    assert a.key == b.key
    assert keys_match(a, b) == "уверенно"


def test_sign_f01_200_not_equal_f01_150():
    a = type_key(
        "Знак F01 Огнетушитель на самоклеящейся плёнке, 200х200",
    )
    b = type_key(
        "Знак F01 Огнетушитель на самоклеящейся плёнке, 150х150",
    )
    assert a.key is not None and b.key is not None
    assert a.key != b.key
    assert keys_match(a, b) != "уверенно"


def test_rukav_du51_20m_not_equal_du66_20m():
    a = type_key(
        "Рукав пожарный напорный РПМ(Д)-51-1,6МПа, с головками ГР-51, (20±1м), Берег",
        _chars(("Диаметр", "51"), ("Длина рукава", "20")),
    )
    b = type_key(
        "Рукав пожарный напорный РПМ(Д)-66-1,6МПа, с головками ГР-66, (20±1м), Берег",
        _chars(("Диаметр", "66"), ("Длина рукава", "20")),
    )
    assert a.kind == b.kind == "рукав"
    assert a.key is not None and b.key is not None
    assert a.key != b.key
    assert keys_match(a, b) != "уверенно"


def test_shkaf_310_nzb_not_equal_310_vzk():
    a = type_key("Шкаф ШПК-310 НЗБ")
    b = type_key("Шкаф ШП-К-310 ВЗК")
    assert a.kind == b.kind == "шкаф"
    # оба без бренда в названии — partial/key могут не собраться, но если
    # собрались (бренд найдётся как None на обеих сторонах — тогда key=None),
    # важно, что они точно не "уверенно" совпадают.
    assert keys_match(a, b) != "уверенно"
    if a.key is not None and b.key is not None:
        assert a.key != b.key


def test_shkaf_310_nzb_distinguishes_install_door_color():
    a = type_key("Шкаф пожарный ШПК-310 НЗБ Пульс")
    b = type_key("Шкаф пожарный ШП-К-310 ВЗК Пульс")
    assert a.key is not None and b.key is not None
    # НЗБ = навесной/закрытый/белый, ВЗК = встроенный/закрытый/красный.
    assert a.key[2] != b.key[2]  # install
    assert a.key[4] != b.key[4]  # color
    assert keys_match(a, b) != "уверенно"


def test_unrecognized_kind_returns_none():
    assert type_key("Комплект ЗПУ к ОП-4,5,6,8,10 (М-30*1,5) с индикатором") is None
    assert type_key("Колесо D-100мм (к ОУ-7,15 и ОП-25-40)") is None
    assert type_key("Инструкция по перезарядке огнетушителей") is None


def test_extinguishing_capability_conflict_blocks_match():
    a = type_key("Огнетушитель порошковый ОП-4 АВСЕ (2А, 55В, С, Е) РИФ")
    b = type_key("Огнетушитель порошковый ОП-4 АВСЕ (3А, 70В, С, Е) РИФ")
    assert a.key == b.key  # основной ключ совпал
    assert keys_match(a, b) is None  # но мягкий признак (способность) расходится


def test_diameter_bare_paren_vs_labeled_conflict_blocks_match():
    """Владелец, 27.10.2026 (правка после отчёта): «Огнетушитель ОУ-3
    (133)ВСЕ РИФ» (133 — диаметр без подписи) и «ОУ-3-BCE (d-114) РИФ»
    (114 — диаметр с подписью d-) совпадают по основному ключу, но это
    разные баллоны — диаметр расходится, автосведение запрещено."""
    a = type_key("Огнетушитель ОУ-3 (133)ВСЕ РИФ")
    b = type_key("Огнетушитель углекислотный ОУ-3-BCE (34В, С, Е) (d-114) РИФ")
    assert a.key == b.key
    assert keys_match(a, b) is None


def test_size_not_mentioned_on_either_side_stays_confident():
    """Та же правка: если размер не указан у ОБЕИХ сторон — это НЕ
    конфликт, пара остаётся «уверенно», как раньше (ОУ-5 без размеров,
    без типа трубы/баллона и без "разобран" у обоих)."""
    a = type_key("Огнетушитель углекислотный ОУ-5 ВСЕ Ярпожинвест")
    b = type_key("Огнетушитель углекислотный ОУ-5-BCE (55В, С, Е) Ярпожинвест")
    assert keys_match(a, b) == "уверенно"


def test_ou3_three_spasatel_variants_vs_one_m01_not_confident_due_to_ambiguity():
    """Владелец, 27.10.2026, правка после обзора 40 пар: три карточки
    Спасателя — ОДИНАКОВЫЙ тип трубы (сварная), но РАЗНЫЙ диаметр (133/
    133/114, диаметр — "мягкий" признак, не входит в жёсткий key) — все
    три буквально совпадают по key с ОДНОЙ карточкой Магазин01 (там
    диаметр вообще не указан, поэтому конфликта по диаметру не возникает).
    Без правила однозначности это даёт 3 "уверенно"-пары на один товар
    М01 — ложно; keys_match_unique должен понизить все три до
    "проверить", т.к. у Спасателя их несколько под одним ключом."""
    from app.services.product_type_keys import keys_match_unique

    variant_1 = type_key("Огнетушитель углекислотный ОУ-3 ВСЕ d=133 мм (сварная труба) Ярпожинвест")
    variant_2 = type_key("Огнетушитель углекислотный ОУ-3 ВСЕ d=133 мм (сварная труба) Ярпожинвест")
    variant_3 = type_key("Огнетушитель углекислотный ОУ-3 ВСЕ d=114 мм (сварная труба) Ярпожинвест")
    m01_item = type_key("Огнетушитель углекислотный ОУ-3-BCE (34В, С, Е) сварная труба Ярпожинвест")

    spasatel_peers = [variant_1, variant_2, variant_3]
    m01_peers = [m01_item]

    for variant in spasatel_peers:
        assert keys_match(variant, m01_item) == "уверенно"  # буквенный key совпадает
        assert keys_match_unique(variant, m01_item, spasatel_peers, m01_peers) != "уверенно"


def test_rukav_heads_only_not_equal_heads_with_stvol():
    """Тест владельца: "с головками ГР-50" vs "с головкой ГР-50 и стволом
    РС-50.01" — другая комплектация, не "уверенно"."""
    a = type_key(
        'Рукав пожарный напорный "Классик" РПК(В) 50-1,0-УХЛ1 с головками ГР-50 (20±1м)',
    )
    b = type_key(
        'Рукав пожарный напорный РПК(В)-50-1,0-УХЛ1 "Классик", с головкой ГР-50 и стволом РС-50.01 (20±1м)',
    )
    assert a.kind == b.kind == "рукав"
    assert keys_match(a, b) != "уверенно"


def test_rukav_without_heads_1to1_is_confident():
    """Тест владельца: «без головок» 1-к-1 (своя группа ровно одна карточка
    на каждой стороне) → "уверенно"."""
    from app.services.product_type_keys import keys_match_unique

    a = type_key(
        'Рукав пожарный напорный "Классик" РПК(В) 50-1,0-УХЛ1 без головок (20±1м)',
    )
    b = type_key(
        'Рукав пожарный напорный РПК(В)-50-1,0-УХЛ1 "Классик", без головок (20±1м), "Русарсенал"',
    )
    assert keys_match(a, b) == "уверенно"
    assert keys_match_unique(a, b, [a], [b]) == "уверенно"
