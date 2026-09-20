"""text_match.similarity() и омоглиф-фолдинг normalize() (владелец, 2026-09-21):
подбор товара для плановой позиции «Перчатки» показывал «Перчатки латексные»
и длинное описание совсем другого перчаточного товара ОБА как 100% — это была
ОДНОСТОРОННЯЯ мера покрытия токенов query (text_match.score), у однословного
запроса она всегда 1.0 у любого названия, куда слово входит целиком. similarity()
— симметричный Jaccard по стемам, 100% только при normalize(a)==normalize(b).

Отдельно: normalize() теперь приводит латинские омоглифы к кириллице внутри
СМЕШАННЫХ (кириллица+латиница в одном слове) или коротких (<=2 символа) чисто
латинских слов — «Размер XL»/«Размер ХL» (кириллическая Х) совпадают, а
«Master-Pro»/«SBARCO» (длинные чисто латинские слова) не трогаются — см.
text_match._fold_word_homoglyphs docstring.

Не копия app.services.product_catalog_match._CHAR_FOLD_MAP (тот — глобальный
fold для ТОЧНОГО дедупа каталога, здесь — узкий fold для ИНТЕРАКТИВНОГО
ранжирования похожести, разные задачи и разный риск ложных срабатываний, см.
докстринг _MIXED_WORD_HOMOGLYPHS в text_match.py)."""
from app.services.text_match import normalize, similarity, tokenize


GLOVE_QUERY = "Перчатки"
GLOVE_LATEX = "Перчатки латексные"
GLOVE_PROTECTIVE = "Защитные перчатки"
GLOVE_LONG_DESCRIPTIVE = (
    "Перчатки цельноспилковые Master-Pro ПРОФИ (ДРАЙВЕР) / водительские "
    "перчатки, размер 10,5 XL, 20 пар 9080-GSD-10"
)


def test_similarity_full_match_is_1():
    assert similarity("Принтер HP", "принтер   hp") == 1.0
    assert similarity("Огнетушитель ОП-5", "огнетушитель  оп-5") == 1.0


def test_similarity_single_word_partial_overlap_is_not_100_percent():
    """Ровно жалоба владельца: однословный query «Перчатки», полностью входящий
    в название товара, — это НЕ 100% совпадение имени."""
    assert similarity(GLOVE_QUERY, GLOVE_LATEX) == 0.5
    assert similarity(GLOVE_QUERY, GLOVE_PROTECTIVE) == 0.5
    assert similarity(GLOVE_QUERY, GLOVE_LONG_DESCRIPTIVE) < 0.2
    # ни один из кандидатов не «100%»
    for name in (GLOVE_LATEX, GLOVE_PROTECTIVE, GLOVE_LONG_DESCRIPTIVE):
        assert similarity(GLOVE_QUERY, name) < 1.0, name


def test_similarity_ranks_closer_name_above_longer_description():
    """«По названию» должен ранжировать «Перчатки латексные»/«Защитные перчатки»
    (симметрично близкие по составу слов) выше длинного описания с кучей
    посторонних слов (артикул, размер, бренд, количество)."""
    scored = sorted(
        (GLOVE_LATEX, GLOVE_PROTECTIVE, GLOVE_LONG_DESCRIPTIVE),
        key=lambda name: -similarity(GLOVE_QUERY, name),
    )
    assert scored[-1] == GLOVE_LONG_DESCRIPTIVE, scored


def test_similarity_symmetric():
    assert similarity(GLOVE_QUERY, GLOVE_LATEX) == similarity(GLOVE_LATEX, GLOVE_QUERY)


def test_homoglyph_fold_mixed_size_code_xl():
    """«Размер XL» (латинские X и L) и «Размер ХL» (кириллическая Х, латинская
    L) — визуально неотличимы, обязаны совпадать после normalize()."""
    assert normalize("Размер XL") == normalize("Размер ХL")
    assert normalize("перчатки, размер 10,5 XL") == normalize("перчатки, размер 10,5 ХL")


def test_homoglyph_fold_mixed_word_matches_correct_cyrillic_spelling():
    """Слово, где раскладка съехала посреди набора (одна латинская буква среди
    кириллицы — «рaзмер» с латинской 'a'), нормализуется так же, как
    правильное написание «размер» целиком кириллицей."""
    assert normalize("рaзмер") == normalize("размер")
    # последняя буква — латинская 'p' (визуальный двойник кириллической «р»,
    # НЕ латинская 'r' — фонетическое, а не зрительное сходство, её в карте нет)
    assert normalize("Ткань 100% полиэстеp") == normalize("Ткань 100% полиэстер")


def test_homoglyph_fold_does_not_corrupt_pure_latin_brand_words():
    """«Master-Pro» и «SBARCO» — чисто латинские слова длиной от 3 символов,
    омоглиф-фолдинг их не трогает (см. _SHORT_PURE_LATIN_LEN=2)."""
    assert normalize("Master-Pro") == "master pro"
    assert normalize("SBARCO") == "sbarco"
    assert tokenize("Master-Pro") == ["master", "pro"]
    assert tokenize("Защитные перчатки SBARCO") == ["защитные", "перчатки", "sbarco"]


def test_homoglyph_fold_does_not_break_long_descriptive_name():
    """Полная длинная строка из реального замечания владельца — Master-Pro
    внутри неё остаётся латиницей, XL внутри неё (не смешанное само по себе,
    но короткое) уходит в кириллицу, GSD (3 буквы, не в карте) не трогается."""
    norm = normalize(GLOVE_LONG_DESCRIPTIVE)
    assert "master" in norm and "pro" in norm
    assert "gsd" in norm
