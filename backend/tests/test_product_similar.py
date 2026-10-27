"""similarity_key — пилот похожих карточек (владелец, 27.10.2026). Фиксирует
ФАКТИЧЕСКОЕ поведение на 5 реальных карточках «Ярпожинвест ОП-2» с прода
(разные магазины, разные названия) — задание прямо требует зафиксировать
поведение, не угадывать идеальный алгоритм."""
from app.services.product_similar import similarity_key

_NAMES = [
    "Огнетушитель порошковый ОП-2 Ярпожинвест (г. Ярославль)",
    "Огнетушитель порошковый Ярпожинвест ОП-2 (з) АВСЕ ЗПУ Китай",
    "Огнетушитель порошковый «Ярпожинвест» ОП-2(3), ABCE-01(А)",
    "Огнетушитель Ярпожинвест ОП-2 з АВСЕ",
    "Огнетушитель порошковый ОП-2 (ЗПУ латунь) Ярпожинвест (г. Ярославль)",
]

_KNOWN_BRANDS = {"ярпожинвест"}


def test_all_five_share_brand_and_base_model():
    keys = [similarity_key(n, None, _KNOWN_BRANDS) for n in _NAMES]
    for k in keys:
        assert k.brand == "ярпожинвест", k
        assert k.base_model == "оп2", k


def test_rest_tokens_differ_for_cards_with_extra_words():
    k0, k1, k2, k3, k4 = (similarity_key(n, None, _KNOWN_BRANDS) for n in _NAMES)
    # #106562 несёт "зпу"/"китай"/"авсе" — этого нет у #88971 (голая карточка)
    assert set(k1.rest_tokens) != set(k0.rest_tokens)
    # #241102 несёт код "abce-01(а)" — тоже отличается от голой карточки
    assert set(k2.rest_tokens) != set(k0.rest_tokens)
    # #2415 несёт "латунь" — отличается от остальных
    assert "латунь" in k4.rest_tokens
    assert "латунь" not in k0.rest_tokens


def test_explicit_manufacturer_field_used_as_brand_when_present():
    key = similarity_key("ОП-2 порошковый", "Ярпожинвест", set())
    assert key.brand == "ярпожинвест"
    assert key.base_model == "оп2"


def test_group_key_none_without_brand_or_model():
    key = similarity_key("Товар без бренда и модели", None, set())
    assert key.group_key is None


# --- Правки после прогона на проде 27.10.2026 ---------------------------

def test_op2_op10_op100_are_different_base_models():
    """Owner 27.10.2026: ОП-1/ОП-10/ОП-100 слиплись в «оп1» из-за
    цифро-буквенного фолда (0→о) — хвостовые нули съедались."""
    k1 = similarity_key("Огнетушитель ОП-1 Ярпожинвест", None, _KNOWN_BRANDS)
    k10 = similarity_key("Огнетушитель ОП-10 Ярпожинвест", None, _KNOWN_BRANDS)
    k100 = similarity_key("Огнетушитель ОП-100 Ярпожинвест", None, _KNOWN_BRANDS)
    assert k1.base_model == "оп1"
    assert k10.base_model == "оп10"
    assert k100.base_model == "оп100"
    assert len({k1.base_model, k10.base_model, k100.base_model}) == 3


def test_ou2_ou20_are_different():
    k2 = similarity_key("Огнетушитель углекислотный ОУ-2 Ярпожинвест", None, _KNOWN_BRANDS)
    k20 = similarity_key("Огнетушитель углекислотный ОУ-20 Ярпожинвест", None, _KNOWN_BRANDS)
    assert k2.base_model == "оу2"
    assert k20.base_model == "оу20"


def test_typo_poroshkovyi_treated_as_stopword():
    k = similarity_key("Огнетушитель поршковый ОП-2 Ярпожинвест", None, _KNOWN_BRANDS)
    assert "поршковый" not in k.rest_tokens


def test_manufacturer_code_from_name_examples():
    from app.services.product_similar import manufacturer_code_from_name
    assert manufacturer_code_from_name("Дрель-шуруповёрт Makita DHP482Z") == "dhp482z"
    assert manufacturer_code_from_name("Автомат DEKraft 14054DEK") == "14054dek"
    assert manufacturer_code_from_name("Стеллаж MS Standart MVA20-1-016-C") == "mva201016c"


def test_manufacturer_code_handles_cyrillic_lookalike_latin_letter():
    """Owner 27.10.2026: «GA5090X01» в исходнике иногда напечатан с
    кириллической «Х» вместо латинской "X" — тот же код должен распознаться."""
    from app.services.product_similar import manufacturer_code_from_name
    assert manufacturer_code_from_name("Болгарка Makita GA5090X01") == "ga5090x01"
    assert manufacturer_code_from_name("Болгарка Makita GA5090Х01") == "ga5090x01"  # кириллическая "Х"


def test_manufacturer_code_excludes_size_and_standard_tokens():
    from app.services.product_similar import manufacturer_code_from_name
    assert manufacturer_code_from_name("Плитка 15x15 белая") is None
    assert manufacturer_code_from_name("Телевизор DVB-T2 1080P") is None
    assert manufacturer_code_from_name("Батарейка CR2016 Philips") is None
    assert manufacturer_code_from_name("Батарейка LR03 Kodak") is None
    assert manufacturer_code_from_name("Краска RAL7035") is None


# --- Приёмка диалога «Похожие товары», п.1 (владелец, 27.10.2026):
# заголовок группы не должен показывать свёрнутый ключ («оп2»/«df332dwme»).

def test_base_model_display_keeps_original_case_and_dash():
    key = similarity_key("Огнетушитель порошковый ОП-2 Ярпожинвест", None, _KNOWN_BRANDS)
    assert key.base_model == "оп2"
    assert key.base_model_display == "ОП-2"


def test_base_model_display_drops_bracket_suffix_like_base_model():
    key = similarity_key("Огнетушитель порошковый Ярпожинвест ОП-2(з) АВСЕ", None, _KNOWN_BRANDS)
    assert key.base_model_display == "ОП-2"


def test_manufacturer_code_display_keeps_original_case():
    key = similarity_key("Дрель-шуруповёрт Makita DF332DWME", "Makita", set())
    assert key.manufacturer_code == "df332dwme"
    assert key.manufacturer_code_display == "DF332DWME"


def test_manufacturer_code_display_uses_raw_article_when_flagged():
    key = similarity_key(
        "Автоматический выключатель", "DEKraft",
        set(), article="14054DEK", article_is_manufacturer=True,
    )
    assert key.manufacturer_code == "14054dek"
    assert key.manufacturer_code_display == "14054DEK"


def test_article_used_as_manufacturer_code_only_when_flagged():
    key_mpo = similarity_key(
        "Автоматический выключатель", "DEKraft",
        set(), article="14054DEK", article_is_manufacturer=True,
    )
    assert key_mpo.manufacturer_code == "14054dek"

    # Сима-ленд/Бауцентр: article — СВОЙ номер магазина, не производителя —
    # article_is_manufacturer=False -> не используется как код (а в названии
    # нет кандидата → manufacturer_code=None).
    key_sima = similarity_key(
        "Огнетушитель порошковый", "Ярпожинвест",
        set(), article="1431671", article_is_manufacturer=False,
    )
    assert key_sima.manufacturer_code is None
