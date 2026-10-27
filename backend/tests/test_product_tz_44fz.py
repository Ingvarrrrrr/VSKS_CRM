"""Тесты build_tz_44fz (backend/app/services/product_tz_44fz.py) — сборка
технического задания по 44-ФЗ (ст. 33) из характеристик каталога. Примеры
взяты с реальной выгрузки (небулайзер OMRON с прода, владелец 26.10.2026) и
из ревью 20 примеров tz44_samples.md (владелец, 26.10.2026, второй заход)."""
import pytest

from app.services.product_tz_44fz import build_tz_44fz


def _omron_characteristics():
    return [
        {"name": "Средний размер частиц", "value": "3,0", "unit": "мкм"},
        {"name": "Объем камеры", "value": "2-7", "unit": "мл"},
        {"name": "Вес", "value": "3.5", "unit": "кг", "in_description": False},
        {"name": "Уровень шума, децибел", "value": "55"},
        {"name": "Страна производства", "value": "Россия"},
        {"name": "Магазин-источник", "value": "Ozon"},
        {"name": "Торговая марка", "value": "OMRON"},
        {"name": "Артикул", "value": "NE-C900-RU"},
        {"name": "Количество в упаковке", "value": "9", "unit": "шт"},
        {"name": "Длина", "value": "27,2", "unit": "см"},
    ]


def test_omron_full_card():
    text, needs_review = build_tz_44fz(
        name="Небулайзер компрессорный OMRON NE-C900-RU",
        characteristics=_omron_characteristics(),
        description=None,
        manufacturer="OMRON",
        article="NE-C900-RU",
    )
    assert text is not None
    lines = text.split("\n")
    assert lines[0] == "Наименование: Небулайзер компрессорный"
    assert lines[1] == ""

    body = "\n".join(lines[2:])
    assert "Средний размер частиц: не более 3,0 мкм" in body
    assert "Объем камеры: от 2 до 7 мл" in body
    assert "Уровень шума, децибел: не более 55" in body
    assert "Количество в упаковке: 9 шт" in body
    assert "Длина: от 24,5 до 29,9 см" in body

    # Прод-ревью 26.10.2026 (п.A1): in_description=False больше не исключает
    # характеристику из ТЗ 44-ФЗ (относится к карточке/точному описанию, не
    # к ТЗ) — "Вес" теперь печатается.
    assert "Вес: не более 3,5 кг" in body
    assert "Страна" not in body
    assert "Магазин" not in body
    assert "Торговая марка" not in body
    assert "Артикул" not in body
    assert "OMRON" not in text
    assert "NE-C900-RU" not in text
    assert "C900" not in text


def test_not_more_keyword_direction():
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[{"name": "Средний размер частиц", "value": "3,0", "unit": "мкм"}],
        description=None,
    )
    assert "не более 3,0 мкм" in text


def test_value_already_range_wins_over_name_keyword():
    text, _ = build_tz_44fz(
        name="Камера",
        characteristics=[{"name": "Объем камеры", "value": "2-7", "unit": "мл"}],
        description=None,
    )
    assert "от 2 до 7 мл" in text


def test_in_description_false_does_not_exclude():
    # Прод-ревью 26.10.2026 (п.A1): in_description=False — про карточку/
    # точное описание поставщика, не про ТЗ 44-ФЗ; характеристика остаётся.
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[
            {"name": "Вес", "value": "3.5", "unit": "кг", "in_description": False},
            {"name": "Цвет", "value": "Белый"},
        ],
        description=None,
    )
    assert "Вес: не более 3,5 кг" in text
    assert "Цвет: Белый" in text


def test_not_more_compound_keyword_wins_over_generic_not_less():
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[{"name": "Уровень шума, децибел", "value": "55"}],
        description=None,
    )
    assert "не более 55" in text


def test_country_and_shop_excluded():
    text, _ = build_tz_44fz(
        name="Товар",
        characteristics=[
            {"name": "Страна производства", "value": "Россия"},
            {"name": "Магазин-источник", "value": "Ozon"},
            {"name": "Цвет", "value": "Белый"},
        ],
        description=None,
    )
    assert "Страна" not in text
    assert "Магазин" not in text
    assert "Цвет: Белый" in text


def test_brand_and_article_excluded_from_name_and_body():
    text, needs_review = build_tz_44fz(
        name="Небулайзер компрессорный портативный OMRON NE-C900-RU",
        characteristics=[
            {"name": "Торговая марка", "value": "OMRON"},
            {"name": "Артикул", "value": "NE-C900-RU"},
            {"name": "Цвет", "value": "Белый"},
        ],
        description=None,
        manufacturer="OMRON",
        article="NE-C900-RU",
    )
    assert needs_review is False
    assert "OMRON" not in text
    assert "NE-C900-RU" not in text
    assert "Небулайзер" in text


def test_exact_keyword_count_in_package():
    text, _ = build_tz_44fz(
        name="Товар",
        characteristics=[{"name": "Количество в упаковке", "value": "9", "unit": "шт"}],
        description=None,
    )
    assert "Количество в упаковке: 9 шт" in text


def test_length_default_range_plus_minus_10_percent():
    text, _ = build_tz_44fz(
        name="Товар",
        characteristics=[{"name": "Длина", "value": "27,2", "unit": "см"}],
        description=None,
    )
    assert "Длина: от 24,5 до 29,9 см" in text


def test_do_prefix_means_not_more():
    text, _ = build_tz_44fz(
        name="Трансформатор промышленный",
        characteristics=[{"name": "Напряжение максимальное", "value": "до 25 кВ"}],
        description=None,
    )
    assert "не более 25 кВ" in text


def test_ot_prefix_means_not_less():
    text, _ = build_tz_44fz(
        name="Насос погружной",
        characteristics=[{"name": "Напор", "value": "от 5", "unit": "м"}],
        description=None,
    )
    assert "не менее 5 м" in text


def test_brand_mentioned_in_other_characteristic_value_marked_equivalent():
    text, _ = build_tz_44fz(
        name="Товар подъёмный",
        characteristics=[
            {"name": "Совместимость", "value": "Только с OMRON"},
        ],
        description=None,
        manufacturer="OMRON",
    )
    assert "OMRON" not in text
    assert "или эквивалент" in text


def test_fallback_from_description_when_no_characteristics():
    text, _ = build_tz_44fz(
        name="Товар без характеристик",
        characteristics=None,
        description="Цвет: Белый\nМатериал: Пластик\nЭто просто предложение без двоеточия.",
    )
    assert text is not None
    assert "Цвет: Белый" in text
    assert "Материал: Пластик" in text


def test_empty_product_returns_none():
    text, needs_review = build_tz_44fz(name="", characteristics=None, description=None)
    assert text is None
    assert needs_review is False


def test_no_characteristics_and_no_parsable_description_returns_none():
    text, needs_review = build_tz_44fz(
        name="Товар",
        characteristics=[],
        description="Просто свободный текст без двоеточий.",
    )
    assert text is None


def test_needs_review_when_name_too_short_after_cleanup():
    text, needs_review = build_tz_44fz(
        name="OMRON NE-C900-RU",
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
        manufacturer="OMRON",
        article="NE-C900-RU",
    )
    assert needs_review is True
    assert "Наименование: OMRON NE-C900-RU" in text


# ================= Ревью 20 примеров tz44_samples.md (26.10.2026) =========


# --- п.1: марки/модели/коды в названии ------------------------------------

def test_p1_name_strips_pure_latin_brand_words():
    # "Масло G-ENERGY Synthetic Active 5W-40 5л" — G-ENERGY/Synthetic/Active
    # латинские слова без цифр убираются целиком; "5л" (размерный токен) —
    # остаётся; "5W-40" (вязкость, буква+цифры без признаков размера) — тоже
    # убирается как код/модель.
    text, _ = build_tz_44fz(
        name="Масло G-ENERGY Synthetic Active 5W-40 5л",
        characteristics=[{"name": "Цвет", "value": "Жёлтый"}],
        description=None,
    )
    name_line = text.split("\n")[0]
    assert "G-ENERGY" not in name_line
    assert "Synthetic" not in name_line
    assert "Active" not in name_line
    assert "5W-40" not in name_line
    assert "5л" in name_line


def test_p1_name_strips_model_codes_keeps_size_tokens():
    # "Автоматический выключатель ВА47-29-3C20 20А/3п/ на Din-рейку" —
    # ВА47-29-3C20 (буквы+цифры, не размер) убирается; "20А" (размер) и
    # "Din" (белый список) остаются.
    text, _ = build_tz_44fz(
        name="Автоматический выключатель ВА47-29-3C20 20А на Din-рейку",
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
    )
    name_line = text.split("\n")[0]
    assert "ВА47-29-3C20" not in name_line
    assert "20А" in name_line
    assert "Din" in name_line


def test_p1_name_strips_lt_suffix_and_empty_parens():
    text, _ = build_tz_44fz(
        name="Ножницы комбинированные НКГС-80 (LT-7)",
        characteristics=[{"name": "Цвет", "value": "Красный"}],
        description=None,
    )
    name_line = text.split("\n")[0]
    assert "LT-7" not in name_line
    assert "(" not in name_line and ")" not in name_line


def test_p1_global_catalog_brands_param_strips_name_and_marks_equivalent():
    # Бренд, который для ЭТОГО товара не указан ни в manufacturer, ни в
    # характеристиках "Бренд/Производитель" — но есть в каталожном наборе
    # brands (собран по ВСЕМ товарам) — всё равно вырезается.
    text, _ = build_tz_44fz(
        name="Крепление на голову для камер GoPro Fujimi",
        characteristics=[
            {"name": "Совместимость", "value": "Камеры Sony и GoPro"},
            {"name": "Цвет", "value": "Чёрный"},
        ],
        description=None,
        brands=frozenset({"GoPro", "Fujimi", "Sony"}),
    )
    assert "GoPro" not in text
    assert "Fujimi" not in text
    assert "Sony" not in text
    assert "или эквивалент" in text


# --- п.2: допуск только к "чистому" числу ----------------------------------

def test_p2_dirty_value_with_extra_word_kept_as_is():
    text, _ = build_tz_44fz(
        name="Видеорегистратор автомобильный",
        characteristics=[{"name": "Объектив", "value": "6-слойная стеклянная линза"}],
        description=None,
    )
    assert "Объектив: 6-слойная стеклянная линза" in text


def test_p2_dirty_value_with_x_separator_and_words_kept_as_is():
    text, _ = build_tz_44fz(
        name="Акустическая система напольная",
        characteristics=[{"name": "Акустическая система", "value": "1 x 200 мм низкочастотный динамик"}],
        description=None,
    )
    assert "Акустическая система: 1 x 200 мм низкочастотный динамик" in text


def test_p2_dirty_value_with_pin_suffix_kept_as_is():
    text, _ = build_tz_44fz(
        name="Микрофон проводной студийный",
        characteristics=[{"name": "Разъем микрофона", "value": "2-4-pin XLR"}],
        description=None,
    )
    assert "Разъем микрофона: 2-4-pin XLR" in text


def test_p2_free_text_with_embedded_range_kept_as_is():
    text, _ = build_tz_44fz(
        name="Пуско-зарядное устройство профессиональное",
        characteristics=[{
            "name": "Ток зарядки аккумуляторов",
            "value": "регулируемый ступенчато в диапазоне от 20 А до 100 А",
        }],
        description=None,
    )
    assert "регулируемый ступенчато в диапазоне от 20 А до 100 А" in text
    assert "не менее" not in text
    assert "не более" not in text


def test_p2_viscosity_grade_kept_as_is_not_ranged():
    text, _ = build_tz_44fz(
        name="Масло моторное синтетическое",
        characteristics=[{"name": "Вязкость по SAE", "value": "5W-40"}],
        description=None,
    )
    assert "Вязкость по SAE: 5W-40" in text


def test_p2_dimensions_composite_still_gets_tolerance_per_number():
    # Исключение правила 2 — габариты "A х B х C <ед>" (только числа и х).
    text, _ = build_tz_44fz(
        name="Ящик инструментальный",
        characteristics=[{"name": "Габариты", "value": "770 х 260 х 200 мм"}],
        description=None,
    )
    assert "Габариты: от" in text
    assert "до" in text
    assert "мм" in text


# --- п.3: EXACT (без допуска) ----------------------------------------------

def test_p3_resolution_is_exact_no_tolerance():
    text, _ = build_tz_44fz(
        name="Телевизор ультратонкий",
        characteristics=[{"name": "Разрешение", "value": "3840 x 2160"}],
        description=None,
    )
    assert "Разрешение: 3840 x 2160" in text


def test_p3_diagonal_is_exact_no_tolerance():
    text, _ = build_tz_44fz(
        name="Телевизор настенный",
        characteristics=[{"name": "Диагональ экрана", "value": "65", "unit": "дюйм"}],
        description=None,
    )
    assert 'Диагональ экрана: 65 дюйм' in text
    assert "от" not in text


def test_p3_core_count_is_exact_no_tolerance():
    text, _ = build_tz_44fz(
        name="Процессор многоядерный",
        characteristics=[{"name": "Количество ядер", "value": "8"}],
        description=None,
    )
    assert "Количество ядер: 8" in text
    assert "от" not in text


# --- п.4: направления ------------------------------------------------------

def test_p4_maximum_word_alone_does_not_force_not_more():
    # "Максимальное рабочее давление" — само слово "максимальн" не триггерит
    # "не более"; при этом явного ключевого слова для давления нет -> range.
    text, _ = build_tz_44fz(
        name="Насос гидравлический",
        characteristics=[{"name": "Максимальное рабочее давление", "value": "80", "unit": "МПа"}],
        description=None,
    )
    assert "не более" not in text


def test_p4_pusk_tok_is_not_less():
    text, _ = build_tz_44fz(
        name="Пуско-зарядное устройство",
        characteristics=[{"name": "Максимальный пусковой ток", "value": "800", "unit": "А"}],
        description=None,
    )
    assert "Максимальный пусковой ток: не менее 800 А" in text


def test_p4_range_and_depth_are_not_less():
    text, _ = build_tz_44fz(
        name="Детектор дронов портативный",
        characteristics=[
            {"name": "Дальность обнаружения", "value": "1500", "unit": "м"},
        ],
        description=None,
    )
    assert "Дальность обнаружения: не менее 1500 м" in text


def test_p4_mass_and_noise_stay_not_more():
    text, _ = build_tz_44fz(
        name="Прибор измерительный",
        characteristics=[
            {"name": "Масса изделия", "value": "425", "unit": "г"},
            {"name": "Уровень шума", "value": "55", "unit": "дБ"},
        ],
        description=None,
    )
    assert "Масса изделия: не более 425 г" in text
    assert "Уровень шума: не более 55 дБ" in text


# --- п.5: шаблонный штамп и дубль названия ---------------------------------

def test_p5_boilerplate_certification_text_dropped():
    text, needs_review = build_tz_44fz(
        name="Автотранспортное средство",
        characteristics=[{
            "name": "Оригинальное сертифицированное изделие",
            "value": (
                "Автотранспортное средство. Соответствует требованиям действующих "
                "стандартов безопасности (ГОСТ / ТР ТС). Поставляется в полной "
                "заводской комплектации, в неповреждённой оригинальной упаковке с "
                "маркировкой изготовителя, паспортом изделия и гарантией."
            ),
        }],
        description=None,
    )
    assert text is None


def test_p5_value_duplicating_product_name_dropped():
    text, _ = build_tz_44fz(
        name="Вертикальная экспедиционная канистра 10л",
        characteristics=[
            {"name": "Наименование товара", "value": "Вертикальная экспедиционная канистра 10л"},
            {"name": "Объем", "value": "10", "unit": "л"},
        ],
        description=None,
    )
    assert "Наименование товара" not in text
    assert "Объем: не менее 10 л" in text


# --- п.6: характеристика "Наименование" как источник имени -----------------

def test_p6_naименование_characteristic_used_as_name_not_duplicated():
    text, _ = build_tz_44fz(
        name="БУЙ ПЛАСТИКОВЫЙ СВМ d40х45см",
        characteristics=[
            {"name": "Наименование", "value": "Буй навигационный пластиковый СВМ"},
            {"name": "Объем буя", "value": "36", "unit": "литров"},
        ],
        description=None,
    )
    lines = text.split("\n")
    assert lines[0] == "Наименование: Буй навигационный пластиковый СВМ"
    assert text.count("Наименование") == 1


# --- п.7: fallback из description (инлайн-пары) -----------------------------

def test_p7_fallback_finds_inline_name_value_pairs_without_leading_colon():
    text, _ = build_tz_44fz(
        name="Товар без структурированных характеристик",
        characteristics=None,
        description="Товар поставляется в следующей комплектации. Диаметр: 40 см, вес: 4 кг. Гарантия производителя 12 месяцев.",
    )
    assert text is not None
    assert "Диаметр: 40 см" in text
    assert "вес: 4 кг" in text


# =============================== Ревью v2 (26.10.2026, второй заход) =====


# --- п.1: стоп-лист брендов, границы по слову, регистр ---------------------

def test_v2p1_stopword_brand_does_not_eat_compound_word():
    text, _ = build_tz_44fz(
        name="Насос промышленный роторный",
        characteristics=[{
            "name": "Материал корпуса насоса",
            "value": "ударопрочный литой металлический сплав (алюминий-цинк)",
        }],
        description=None,
        brands=frozenset({"Цинк", "Красный", "Черный"}),
    )
    assert "алюминий-цинк" in text


def test_v2p1_stopword_color_preserved_in_other_value():
    text, _ = build_tz_44fz(
        name="Буй пластиковый сигнальный",
        characteristics=[{"name": "Цвет корпуса", "value": "ярко-красный сигнальный"}],
        description=None,
        brands=frozenset({"Красный"}),
    )
    assert "ярко-красный" in text


def test_v2p1_brand_match_is_case_sensitive():
    # Бренд записан с заглавной — не должен вырезать то же слово строчными
    # буквами в обычном тексте.
    text, _ = build_tz_44fz(
        name="Прибор диагностический",
        characteristics=[{"name": "Материал", "value": "сталь, цвет матовый черный"}],
        description=None,
        brands=frozenset({"Черный"}),  # с заглавной
    )
    assert "черный" in text  # строчное "черный" в значении не тронуто


def test_v2p1_empty_brackets_cleaned_after_brand_removal():
    text, _ = build_tz_44fz(
        name="Детектор дронов портативный",
        characteristics=[{"name": "Комплектация", "value": 'детектор «Булат» v.4, антенна'}],
        description=None,
        brands=frozenset({"Булат"}),
    )
    assert "« »" not in text
    assert "Булат" not in text


# --- п.2: убранные из названия бренд/модель-коды вырезаются и из значений -

def test_v2p2_removed_name_tokens_stripped_from_values_too():
    text, _ = build_tz_44fz(
        name="Телевизор Xiaomi TV A 65 + КРОНШТЕЙН ONKRON NN24",
        characteristics=[{
            "name": "Состав комплекта",
            "value": "В комплекте телевизор Xiaomi TV A 65 и кронштейн ONKRON NN24 для монтажа",
        }],
        description=None,
        brands=frozenset({"Xiaomi", "ONKRON"}),
    )
    body = text.split("\n\n", 1)[1]
    assert "Xiaomi" not in body
    assert "ONKRON" not in body
    assert "NN24" not in body


# --- п.3: голые числа убираются из названия, слэш/счёт сохраняются --------

def test_v2p3_bare_leftover_number_removed_from_name():
    text, _ = build_tz_44fz(
        name="Микрофон проводной JBL PBM 100",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"JBL"}),
    )
    name_line = text.split("\n")[0]
    assert name_line == "Наименование: Микрофон проводной"


def test_v2p3_count_phrase_preserved():
    text, _ = build_tz_44fz(
        name="Кабель 3 в 1 VENTION USB-C",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"VENTION"}),
    )
    assert "3 в 1" in text.split("\n")[0]


def test_v2p3_slash_between_numbers_preserved():
    text, _ = build_tz_44fz(
        name="Пуско-зарядное устройство Gigant 12/24 В, 800 А",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"Gigant"}),
    )
    assert "12/24 В" in text.split("\n")[0]
    assert "800 А" in text.split("\n")[0]


def test_v2p3_duplicate_parenthesis_collapsed():
    text, _ = build_tz_44fz(
        name="Канистра стальная AUTOPROFI 20L (20L)",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"AUTOPROFI"}),
    )
    name_line = text.split("\n")[0]
    assert name_line.count("20L") == 1


# --- п.4: многострочное значение — пары с ПЕРВОЙ строки --------------------

def test_v2p4_multiline_value_split_into_pairs_without_group_header():
    text, _ = build_tz_44fz(
        name="Головка торцевая ударная",
        characteristics=[{
            "name": "Параметры соединения и геометрия",
            "value": "Размер рабочего профиля\n38 мм\nФорма профиля\n6-гранный профиль",
        }],
        description=None,
    )
    assert "Параметры соединения и геометрия" not in text
    # Прод-ревью 26.10.2026 (п.1, пятый заход): границы ±10% теперь считаются
    # по величине (< 100 -> 1 знак), а не по числу знаков исходного числа —
    # 38*0,9=34,2 / 38*1,1=41,8 (старое "от 34 до 42" было ±15-16% из-за
    # floor/ceil до целого).
    assert "Размер рабочего профиля: от 34,2 до 41,8 мм" in text
    assert "Форма профиля: 6-гранный профиль" in text


def test_v2p4_odd_number_of_lines_joined_with_semicolon():
    text, _ = build_tz_44fz(
        name="Прибор составной",
        characteristics=[{
            "name": "Параметры",
            "value": "Метка1\nЗначение1\nМетка2",
        }],
        description=None,
    )
    assert "Параметры: Метка1; Значение1; Метка2" in text


# --- п.5: направления -------------------------------------------------------

def test_v2p5_count_in_set_is_exact():
    text, _ = build_tz_44fz(
        name="Рампа заездная гидравлическая",
        characteristics=[{"name": "Количество в комплекте", "value": "2", "unit": "шт."}],
        description=None,
    )
    assert "Количество в комплекте: 2 шт." in text


def test_v2p5_nominal_current_is_exact():
    text, _ = build_tz_44fz(
        name="Автоматический выключатель однополюсный",
        characteristics=[{"name": "Номинальный ток", "value": "16", "unit": "А"}],
        description=None,
    )
    assert "Номинальный ток: 16 А" in text


def test_v2p5_breaking_capacity_is_not_less():
    text, _ = build_tz_44fz(
        name="Автоматический выключатель однополюсный",
        characteristics=[{"name": "Отключающая способность", "value": "6", "unit": "кА"}],
        description=None,
    )
    assert "Отключающая способность: не менее 6 кА" in text


def test_v2p5_continuous_work_time_is_not_less():
    text, _ = build_tz_44fz(
        name="Детектор дронов портативный",
        characteristics=[{"name": "Время непрерывной автономной работы", "value": "15", "unit": "часов"}],
        description=None,
    )
    assert "Время непрерывной автономной работы: не менее 15 часов" in text


# =============================== Ревью v3 (26.10.2026, третий заход) =====


# --- п.A: вложенные группы в description (raw со стенда, id 582631/582099) -

def test_v3pA_nested_group_header_582631_raw_description():
    text, _ = build_tz_44fz(
        name="Ключ баллонный STELS",
        characteristics=None,
        description=(
            "Общая информация\nПроизводитель\nSTELS\nАртикул производителя\n14299\n"
            "Тип\nключ баллонный грузовой двухсторонний трубчатый\n"
            "Назначение\nмонтаж и демонтаж колесных гаек грузовых автомобилей КАМАЗ, МАЗ, автобусов и прицепов\n"
            "Технические характеристики\nРазмеры рабочих зевов\n32 х 38 мм\n"
            "Форма рабочего профиля\n6-гранный\nДлина ключа\n500 мм\n"
            "Диаметр прутка (тела)\n26 мм\nОтверстие под вороток\n"
            "сквозное диаметром 20 мм под монтажную лопатку (вороток)\n"
            "Материалы и прочность\nМатериал\nуглеродистая конструкционная сталь 45\n"
            "Твердость рабочих частей\n41 HRC (строгое соответствие ГОСТ 25605-83)\n"
            "Защитное покрытие\nантикоррозийное цинковое / оксидированное покрытие\n"
            "Масса инструмента\n2.35 кг"
        ),
    )
    assert "Материал: углеродистая конструкционная сталь 45" in text
    assert "Твердость рабочих частей: 41 HRC (строгое соответствие ГОСТ 25605-83)" in text
    assert ": Защитное покрытие" not in text
    assert ": Масса инструмента" not in text
    assert "Материалы и прочность" not in text


def test_v3pA_nested_group_header_582099_raw_description():
    text, _ = build_tz_44fz(
        name="Рампы заездные гидравлические KraftWell",
        characteristics=None,
        description=(
            "Общая информация\nПроизводитель\nKraftWell\nМодель\nKRWCR2\n"
            "Тип\nрампы заездные автомобильные с гидравлическим подъемом\n"
            "Количество в комплекте\n2 шт.\n"
            "Технические характеристики\nГрузоподъемность комплекта\n2000 кг (2 т)\n"
            "Грузоподъемность одной рампы\n1000 кг (1 т)\n"
            "Механизм подъема\nвстроенный гидравлический домкрат\n"
            "Минимальная высота подхвата\n245 мм\nМаксимальная высота подъема\n365 мм\n"
            "Размер рабочей площадки под колесо\n280 х 240 мм\n"
            "Максимальная ширина шины\n240 мм\n"
            "Конструктивные параметры\nМатериал конструкции\nусиленная конструкционная сталь\n"
            "Покрытие\nпорошковое антикоррозионное\n"
            "Фиксаторы безопасности\nмеханические стопорные штифты\n"
            "Габаритные размеры\n1140 x 320 x 300 мм\nМасса комплекта\n36 кг"
        ),
    )
    # "Габаритные размеры" — не EXACT-ключ, составное "A x B x C" получает
    # допуск ±10% по каждому числу (п.2, не часть этого ревью) — проверяем
    # только корректную разбивку метка/значение, не формулу допуска.
    assert "Габаритные размеры: от" in text
    assert "Покрытие: порошковое антикоррозионное" in text
    assert ": Фиксаторы безопасности" not in text
    assert ": Масса комплекта" not in text
    assert "Конструктивные параметры" not in text


# --- п.B: "время работы" форсированно "не менее" -----------------------

def test_v3pB_continuous_autonomous_work_time_forced_not_less():
    text, _ = build_tz_44fz(
        name="Детектор дронов портативный",
        characteristics=[{"name": "Время непрерывной автономной работы", "value": "15", "unit": "часов"}],
        description=None,
    )
    assert "Время непрерывной автономной работы: не менее 15 часов" in text
    assert "не более" not in text


def test_v3pB_explicit_do_wording_overridden_to_not_less():
    # Даже если поставщик написал явное "до X" — для времени автономной
    # работы это всё равно "не менее" (п.B).
    text, _ = build_tz_44fz(
        name="Детектор дронов портативный",
        characteristics=[{"name": "Время автономной работы", "value": "до 15 часов"}],
        description=None,
    )
    assert "не менее 15 часов" in text
    assert "не более" not in text


# --- п.C: удаление голых чисел — только СРАЗУ после убранного токена -----

def test_v3pC_only_numbers_right_after_removed_token_are_dropped():
    text, _ = build_tz_44fz(
        name=(
            "Ключ баллонный STELS, двухсторонний 32 x 38, длина 500 мм "
            "(для КАМАЗ), сталь 45 твердостью 41 HRC (ГОСТ), антикоррозийное "
            "покрытие, балонный ключ для автомобиля, 14299"
        ),
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"STELS"}),
    )
    name_line = text.split("\n")[0]
    assert "STELS" not in name_line
    assert "32 x 38" in name_line
    assert "45" in name_line
    assert "41 HRC" in name_line


def test_v3pC_chained_numbers_after_removed_token_still_dropped():
    text, _ = build_tz_44fz(
        name="Телевизор Xiaomi TV A 65 2026 + КРОНШТЕЙН ONKRON NN24",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"Xiaomi", "ONKRON"}),
    )
    name_line = text.split("\n")[0]
    assert name_line == "Наименование: Телевизор TV + КРОНШТЕЙН"


def test_v3pC_apostrophe_remnant_removed_whole_token():
    text, _ = build_tz_44fz(
        name="Амортизатор рывка ASAP'SORBER универсальный",
        characteristics=[{"name": "Цвет", "value": "Черный"}],
        description=None,
        brands=frozenset({"ASAP"}),
    )
    name_line = text.split("\n")[0]
    assert "'SORBER" not in name_line
    assert "SORBER" not in name_line


# ===================== Прод-ревью 26.10.2026 (четвёртый заход) ===========


def test_p_a1_in_description_false_only_name_excludes():
    # name-only исключение (бренд/магазин/страна) продолжает работать, а
    # in_description=False сам по себе — нет (п.A1).
    text, _ = build_tz_44fz(
        name="Огнетушитель порошковый ОП-2(3)",
        characteristics=[
            {"name": "Вес брутто", "value": "2786", "unit": "г", "in_description": False},
            {"name": "Магазин-источник", "value": "Сима-ленд (sima-land.ru)", "in_description": False},
        ],
        description=None,
    )
    assert "Вес брутто: не более 2786 г" in text
    assert "Магазин" not in text


def test_p_a2_zero_value_dropped():
    text, _ = build_tz_44fz(
        name="Прибор тестовый",
        characteristics=[
            {"name": "Вес брутто", "value": "0", "unit": "кг"},
            {"name": "Цвет", "value": "Белый"},
        ],
        description=None,
    )
    assert "Вес брутто" not in text
    assert "Цвет: Белый" in text


def test_p_a3_cable_core_count_is_exact():
    text, _ = build_tz_44fz(
        name="Кабель силовой",
        characteristics=[{"name": "Количество жил кабеля", "value": "2"}],
        description=None,
    )
    assert "Количество жил кабеля: 2" in text
    assert "от 1 до 3" not in text


def test_p_a4_breaker_curve_token_and_rj45_kept_model_and_article_removed():
    text, _ = build_tz_44fz(
        name=(
            "Автоматический выключатель DZ47-63/3P C50A/3п/ 4,5кА на "
            "Din-рейку ADL01-097 (ANDELI)"
        ),
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
        manufacturer="ANDELI",
        article="ADL01-097",
    )
    name_line = text.split("\n")[0]
    assert "C50A" in name_line
    assert "3п" in name_line
    assert "4,5кА" in name_line
    assert "Din" in name_line
    assert "DZ47-63" not in name_line
    assert "ADL01-097" not in name_line
    assert "ANDELI" not in name_line


def test_p_a4_rj45_socket_kept_brand_and_article_removed():
    text, _ = build_tz_44fz(
        name="Розетка Infinity FSE000186 компьютерная RJ45 6А с/п арктический лед",
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
        brands=frozenset({"Infinity", "Systeme Electric"}),
    )
    name_line = text.split("\n")[0]
    assert "RJ45" in name_line
    assert "Infinity" not in name_line
    assert "FSE000186" not in name_line


def test_p_a5_unclosed_trailing_paren_dropped():
    text, _ = build_tz_44fz(
        name='Кабель Р=0,050 кг/м (Севкабель С-Петерб',
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
        manufacturer="Севкабель",
    )
    name_line = text.split("\n")[0]
    assert "(" not in name_line
    assert "С-Петерб" not in name_line


def test_p_a5_sparse_paren_dropped_after_brand_removal():
    text, _ = build_tz_44fz(
        name="Спринклер оросительный (типа ESFR)",
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
        brands=frozenset({"ESFR"}),
    )
    name_line = text.split("\n")[0]
    assert "(типа" not in name_line
    assert "ESFR" not in name_line


def test_p_a6_quoted_brand_in_manufacturer_stripped_with_quotes():
    text, _ = build_tz_44fz(
        name='Индейка "Котто", нарезка',
        characteristics=[{"name": "Состав", "value": 'ООО "МЯСОКОМБИНАТ ЭКО": мясо индейки'}],
        description=None,
        manufacturer="Котто",
    )
    name_line = text.split("\n")[0]
    assert "Котто" not in name_line
    assert '"' not in name_line


def test_p_a7_sprinkler_temperature_is_exact():
    text, _ = build_tz_44fz(
        name="Спринклер оросительный",
        characteristics=[{"name": "Температура срабатывания", "value": "93"}],
        description=None,
    )
    assert "Температура срабатывания: 93" in text
    assert "от" not in text


def test_p_a7_efficiency_coefficient_is_exact():
    text, _ = build_tz_44fz(
        name="Насос",
        characteristics=[{"name": "Коэффициент производительности", "value": "1,91"}],
        description=None,
    )
    assert "Коэффициент производительности: 1,91" in text
    assert "от" not in text


def test_p_a1a2_fire_extinguisher_prod_sample():
    # Пример с прода (Сима-ленд, огнетушитель) — in_description=False не
    # исключает характеристики (п.A1), страна/магазин — исключены по имени,
    # габариты получают допуск ±10% по каждому числу.
    text, needs_review = build_tz_44fz(
        name='Огнетушитель порошковый «Ярпожинвест» ОП-2(3), ABCE-01(А)',
        characteristics=[
            {"name": "Страна-производитель", "value": "Россия"},
            {"name": "Вес брутто", "value": "2786 г", "in_description": False},
            {"name": "Габариты (ДхШхВ)", "value": "31.5 x 11.5 x 11 см", "in_description": False},
            {"name": "Магазин-источник", "value": "Сима-ленд (sima-land.ru)", "in_description": False},
        ],
        description=None,
        manufacturer="Ярпожинвест",
        article="5182898",
    )
    assert text is not None
    assert "Ярпожинвест" not in text
    assert "Страна" not in text
    assert "Магазин" not in text
    assert "Вес брутто: не более 2786 г" in text
    assert "Габариты (ДхШхВ): от" in text and "до" in text and "см" in text


# ===================== Прод-ревью 26.10.2026 (пятый заход) ===============


def test_p5_1_tolerance_rounding_by_magnitude_not_source_decimals():
    # 13 * 0,9 = 11,7 / 13 * 1,1 = 14,3 — один знак (значение < 100), а не
    # floor/ceil до целого ("от 11 до 15" — это было ±15%, не ±10%).
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[{"name": "Длина", "value": "13", "unit": "см"}],
        description=None,
    )
    assert "Длина: от 11,7 до 14,3 см" in text


def test_p5_1_tolerance_rounding_trims_trailing_zero():
    # 10 * 0,9 = 9,0 / 10 * 1,1 = 11,0 — границы ровные, без ",0".
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[{"name": "Длина", "value": "10", "unit": "см"}],
        description=None,
    )
    assert "Длина: от 9 до 11 см" in text


def test_p5_1_tolerance_escalates_decimals_when_bounds_collapse():
    # 0,1 * 0,9 = 0,09 / 0,1 * 1,1 = 0,11 — на 1 знаке обе границы схлопнутся
    # в "0,1", добавляем знак (максимум 3).
    text, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[{"name": "Высота", "value": "0,1", "unit": "см"}],
        description=None,
    )
    assert "Высота: от 0,1 до 0,1 см" not in text
    assert "Высота: от 0,09 до 0,11 см" in text


def test_p5_2_letter_equals_number_token_kept_in_name():
    text, _ = build_tz_44fz(
        name="Снежколеп-песколеп, «Колобок», d=7.5 см, МИКС",
        characteristics=[{"name": "Цвет", "value": "Белый"}],
        description=None,
    )
    name_line = text.split("\n")[0]
    assert "d=7.5" in name_line


def test_p5_3_fire_class_token_kept_in_name_exact_string():
    text, needs_review = build_tz_44fz(
        name='Огнетушитель порошковый «Ярпожинвест» ОП-2(3), ABCE-01(А)',
        characteristics=[
            {"name": "Страна-производитель", "value": "Россия"},
            {"name": "Вес брутто", "value": "2786 г", "in_description": False},
            {"name": "Габариты (ДхШхВ)", "value": "31.5 x 11.5 x 11 см", "in_description": False},
            {"name": "Магазин-источник", "value": "Сима-ленд (sima-land.ru)", "in_description": False},
        ],
        description=None,
        manufacturer="Ярпожинвест",
        article="5182898",
    )
    assert needs_review is False
    lines = text.split("\n")
    assert lines[0] == "Наименование: Огнетушитель порошковый ОП-2(3), ABCE-01(А)"
    assert "Габариты (ДхШхВ): от 28,4 до 34,7 х от 10,4 до 12,7 х от 9,9 до 12,1 см" in text


# ------------------------- product_type как источник наименования -------
# Владелец, 26.10.2026: «Наименование» в ТЗ 44-ФЗ берётся из Product.
# product_type («Тип товара»), а не из названия, если product_type заполнен.
# Приоритет: product_type > характеристика «Наименование» > название.


def test_p6_product_type_overrides_name_prod_sample():
    # Прод-пример владельца: name «Кусачки ГКС - 80 х», product_type
    # «Кусачки гидравлические ГАСИ» → наименование из product_type целиком.
    text, needs_review = build_tz_44fz(
        name="Кусачки ГКС - 80 х",
        characteristics=[
            {"name": "Длина", "value": "80", "unit": "см"},
        ],
        description=None,
        product_type="Кусачки гидравлические ГАСИ",
    )
    assert needs_review is False
    lines = text.split("\n")
    assert lines[0] == "Наименование: Кусачки гидравлические ГАСИ"


def test_p6_product_type_runs_through_brand_cleanup():
    # product_type с брендом внутри — чистится ТОЙ ЖЕ функцией, что и
    # название (brands из каталога), бренд вырезается.
    text, needs_review = build_tz_44fz(
        name="Лампа светодиодная Smartbuy A60",
        characteristics=[
            {"name": "Мощность", "value": "9", "unit": "Вт"},
        ],
        description=None,
        product_type="Лампа Smartbuy светодиодная",
        brands=frozenset({"Smartbuy"}),
    )
    assert needs_review is False
    lines = text.split("\n")
    assert lines[0] == "Наименование: Лампа светодиодная"
    assert "Smartbuy" not in text


def test_p6_empty_product_type_falls_back_to_previous_behavior():
    # Пустой/None product_type — поведение как раньше: характеристика
    # «Наименование», иначе Product.name.
    text_name_only, needs_review = build_tz_44fz(
        name="Небулайзер компрессорный OMRON NE-C900-RU",
        characteristics=[{"name": "Вес", "value": "3.5", "unit": "кг"}],
        description=None,
        manufacturer="OMRON",
        article="NE-C900-RU",
        product_type=None,
    )
    assert text_name_only.split("\n")[0] == "Наименование: Небулайзер компрессорный"

    text_blank, _ = build_tz_44fz(
        name="Небулайзер компрессорный OMRON NE-C900-RU",
        characteristics=[{"name": "Вес", "value": "3.5", "unit": "кг"}],
        description=None,
        manufacturer="OMRON",
        article="NE-C900-RU",
        product_type="   ",
    )
    assert text_blank == text_name_only

    text_characteristic, _ = build_tz_44fz(
        name="Прибор",
        characteristics=[
            {"name": "Наименование", "value": "Прибор измерительный"},
            {"name": "Вес", "value": "3.5", "unit": "кг"},
        ],
        description=None,
        product_type=None,
    )
    assert text_characteristic.split("\n")[0] == "Наименование: Прибор измерительный"


# ===================== 27.10.2026: fallback из description — реальные товары
# прода без characteristics (id 3002, 4481) ================================


def test_prod_3002_fire_extinguisher_height_from_dash_separated_description():
    # "Высота огнетушителя  - 440 мм" (дефис, два пробела перед ним) — без
    # нового формата "Метка - значение" в product_characteristics_parse эта
    # строка не разбиралась вовсе (characteristic "Высота огнетушителя"
    # терялась). "Высота" не входит ни в один словарь направлений ->
    # обычный range ±10%: 440*0,9=396 / 440*1,1=484.
    description = (
        "Огнетушитель ОП-3 предназначен для первичного тушения пожаров и "
        "возгораний класса A, B, C, E (горючие и легковоспламеняющиеся "
        "жидкости, твердые горючие вещества и газы, электроустановки, не "
        "превышающие напряжение 1000 Вольт). Комплектуется распылителем на "
        "ЗПУ.\n\nИзделие подходит для оснащения различных объектов и "
        "помещений: административных зданий, жилых домов, офисов, "
        "гостиниц, промышленных участков и мн. др.\n"
        "Высота огнетушителя  - 440 мм\nТип порошковый (ОП)\n"
        "Конструкция переносной\nМатериал корпуса металл\n"
        "Перезаряжаемый да\nПринцип вытеснения вещества закачной\n"
        "Продолжительность подачи огнетушащего вещества 8 с, (не менее)\n"
        "Max длина струи огнетушителя 2 м\nНоминальная масса ОТВ 3 кг\n"
        "Мах масса заряженного огнетушителя 4.2 кг\nДиаметр 110 мм\n"
        "Объем 3 л\nВес пустого баллона 1.2 кг"
    )
    text, needs_review = build_tz_44fz(
        name="Огнетушитель ОП-3",
        characteristics=None,
        description=description,
        product_type="Огнетушитель",
    )
    assert text is not None
    assert text.split("\n")[0] == "Наименование: Огнетушитель"
    assert "Высота огнетушителя: от 396 до 484 мм" in text
    # 27.10.2026, коррекция владельца: предложение с двоеточием внутри
    # ("Изделие подходит для оснащения ... помещений: административных
    # зданий...") — не характеристика, не должно попадать в ТЗ ни строкой.
    assert "Изделие подходит" not in text
    assert "административных зданий" not in text


def test_prod_4481_vest_mass_and_buoyancy_qualifier_in_label():
    # Квалификатор "не более"/"не менее" (+ единица "кг") сидит ВНУТРИ самой
    # метки характеристики ("Масса, не более, кг.", "...не более, кг.":
    # без извлечения получалось "Масса, не более, кг.: не более 0,85 ."
    # (дубль квалификатора + хвостовая точка от "0.85.").
    description = (
        "Жилет «Мастер» р. 108-112\n  \n"
        " Материал оболочки: полиэстеровая ткань\n"
        " Наполнитель: пенополиэтилен изолон ППЭ-Л\n"
        " Ремень: полипропилен\n"
        " Типоразмер (обхват груди), см.: 108-112 (XL)\n"
        " Масса, не более, кг.: 0.85.\n"
        " Положительная плавучесть, не менее, кг.: 10.5\n"
        " Рассчитан на вес человека не более, кг.: 95\n"
        " Цвет изделия: оранжевый (внутри подкладка желтая)\n"
        " Жилет имеет 2 ремня черного цвета, с пластмассовыми застежками "
        "черного цвета (2 шт.)\n  \n"
        " Нанесение должно быть осуществлено методом шелкографии на "
        "лицевую и тыльную поверхность жилета\n"
        " Поставщик предоставляет гарантию на поставленный товар в "
        "течении 1 года с момента поставки."
    )
    text, _ = build_tz_44fz(
        name='Жилет «Мастер» р.108-112 (XL) c нанесением "ВСКС"',
        characteristics=None,
        description=description,
        product_type="Жилет",
    )
    assert text is not None
    assert "Масса: не более 0,85 кг" in text
    assert "Положительная плавучесть: не менее 10,5 кг" in text
    assert "Рассчитан на вес человека: не более 95 кг" in text
    # Квалификатор не продублирован в имени и хвостовая точка не осталась.
    assert "не более, кг." not in text
    assert "не менее, кг." not in text
    assert "0,85 ." not in text and "0.85." not in text


def test_prod_32655_long_but_legit_label_not_dropped_as_sentence():
    # Коррекция владельца 27.10.2026: порог 5 слов/40 симв. резал легитимную
    # метку характеристики (5 слов, 52 симв.) — порог смягчён до 10/80,
    # глагол-маркер предложения остаётся основным сигналом (3002 — ниже).
    description = (
        "Общая информация\nПроизводитель: ООО «Фирма СПРУТ» (Россия)\n"
        "Модель: КГС-80Х (Кусачки гидравлические «Спрут»)\n"
        "Тип изделия: инструмент гидравлический аварийно-спасательный (ГАСИ)\n\n"
        "Технические характеристики\n"
        "Назначение: перекусывание стальных прутков, арматуры, труб, "
        "профильного проката и кабельных линий при деблокировании "
        "пострадавших в ДТП и завалах\n"
        "Максимальное рабочее давление: 80 МПа (800 кгс/см²)\n"
        "Максимальный диаметр перекусываемого стального прутка: не менее 30 мм (сталь 20)\n"
        "Максимальное раскрытие концов лезвий: 145 мм\n"
        "Материал лезвий: высокопрочная кованая инструментальная "
        "легированная сталь с термической обработкой (возможность "
        "многократной переточки)\n"
        "Управление: поворотная рукоятка гидрораспределителя золотникового "
        "типа («мертвец» — автовозврат в нейтраль)\n"
        "Подключение: одношланговая мономуфта или быстроразъемные "
        "соединения БРС со встроенными обратными клапанами\n\n"
        "Габариты и масса\nГабариты: 730 × 240 × 190 мм\nМасса изделия: 14.5 кг\n\n"
        "Сертификация\nГОСТ Р 50982-2019 (Инструмент комплексный "
        "гидравлический аварийно-спасательный)"
    )
    text, _ = build_tz_44fz(
        name="Кусачки ГКС - 80 х",
        characteristics=None,
        description=description,
        product_type="Кусачки гидравлические ГАСИ",
    )
    assert text is not None
    assert (
        "Максимальный диаметр перекусываемого стального прутка: "
        "не менее 30 мм (сталь 20)" in text
    )


def test_prod_6762_unit_before_qualifier_and_unit_only_nominal_diameter():
    # id 6762: "Масса, кг, не более" (единица ПЕРЕД квалификатором — обратный
    # порядок относительно 4481) и "Условный проход, мм" (единица без
    # квалификатора вовсе, направление — точное по словарю "условный проход").
    description = (
        "Пожарный ручной ствол РСКУ-50 предназначаются чтобы создавать и "
        "направлять в очаг пожара струю воды, а также для создания "
        "водяной завесы предохраняющей от огня и тепловых излучений.\n\n"
        "Расход литража\t2-8 л/с\n"
        "Диапазон изменения угла факела распыленной струи\t0ᵒ-120ᵒ\n"
        "Масса, кг, не более\t1,7\n"
        "Условный проход, мм\t50"
    )
    text, _ = build_tz_44fz(
        name="Ствол пожарный ручной РСКУ-50",
        characteristics=None,
        description=description,
        product_type="Ствол",
    )
    assert text is not None
    assert "Масса: не более 1,7 кг" in text
    assert "Условный проход: 50 мм" in text


def test_p6_product_type_wins_over_naименование_characteristic():
    # Приоритет: product_type > характеристика «Наименование» > название.
    text, needs_review = build_tz_44fz(
        name="Прибор",
        characteristics=[
            {"name": "Наименование", "value": "Прибор измерительный"},
            {"name": "Вес", "value": "3.5", "unit": "кг"},
        ],
        description=None,
        product_type="Прибор контрольно-измерительный",
    )
    assert needs_review is False
    assert text.split("\n")[0] == "Наименование: Прибор контрольно-измерительный"


# ------------------------------------------- роутер preview (401/404) ----


@pytest.mark.asyncio
async def test_preview_requires_auth(client):
    r = await client.post("/api/products/1/tz-44fz/preview")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_preview_404_on_missing_product(client, superadmin_headers):
    r = await client.post("/api/products/999999999/tz-44fz/preview", headers=superadmin_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_returns_generated_text(client, superadmin_headers, db_session):
    r_create = await client.post(
        "/api/products/",
        headers=superadmin_headers,
        json={"name": "Тестовый прибор для ТЗ 44-ФЗ", "category": "Прочее"},
    )
    assert r_create.status_code == 200, r_create.text
    product_id = r_create.json()["id"]

    # characteristics (JSONB) заполняется только импортом прайса (докстринг
    # app/models/product.py) — ProductCreate его не принимает, поэтому для
    # теста кладём напрямую в той же транзакции, что и client (db_session).
    from app.models.product import Product
    product = await db_session.get(Product, product_id)
    product.characteristics = [
        # Числовая характеристика, а не "Цвет: Белый" — на реальном
        # (грязном) каталоге стенда "Белый" сам может быть чьим-то
        # мусорным значением характеристики "Бренд/Производитель" и
        # попасть в глобальный набор brands, см. collect_catalog_brands();
        # тест проверяет сам факт работы роутера, не конкретное слово.
        {"name": "Диаметр", "value": "12", "unit": "см"},
        {"name": "Производитель", "value": "ACME-TEST-UNIQUE-9f3c"},
    ]
    product.manufacturer = "ACME-TEST-UNIQUE-9f3c"
    await db_session.flush()

    r_preview = await client.post(
        f"/api/products/{product_id}/tz-44fz/preview", headers=superadmin_headers,
    )
    assert r_preview.status_code == 200, r_preview.text
    body = r_preview.json()
    assert body["text"] is not None
    assert "Диаметр" in body["text"]
    assert "ACME-TEST-UNIQUE-9f3c" not in body["text"]
    assert "needs_review" in body