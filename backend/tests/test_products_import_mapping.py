"""Регресс дефекта №2 плана dreamy-booping-piglet.md (задача B): импорт
товаров угадывал колонки фаззи-цепочкой и на боевом файле владельца
(«ТЗ для АПИ (4).xlsx», лист «ТЗ») взял «Категорию товара» за наименование —
создано 1022 товара с именами вроде «Цифровая техника».

`suggest_products_column_mapping` (app/services/products_import_map.py)
заменяет фаззи-цепочку на точное совпадение по COLUMN_MAP — этот тест
проверяет ИМЕННО заголовки боевого файла: «name» обязан указать на колонку
«Наименование», а не на «Категория товара» (и вообще ни на что, если бы
«Наименование» не было в списке — но здесь оно есть, точным совпадением).
"""
from app.services.products_import_map import suggest_products_column_mapping

# Заголовки листа «ТЗ» файла владельца (буквально из плана
# dreamy-booping-piglet.md, задача B) — «Категория товара» стоит РАНЬШЕ
# «Наименования» в файле, поэтому старая фаззи-цепочка матчила её первой.
_TZ_HEADERS = [
    "Номер", "фото", "Ссылка на фото", "Категория товара", "Вид",
    "Наименование", "Многоразовое или одноразовое", "Описание",
    "Уточняющая ссылка", "Ед. изм.", "Не заполнять", "Цена за ед.",
]


def test_name_maps_to_naimenovanie_not_category():
    mapping = suggest_products_column_mapping(_TZ_HEADERS)
    assert mapping.get("name") == 5, (
        f"'name' обязан указывать на индекс 5 («Наименование»), получено: {mapping}"
    )
    assert _TZ_HEADERS[mapping["name"]] == "Наименование"


def test_category_column_not_confused_with_name():
    mapping = suggest_products_column_mapping(_TZ_HEADERS)
    # «Категория товара» (индекс 3) НЕ должна попасть ни в 'name', ни вообще
    # в подсказку — в COLUMN_MAP нет точного ключа "категория товара" (есть
    # только "категория"), и фаззи-цепочки, которая раньше ловила её
    # по подстроке "категор", больше нет.
    assert mapping.get("name") != 3
    assert "category" not in mapping


def test_no_fuzzy_reassignment_of_name_by_data_type():
    """Раньше был отдельный пост-эвристический проход: если в колонке name
    первые строки данных — числа, брали первую "строковую" колонку вместо
    неё. Эта функция принимает ТОЛЬКО заголовки (без данных) — по построению
    у неё физически нет доступа к строкам данных, значит переназначить name
    по типу данных она не может."""
    import inspect
    sig = inspect.signature(suggest_products_column_mapping)
    assert list(sig.parameters.keys()) == ["headers"], (
        "suggest_products_column_mapping не должна принимать строки данных — "
        "иначе фаззи-эвристика по типу данных могла бы вернуться"
    )


def test_description_and_product_type_recognized_exactly():
    mapping = suggest_products_column_mapping(_TZ_HEADERS)
    assert mapping.get("description") == 7
    assert mapping.get("product_type") == 4


def test_unmapped_header_yields_no_field():
    """Заголовки, которых нет в COLUMN_MAP (и не подходят под «Ссылка N» /
    «Цена ссылки N»), не должны попадать в подсказку вовсе — раньше на такой
    заголовок могла сработать фаззи-подстрока."""
    mapping = suggest_products_column_mapping(["Уточняющая ссылка", "Не заполнять"])
    assert mapping == {}


def test_link_columns_still_detected_dynamically():
    mapping = suggest_products_column_mapping(["Наименование", "Ссылка 1", "Цена ссылки 1"])
    assert mapping["name"] == 0
    assert mapping["link_url_1"] == 1
    assert mapping["link_price_1"] == 2
