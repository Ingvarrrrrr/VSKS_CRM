"""Дефект №1 (2026-09-15): на боевом файле владельца («ТЗ для АПИ (4).xlsx»,
лист «ТЗ») подсказка `mapping_hint` ставила `photo_link` на колонку 1
(«фото» — пустая во всех строках), хотя реальные адреса лежат в колонке 2
(«Ссылка на фото»). Причина — в COLUMN_MAP оба заголовка точно совпадают
с полем `photo_link`, а `suggest_products_column_mapping` берёт первый по
порядку. Фикс — `suggest_products_column_mapping_with_hints(headers, sample)`
пересматривает поля с несколькими точными совпадениями по данным образца:
побеждает заголовок, у которого в `sample` есть хоть одно непустое значение
(services/products_import_map.py::_pick_best_exact_candidate).

Живая проверка через /api/products/import-preview на этом файле (до фикса)
дала mapping_hint = {'photo_link': 1, ...} — см. план задачи."""
from app.services.products_import_map import suggest_products_column_mapping_with_hints

# Заголовки листа «ТЗ» файла владельца, буквально как в диагнозе задачи —
# «фото» (индекс 1, пустая колонка) стоит раньше «Ссылка на фото» (индекс 2,
# реальные адреса).
_TZ_HEADERS = [
    "Номер", "фото", "Ссылка на фото", "Категория товара", "Вид",
    "Наименование", "Многоразовое или одноразовое", "Описание",
    "Уточняющая ссылка", "Ед. изм.", "Не заполнять", "Цена за ед.",
]

# Образец строк как их вернул бы /import-preview: колонка 1 («фото») пустая
# во всех строках, колонка 2 («Ссылка на фото») содержит реальные URL.
_TZ_SAMPLE = [
    ["1", "", "https://basket-05.wbbasket.ru/vol900/part90038/90038379/images/big/1.webp",
     "Хозтовары", "Одноразовая посуда", "Тарелка", "одноразовое", "Тарелка бумажная",
     "", "шт", "", "12.5"],
    ["2", "", "https://basket-05.wbbasket.ru/vol900/part90038/90038380/images/big/1.webp",
     "Хозтовары", "Одноразовая посуда", "Стакан", "одноразовое", "Стакан пластиковый",
     "", "шт", "", "3.2"],
]


def test_photo_link_prefers_column_with_data_not_first_match():
    """Дефект №1 — при двух точных совпадениях на photo_link («фото» и
    «Ссылка на фото») подсказка обязана указать на колонку 2 (данные есть),
    а не на колонку 1 (пустая во всём образце)."""
    mapping = suggest_products_column_mapping_with_hints(_TZ_HEADERS, _TZ_SAMPLE)
    assert mapping.get("photo_link") == 2, (
        f"photo_link обязан указывать на индекс 2 («Ссылка на фото»), получено: {mapping}"
    )
    assert _TZ_HEADERS[mapping["photo_link"]] == "Ссылка на фото"


def test_name_still_maps_to_naimenovanie_with_sample_passed():
    """Передача sample не должна ломать уже верное сопоставление 'name' —
    у этого поля только один точный кандидат («Наименование», индекс 5),
    пересмотр по образцу его не касается."""
    mapping = suggest_products_column_mapping_with_hints(_TZ_HEADERS, _TZ_SAMPLE)
    assert mapping.get("name") == 5
    assert _TZ_HEADERS[mapping["name"]] == "Наименование"


def test_without_sample_falls_back_to_first_match_as_before():
    """Без образца (sample=None/пуст) — прежнее поведение: первый по порядку
    точный кандидат побеждает. Не должно ронять вызовы без sample (старые
    тесты test_products_import_mapping.py зовут функцию без него)."""
    mapping = suggest_products_column_mapping_with_hints(_TZ_HEADERS)
    assert mapping.get("photo_link") == 1
    mapping_empty_sample = suggest_products_column_mapping_with_hints(_TZ_HEADERS, [])
    assert mapping_empty_sample.get("photo_link") == 1


def test_ambiguous_field_with_no_data_anywhere_falls_back_to_first():
    """Если ни один из кандидатов не имеет данных в образце (пустой файл /
    все строки образца пустые в обеих колонках) — берём первый, как раньше,
    вместо того чтобы вообще ничего не предложить."""
    empty_sample = [["", "", "", "", "", "", "", "", "", "", "", ""]]
    mapping = suggest_products_column_mapping_with_hints(_TZ_HEADERS, empty_sample)
    assert mapping.get("photo_link") == 1


def test_single_excel_error_cell_does_not_outweigh_densely_filled_column():
    """Регресс живой проверки на боевом файле (2026-09-15): в одной строке
    образца колонка «фото» (пустая везде) содержала не пустоту, а `#REF!`
    (Excel-артефакт битой формулы/ссылки) — правило «есть хоть одна непустая
    ячейка» из первой версии фикса из-за этого снова выбирало пустую колонку
    вместо «Ссылка на фото», где реальные адреса в 5 строках из 5. Подсчёт
    заполненности (`_sample_fill_count`, игнорирует #REF!/#N/A/…) обязан
    отдать колонку 2 — она гуще заполнена, единичный Excel-мусор не в счёт."""
    sample_with_ref_error = [
        ["1", "", "https://basket-05.wbbasket.ru/vol900/part90038/90038379/images/big/1.webp",
         "Хозтовары", "Одноразовая посуда", "Тарелка", "одноразовое", "Тарелка бумажная",
         "", "шт", "", "12.5"],
        ["2", "", "https://uniguardgps.com/wp-content/uploads/2014/03/GF22-pack-700x700.jpg",
         "Хозтовары", "Одноразовая посуда", "Стакан", "одноразовое", "Стакан пластиковый",
         "", "шт", "", "3.2"],
        ["3", "#REF!", "НЕ смог найти",
         "Хозтовары", "Одноразовая посуда", "Вилка", "одноразовое", "Вилка пластиковая",
         "", "шт", "", "1.1"],
        ["4", "", "https://avtohart.ru/netcat_files/290/439/123.jpg",
         "Хозтовары", "Одноразовая посуда", "Ложка", "одноразовое", "Ложка пластиковая",
         "", "шт", "", "1.3"],
    ]
    mapping = suggest_products_column_mapping_with_hints(_TZ_HEADERS, sample_with_ref_error)
    assert mapping.get("photo_link") == 2, (
        f"Единичный #REF! в колонке «фото» не должен перевешивать 3/4 заполненных "
        f"строк в «Ссылка на фото»; получено: {mapping}"
    )
