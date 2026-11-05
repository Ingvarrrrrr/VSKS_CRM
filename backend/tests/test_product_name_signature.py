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


# ---------------------------------------------------------------------------
# Ревью 113 авто-пар на проде, 27.10.2026, правило «название + индекс
# модели» — найденные ложные сведения (должны стать НЕ auto) и контроль,
# что правильные пары того же ревью остаются auto/check.
# ---------------------------------------------------------------------------

def test_model_modifier_letter_din():
    # "Д" отдельным словом сразу после кода модели ДИН2 — часть индекса
    # (п.1), не "похожесть"; есть у одного, нет у другого → no.
    res = _decision(
        "Светоуказатель Кристалл-24 ДИН2 с динамическим табло (24В)",
        "Светоуказатель двусторонний Кристалл-24 ДИН2 Д с динамическим табло",
    )
    assert res["decision"] == "no", res


def test_model_modifier_letter_gps():
    res = _decision("Генератор пены ГПС-200", "Генератор пены ГПС-200 П - Перекрывной")
    assert res["decision"] == "no", res


def test_model_modifier_letter_szp():
    res = _decision("Станция зарядная порошковая СЗП-02ГУ", "Станция зарядная порошковая СЗП-02ГУ М")
    assert res["decision"] == "no", res


def test_szu_complect_one_sided_is_check_not_auto():
    # "с комплектацией" указано только у одного (п.2) — check, не auto.
    res = _decision(
        "Станция зарядная углекислотная СЗУ-03НД",
        "Станция зарядная углекислотная СЗУ-03НД с комплектацией",
    )
    assert res["decision"] == "check", res


def test_hose_type_both_specified_different_is_no():
    # "всасывающий" ≠ "напорно-всасывающий" — указано у ОБОИХ и разное → no.
    res = _decision(
        "Рукав всасывающий гофрированный 125 мм",
        "Рукав напорно-всасывающий гофрированный 125 мм",
    )
    assert res["decision"] == "no", res


def test_coating_word_one_sided_not_auto():
    # "никель" указано только у одного (п.2, группа "покрытие") — не auto.
    res = _decision(
        "Огнетушитель воздушно-эмульсионный ОВЭ-5 Ратоборец",
        "Огнетушитель воздушно-эмульсионный ОВЭ-5 ТД Русинтэк никель",
    )
    assert res["decision"] != "auto", res


def test_known_good_sign_e21_still_auto():
    res = _decision("Знак E21 'Пункт (место) сбора' 200х200 мм", "Знак E21 Пункт (место) сбора")
    assert res["decision"] == "auto", res


def test_known_good_piroplate_still_auto():
    res = _decision("ПироПластина Ф-30 автономное устройство пожаротушения", "ПироПластина Ф-30")
    assert res["decision"] == "auto", res


def test_known_good_extinguisher_cover_still_auto():
    res = _decision("Чехол для огнетушителя ОП-70 360*1070 мм", "Чехол ОП-70 360*1070 мм")
    assert res["decision"] == "auto", res


def test_known_good_makita_battery_still_auto():
    res = _decision("Аккумулятор Makita тип BL1860B", "Аккумулятор 18 В 6,0 Ач Makita LXT BL1860B",
                     a_manufacturer="MAKITA", b_manufacturer="MAKITA")
    assert res["decision"] == "auto", res


def test_known_good_self_rescuer_minutes_note_still_auto():
    res = _decision(
        "Самоспасатель СПИ-50 (не менее 50 мин.)",
        "Самоспасатель СПИ-50 (50 мин.)",
    )
    assert res["decision"] == "auto", res


def test_known_good_install_mode_one_sided_check_is_acceptable():
    # "стационарный" указан только у одного — check допустим (владелец:
    # если ГПСС бывают только стационарными, check — не регрессия).
    res = _decision("Генератор пены ГПСС-2000 стационарный", "Генератор пены ГПСС-2000")
    assert res["decision"] == "check", res


def test_known_good_zinc_coating_one_sided_check_is_acceptable():
    res = _decision("Зажим рукавный ЗПР-80", "Зажим рукавный ЗПР-80 оцинкованный")
    assert res["decision"] == "check", res


# ---------------------------------------------------------------------------
# Доп. ревью Кувалда↔Бауцентр, 27.10.2026: хвостовые коды магазина,
# региональный суффикс артикула, комплектация по батарее.
# ---------------------------------------------------------------------------

def test_store_tail_code_in_parens_and_repeated_ignored():
    res = _decision(
        "Дрель безударная сетевая DEKO DKSD400W (063-4086) 063-4086",
        "Дрель безударная сетевая DEKO DKSD400W",
    )
    assert res["decision"] == "auto", res


def test_market_suffix_se00_same_index():
    res = _decision(
        "Перфоратор сетевой SKIL RH1183 SDS+ RH1183SE00",
        "Перфоратор SDS-Plus 1500 Вт 5,0 Дж SKIL RH1183SE00",
    )
    assert res["decision"] == "auto", res


def test_market_suffix_xj_same_index():
    res = _decision("Дрель-шуруповёрт DEWALT DCF887N", "Дрель-шуруповёрт DEWALT DCF887N-XJ",
                     a_manufacturer="DEWALT", b_manufacturer="DEWALT")
    assert res["decision"] == "auto", res


def test_unknown_suffix_not_stripped_different_configuration():
    # DHR242Z ≠ DHR242RT — "Z"/"RT" НЕ в закрытом списке суффиксов, это
    # разная комплектация, не региональный суффикс (п.4).
    res = _decision("Дрель-шуруповёрт DEWALT DHR242Z", "Дрель-шуруповёрт DEWALT DHR242RT",
                     a_manufacturer="DEWALT", b_manufacturer="DEWALT")
    assert res["decision"] == "no", res


def test_ean_like_long_numeric_tail_code_ignored():
    # EAN-хвост игнорируется, "станок циркулярный"/"распиловочный станок" —
    # тот же словарный вид "станок" (вид ищем среди первых 5 слов). НО
    # мощность в названии теперь сравнивается с переводом единиц (владелец,
    # посл. правка, 27.10.2026): 2,0 кВт = 2000 Вт ≠ 2500 Вт → no.
    res = _decision(
        "Станок циркулярный Jib 3255A-2 2,0 кВт, 230В 0111020231000",
        "Распиловочный станок 2500 Вт 254 мм + станина JIB 3255A-2",
    )
    assert res["decision"] == "no", res
    assert "мощность" in res["reason"]


def test_power_mentioned_only_on_one_side_still_auto():
    # Мощность указана только у Бауцентра — НЕ противоречие (п.4).
    res = _decision(
        "Перфоратор MAKITA M8701B",
        "Перфоратор 800 Вт 2,3 Дж SDS-Plus Makita M8701B",
        a_manufacturer="MAKITA", b_manufacturer="MAKITA",
    )
    assert res["decision"] == "auto", res


def test_product_type_adjective_first_hammer_still_matches():
    # Бауцентр ставит прилагательное первым словом ("Отбойный молоток") —
    # вид ищем среди первых 5 слов, не только по первому слову (п. доп.
    # ревью). "Молот" = "молоток" (синоним-основа).
    res = _decision(
        "Молот ударный сетевой SKIL RH1792 RH1792SE00",
        "Отбойный молоток SDS-Max 1150 Вт 12 Дж SKIL RH1792SE00",
    )
    assert res["decision"] == "auto", res


def test_product_type_adjective_first_grinder_still_matches():
    res = _decision(
        "Шлифмашина ленточная сетевая HANSKONNER HBS8512",
        "Ленточная шлифмашина Hanskonner HBS8512, 1200 Вт 76х533 мм",
    )
    assert res["decision"] == "auto", res


def test_product_type_cabinet_vs_case_still_no():
    res = _decision("Шкаф для огнетушителя DAKEN Regon 82170",
                     "Пенал для огнетушителя DAKEN Regon 82170")
    assert res["decision"] == "no", res
    assert "вид товара" in res["reason"]


# ---------------------------------------------------------------------------
# Доп. ревью Delta/Security Force/BT аккумуляторов, 27.10.2026, п.2 дефекта
# пробного прогона merge_by_name_model: бренды не распознаны (manufacturer
# не передан), совпавший вид товара "аккумулятор" обходил порог похожести
# слов, хотя латинские слова-кандидаты в бренд разные ("Delta" ≠ "Security
# Force" ≠ "BT"), а габариты отличаются.
# ---------------------------------------------------------------------------

def test_brand_like_words_differ_delta_vs_security_force():
    res = _decision(
        "Аккумуляторная батарея Delta DT 1240 (12В 40Ач) 198х166х170 мм",
        "Аккумуляторная батарея Security Force SF 1240 (12В 40Ач) 195х165х170 мм",
    )
    assert res["decision"] == "no", res
    assert "бренд" in res["reason"]


def test_brand_like_words_differ_delta_vs_bt():
    res = _decision(
        "Аккумуляторная батарея Delta DT 1240 (12В 40Ач) 198х166х170 мм",
        "Аккумуляторная батарея BT 1240 (12В 40Ач) 195х165х170 мм",
    )
    assert res["decision"] == "no", res
    assert "бренд" in res["reason"]


def test_brand_like_words_differ_security_force_vs_bt():
    res = _decision(
        "Аккумуляторная батарея Security Force SF 1240 (12В 40Ач) 195х165х170 мм",
        "Аккумуляторная батарея BT 1240 (12В 40Ач) 195х165х170 мм",
    )
    assert res["decision"] == "no", res
    assert "бренд" in res["reason"]


def test_dimensions_differ_even_with_same_confirmed_brand():
    # Изолируем переменную (не брендовый гейт, а именно размеры через «х»):
    # manufacturer ОДИНАКОВЫЙ у обоих — confirmed_same_brand=True, значит
    # гейт "вероятно разные бренды" тут не сработает, и единственная причина
    # "no" — несовпавшие габариты Д×Ш×В ("170" совпадает, но первые две оси
    # разные).
    res = _decision(
        "Аккумуляторная батарея Delta DT 1240 198х166х170 мм",
        "Аккумуляторная батарея Delta DT 1240 195х165х170 мм",
        a_manufacturer="Delta", b_manufacturer="Delta",
    )
    assert res["decision"] == "no", res
    assert "размеры" in res["reason"]


def test_dimensions_match_when_axes_equal():
    res = _decision(
        "Аккумуляторная батарея Delta DT 1240 198х166х170 мм",
        "Аккумуляторная батарея Delta DT 1240 198х166х170 мм",
        a_manufacturer="Delta", b_manufacturer="Delta",
    )
    assert res["decision"] == "auto", res


def test_brand_like_word_overlap_does_not_block_known_good_pairs():
    # Прежние правильные пары того же ревью (владелец) остаются auto:
    # общее латинское слово-кандидат в бренд ("CBR"/"HP") есть с обеих
    # сторон — гейт "вероятно разные бренды" не срабатывает (пересечение
    # не пустое), и обход overlap-порога по виду товара тоже разрешён.
    res_cbr = _decision(
        "ИБП CBR ESN-1KT-4I-LCHERSC",
        "ИБП CBR Essence Online Tower ESN-1KT-4I-LCHERSC",
    )
    assert res_cbr["decision"] == "auto", res_cbr

    res_hp = _decision(
        "Компьютер HP Z2 G9 TWR 4N3U8AV",
        "Настольный компьютер HP Z2 Tower G9 Workstation (4N3U8AV)",
    )
    assert res_hp["decision"] == "auto", res_hp


def test_battery_solo_vs_akb_count_not_auto():
    # "solo" ≠ "2 АКБ ..." — комплектация по батарее указана у обоих и
    # разная → не auto (п.5).
    res = _decision("Шуруповёрт SKIL ID6739 solo", "Шуруповёрт SKIL ID6739 2 АКБ 4,0+2,0 Ач")
    assert res["decision"] != "auto", res


# ---------------------------------------------------------------------------
# Доп. ревью стволов РС-50 (Спасатель↔Магазин 01), 28.10.2026: вид товара
# как ключ группировки + сокращения материала/закачного, слитные с кодом
# модели ("РС-50А" = "РС-50 Алюм."), номер приказа/ГОСТ/ТУ и "аналог X" —
# не код модели, размеры Д×Ш с единицей на каждой оси.
# ---------------------------------------------------------------------------

def test_fused_aluminum_suffix_matches_spelled_out_word():
    # "РС-50А" (суффикс слитно с кодом) = "РС-50 Алюм." (слово отдельно) —
    # ОДИН И ТОТ ЖЕ материал (владелец, 28.10.2026).
    res = _decision(
        "Ствол пожарный ручной РС-50 Алюм. (диам. 16мм)",
        "Ствол пожарный РС-50А (диаметр 16 мм)",
    )
    assert res["decision"] == "auto", res


def test_fused_material_suffix_conflict_plastic_vs_aluminum():
    # "РС-50,01 Пластик" (слово) ≠ "РС-50.01А" (суффикс "А" = алюминий,
    # десятичная запятая/точка в коде — тот же код "рс5001") — материал
    # различается → no, а не ложное auto по совпавшему коду.
    res = _decision(
        "Ствол пожарный ручной РС-50,01 Пластик",
        "Ствол пожарный РС-50.01А (под навязку)",
    )
    assert res["decision"] == "no", res
    assert "материал" in res["reason"]


def test_fused_suffix_does_not_break_plain_ampere_quantity():
    # Контроль: "18 В" (число-с-единицей, пробел перед единицей) — ПО
    # ПРЕЖНЕМУ вырезается как количество, суффикс-гейт его не трогает
    # (регрессия на test_name_unit_quantity_is_not_model_index).
    res = _decision(
        "Аккумулятор ЗУБР АКБ-18-4 18 В 1х5,0 Ач 2,0 Дж",
        "Аккумулятор ЗУБР АКБ-18-4",
        a_manufacturer="ЗУБР", b_manufacturer="ЗУБР",
    )
    assert res["decision"] == "auto", res


def test_belt_pouch_vs_carry_torch_axe_execution_conflict():
    # "поясной" ≠ "носимый" — способ ношения, жёсткая группа "исполнение"
    # (владелец, 28.10.2026): "Топор пожарного поясной ТПП-1" ≠ "... носимый
    # ТПП-1".
    res = _decision(
        "Топор пожарного поясной ТПП-1",
        "Топор пожарного носимый ТПП-1 (с диэлектрической ручкой)",
    )
    assert res["decision"] == "no", res
    assert "исполнение" in res["reason"]


def test_analog_reference_is_not_this_products_code():
    # "Ствол лафетный ЛС-П20 (аналог СЛК-П20)" — код после "аналог" это
    # ДРУГОЙ товар-аналог, не код ЭТОГО товара; "СЛК-П20 (ПЛС-П20)" — другой
    # товар целиком (владелец, 28.10.2026) → не auto.
    res = _decision(
        "Ствол лафетный ЛС-П20 (аналог СЛК-П20)",
        "Ствол лафетный СЛК-П20 (ПЛС-П20)",
    )
    assert res["decision"] != "auto", res


def test_order_reference_number_is_not_model_code():
    # "№1164н"/"приказ МИНЗДРАВА РФ №1164н" — номер нормативного документа,
    # не код товара (владелец, 28.10.2026) — вырезается из названия до
    # разбора индекса.
    from app.services.product_name_signature import build_signature
    sig = build_signature({"name": "КИМГЗ по Приказу МИНЗДРАВА РФ №1164н", "manufacturer": None, "characteristics": []})
    assert not any("1164" in t for t in sig.digit_tokens), sig.digit_tokens


def test_spaced_axis_dimensions_conflict_same_model_code():
    # "300мм х 300мм" (единица ПОСЛЕ каждой оси) — тот же разбор Д×Ш, что и
    # слитный "300х300 мм" (владелец, доп. ревью клапанов, 28.10.2026): при
    # ОДНОМ И ТОМ ЖЕ коде модели разные размеры → no, изолируем переменную
    # (код искусственно совпадает на обеих сторонах).
    res = _decision(
        "Клапан противопожарный КЛОП-1 300мм х 300мм",
        "Клапан противопожарный КЛОП-1 250мм х 250мм",
    )
    assert res["decision"] == "no", res
    assert "размеры" in res["reason"] or "длина" in res["reason"]


def test_nozzle_type_both_specified_conflict_is_check_not_no():
    # "комбинированный" ≠ "распылительный" — тип насадки ствола, владелец
    # (доп. ревью, 28.10.2026) просит МЯГКОЕ решение при расхождении у ОБЕИХ
    # сторон: check, не no (не так однозначно, как материал/цвет/страна).
    res = _decision(
        "Ствол пожарный ручной РСК-50 (комбинированный)",
        "Ствол пожарный ручной РСК-50 (распылительный)",
    )
    assert res["decision"] == "check", res


def test_minutes_duration_one_sided_still_auto():
    # "(30 мин.)" указано только у одной стороны — не код модели, не
    # противоречие (п.4), контроль на регрессию известной верной пары
    # владельца (Феникс-2).
    res = _decision(
        "Самоспасатель Феникс-2 фильтрующий (30 мин.)",
        "Фильтрующий универсальный самоспасатель ФЕНИКС-2 (ФУС ФЕНИКС-2)",
    )
    assert res["decision"] == "auto", res


def test_bare_number_only_signature_has_no_model_code():
    # "Тапочки размер 43"/"Коврик 43х28 см" — общий только ГОЛЫЙ номер без
    # единой буквы: не код модели (владелец, 28.10.2026, п.1) — grouping_key
    # не должен использовать такую сигнатуру как ключ поиска кандидатов.
    from app.services.product_name_signature import build_signature, grouping_key
    sig = build_signature({"name": "Тапочки размер 43", "manufacturer": None, "characteristics": []})
    assert sig.model_code_tokens == frozenset()
    assert grouping_key(sig) is None


def test_bare_diagonal_number_does_not_block_monitor_match():
    # Срочная правка (прод, 998 "неоднозначных" групп, 28.10.2026): голое
    # число диагонали "27" без кода рядом — не часть индекса; код "27g3q"
    # совпадает → auto, а не "no" по голому числу.
    res = _decision('Монитор Hisense 27G3Q', 'Монитор Hisense 27" 27G3Q')
    assert res["decision"] == "auto", res


def test_bare_diagonal_number_dell_still_matches():
    res = _decision("Dell E2425HM", 'Dell 24" Pro E2425HM')
    assert res["decision"] == "auto", res


def test_bare_diagonal_number_cbr_still_matches():
    res = _decision("CBR MQ-3201", 'CBR 32" MQ-3201')
    assert res["decision"] == "auto", res


def test_diagonal_inch_conflict_same_code_different_size():
    # Диагональ указана у ОБЕИХ сторон и различается → no (не голое число
    # без контекста — именно единица "дюйм"/«"»).
    res = _decision('Монитор Dell 24" E2425HM', 'Монитор Dell 27" E2425HM')
    assert res["decision"] == "no", res
    assert "диагональ" in res["reason"]


def test_grouping_key_requires_same_product_type():
    # Один и тот же код модели, но РАЗНЫЙ явный вид (Product.product_type) —
    # grouping_key их не объединяет (владелец, 28.10.2026, п.1: вид товара —
    # первый уровень группировки).
    from app.services.product_name_signature import build_signature, grouping_key
    a = build_signature({
        "name": "Деталь АБВ-100", "manufacturer": None, "characteristics": [],
        "product_type": "Ствол", "category": "Другая категория",
    })
    b = build_signature({
        "name": "Деталь АБВ-100", "manufacturer": None, "characteristics": [],
        "product_type": "Рукав", "category": "Другая категория",
    })
    assert grouping_key(a) != grouping_key(b)


def test_spaced_model_code_and_parenthesized_brand_matches():
    from app.services.product_name_signature import (
        build_signature, grouping_key, match, merge_characteristics, merge_price_links,
    )
    from app.services.product_query_parse import ManufacturerBrandDictionary

    bdict = ManufacturerBrandDictionary(["Ярпожинвест", "Меланти", "РИФ"])
    a = build_signature(
        {"name": "Огнетушитель ОП 2 (ярпожинвест)", "manufacturer": None, "characteristics": []},
        brand_dictionary=bdict,
    )
    b = build_signature(
        {"name": "Огнетушитель порошковый ОП-2 АВСЕ", "manufacturer": "Ярпожинвест", "characteristics": []},
        brand_dictionary=bdict,
    )
    c = build_signature(
        {"name": "Огнетушитель ОП-2 (Меланти)", "manufacturer": None, "characteristics": []},
        brand_dictionary=bdict,
    )
    assert grouping_key(a) == grouping_key(b)
    assert match(a, b)["decision"] == "auto"
    assert match(a, c)["decision"] == "no"


def test_spaced_vs_fused_zakachnoy_suffix_matches():
    res = _decision(
        "Огнетушитель порошковый ОП-2 (з) АВСЕ",
        "Огнетушитель порошковый ОП-2(з) АВСЕ",
        a_manufacturer="Ярпожинвест", b_manufacturer="Ярпожинвест",
    )
    assert res["decision"] == "auto", res


def test_custom_vsks_vest_has_no_grouping_key_and_does_not_auto_merge():
    from app.services.product_name_signature import build_signature, grouping_key
    sig = build_signature({
        "name": "Спасательный жилет с нанесением ВСКС",
        "manufacturer": None,
        "characteristics": [],
    })
    assert grouping_key(sig) is None


def test_merge_characteristics_and_price_links():
    from app.services.product_name_signature import merge_characteristics, merge_price_links

    c1 = [{"name": "Вес брутто", "value": "3.1", "unit": "Килограмм"}]
    c2 = [
        {"name": "Вес брутто (не более)", "value": "3.2", "unit": "Килограмм"},
        {"name": "Габариты брутто", "value": "450x150x150", "unit": "мм"},
    ]
    merged_c = merge_characteristics(c1, c2)
    assert len(merged_c) == 2
    assert merged_c[0]["value"] == "3.1"
    assert merged_c[1]["name"] == "Габариты брутто"

    l1 = [{"url": "https://store1.ru/item/1", "price": 500.0}]
    l2 = [
        {"url": "https://store1.ru/item/1", "price": 520.0},
        {"url": "https://store2.ru/item/2", "price": 490.0},
    ]
    merged_l_keep = merge_price_links(l1, l2, update_existing_prices=False)
    assert len(merged_l_keep) == 2
    assert merged_l_keep[0]["price"] == 500.0
    assert merged_l_keep[1]["url"] == "https://store2.ru/item/2"

    merged_l_upd = merge_price_links(l1, l2, update_existing_prices=True)
    assert len(merged_l_upd) == 2
    assert merged_l_upd[0]["price"] == 520.0


def test_unicode_multiply_dimensions_and_1d_vs_2d_mm_conflict():
    # Unicode × (\u00d7) в габаритах: 1250x620х9 мм != 2500×1250×12 мм
    osp1 = build_signature({"name": "Плита ОСП-3 1250x620х9 мм"})
    osp2 = build_signature({"name": "Плита ОСП-3 2500×1250×12 мм"})
    assert match(osp1, osp2)["decision"] == "no"

    # Одиночный диаметр 2,5 мм против 3,0x350 мм (2.5 не входит в {3.0, 350.0})
    el1 = build_signature({"name": "Сварочные электроды АНО-21, 2,5 мм 2,5 кг ESAB", "manufacturer": "ESAB"})
    el2 = build_signature({"name": "Электроды ESAB АНО-21 3,0x350 мм (2,5 кг)", "manufacturer": "ESAB"})
    assert match(el1, el2)["decision"] == "no"

    # Одиночный диаметр 3,0 мм против 3,0x350 мм — 3.0 совпадает с первой осью
    el3 = build_signature({"name": "Сварочные электроды АНО-21, 3,0 мм 2,5 кг ESAB", "manufacturer": "ESAB"})
    assert match(el3, el2)["decision"] == "auto"


def test_clean_characteristics_list_and_separate_unit():
    from app.services.product_characteristics_parse import clean_characteristics_list

    raw = [
        {"name": "Защищаемая площадь (до), м²", "value": "20", "unit": None},
        {"name": "Масса огнетушителя полная (не более)", "value": "2,9", "unit": "Килограмм"},
        {"name": "Срок службы до перезарядки (не более), лет", "value": "5", "unit": None},
        {"name": "Продолжительность разового залпа ОТВ", "value": "от 6 секунд.", "unit": None},
        {"name": "Общая масса баллона с наполнением", "value": "не больше 3,2кг.", "unit": None},
        {"name": "Протяжённость направленной тушащей струи ОТВ", "value": "от 2 метров.", "unit": None},
        {"name": "Охватываемая площадь возгорания", "value": "не больше 20м2.", "unit": None},
        {"name": "Рабочее давление в баллоне", "value": "1,4МПа.", "unit": None},
        {"name": "Допустимый температурный режим хранения", "value": "от -40 до +50°С.", "unit": None},
        {"name": "Габариты", "value": "высота-38см, диаметр-11см.", "unit": None},
        {"name": "Габариты упаковки", "value": "31.5 x 11.5 x 11 см", "unit": None},
        {"name": "Вес брутто", "value": "2786 г", "unit": None},
        {"name": "Магазин-источник", "value": "К-Спасатель (k-spasatel.ru)", "unit": None},
        {"name": "Артикул Сима-ленд", "value": "5182898", "unit": None},
        {"name": "Модель производителя", "value": "00-00002791", "unit": None},
    ]
    cleaned = clean_characteristics_list(raw)
    by_name = {c["name"]: c for c in cleaned}

    assert by_name["Защищаемая площадь"] == {"name": "Защищаемая площадь", "value": "20", "unit": "м²"}
    assert by_name["Масса огнетушителя полная"] == {"name": "Масса огнетушителя полная", "value": "2,9", "unit": "кг"}
    assert by_name["Срок службы до перезарядки"] == {"name": "Срок службы до перезарядки", "value": "5", "unit": "лет"}
    assert by_name["Продолжительность разового залпа ОТВ"] == {"name": "Продолжительность разового залпа ОТВ", "value": "6", "unit": "с"}
    assert by_name["Общая масса баллона с наполнением"] == {"name": "Общая масса баллона с наполнением", "value": "3,2", "unit": "кг"}
    assert by_name["Протяжённость направленной тушащей струи ОТВ"] == {"name": "Протяжённость направленной тушащей струи ОТВ", "value": "2", "unit": "м"}
    assert by_name["Охватываемая площадь возгорания"] == {"name": "Охватываемая площадь возгорания", "value": "20", "unit": "м²"}
    assert by_name["Рабочее давление в баллоне"] == {"name": "Рабочее давление в баллоне", "value": "1,4", "unit": "МПа"}
    assert by_name["Допустимый температурный режим хранения"] == {"name": "Допустимый температурный режим хранения", "value": "-40...+50", "unit": "°C"}
    assert by_name["Высота"] == {"name": "Высота", "value": "38", "unit": "см", "in_description": None}
    assert by_name["Диаметр"] == {"name": "Диаметр", "value": "11", "unit": "см", "in_description": None}
    assert by_name["Габариты упаковки"] == {"name": "Габариты упаковки", "value": "31.5x11.5x11", "unit": "см"}
    assert by_name["Вес брутто"] == {"name": "Вес брутто", "value": "2786", "unit": "г"}
    assert "Магазин-источник" not in by_name
    assert "Артикул Сима-ленд" not in by_name
    assert "Модель производителя" not in by_name


def test_op2_yarpozhinvest_all_real_variants_auto_match():
    from app.services.product_query_parse import ManufacturerBrandDictionary
    from scripts.merge_by_name_model import _is_group_unique

    bdict = ManufacturerBrandDictionary(["Ярпожинвест", "РИФ", "Меланти"])
    cards = [
        {"id": 2415, "name": "Огнетушитель порошковый ОП-2 (ЗПУ латунь) Ярпожинвест (г. Ярославль)", "manufacturer": None, "characteristics": []},
        {"id": 29503, "name": "Огнетушитель Ярпожинвест ОП-2 з АВСЕ", "manufacturer": None, "characteristics": [{"name": "Вес", "value": "3.1", "unit": "кг"}]},
        {"id": 812302, "name": "Огнетушитель порошковый ОП-2 Ярпожинвест (г. Ярославль)", "manufacturer": "Ярпожинвест", "characteristics": [{"name": "Вес", "value": "2,9", "unit": "кг"}]},
        {"id": 812306, "name": "Огнетушитель порошковый Ярпожинвест ОП-2 (з) АВСЕ ЗПУ Китай", "manufacturer": "Ярпожинвест", "characteristics": [{"name": "Общая масса баллона с наполнением", "value": "3,2", "unit": "кг"}]},
        {"id": 812307, "name": "Огнетушитель поршковый Ярпожинвест ОП-2 (з) ВСЕ ЗПУ Китай", "manufacturer": "Ярпожинвест", "characteristics": []},
        {"id": 812308, "name": "Огнетушитель поршковый Ярпожинвест ОП-2 (з) ВСЕ ЗПУ Россия", "manufacturer": "Ярпожинвест", "characteristics": []},
        {"id": 812312, "name": "Огнетушитель порошковый «Ярпожинвест» ОП-2(3), ABCE-01(А)", "manufacturer": "Ярпожинвест", "characteristics": [{"name": "Вес брутто", "value": "2786", "unit": "г"}]},
        {"id": 1315441, "name": "Огнетушитель порошковый ОП-2 (з) ABCE", "manufacturer": None, "description": "Описание Огнетушитель порошковый Ярпожинвест ОП-2 (з) АВСЕ ЗПУ Россия", "characteristics": []},
        {"id": 1318365, "name": "Огнетушитель порошковый Ярпожинвест ОП-2 (з) АВСЕ 00-00002791", "manufacturer": "Ярпожинвест", "characteristics": []},
    ]
    sigs = {c["id"]: build_signature(c, brand_dictionary=bdict) for c in cards}
    ids = [c["id"] for c in cards]
    assert all(sigs[cid].brand_fold == "ярпожинвест" for cid in ids)
    assert _is_group_unique(ids, sigs) is True


def test_phonetic_brand_match_cyrillic_and_latin():
    """Кириллическое и латинское написание бренда ('Макита'↔'Makita',
    'Бош'↔'Bosch', 'Штиль'↔'Stihl', 'Керхер'↔'Karcher', 'Деволт'↔'DeWalt')
    сопоставляется через общую фонетику в build_signature/match()."""
    a = build_signature({"name": "Перфоратор Макита HR2470", "manufacturer": "Макита"})
    b = build_signature({"name": "Перфоратор Makita HR-2470", "manufacturer": "Makita"})
    assert match(a, b)["decision"] == "auto"

    c = build_signature({"name": "Перфоратор Бош GBH 2-26", "manufacturer": "Бош"})
    d = build_signature({"name": "Перфоратор Bosch GBH 2-26", "manufacturer": "Bosch"})
    assert match(c, d)["decision"] == "auto"

    e = build_signature({"name": "Бензопила Штиль MS-180", "manufacturer": "Штиль"})
    f = build_signature({"name": "Бензопила Stihl MS-180", "manufacturer": "Stihl"})
    assert match(e, f)["decision"] == "auto"


def test_accessory_preposition_does_not_steal_target_product_type():
    """Принадлежность ('Подставка под огнетушитель ОП-2', 'Держатель под
    огнетушитель ОП-2') не должна получать вид товара 'огнетушитель' по слову
    после предлога 'под'/'для'."""
    stand = build_signature({"name": "Подставка под огнетушитель ОП-2"})
    holder = build_signature({"name": "Держатель под огнетушитель ОП-2"})
    ext = build_signature({"name": "Огнетушитель порошковый ОП-2"})
    assert stand.product_type == "подставка"
    assert holder.product_type is None
    assert ext.product_type == "огнетушитель"
    assert match(stand, ext)["decision"] == "no"


def test_size_or_preposition_in_manufacturer_rejected_as_brand():
    """Размерные обозначения ('XL', 'А4') и предлоги ('для'), попавшие в
    manufacturer, не считаются брендом карточки в build_signature."""
    sig_xl = build_signature({"name": "Костюм рабочий КР-1", "manufacturer": "XL"})
    sig_a4 = build_signature({"name": "Бумага офисная Снегурочка", "manufacturer": "А4"})
    sig_prep = build_signature({"name": "Кронштейн КР-1", "manufacturer": "для"})
    assert sig_xl.brand is None
    assert sig_a4.brand is None
    assert sig_prep.brand is None

