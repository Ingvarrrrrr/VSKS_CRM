"""Тесты backend/app/services/catalog_gala/ad_text_filter.py (владелец,
26.10.2026, Задача 1, решение дня после _strip_description_prefix).

Тексты — РЕАЛЬНЫЕ description трёх товаров из
C:\\Users\\1\\Downloads\\Товары и ТЗ\\fire_equipment_nomenclature.json
(name == "Гидроэлеватор пожарный Г-600" / "Колонка пожарная КПА" /
"ШКПС (шлем-каска пожарного спасателя) с пелериной (черная)"), взяты как
есть (не упрощены) — см. rebuild_samples.md для контекста "было/станет"."""
from app.services.catalog_gala.ad_text_filter import strip_ad_sentences
from app.services.catalog_gala.from_store_nomenclature import _strip_description_prefix

_G600_RAW = (
    "Гидроэлеватор пожарный Г-600 по низким ценам в Москве в компании "
    "Magazin01. На нашем сайте большой выбор пожарного оборудования, у нас "
    "вы можете купить гидроэлеватор Г-600 с доставкой по России."
)

_KPA_RAW = (
    "Колонка пожарная КПА по низким ценам в Москве в компании Magazin01. "
    "На нашем сайте большой выбор пожарного оборудования, у нас вы можете "
    "купить пожарную водоразборную колонку КПА с доставкой по России."
)

_SHKPS_RAW = (
    "ШКПС (шлем-каска пожарного спасателя) с пелериной (черная) в Москве "
    "по выгодным ценам в интернет-магазине Magazin01.ru. Продажа шлемов и "
    "касок для пожарных, пожарного и противопожарного оборудования с "
    "доставкой по всей России."
)


def test_g600_is_entirely_ad_becomes_none():
    """Г-600: оба предложения рекламные ("по низким ценам"/"в компании" и
    "на нашем сайте"/"купить"/"с доставкой по") — результат None."""
    assert strip_ad_sentences(_G600_RAW) is None


def test_kpa_is_entirely_ad_becomes_none():
    """КПА: тот же паттерн, что у Г-600 — результат None."""
    assert strip_ad_sentences(_KPA_RAW) is None


def test_shkps_actual_result():
    """ШКПС: первое предложение рекламное ("по выгодным ценам"/
    "интернет-магазин"/"magazin01"), второе тоже рекламное ("продаж" —
    корень слова "Продажа" — и "с доставкой по") — фактический результат:
    всё удалено, None. Зафиксировано как есть, не подогнано."""
    assert strip_ad_sentences(_SHKPS_RAW) is None


def test_empty_and_none_input():
    assert strip_ad_sentences(None) is None
    assert strip_ad_sentences("") is None
    assert strip_ad_sentences("   ") is None


def test_non_ad_text_is_untouched():
    """Ластик 152085 (Сима-ленд) — текст без рекламных маркеров, не трогаем."""
    text = "Ластик фигурный «Панда». Сертифицированная продукция."
    assert strip_ad_sentences(text) == text


def test_only_ad_sentence_removed_rest_kept():
    text = "Нормальный технический текст о товаре. Купить можно у нас с доставкой по России."
    assert strip_ad_sentences(text) == "Нормальный технический текст о товаре."


def test_multiple_lines_each_filtered_independently():
    text = (
        "Описание товара без рекламы.\n"
        "Купить с доставкой по Москве в компании Magazin01.\n"
        "Второй технический абзац."
    )
    result = strip_ad_sentences(text)
    assert "Купить" not in result
    assert "Описание товара без рекламы." in result
    assert "Второй технический абзац." in result


def test_marker_matches_case_insensitive_and_as_substring():
    assert strip_ad_sentences("Товар. КУПИТЬ можно здесь.") == "Товар."
    assert strip_ad_sentences("Товар. Продажа и продаже запрещены без документов.") == "Товар."


# --- Задача 2 (владелец, 26.10.2026, расширение _AD_MARKERS, пример — пояс
# ППС-А) ------------------------------------------------------------------

# РЕАЛЬНЫЙ description товара "Пояс пожарный спасательный ППС-А
# (двухштыревой) 3/1050-1320" из
# C:\\Users\\1\\Downloads\\Товары и ТЗ\\fire_equipment_nomenclature.json
# (Magazin01), взят как есть.
_PPS_A_RAW = (
    "Пояс пожарный спасательный ППС-А (двухштыревой) 3/1050-1320 в Москве "
    "в интернет-магазине Magazin01.ru. Пожарные страховочные привязи, "
    "пояса и карабины в Москве в специализированном магазине пожарной "
    "техники. Доставка по всей России."
)


def test_pps_a_new_markers_strip_each_sentence():
    """Каждое из трёх предложений ППС-А попадает под СВОЙ маркер:
    1) "интернет-магазин"/"magazin01" (уже были);
    2) "в специализированном магазине" + "магазине пожарной техники" (новые,
       задача 2);
    3) "доставка по всей россии" (новый, задача 2).
    Проверяем по отдельности — так видно, что именно новые маркеры режут."""
    s2 = (
        "Пожарные страховочные привязи, пояса и карабины в Москве в "
        "специализированном магазине пожарной техники."
    )
    s3 = "Доставка по всей России."
    assert strip_ad_sentences(s2) is None
    assert strip_ad_sentences(s3) is None


def test_pps_a_full_description_actual_result_after_prefix_and_ad_filter():
    """Полный путь, как в from_store_nomenclature.convert: срезка служебного
    префикса (здесь префикса "Описание ..." нет — ППС-А начинается не с
    него, _strip_description_prefix возвращает текст без изменений) + новый
    расширенный strip_ad_sentences.

    ФАКТИЧЕСКИЙ результат (не подогнан искусственно): у ППС-А реклама
    занимает ВСЕ три предложения описания (магазин/доставка — в каждом),
    собственного технического текста (материал, размер пояса и т.п.) в
    этом description у поставщика не было вообще — результат None.
    Техданные пояса (размер 3/1050-1320) приходят не из description, а из
    названия товара и характеристик (specifications), которые этот фильтр
    не трогает."""
    prefixed = _strip_description_prefix(_PPS_A_RAW, "Пояс пожарный спасательный ППС-А (двухштыревой) 3/1050-1320")
    assert prefixed == _PPS_A_RAW  # префикса "Описание" в этом тексте нет

    result = strip_ad_sentences(prefixed)
    assert result is None
