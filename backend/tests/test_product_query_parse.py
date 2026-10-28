# -*- coding: utf-8 -*-
"""parse_query() поверх build_signature (Правило №6, см. docstring
product_query_parse.py) — «этап 0» поиска товара по фразе «как помнит»
(владелец, 28.10.2026). Покрывает: required/optional разбор, нормализацию
величины («4л»="4 л") и модели («5w40»="5W-40"), стоп-слова, specific,
и кэш словаря брендов из своего manufacturer (get_manufacturer_brand_
dictionary)."""
import pytest

from app.models.product import Product
import app.services.product_query_parse as product_query_parse_module
from app.services.product_query_parse import (
    ManufacturerBrandDictionary,
    get_manufacturer_brand_dictionary,
    parse_query,
)


class _FakeBrandDict:
    """Фиктивный словарь брендов того же контракта, что и build_signature
    принимает (`.find_in_name`) — без похода в БД/файлы, только для теста
    разбора одной конкретной фразы. Отдаёт КИРИЛЛИЧЕСКОЕ каноническое
    написание бренда, совпадающее по письму со словом в query — кросс-
    скриптовая транслитерация (кириллица-запрос ↔ латиница-бренд в каталоге)
    не входит в задачу этого модуля, см. docstring parse_query про
    get_manufacturer_brand_dictionary."""

    def find_in_name(self, name):
        if "макита" in name.lower():
            return "Макита"
        return None


# ── вид товара без прочих признаков — НЕ specific ──────────────────────────

def test_product_type_only_is_not_specific():
    parsed = parse_query("болгарка")
    # product_type — КАНОНИЧЕСКИЙ вид (метаданные/specific); required несёт
    # ЛИТЕРАЛЬНОЕ слово из фразы ("болгарка", не "шлифмашина") — так его
    # найдёт полнотекстовый поиск по реальному тексту каталога (владелец,
    # 28.10.2026, см. docstring parse_query).
    assert parsed.product_type == "шлифмашина"
    assert parsed.required == ["болгарка"]
    assert parsed.optional == []
    assert parsed.dropped_stopwords == []
    assert parsed.specific is False


# ── фраза с брендом, цифровым токеном и лишними словами ────────────────────

def test_phrase_with_brand_model_and_extra_words():
    # "с" НЕ ставим сразу после цифры: "125 с" — build_signature считает
    # "с" единицей измерения (секунды, см. UNIT_WORDS) и вырезает "125 с"
    # целиком как величину (_strip_unit_quantities, то же правило, что и у
    # product_name_signature.py для сравнения «тот же товар», Правило №6 —
    # этот модуль его не переопределяет). Порядок слов в фразе ниже избегает
    # этого наложения, сохраняя смысл («с регулировкой» — лишние слова).
    parsed = parse_query("болгарка с регулировкой макита 125", brand_dictionary=_FakeBrandDict())
    assert parsed.brand == "Макита"
    assert parsed.product_type == "шлифмашина"
    assert parsed.required == ["Макита", "болгарка", "125"]
    assert parsed.optional == ["регулировкой"]
    assert parsed.dropped_stopwords == ["с"]
    assert parsed.specific is True


# ── величина с единицей измерения: «4 кг» в самой фразе ────────────────────

def test_quantity_with_space_normalizes_and_type_required():
    parsed = parse_query("огнетушитель порошковый 4 кг")
    assert parsed.product_type == "огнетушитель"
    assert "огнетушитель" in parsed.required
    assert "4 кг" in parsed.required
    assert parsed.optional == ["порошковый"]
    assert parsed.specific is True


# ── слитная форма величины «4л» = «4 л» (нормализация, не два разных токена)

def test_quantity_fused_without_space_normalizes_with_space():
    parsed = parse_query("масло 4л")
    assert parsed.required == ["4 л"]
    assert parsed.optional == ["масло"]
    assert parsed.specific is True


# ── модельный/вязкостный токен «5w40» = «5W-40» ─────────────────────────────

def test_model_viscosity_token_normalizes():
    parsed = parse_query("масло лукойл 5w40 4л")
    assert "5W-40" in parsed.required
    assert "4 л" in parsed.required
    # "масло" и "лукойл" — ни вид товара (нет в словаре), ни бренд (словарь
    # брендов не передан) — остаются optional, не required.
    assert set(parsed.optional) == {"масло", "лукойл"}
    assert parsed.specific is True


# ── опечатка — слово не распознано словарём вида товара → остаётся optional,
#    specific=False (как «просто болгарка», не повод уходить в fuzzy здесь —
#    это решает уже search_products на следующем шаге)

def test_typo_not_recognized_stays_optional_and_not_specific():
    parsed = parse_query("огнитушитель")
    assert parsed.product_type is None
    assert parsed.required == []
    assert parsed.optional == ["огнитушитель"]
    assert parsed.specific is False


# ── стоп-слова (предлоги/союзы) выбрасываются, не попадают ни в required,
#    ни в optional

def test_stopwords_are_dropped_not_optional():
    parsed = parse_query("огнетушитель для склада")
    assert "для" in parsed.dropped_stopwords
    assert "для" not in parsed.optional
    assert "для" not in parsed.required
    assert "склада" in parsed.optional


# ── пустой запрос — пустой разбор, не падает ────────────────────────────────

def test_empty_query_returns_empty_parsed_query():
    parsed = parse_query("")
    assert parsed.required == []
    assert parsed.optional == []
    assert parsed.specific is False

    parsed_none = parse_query(None)
    assert parsed_none.required == []
    assert parsed_none.specific is False


# ── specific: True при цифровом/модельном токене даже без вида/бренда ──────

def test_specific_true_with_bare_digit_token():
    parsed = parse_query("дрель ВА-47")
    assert parsed.specific is True
    assert any("47" in tok for tok in parsed.required)


# ── словарь брендов из своего manufacturer (кэш в памяти процесса) ─────────

@pytest.mark.asyncio
async def test_manufacturer_brand_dictionary_builds_from_db(db_session):
    # Кэш — МОДУЛЬНЫЙ (процесс-wide, Правило дешёвого онлайн-пути, см.
    # docstring get_manufacturer_brand_dictionary) — другие тесты в этом же
    # файле/прогоне (search_products теперь сам вызывает эту функцию, см.
    # product_search.py, ревью «этап 0») могли прогреть его ДО вставки
    # "Bosch" этим тестом. Сбрасываем явно, чтобы тест был детерминирован,
    # а не зависел от порядка запуска.
    product_query_parse_module._brand_dict_cache["dictionary"] = None
    product_query_parse_module._brand_dict_cache["built_at"] = 0.0

    p = Product(name="Дрель ударная", category="Инструмент", manufacturer="Bosch")
    db_session.add(p)
    await db_session.commit()

    dictionary = await get_manufacturer_brand_dictionary(db_session)
    assert isinstance(dictionary, ManufacturerBrandDictionary)
    assert dictionary.find_in_name("дрель bosch professional gsb") == "Bosch"
    assert dictionary.find_in_name("дрель без бренда") is None

    # Повторный вызов в пределах TTL — тот же закэшированный объект, без
    # нового запроса в БД (идентичность объекта как доказательство кэша).
    dictionary2 = await get_manufacturer_brand_dictionary(db_session)
    assert dictionary2 is dictionary


# ── кириллическое написание латинского бренда («болгарка макита») ──────────
# владелец, 28.10.2026: бренды в словаре латиницей, люди пишут кириллицей —
# fold_brand_or_code (гомоглифы/регистр) этого не берёт, нужен фонетический
# ключ + малая ручная таблица алиасов (см. docstring product_query_parse.py
# у ManufacturerBrandDictionary._find_phonetic).

_PHONETIC_BRANDS = ["Makita", "Bosch", "Karcher", "DeWalt", "Stihl", "Husqvarna", "Metabo", "Ryobi"]


@pytest.mark.parametrize(
    "word,expected_brand",
    [
        ("макита", "Makita"),
        ("бош", "Bosch"),
        ("керхер", "Karcher"),
        ("кархер", "Karcher"),
        ("деволт", "DeWalt"),
        ("девольт", "DeWalt"),
        ("штиль", "Stihl"),
        ("хускварна", "Husqvarna"),
        ("метабо", "Metabo"),
        ("риоби", "Ryobi"),
    ],
)
def test_cyrillic_brand_spelling_resolves_to_latin_canon(word, expected_brand):
    dictionary = ManufacturerBrandDictionary(_PHONETIC_BRANDS)
    assert dictionary.find_in_name(word) == expected_brand


@pytest.mark.parametrize(
    "phrase",
    [
        "болгарка",
        "огнетушитель",
        "кабель медный",
        "перчатки",
        "костюм горка",
        "масло моторное",
        "шкаф металлический",
        "лопата штыковая",
    ],
)
def test_cyrillic_phonetic_brand_no_false_positive(phrase):
    """Виды товара/материалы/стоп-слова не должны фонетически «находить»
    бренд, которого в запросе нет (владелец, 28.10.2026, проверка перед
    подключением фонетики — см. ПРАВИЛО №2 раздела в задании)."""
    dictionary = ManufacturerBrandDictionary(_PHONETIC_BRANDS)
    assert dictionary.find_in_name(phrase) is None


def test_cyrillic_brand_spelling_makes_query_specific():
    dictionary = ManufacturerBrandDictionary(_PHONETIC_BRANDS)
    parsed = parse_query("болгарка макита", dictionary)
    assert parsed.specific is True
    assert parsed.brand == "Makita"
    assert "Makita" in parsed.required

    parsed_with_size = parse_query("болгарка макита 125", dictionary)
    assert parsed_with_size.specific is True
    assert "125" in parsed_with_size.required


# ── короткие/буквенно-цифровые "бренды" из прод-словаря manufacturer ──────
# владелец, 28.10.2026: аудит прод-словаря (3733 значения) нашёл ложные
# срабатывания на ТОЧНОМ пути (self._combined) — короткие коды упаковки/
# размера, случайно попавшие в manufacturer, распознавались как бренд:
# «бумага офисная А4»→«А4», «футболка XL»→XL, «кабель SE»→SE, «аптечка
# ST»→ST, «рация GT»→GT, «трос ET»→ET, «фонарь GP»→GP. При этом настоящие
# короткие бренды (HP, LG, WD...) должны находиться — белый список
# _SHORT_BRAND_WHITELIST решает это, не убирая короткие коды совсем.

_PROD_SHORT_DICT_SAMPLE = [
    "А4", "XL", "ST", "SE", "GT", "ET", "GP", "QF",  # ложные (не бренды)
    "HP", "LG", "WD",  # настоящие короткие бренды (белый список)
    "Makita", "Bosch", "Зубр",  # обычные бренды — для контроля, что фильтр их не ломает
]


@pytest.mark.parametrize(
    "word",
    ["А4", "XL", "ST", "SE", "GT", "ET", "GP", "QF"],
)
def test_short_non_whitelisted_code_is_not_a_brand(word):
    dictionary = ManufacturerBrandDictionary(_PROD_SHORT_DICT_SAMPLE)
    assert dictionary.find_in_name(word) is None


@pytest.mark.parametrize(
    "word,expected_brand",
    [
        ("HP", "HP"),
        ("LG", "LG"),
        ("WD", "WD"),
        ("Makita", "Makita"),
        ("бош", "Bosch"),
        ("зубр", "Зубр"),
    ],
)
def test_whitelisted_short_or_normal_brand_still_found(word, expected_brand):
    dictionary = ManufacturerBrandDictionary(_PROD_SHORT_DICT_SAMPLE)
    assert dictionary.find_in_name(word) == expected_brand


def test_short_code_inside_phrase_does_not_block_real_brand_elsewhere():
    """«бумага офисная А4» не даёт бренд, но «картридж HP» — даёт (тот же
    словарь, оба пути — точный/фонетический — используют общий фильтр
    _is_recognizable_brand_word)."""
    dictionary = ManufacturerBrandDictionary(_PROD_SHORT_DICT_SAMPLE)
    assert dictionary.find_in_name("бумага офисная А4") is None
    assert dictionary.find_in_name("картридж HP") == "HP"


# ── размерные обозначения (одежда/бумага) — никогда не бренд ───────────────

@pytest.mark.parametrize("size", ["XL", "XXL", "XXXL", "S", "M", "L", "А4"])
def test_size_token_never_a_brand_even_if_whitelisted_by_mistake(size):
    # Даже если бы размер случайно оказался в белом списке — _SIZE_TOKENS
    # исключает его безусловно (владелец, 28.10.2026, п.3 задания).
    dictionary = ManufacturerBrandDictionary([size, "Makita"])
    assert dictionary.find_in_name(f"товар {size} размер") is None


# ── предлог/союз или вид товара, совпавший со значением manufacturer, —
#    не бренд (общий фильтр _is_recognizable_brand_word, п.2 задания).
#    Длина ключа у этих слов >3 — короткий gate (п.1) их не ловит, нужен
#    именно общий хелпер фильтра стоп-слов/видов товара.

# ── вид товара по словоформе (владелец, 28.10.2026, QA-находка: "болгарку"
#    должна находить то же, что "болгарка" — через ts_lexize('russian_stem'),
#    тот же стеммер, что у to_tsvector('russian', ...) в product_search.py,
#    см. docstring resolve_type_by_stem) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_type_by_stem_recognizes_inflected_form(db_session):
    product_query_parse_module._type_stem_cache["index"] = None
    product_query_parse_module._type_stem_cache["built_at"] = 0.0

    parsed = parse_query("болгарку")
    assert parsed.product_type is None  # точно (буквально) не распознано

    resolved = await product_query_parse_module.resolve_type_by_stem(db_session, parsed)
    assert resolved.product_type == "шлифмашина"
    assert resolved.type_literal == "болгарку"
    assert "болгарку" in resolved.required
    assert "болгарку" not in resolved.optional


@pytest.mark.asyncio
async def test_resolve_type_by_stem_skips_db_when_already_recognized():
    """Если parse_query() УЖЕ нашла вид буквально — resolve_type_by_stem
    не идёт в БД вовсе (возвращает тот же объект без изменений) — db=None
    не должен уронить вызов."""
    parsed = parse_query("болгарка")
    assert parsed.product_type == "шлифмашина"
    resolved = await product_query_parse_module.resolve_type_by_stem(None, parsed)
    assert resolved is parsed


def test_preposition_matching_manufacturer_value_is_not_a_brand():
    # "для" — предлог (_PREPOSITION_STOPWORDS), гипотетически попавший в
    # manufacturer при грязном импорте — не должен мешать обычным фразам.
    dictionary = ManufacturerBrandDictionary(["для", "Makita"])
    assert dictionary.find_in_name("чехол для дрели") is None


def test_product_type_word_matching_manufacturer_value_is_not_a_brand():
    # "лопата" — вид товара (PRODUCT_TYPE_WORDS), гипотетически попавший в
    # manufacturer, — не должен мешать фразе "лопата штыковая".
    dictionary = ManufacturerBrandDictionary(["лопата", "Makita"])
    assert dictionary.find_in_name("лопата штыковая") is None
