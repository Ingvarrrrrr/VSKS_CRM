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


# --- Задача 3 (владелец, 2026-10-26, расширение _AD_MARKERS — найдена
# непойманная реклама "Широкий выбор..." у 403 товаров Магазин 01 /
# К-Спасатель; проверка на всём prod-каталоге, см. ad_filter_review.md)
# -----------------------------------------------------------------------

# РЕАЛЬНЫЙ description товара (Магазин 01, fire_equipment_nomenclature.json,
# id 59186/91073/91094 и др.) — пример владельца.
_VALVE_WIDE_CHOICE_RAW = (
    "Широкий выбор запорно-регулирующей арматуры для систем водяного и "
    "пенного пожаротушения: противопожарные клапаны, задвижки, вентили, "
    "затворы.\n\nДиаметр: 300 мм"
)


def test_owner_example_wide_choice_valve_removed():
    """Пример владельца: предложение-реклама удаляется, техническая
    характеристика (второй абзац) не затрагивается этой функцией (она
    работает только с description, абзац характеристик — отдельное
    поле)."""
    sentence = (
        "Широкий выбор запорно-регулирующей арматуры для систем водяного "
        "и пенного пожаротушения: противопожарные клапаны, задвижки, "
        "вентили, затворы."
    )
    assert strip_ad_sentences(sentence) is None


# --- Защита от ложных срабатываний на технический текст -----------------

def test_fp_delivery_of_cargo_not_removed():
    """«Авиадесантируемый кейс ... для доставки грузов ...» — доставка
    ГРУЗОВ (технический термин), не доставка покупателю — не трогаем."""
    text = "Авиадесантируемый кейс предназначен для доставки грузов и оборудования к месту применения."
    assert strip_ad_sentences(text) == text


def test_fp_insulation_material_quality_not_removed():
    text = "В качестве утеплителя используется гусиный пух высокого качества."
    assert strip_ad_sentences(text) == text


def test_fp_fraction_not_removed_by_discount_marker():
    """"скидк" — корень "скидка", не должен ловить "фракция"."""
    text = "Масса 10 кг, фракция 7-15 см."
    assert strip_ad_sentences(text) == text


def test_fp_brooch_bouquet_not_removed():
    text = "Брошь «Букет цветов в корзине»."
    assert strip_ad_sentences(text) == text


def test_fp_wide_choice_of_diameters_not_removed():
    """«Большой выбор диаметров и размеров» — про сам товар (разные
    диаметры одной позиции), не "широкий выбор" магазина — маркер
    анкорен к началу предложения и не ловит "больш..." вообще."""
    text = "Большой выбор диаметров и размеров, позволяющий подобрать необходимые кранцы на судно любого размера."
    assert strip_ad_sentences(text) == text


def test_fp_wide_assortment_of_compatible_gear_not_removed():
    """«...широкого ассортимента применяемого на высоте оборудования» —
    про совместимость снаряжения, "широкий ассортимент" не в начале
    предложения — не трогаем."""
    text = "Универсальный комплект для защиты от падения широкого ассортимента применяемого на высоте оборудования."
    assert strip_ad_sentences(text) == text


def test_fp_wide_choice_of_buoyancy_not_removed():
    """«Широкий выбор по плавучести»/«по форме и плавающей способности» —
    реальный технический текст о поплавках (не реклама магазина),
    исключено явным отрицательным просмотром вперёд."""
    assert strip_ad_sentences("Широкий выбор по плавучести.") == "Широкий выбор по плавучести."
    assert strip_ad_sentences(
        "Широкий выбор по форме и плавающей способности."
    ) == "Широкий выбор по форме и плавающей способности."


def test_fp_courier_delivery_restriction_not_removed():
    """«...курьерская доставка по Москве. Не отправляем транспортными
    компаниями... из-за ограничений на перевозку опасных грузов» — важное
    техническое ограничение по опасному грузу, не реклама; "доставка по"
    сама по себе маркером не является (слишком широко)."""
    text = "Важно: только самовывоз или курьерская доставка по Москве."
    assert strip_ad_sentences(text) == text


# --- Новые маркеры (Задача 3) — по одному реальному примеру из prod ------

def test_marker_u_nas_bolshoy_vybor():
    text = "У нас большой выбор противопожарных средств и оборудования."
    assert strip_ad_sentences(text) is None


def test_marker_my_predlagaem_shirokiy_assortiment():
    text = "Мы предлагаем широкий ассортимент средств пожаротушения и пожарной безопасности."
    assert strip_ad_sentences(text) is None


def test_marker_v_nashem_kataloge():
    text = "В нашем каталоге представлены только сертифицированное пожарное оборудование и средства тушения пожаров."
    assert strip_ad_sentences(text) is None


def test_marker_vy_mozhete_priobresti():
    text = "Здесь вы можете приобрести строп для применения в страховочных системах."
    assert strip_ad_sentences(text) is None


def test_marker_po_dostupnoy_cene():
    text = "Здесь вы сможете приобрести одинарный строп ленточный по доступной цене."
    assert strip_ad_sentences(text) is None


def test_marker_po_dostupnym_cenam():
    text = "Профессиональная справочная литература по доступным ценам."
    assert strip_ad_sentences(text) is None


def test_marker_melkim_optom():
    text = "Если вам нужна мелким оптом аптечка настенная металлическая - обратитесь к менеджерам."
    assert strip_ad_sentences(text) is None


def test_marker_skidka():
    text = "Всем клиентам мы предоставляем индивидуальные условия и специальные скидки в зависимости от объема заказа."
    assert strip_ad_sentences(text) is None


def test_marker_garantiruem():
    text = "Мы гарантируем надежность и качество поставленного товара."
    assert strip_ad_sentences(text) is None


def test_marker_garantiya_kachestva():
    text = "Гарантия качества, доставка по РФ."
    assert strip_ad_sentences(text) is None


def test_marker_onlayn_zakaz():
    text = "Онлайн заказ с доставкой."
    assert strip_ad_sentences(text) is None


def test_marker_dostavka_po_rf():
    text = "Доставка по РФ."
    assert strip_ad_sentences(text) is None


def test_marker_dostavka_vo_vse_regiony():
    text = "Мы предлагаем короба и кабельные каналы с доставкой во все регионы России."
    assert strip_ad_sentences(text) is None


def test_marker_shirokiy_vybor_pattern():
    text = "Широкий выбор пожарных извещателей: дымовые, тепловые, ручные и комбинированные модели."
    assert strip_ad_sentences(text) is None


def test_marker_shirokiy_assortiment_pattern():
    text = "Широкий ассортимент аварийного и пожарного оборудования."
    assert strip_ad_sentences(text) is None


# --- Задача 4 (владелец, 27.10.2026): корень "продаж" снят — ловил
# технические поля (гарантия/дата/атрибут), где "продажи"/"продаже" не
# реклама; см. strip_ads_from_descriptions.py --apply на prod CSV
# (213 519 товаров) и докстринг _AD_MARKERS выше. Вместо широкого корня —
# узкие формы ("продажа ... с доставкой"/"продажа ... по ... ценам"/
# "осуществляем продажу") в _AD_MARKER_PATTERNS/_AD_MARKERS. -----------

def test_marker_prodazha_s_dostavkoy_removed():
    text = "Продажа огнетушителей ОП-4 с доставкой по городу."
    assert strip_ad_sentences(text) is None


def test_marker_prodazha_po_cenam_removed():
    text = "Осуществляем продажу пожарных рукавов по оптовым ценам для организаций."
    assert strip_ad_sentences(text) is None


def test_marker_osushestvlyaem_prodazhu_removed():
    text = "Мы осуществляем продажу любых объёмов партий товара."
    assert strip_ad_sentences(text) is None


# --- 10 ложных срабатываний старого корня "продаж" (реальные тексты
# prod CSV, отчёт 27.10.2026) — технические поля/гарантийные сроки, НЕ
# реклама, теперь не удаляются. ---------------------------------------

def test_fp_rasprodazha_net_not_removed():
    assert strip_ad_sentences("Распродажа:\tНет") == "Распродажа:\tНет"


def test_fp_edinica_prodazhi_not_removed():
    text = "Единица продажи"
    assert strip_ad_sentences(text) == text


def test_fp_lider_prodazh_not_removed():
    text = "Лидер продаж: Да"
    assert strip_ad_sentences(text) == text


def test_fp_garantijnye_obyazatelstva_so_dnya_prodazhi_not_removed():
    text = "Гарантийные обязательства: 1 год со дня продажи."
    assert strip_ad_sentences(text) == text


def test_fp_kolichestvo_edinic_prodazh_v_upakovke_not_removed():
    text = "Количество единиц продаж в транспортной упаковке"
    assert strip_ad_sentences(text) == text


def test_fp_srok_dejstviya_garantii_s_daty_prodazhi_not_removed():
    text = "Срок действия гарантии: 12 месяцев с даты продажи"
    assert strip_ad_sentences(text) == text


def test_fp_srok_garantijnogo_obsluzhivaniya_s_daty_prodazhi_not_removed():
    text = "Срок гарантийного обслуживания: 2 года (с даты продажи)"
    assert strip_ad_sentences(text) == text


def test_fp_garantijnyj_srok_ekspluatacii_so_dnya_prodazhi_not_removed():
    text = "Гарантийный срок эксплуатации: 1 календарный год со дня продажи"
    assert strip_ad_sentences(text) == text


def test_fp_v_prodazhe_s_goda_not_removed():
    text = "В продаже с:\t2018 года"
    assert strip_ad_sentences(text) == text


def test_fp_garantijnyj_srok_ekspluatacii_s_daty_prodazhi_mesyacev_not_removed():
    text = "Гарантийный срок эксплуатации с даты продажи, месяцев не менее 12"
    assert strip_ad_sentences(text) == text
