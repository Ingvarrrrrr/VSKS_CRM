"""Тесты правила «тот же товар» (владелец, 27.10.2026) —
app.services.product_name_signature. SECRET_KEY для импорта app.* берётся
из tests/conftest.py (ПРАВИЛО №6, второй фиктивный ключ здесь не завести)."""
from app.services.product_name_signature import build_signature, match


def _sig(name, manufacturer=None, characteristics=None, brand_dictionary=None):
    item = {
        "name": name,
        "manufacturer": manufacturer,
        "characteristics": characteristics or [],
    }
    return build_signature(item, brand_dictionary=brand_dictionary)


def _decision(a_name, b_name, **kw_a_b):
    """kw_a_b: a_manufacturer/b_manufacturer/a_characteristics/b_characteristics."""
    a = _sig(a_name,
             manufacturer=kw_a_b.get("a_manufacturer"),
             characteristics=kw_a_b.get("a_characteristics"))
    b = _sig(b_name,
             manufacturer=kw_a_b.get("b_manufacturer"),
             characteristics=kw_a_b.get("b_characteristics"))
    return match(a, b)


def test_op2_not_op20():
    res = _decision("Огнетушитель ОП-2", "Огнетушитель ОП-20")
    assert res["decision"] == "no"


def test_fire_class_fused_or_spaced_still_matches():
    res = _decision("ОУ-5 ВСЕ РИФ", "ОУ-5-ВСЕ (55В, С, Е) РИФ",
                     a_manufacturer="РИФ", b_manufacturer="РИФ")
    assert res["decision"] == "auto", res


def test_country_conflict():
    res = _decision("ЗПУ Китай", "ЗПУ Россия")
    assert res["decision"] == "no"
    assert "страна" in res["reason"]


def test_multiple_variants_in_one_store_is_check():
    # Три варианта ОУ-3 у магазина A (отличаются исполнением — бесшовная/
    # сварная, без доп. цифр в названии, чтобы не задеть жёсткий гейт по
    # цифровым токенам), один у магазина B — однозначности нет (п.5),
    # decision=check, а не auto.
    from app.services.product_name_signature import match as _match

    a1 = _sig("Огнетушитель ОУ-3 бесшовная", manufacturer="РИФ")
    a2 = _sig("Огнетушитель ОУ-3 сварная", manufacturer="РИФ")
    a3 = _sig("Огнетушитель ОУ-3", manufacturer="РИФ")
    b1 = _sig("Огнетушитель ОУ-3", manufacturer="РИФ")

    res = _match(a1, b1, peers_a=(a2, a3))
    assert res["decision"] == "check", res


def test_color_conflict_white_vs_gold():
    res = _decision("CAPPIO RK001 белая", "CAPPIO RK001 золото",
                     a_manufacturer="CAPPIO", b_manufacturer="CAPPIO")
    assert res["decision"] == "no"
    assert "цвет" in res["reason"]


def test_makita_different_model_suffix():
    res = _decision("Дрель-шуруповёрт Makita DF333DWME", "Дрель-шуруповёрт Makita DF333DWAE",
                     a_manufacturer="MAKITA", b_manufacturer="MAKITA")
    assert res["decision"] == "no"


def test_makita_same_model_extra_words_match():
    res = _decision("Makita LXT DJR187Z", "Сабельная пила аккумуляторная Makita LXT DJR187Z",
                     a_manufacturer="MAKITA", b_manufacturer="MAKITA")
    assert res["decision"] == "auto", res


def test_hose_with_heads_not_same_as_hose_with_head_and_nozzle():
    res = _decision("Рукав пожарный с головками ГР-50",
                     "Рукав пожарный с головкой ГР-50 и стволом РС-50.01")
    assert res["decision"] != "auto"


def test_brand_conflict_same_model_code():
    res = _decision("Батарейка CR2016 Philips", "Батарейка CR2016 Kodak",
                     a_manufacturer="Philips", b_manufacturer="Kodak")
    assert res["decision"] == "no"
    assert "бренд" in res["reason"]


def test_corrugated_box_different_dimensions_and_grade():
    # Инцидент июня: "примерное" сравнение без жёсткой проверки цифр ложно
    # склеило разные товары — размеры и марка ДОЛЖНЫ отличать, не "похожесть".
    res = _decision(
        "Гофрокороб д600*ш400*в400 мм, марка Т24, профиль С, 3-слойный",
        "Гофрокороб д500*ш370*в120 мм, марка Т22, профиль С, 3-слойный",
    )
    assert res["decision"] == "no"


def test_laptop_different_generation_and_cpu():
    res = _decision("Ноутбук ASUS ZenBook 14 i7", "Ноутбук ASUS ZenBook 13 i5",
                     a_manufacturer="ASUS", b_manufacturer="ASUS")
    assert res["decision"] == "no"


def test_mass_conflict_same_name_different_weight():
    res = _decision(
        "Огнетушитель ОП-4(з) АВСЕ Ярпожинвест",
        "Огнетушитель ОП-4(з) АВСЕ Ярпожинвест",
        a_manufacturer="Ярпожинвест", b_manufacturer="Ярпожинвест",
        a_characteristics=[{"name": "Масса огнетушителя полная (не более)", "value": "4", "unit": "кг"}],
        b_characteristics=[{"name": "Масса огнетушителя полная (не более)", "value": "5", "unit": "кг"}],
    )
    assert res["decision"] == "no"
    assert "масс" in res["reason"]


def test_mass_unit_conversion_kg_equals_grams():
    res = _decision(
        "Гиря спортивная 2 кг",
        "Гиря спортивная 2 кг",
        a_characteristics=[{"name": "Вес", "value": "2", "unit": "кг"}],
        b_characteristics=[{"name": "Масса", "value": "2000", "unit": "г"}],
    )
    assert res["decision"] == "auto", res


def test_cabinet_vs_case_different_product_type():
    # Владелец, ревью auto-пар 27.10.2026: тот же артикул производителя у
    # обоих, но "Шкаф" (cabinet) != "Пенал" (case) — разный вид товара.
    res = _decision("Шкаф для огнетушителя DAKEN Regon 82170",
                     "Пенал для огнетушителя DAKEN Regon 82170")
    assert res["decision"] == "no"
    assert "вид товара" in res["reason"]


def test_ups_abbreviation_matches_full_name_product_type():
    from app.services.product_name_signature import match as _match
    a = _sig("ИБП Штиль SR1103L")
    b = _sig("Источник бесперебойного питания ШТИЛЬ SR1103L (внешние АКБ)")
    res = _match(a, b)
    assert res["decision"] == "auto", res


def test_name_unit_quantity_is_not_model_index():
    # Владелец, ревью kuvalda↔baucenter: лишние "18 В 1х5,0 Ач 2,0 Дж" у
    # одной стороны — свойство, не код модели, НЕ должно ломать точное
    # совпадение индекса.
    res = _decision(
        "Аккумулятор ЗУБР АКБ-18-4 18 В 1х5,0 Ач 2,0 Дж",
        "Аккумулятор ЗУБР АКБ-18-4",
        a_manufacturer="ЗУБР", b_manufacturer="ЗУБР",
    )
    assert res["decision"] == "auto", res


def test_brand_case_and_punctuation_insensitive():
    # Владелец, 27.10.2026: регистр/пунктуация у бренда не важны —
    # "MAKITA" = "Makita", дефект был в fold_brand_or_code (гомоглиф-карта
    # не симметрична по регистру исходных букв), см. _fold().
    res = _decision(
        "Перфоратор MAKITA M8701B",
        "Перфоратор 800 Вт 2,3 Дж SDS-Plus Makita M8701B",
        a_manufacturer="MAKITA", b_manufacturer="Makita",
    )
    assert res["decision"] == "auto", res


def test_brand_punctuation_sturm():
    res = _decision("Генератор Sturm PG8755E", "Генератор Sturm! PG8755E",
                     a_manufacturer="Sturm", b_manufacturer="Sturm!")
    assert res["decision"] == "auto", res


def test_brand_case_hanskonner():
    res = _decision("Дрель HANSKONNER HCD1645BLC", "Дрель Hanskonner HCD1645BLC",
                     a_manufacturer="HANSKONNER", b_manufacturer="Hanskonner")
    assert res["decision"] == "auto", res


def test_brand_hyphen_insensitive():
    res = _decision("Фреза Tech-KREP F100", "Фреза Techkrep F100",
                     a_manufacturer="Tech-KREP", b_manufacturer="Techkrep")
    assert res["decision"] == "auto", res


def test_brand_all_digits_is_undetermined():
    # "Бренд" из одних цифр — не бренд, значит гейт по бренду не блокирует,
    # а решение падает на дальнейшие проверки (индекс/свойства).
    a = _sig("Удлинитель 200", manufacturer="200")
    b = _sig("Удлинитель 200", manufacturer="200")
    assert a.brand_fold == "" and b.brand_fold == ""


def test_missing_property_on_one_side_is_not_a_conflict():
    # Цвет указан только у одного — это НЕ противоречие (п.4).
    res = _decision("Шлем ШКПС", "Шлем ШКПС белый")
    assert res["decision"] != "no"
