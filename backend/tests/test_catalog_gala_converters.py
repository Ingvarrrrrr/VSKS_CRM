"""Тесты конвертеров backend/app/services/catalog_gala/ в формат GALA."""
from app.services.catalog_gala.format import validate_gala_catalog, GALA_FORMAT_NAME, GALA_FORMAT_VERSION
from app.services.catalog_gala import (
    from_electro_mpo, from_vkusvill, from_gala_sheet, from_baucenter, from_store_nomenclature,
)
from app.services.catalog_gala.clean import clean_text, strip_leading_code
from app.services.catalog_gala.spec_parse import split_key_unit


def _envelope(source, items):
    return {
        "format": GALA_FORMAT_NAME,
        "version": GALA_FORMAT_VERSION,
        "source": source,
        "source_file": "test.json",
        "generated_at": "2026-10-26T00:00:00+00:00",
        "items": items,
    }


def test_electro_mpo_converter():
    raw = [{
        "name": "Накладка Mosaic 078604",
        "category": "Электротехническая продукция",
        "section": "rozetki",
        "subsection": "r23",
        "price": 403.82,
        "unit": "шт",
        "url": "https://example.com/item",
        "photo": "https://example.com/photo.jpg",
        "specifications": {
            "Производитель": "Legrand",
            "Номера поставщика": "078604",
            "Тип изделия": "Розетка телефонная",
            "Высота в м": "0.015",
            "Объём  в м3": "3.0E-5",
            "Серия": "Mosaic",
        },
    }]
    result = from_electro_mpo.convert(raw, "electro.json")
    assert result["source"] == "electro_mpo"
    item = result["items"][0]
    assert item["manufacturer"] == "Legrand"
    assert item["article"] == "078604"
    assert item["product_type"] == "Розетка телефонная"
    # Задача 2 (26.10): «Высота»/«Объём» — габариты упаковки, не попадают в
    # техописание (in_description=False), но хранятся в карточке полностью.
    assert {"name": "Высота", "value": "0.015", "unit": "м", "in_description": False} in item["characteristics"]
    assert {"name": "Объём", "value": "3.0E-5", "unit": "м³", "in_description": False} in item["characteristics"]
    assert {"name": "Серия", "value": "Mosaic", "unit": None} in item["characteristics"]
    assert item["source_url"] == "https://example.com/item"
    assert item["links"] == [{"url": "https://example.com/item", "price": 403.82}]
    assert item["photos"] == ["https://example.com/photo.jpg"]
    assert validate_gala_catalog(_envelope("electro_mpo", result["items"])) == []


def test_electro_mpo_excludes_more_packaging_characteristics_from_description():
    """Остальные характеристики упаковки из списка Задачи 2: "Номер по
    прайс-листу", "Торговая единица", "Количество товара в упаковке",
    "Хрупкость", "Ширина", "Глубина" — тоже не попадают в описание."""
    raw = [{
        "name": "Товар", "category": "C", "price": 10, "unit": "шт", "url": "", "photo": "",
        "specifications": {
            "Номер по прайс-листу": "123",
            "Торговая единица": "шт",
            "Количество товара в упаковке": "10",
            "Хрупкость": "да",
            "Ширина в м": "0.1",
            "Глубина в м": "0.2",
            "Вес в кг": "1.5",
        },
    }]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    for name in ("Номер по прайс-листу", "Торговая единица", "Количество товара в упаковке", "Хрупкость"):
        assert by_name[name]["in_description"] is False, name
    assert by_name["Ширина"]["in_description"] is False
    assert by_name["Глубина"]["in_description"] is False
    # "Вес" НЕ входит в список исключений — остаётся в описании (нет флага).
    assert "in_description" not in by_name["Вес"]


def test_electro_mpo_zero_dimension_value_not_written():
    """Владелец, 2026-10-26 (electro_mpo_breakers_all.json): у автоматов
    "Высота"/"Ширина"/"Глубина"/"Объём"/"Вес" часто "0" — это не значение, а
    "не измерялось", характеристика не должна появляться в characteristics."""
    raw = [{
        "name": "Автомат", "category": "C", "price": 10, "unit": "шт", "url": "", "photo": "",
        "specifications": {
            "Высота в м": "0", "Ширина в м": "0.0", "Глубина в м": "0,0",
            "Объём в м3": "0", "Вес в кг": "0",
            "Номинальный ток": "16",
        },
    }]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    names = {c["name"] for c in item["characteristics"]}
    assert names == {"Номинальный ток"}


def test_electro_mpo_paren_unit_format_and_normalization():
    """Выгрузка кабелей (electro_mpo_cables_all.json, 26.10): единица в
    скобках в конце ключа — "<Имя> (<ед>)" — плюс нормализация мм2→мм²,
    см2→см², м3→м³ (та же _normalize_unit, что у формата "в <ед>")."""
    raw = [{
        # "1х16" согласован с "Сечение жилы кабеля (мм2)": "16.0" ниже — иначе
        # Задача 2 (26.10, check_cable_consistency) отбросит позицию как
        # противоречивую (этот тест — про разбор ключей, не про проверку
        # согласованности, та проверяется отдельно в test_electro_consistency.py).
        "name": "Провод ПуВ 1х16 кв.мм белый ГОСТ", "category": "Кабельно-проводниковая продукция",
        "price": 16.47, "unit": "м", "url": "", "photo": "",
        "specifications": {
            "Марка изделия": "ПуВ",
            "Сечение жилы кабеля (мм2)": "16.0",
            "Диаметр жилы (мм)": "4.5",
            "Площадь сечения (см2)": "1.2",
        },
    }]
    item = from_electro_mpo.convert(raw, "cables.json")["items"][0]
    assert {"name": "Марка изделия", "value": "ПуВ", "unit": None} in item["characteristics"]
    assert {"name": "Сечение жилы кабеля", "value": "16.0", "unit": "мм²"} in item["characteristics"]
    assert {"name": "Диаметр жилы", "value": "4.5", "unit": "мм"} in item["characteristics"]
    assert {"name": "Площадь сечения", "value": "1.2", "unit": "см²"} in item["characteristics"]
    assert validate_gala_catalog(_envelope("electro_mpo", [item])) == []


def test_electro_mpo_zero_price_is_null():
    raw = [{"name": "X", "category": "C", "price": 0, "unit": "шт", "url": "", "photo": "", "specifications": {}}]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    assert item["price"] is None
    assert item["links"] == []
    assert item["photos"] == []


def test_vkusvill_flat_format():
    raw = [{
        "name": "Творог", "category": "Продукты питания", "price": 0.0,
        "unit": "шт", "url": "https://vkusvill.ru/goods/x/",
        "photo": "https://img.example.com/x.jpg", "description": "Описание товара.",
    }]
    result = from_vkusvill.convert(raw, "flat.json")
    item = result["items"][0]
    assert item["price"] is None  # 0.0 → цены нет
    assert item["category"] == "Продукты питания"
    assert item["category_path"] == ["Продукты питания"]
    assert item["photos"] == ["https://img.example.com/x.jpg"]
    # Владелец, 2026-10-26: description ВкусВилла — реклама, не переносится.
    assert item["description"] is None
    assert validate_gala_catalog(_envelope("vkusvill", result["items"])) == []


def test_vkusvill_structured_format():
    raw = [{
        "id": 20698, "name": "Творог", "slug": "tvorog", "description": "d",
        "price": {"current": 278, "currency": "RUB"},
        "unit": "шт", "weight": {"value": 0.35, "unit": "кг"},
        "rating": {"average": 4.8, "count": 100},
        "url": "https://vkusvill.ru/goods/tvorog-20698/",
        "images": [{"small": "s", "medium": "m", "large": "https://img.example.com/large.webp"}],
        "category": [
            {"id": 1, "name": "Творог", "slug": "tvorog"},
            {"id": 2, "name": "Молочные продукты, яйцо", "slug": "molochnye"},
        ],
        "properties": [{"name": "Состав", "value": "молоко<br>закваска"}],
    }]
    result = from_vkusvill.convert(raw, "structured.json")
    item = result["items"][0]
    assert item["price"] == 278
    assert item["category"] == "Продукты питания"
    assert item["category_path"] == ["Молочные продукты, яйцо", "Творог"]
    assert item["product_type"] == "Творог"
    assert item["source_id"] == "20698"
    assert item["photos"] == ["https://img.example.com/large.webp"]
    assert {"name": "Состав", "value": "молоко\nзакваска", "unit": None} in item["characteristics"]
    assert {"name": "Вес", "value": "0.35", "unit": "кг"} in item["characteristics"]
    assert validate_gala_catalog(_envelope("vkusvill", result["items"])) == []


def test_vkusvill_empty_input():
    result = from_vkusvill.convert([], "massive.json")
    assert result["items"] == []


def test_gala_sheet_list_format():
    raw = [{
        "row": 2, "name": "Компьютер Dell", "description": "Core i5",
        "category": "Оргтехника", "kind": "Рабочая станция", "unit": "шт",
        "pkg_qty": 1, "pkg_unit": "шт", "price": "85000", "price_date": "01.09.2026",
        "link_1": "https://a.com", "price_1": "83000",
        "link_2": "", "price_2": None, "link_3": "", "price_3": None,
        "photo_url": "", "is_reusable": "да", "is_active": "Да",
        "feo_category": "Техническое оснащение",
    }]
    result = from_gala_sheet.convert(raw, "sheet.json")
    item = result["items"][0]
    assert item["price"] == 85000.0
    assert item["price_date"] == "2026-09-01"
    assert item["is_reusable"] is True
    assert item["is_active"] is True
    assert item["source_id"] == "2"
    assert item["links"] == [{"url": "https://a.com", "price": 83000.0}]
    assert "feo_category" not in item
    assert validate_gala_catalog(_envelope("gala_sheet", result["items"])) == []


def test_gala_sheet_dict_format_flattened():
    raw = {
        "Оргтехника": [{"row": 2, "name": "A", "category": "Оргтехника", "kind": None, "unit": "шт",
                         "pkg_qty": None, "pkg_unit": None, "price": None, "price_date": None,
                         "is_reusable": None, "is_active": None}],
        "Не указано": [{"row": 5, "name": "B", "category": "Не указано", "kind": None, "unit": "шт",
                         "pkg_qty": None, "pkg_unit": None, "price": None, "price_date": None,
                         "is_reusable": "нет", "is_active": "нет"}],
    }
    result = from_gala_sheet.convert(raw, "by_cat.json")
    assert len(result["items"]) == 2
    names = {i["name"] for i in result["items"]}
    assert names == {"A", "B"}
    item_b = next(i for i in result["items"] if i["name"] == "B")
    assert item_b["category"] is None  # "Не указано" -> null
    assert item_b["is_reusable"] is False


def test_validate_catches_missing_name():
    envelope = _envelope("gala_sheet", [{"category": "X"}])
    errors = validate_gala_catalog(envelope)
    assert any("name" in e for e in errors)


def test_validate_catches_bad_format_and_version():
    envelope = {"format": "wrong", "version": 2, "items": []}
    errors = validate_gala_catalog(envelope)
    assert any("format" in e for e in errors)
    assert any("version" in e for e in errors)


def test_validate_catches_bad_characteristic():
    envelope = _envelope("gala_sheet", [{"name": "X", "characteristics": [{"value": "no name"}]}])
    errors = validate_gala_catalog(envelope)
    assert any("characteristics" in e for e in errors)


def test_validate_ok_on_minimal_item():
    envelope = _envelope("gala_sheet", [{"name": "Минимальный товар"}])
    assert validate_gala_catalog(envelope) == []


def test_validate_accepts_in_description_flag_and_excluded():
    envelope = _envelope("electro_mpo", [{
        "name": "X", "characteristics": [{"name": "Высота", "value": "1", "in_description": False}],
    }])
    envelope["excluded"] = [{"name": "Y", "reason": "сечение не совпадает"}]
    assert validate_gala_catalog(envelope) == []


def test_validate_catches_bad_in_description_and_excluded():
    envelope = _envelope("electro_mpo", [{
        "name": "X", "characteristics": [{"name": "Высота", "value": "1", "in_description": "нет"}],
    }])
    errors = validate_gala_catalog(envelope)
    assert any("in_description" in e for e in errors)

    envelope2 = _envelope("electro_mpo", [{"name": "X"}])
    envelope2["excluded"] = [{"name": "Y"}]  # нет reason
    errors2 = validate_gala_catalog(envelope2)
    assert any("excluded" in e for e in errors2)


# --- clean_text (Задача 1, 26.10) --------------------------------------------

def test_clean_text_html_entities_and_nbsp():
    assert clean_text('Творог "Пластовой" обезжиренный, 250&nbsp;г') == 'Творог "Пластовой" обезжиренный, 250 г'


def test_clean_text_br_tags_and_other_tags_stripped():
    assert clean_text("Строка 1<br>Строка 2<b>жирный</b><br/>Строка 3") == "Строка 1\nСтрока 2жирный\nСтрока 3"


def test_clean_text_collapses_spaces():
    assert clean_text("Слово1   Слово2\t\tСлово3") == "Слово1 Слово2 Слово3"


def test_clean_text_none_and_non_string_passthrough():
    assert clean_text(None) is None
    assert clean_text(42) == 42


def test_clean_text_empty_after_cleaning_returns_none():
    assert clean_text("   ") is None
    assert clean_text("<br>") is None


def test_vkusvill_name_nbsp_cleaned():
    """Повод задачи 1: названия ВкусВилла с &nbsp; перед единицей."""
    raw = [{
        "id": 1, "name": 'Творог "Пластовой" обезжиренный, 250&nbsp;г', "description": None,
        "price": {"current": 100}, "unit": "шт", "url": "https://x", "images": [],
        "category": [{"name": "Творог"}], "properties": [],
    }]
    item = from_vkusvill.convert(raw, "f.json")["items"][0]
    assert item["name"] == 'Творог "Пластовой" обезжиренный, 250 г'


# --- from_baucenter -----------------------------------------------------------

def test_baucenter_converter():
    raw = [{
        "id": 982926, "name": "Гипсокартон 12,5 мм", "brand": "", "article": "506000393",
        "category": "Гипсокартон и ГВЛ", "unit": "", "price": 1049.0,
        "url": "https://baucenter.ru/product/x/",
        "photo": "https://baucenter.ru/upload/x-0.webp",
        "all_photos": ["https://baucenter.ru/upload/x-0.webp", "https://baucenter.ru/upload/x-11.webp"],
    }]
    result = from_baucenter.convert(raw, "baucenter.json")
    assert result["source"] == "baucenter"
    item = result["items"][0]
    assert item["category"] == "Строительные и отделочные материалы"
    assert item["category_path"] == ["Гипсокартон и ГВЛ"]
    assert item["product_type"] == "Гипсокартон и ГВЛ"
    assert item["manufacturer"] is None  # brand="" -> None
    assert item["article"] == "506000393"
    assert item["unit"] is None  # unit="" -> None
    assert item["source_id"] == "982926"
    assert item["photos"] == ["https://baucenter.ru/upload/x-0.webp", "https://baucenter.ru/upload/x-11.webp"]
    assert item["links"] == [{"url": "https://baucenter.ru/product/x/", "price": 1049.0}]
    assert item["description"] is None
    assert item["characteristics"] == []
    assert validate_gala_catalog(_envelope("baucenter", result["items"])) == []


def test_baucenter_zero_price_is_null_and_photo_fallback():
    raw = [{
        "id": 1, "name": "X", "brand": "", "article": "", "category": "Кат",
        "unit": "шт", "price": 0, "url": "", "photo": "https://x/p.jpg", "all_photos": [],
    }]
    item = from_baucenter.convert(raw, "f.json")["items"][0]
    assert item["price"] is None
    assert item["article"] is None
    assert item["photos"] == ["https://x/p.jpg"]
    assert item["links"] == []


def test_baucenter_specifications_country_origin_and_marka_dedup():
    """Владелец, 2026-10-26 (новая версия baucenter_construction_all.json):
    specifications → characteristics (той же функцией, что у electro_mpo);
    «Страна производства» дублируется в country_origin, но НЕ убирается из
    characteristics; «Марка», совпадающая с brand, в characteristics не
    дублируется; «Вес брутто» остаётся обычной характеристикой (без
    in_description=False — это правило только у electro_mpo)."""
    raw = [{
        "id": 2414350, "name": "Колодец смотровой", "brand": "РУВИНИЛ", "article": "537000858",
        "category": "Системы закрытого дренажа", "unit": "шт", "price": 5290.0,
        "url": "https://baucenter.ru/product/x/", "photo": "", "all_photos": [],
        "description": "Рекламный текст, который не должен попасть в GALA.",
        "specifications": {
            "Вес брутто (кг)": "7.7",
            "Диаметр (мм)": "340",
            "Марка": "РУВИНИЛ",
            "Страна производства": "Россия",
        },
    }]
    item = from_baucenter.convert(raw, "f.json")["items"][0]
    assert item["description"] is None
    assert item["country_origin"] == "Россия"
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Вес брутто"] == {"name": "Вес брутто", "value": "7.7", "unit": "кг"}
    assert by_name["Диаметр"] == {"name": "Диаметр", "value": "340", "unit": "мм"}
    assert by_name["Страна производства"]["value"] == "Россия"
    assert "Марка" not in by_name, "«Марка» совпадает с brand — не дублируем"
    assert validate_gala_catalog(_envelope("baucenter", [item])) == []


def test_baucenter_marka_different_from_brand_kept():
    raw = [{
        "id": 1, "name": "X", "brand": "БрендА", "article": "", "category": "Кат",
        "unit": "шт", "price": 100, "url": "", "photo": "", "all_photos": [],
        "specifications": {"Марка": "ДругаяМарка"},
    }]
    item = from_baucenter.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Марка"]["value"] == "ДругаяМарка"


def test_baucenter_composite_unit_normalized():
    """"Расход в один слой до (м2/л)" — составная единица, степень
    нормализуется НЕ только в конце строки (units_normalize.py)."""
    raw = [{
        "id": 1, "name": "X", "brand": "", "article": "", "category": "Кат",
        "unit": "шт", "price": 100, "url": "", "photo": "", "all_photos": [],
        "specifications": {"Расход в один слой до (м2/л)": "0.3"},
    }]
    item = from_baucenter.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Расход в один слой до"]["unit"] == "м²/л"


# --- spec_parse: формат "<Имя>, <ед>" (Задача 1, 26.10) -----------------------

def test_split_key_unit_comma_format():
    assert split_key_unit("Диаметр, мм") == ("Диаметр", "мм")
    assert split_key_unit("Защищаемая площадь (до), м²") == ("Защищаемая площадь (до)", "м²")


def test_split_key_unit_comma_format_not_a_unit_untouched():
    """Хвост после запятой не похож на единицу (не короткий код, нет цифры)
    — ключ остаётся целым, без разбора."""
    assert split_key_unit("Рост, женские модели") == ("Рост, женские модели", None)


# --- clean.strip_leading_code (Задача 3, 26.10) --------------------------------

def test_strip_leading_code_removes_supplier_code():
    assert strip_leading_code("00113. . Провод АПВ 16,0 кв.мм") == "Провод АПВ 16,0 кв.мм"
    assert strip_leading_code("04610. Автоматический выключатель") == "Автоматический выключатель"
    assert strip_leading_code("13430.  Кабель АВВГ") == "Кабель АВВГ"


def test_strip_leading_code_leaves_names_without_code():
    assert strip_leading_code("Накладка Mosaic 078604") == "Накладка Mosaic 078604"
    assert strip_leading_code(None) is None


# --- from_electro_mpo: код в названии + кабельные характеристики (26.10) ------

def test_electro_mpo_strips_leading_supplier_code():
    raw = [{
        "name": "00113. . Провод АПВ 16,0 кв.мм", "category": "C", "price": 10, "unit": "м",
        "url": "", "photo": "", "specifications": {},
    }]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    assert item["name"] == "Провод АПВ 16,0 кв.мм"


def test_electro_mpo_cable_laying_and_purpose_excluded_from_description():
    """Задача 4: у кабелей (категория "Кабельно-проводниковая продукция")
    "Способ прокладки"/"Назначение" — in_description=False."""
    raw = [{
        "name": "Кабель ВВГ 3х1,5 кв.мм", "category": "Кабельно-проводниковая продукция",
        "price": 10, "unit": "м", "url": "", "photo": "",
        "specifications": {
            "Способ прокладки": "Открыто",
            "Назначение": "Для электрического освещения",
            "Сечение жилы кабеля": "1.5",
            "Количество жил кабеля": "3",
        },
    }]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Способ прокладки"]["in_description"] is False
    assert by_name["Назначение"]["in_description"] is False
    assert "in_description" not in by_name["Сечение жилы кабеля"]


def test_electro_mpo_laying_and_purpose_kept_in_description_outside_cables():
    """Та же характеристика у НЕ-кабельной категории — без флага (правило
    только для "Кабельно-проводниковая продукция")."""
    raw = [{
        "name": "X", "category": "Электротехническая продукция", "price": 10, "unit": "шт",
        "url": "", "photo": "", "specifications": {"Назначение": "Общего применения"},
    }]
    item = from_electro_mpo.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert "in_description" not in by_name["Назначение"]


# --- from_vkusvill: названия поставщиков в Составе/Пищевой ценности (26.10) ---

def test_vkusvill_single_supplier_prefix_stripped():
    """Пример владельца 1: один поставщик-префикс в значении "Состава"."""
    raw = [{
        "id": 1, "name": "Томаты", "description": None,
        "price": {"current": 100}, "unit": "шт", "url": "https://x", "images": [],
        "category": [{"name": "Овощи"}],
        "properties": [{"name": "Состав", "value": 'ООО "МАНГОФРЕШ":Томаты розовые Краснодар;'}],
    }]
    item = from_vkusvill.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Состав"]["value"] == "Томаты розовые Краснодар"
    assert by_name["Поставщики"]["value"] == 'ООО "МАНГОФРЕШ"'
    assert by_name["Поставщики"]["in_description"] is False


def test_vkusvill_postavshiki_marker_list_stripped():
    """Пример владельца 2: отдельная строка "Поставщики:А;Б;В;Г" в значении."""
    raw = [{
        "id": 1, "name": "Томаты Пинк Парадайз", "description": None,
        "price": {"current": 100}, "unit": "шт", "url": "https://x", "images": [],
        "category": [{"name": "Овощи"}],
        "properties": [{
            "name": "Состав",
            "value": 'Томаты Пинк Парадайз, 500 г\nПоставщики:ООО "КОЛОС";ООО "ЗАПАДНЫЕ ВОРОТА";'
                     'ООО ЮЖНЫЙ ВЕТЕР;ООО "АГРО-ЛИДЕР"',
        }],
    }]
    item = from_vkusvill.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Состав"]["value"] == "Томаты Пинк Парадайз, 500 г"
    assert by_name["Поставщики"]["value"] == (
        'ООО "КОЛОС"; ООО "ЗАПАДНЫЕ ВОРОТА"; ООО ЮЖНЫЙ ВЕТЕР; ООО "АГРО-ЛИДЕР"'
    )


def test_vkusvill_suppliers_merged_across_sostav_and_nutrition_and_deduped():
    raw = [{
        "id": 1, "name": "Творог", "description": None,
        "price": {"current": 100}, "unit": "шт", "url": "https://x", "images": [],
        "category": [{"name": "Молочное"}],
        "properties": [
            {"name": "Состав", "value": 'ООО "НИКОН":молоко цельное.;<br>Гелиос ЗАО:молоко цельное.;'},
            {
                "name": "Пищевая и энергетическая ценность в 100 г",
                "value": 'ООО "НИКОН": белки 12 г; 234 ккал<br>Гелиос ЗАО: белки 14 г; 245 ккал',
            },
        ],
    }]
    item = from_vkusvill.convert(raw, "f.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    # одинаковый текст состава у обоих поставщиков — один экземпляр
    assert by_name["Состав"]["value"] == "молоко цельное."
    # разные варианты пищевой ценности — оба, каждый с новой строки
    assert by_name["Пищевая и энергетическая ценность в 100 г"]["value"] == (
        "белки 12 г; 234 ккал\nбелки 14 г; 245 ккал"
    )
    # поставщики собраны из обоих полей, без дублей
    assert by_name["Поставщики"]["value"] == 'ООО "НИКОН"; Гелиос ЗАО'


def test_vkusvill_no_suppliers_marker_characteristic_absent():
    raw = [{
        "id": 1, "name": "X", "description": None, "price": {"current": 10}, "unit": "шт",
        "url": "https://x", "images": [], "category": [{"name": "Кат"}],
        "properties": [{"name": "Состав", "value": "мука, вода, соль"}],
    }]
    item = from_vkusvill.convert(raw, "f.json")["items"][0]
    names = {c["name"] for c in item["characteristics"]}
    assert "Поставщики" not in names
    assert next(c for c in item["characteristics"] if c["name"] == "Состав")["value"] == "мука, вода, соль"


# --- from_store_nomenclature (Задача 1, 26.10) --------------------------------

def test_store_nomenclature_basic_mapping():
    raw = [{
        "name": "Детская страховочная система OUISTITI",
        "category": "Альпинистское снаряжение и промальп",
        "unit": "шт", "price_rub": 7490.0,
        "source_store": "АльпИндустрия / Ледниковый период",
        "link_1": "https://ice-age.ru/product/x",
        "photo_url": "https://cdn.example.com/x.jpeg",
        "description": "Рекламный текст, который не переносим.",
        "specifications": {"Артикул": "C068AA00"},
    }]
    result = from_store_nomenclature.convert(raw, "promalp_height_safety_nomenclature.json")
    assert result["source"] == "store_nomenclature"
    item = result["items"][0]
    assert item["category"] == "Альпинистское снаряжение и промальп"
    assert item["category_path"] == ["Альпинистское снаряжение и промальп"]
    assert item["product_type"] is None
    assert item["price"] == 7490.0
    assert item["article"] == "C068AA00"
    assert item["description"] is None
    assert item["photos"] == ["https://cdn.example.com/x.jpeg"]
    assert item["links"] == [{"url": "https://ice-age.ru/product/x", "price": 7490.0}]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Магазин-источник"]["value"] == "АльпИндустрия / Ледниковый период"
    assert by_name["Магазин-источник"]["in_description"] is False
    assert "Артикул" not in by_name
    assert validate_gala_catalog(_envelope("store_nomenclature", result["items"])) == []


def test_store_nomenclature_zero_and_missing_price_is_null():
    raw = [{"name": "X", "category": "C", "unit": "шт", "price_rub": 0, "source_store": "S",
            "link_1": "", "photo_url": None, "specifications": {}}]
    item = from_store_nomenclature.convert(raw, "f.json")["items"][0]
    assert item["price"] is None
    assert item["links"] == []
    assert item["photos"] == []


def test_store_nomenclature_drops_junk_keys_and_stub_values():
    """Задача 1: пустые/цифровые/заглушечные ключи и значения-заглушки, а
    также значения длиннее 300 символов — выбрасываются; хвостовое ":" у
    ключа — срезается, не выбрасывается."""
    raw = [{
        "name": "Огнетушитель", "category": "Огнетушители", "unit": "шт", "price_rub": 100,
        "source_store": "Магазин 01", "link_1": "", "photo_url": None,
        "specifications": {
            "#PROP_TITLE#": "#PROP_VALUE#",
            "123": "мусор",
            "": "мусор",
            "Масса, кг": "х" * 301,
            "Срок службы, лет": "10",
            "Комплектация:": "На тележке",
        },
    }]
    item = from_store_nomenclature.convert(raw, "fire_equipment_nomenclature.json")["items"][0]
    names = {c["name"] for c in item["characteristics"]}
    assert "#PROP_TITLE#" not in names
    assert "123" not in names
    assert "Масса" not in names  # значение >300 символов выброшено целиком
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Срок службы"]["unit"] == "лет"
    assert by_name["Срок службы"]["value"] == "10"
    assert by_name["Комплектация"]["value"] == "На тележке"  # хвостовое ":" у ключа убрано


def test_store_nomenclature_article_and_manufacturer_priority():
    raw = [{
        "name": "Жгут", "category": "Медицина", "unit": "шт", "price_rub": 100,
        "source_store": "Медплант", "link_1": "", "photo_url": None,
        "specifications": {
            "Артикул": "A1",
            "Производитель": "ООО Медплант",
            "Бренд": "ООО Медплант",
        },
    }]
    item = from_store_nomenclature.convert(raw, "f.json")["items"][0]
    assert item["article"] == "A1"
    assert item["manufacturer"] == "ООО Медплант"
    names = {c["name"] for c in item["characteristics"]}
    assert "Производитель" not in names
    assert "Бренд" not in names  # совпадает с "Производитель" — не дублируем


def test_store_nomenclature_brand_different_from_manufacturer_kept():
    raw = [{
        "name": "X", "category": "Кат", "unit": "шт", "price_rub": 100,
        "source_store": "S", "link_1": "", "photo_url": None,
        "specifications": {"Производитель": "ПроизводительА", "Бренд": "БрендБ"},
    }]
    item = from_store_nomenclature.convert(raw, "f.json")["items"][0]
    assert item["manufacturer"] == "ПроизводительА"
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Бренд"]["value"] == "БрендБ"


def test_store_nomenclature_rescue_medical_package_dims_excluded_from_description():
    """Задача 1: в rescue_medical "Длина"/"Ширина"/"Высота"/"Вес" без
    уточнения — габариты упаковки магазина, in_description=False; у
    уточнённых ключей ("Длина ленты") правило не действует; в других файлах
    (не rescue_medical) правило тоже не действует."""
    raw = [{
        "name": "Жгут", "category": "Медицина", "unit": "шт", "price_rub": 100,
        "source_store": "Медплант", "link_1": "", "photo_url": None,
        "specifications": {"Длина": "102 см", "Длина ленты": "950 мм"},
    }]
    item = from_store_nomenclature.convert(raw, "rescue_medical_nomenclature.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Длина"]["in_description"] is False
    assert "in_description" not in by_name["Длина ленты"]

    item2 = from_store_nomenclature.convert(raw, "fire_equipment_nomenclature.json")["items"][0]
    by_name2 = {c["name"]: c for c in item2["characteristics"]}
    assert "in_description" not in by_name2["Длина"]


def test_store_nomenclature_is_junk_key():
    """Задача (владелец, 26.10): фильтр мусорных ключей характеристик —
    обрывки фраз, маркеры списка, код/артикул поставщика, текст про
    логистику/цену, слишком длинные ключи."""
    is_junk = from_store_nomenclature._is_junk_key
    # обрывки фраз разобранного описания (начинаются со строчной буквы)
    assert is_junk("неблагоприятных климатических воздействий") is True
    assert is_junk("по основе") is True
    assert is_junk("от -40⁰С до +40⁰С") is True
    # маркеры списка
    assert is_junk("- пункт списка") is True
    assert is_junk("• пункт списка") is True
    assert is_junk("– пункт списка") is True
    assert is_junk("* пункт списка") is True
    # логистика/цена магазина
    assert is_junk("Цена, руб") is True
    assert is_junk("Цена, ₽") is True
    assert is_junk("Доставка по МКАД") is True
    assert is_junk("Распродажа/уценка") is True
    # код/артикул поставщика
    assert is_junk("DSUS003") is True
    assert is_junk("БВ-3-1") is True
    assert is_junk("01-2611") is True
    assert is_junk("б/н") is True
    # слишком длинный
    assert is_junk("Слово " * 7) is True  # >6 слов
    assert is_junk("Х" * 61) is True  # >60 символов
    # "руб" как ПОДСТРОКА внутри "трубка"/"патрубок"/"струбцина" — НЕ мусор
    # (слова про трубы/зажим, не про рубли), а отдельное "руб"/"рублей" — мусор
    assert is_junk("Длина трубки") is False
    assert is_junk("Диаметр патрубков") is False
    assert is_junk("Усл.проход вход.патрубка") is False
    assert is_junk("Цена, руб") is True
    assert is_junk("5690 руб.") is True
    assert is_junk("Стоимость в рублях") is True
    # нормальные ключи с единицами — НЕ мусор
    assert is_junk("Вес (кг)") is False
    assert is_junk("Диаметр, мм") is False
    assert is_junk("Объем (л)") is False
    assert is_junk("Ширина сиденья") is False
    assert is_junk("Рабочее давление") is False
    assert is_junk("IP-защита") is False
    assert is_junk("Артикул") is False


def test_store_nomenclature_drops_junk_keys_in_convert():
    """Интеграционная проверка: мусорные ключи не попадают в characteristics
    через convert(), нормальные — остаются."""
    raw = [{
        "name": "Товар", "category": "Кат", "unit": "шт", "price_rub": 100,
        "source_store": "Магазин", "link_1": "", "photo_url": None,
        "specifications": {
            "неблагоприятных климатических воздействий": "отрицательных температур",
            "- маркер списка": "значение",
            "Доставка по МКАД": "бесплатно",
            "DSUS003": "значение",
            "б/н": "значение",
            "Вес (кг)": "5",
            "Рабочее давление": "10 МПа",
        },
    }]
    item = from_store_nomenclature.convert(raw, "f.json")["items"][0]
    names = {c["name"] for c in item["characteristics"]}
    assert names == {"Вес", "Рабочее давление", "Магазин-источник"}


def test_store_nomenclature_comma_unit_split():
    raw = [{
        "name": "Огнетушитель", "category": "Огнетушители", "unit": "шт", "price_rub": 100,
        "source_store": "Магазин 01", "link_1": "", "photo_url": None,
        "specifications": {"Защищаемая площадь (до), м²": "150"},
    }]
    item = from_store_nomenclature.convert(raw, "fire_equipment_nomenclature.json")["items"][0]
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Защищаемая площадь (до)"]["unit"] == "м²"
    assert by_name["Защищаемая площадь (до)"]["value"] == "150"


# --- from_store_nomenclature: Сима-ленд (brand/article верхнего уровня, 26.10) -

def test_store_nomenclature_sima_land_fragment():
    """Фрагмент реального sima_land_catalog_all.json (26.10): верхнеуровневые
    brand/article приоритетнее характеристик, "Артикул Сима-ленд"/"Торговая
    марка" с тем же значением — не дублируются, "Страна-производитель" идёт
    и в country_origin, и в characteristics, "Вес брутто"/"Габариты (ДхШхВ)"
    — упаковка (in_description=False)."""
    raw = [{
        "name": "Челюсть «Вампир», зелёная", "category": "Приколы", "brand": "Сима-ленд",
        "article": "4878510", "unit": "шт", "price_rub": 3.58,
        "source_store": "Сима-ленд (sima-land.ru)",
        "link_1": "https://www.sima-land.ru/4878510/",
        "photo_url": "https://goods-photos.static1-sima-land.com/items/4234704/0/700.jpg",
        "description": "Челюсть «Вампир», зелёная. Сертифицированная продукция.",
        "specifications": {
            "Артикул Сима-ленд": "4878510",
            "Страна-производитель": "Китай",
            "Вес брутто": "2 г",
            "Габариты (ДхШхВ)": "5.5 x 4 x 2 см",
        },
    }]
    result = from_store_nomenclature.convert(raw, "sima_land_catalog_all.json")
    item = result["items"][0]
    assert item["manufacturer"] == "Сима-ленд"
    assert item["article"] == "4878510"
    assert item["country_origin"] == "Китай"
    assert item["description"] is None
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert "Артикул Сима-ленд" not in by_name, "дубль article — не пишем"
    assert by_name["Страна-производитель"]["value"] == "Китай"
    assert by_name["Вес брутто"] == {"name": "Вес брутто", "value": "2 г", "unit": None, "in_description": False}
    assert by_name["Габариты (ДхШхВ)"] == {
        "name": "Габариты (ДхШхВ)", "value": "5.5 x 4 x 2 см", "unit": None, "in_description": False,
    }
    assert validate_gala_catalog(_envelope("store_nomenclature", result["items"])) == []


def test_store_nomenclature_sima_land_torgovaya_marka_dedup_and_kept():
    raw = [{
        "name": "A", "category": "C", "brand": "БрендА", "article": "1", "unit": "шт", "price_rub": 10,
        "source_store": "Сима-ленд (sima-land.ru)", "link_1": "", "photo_url": None,
        "specifications": {"Торговая марка": "БрендА"},
    }]
    item = from_store_nomenclature.convert(raw, "sima_land_catalog_all.json")["items"][0]
    names = {c["name"] for c in item["characteristics"]}
    assert "Торговая марка" not in names, "совпадает с brand — не дублируем"

    raw2 = [{
        "name": "B", "category": "C", "brand": "БрендА", "article": "2", "unit": "шт", "price_rub": 10,
        "source_store": "Сима-ленд (sima-land.ru)", "link_1": "", "photo_url": None,
        "specifications": {"Торговая марка": "ДругойБренд"},
    }]
    item2 = from_store_nomenclature.convert(raw2, "sima_land_catalog_all.json")["items"][0]
    by_name2 = {c["name"]: c for c in item2["characteristics"]}
    assert by_name2["Торговая марка"]["value"] == "ДругойБренд"


def test_store_nomenclature_sima_land_article_differs_kept_as_characteristic():
    raw = [{
        "name": "A", "category": "C", "brand": "", "article": "100", "unit": "шт", "price_rub": 10,
        "source_store": "Сима-ленд (sima-land.ru)", "link_1": "", "photo_url": None,
        "specifications": {"Артикул поставщика": "200"},
    }]
    item = from_store_nomenclature.convert(raw, "sima_land_catalog_all.json")["items"][0]
    assert item["article"] == "100"
    by_name = {c["name"]: c for c in item["characteristics"]}
    assert by_name["Артикул поставщика"]["value"] == "200"


def test_store_nomenclature_top_level_brand_article_no_specs():
    """Без specifications — просто brand/article верхнего уровня, без
    зависимости от старого ключа "Артикул"/"Производитель" в specifications."""
    raw = [{
        "name": "A", "category": "C", "brand": "Сима-ленд", "article": "999", "unit": "шт",
        "price_rub": 10, "source_store": "Сима-ленд (sima-land.ru)", "link_1": "", "photo_url": None,
        "specifications": {},
    }]
    item = from_store_nomenclature.convert(raw, "sima_land_catalog_all.json")["items"][0]
    assert item["manufacturer"] == "Сима-ленд"
    assert item["article"] == "999"
