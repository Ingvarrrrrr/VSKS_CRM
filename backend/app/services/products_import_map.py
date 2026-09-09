"""Подсказка соответствия колонок Excel-файла товарного справочника полям
`Product`. ТОЛЬКО точное совпадение нормализованного заголовка с `COLUMN_MAP`
(плюс распознавание пронумерованных «Ссылка N» / «Цена ссылки N») — никакой
фаззи-цепочки по подстрокам и никакой пост-эвристики «в колонке name одни
числа — возьмём другую колонку».

Обе убранные ветки — ровно то, что на боевом файле владельца
(«ТЗ для АПИ (4).xlsx», лист «ТЗ») превратило колонку «Категория товара» в
`name`: строка `'категор' in h` фаззи-цепочки матчила «Категория товара» на
`category`, но перед этим `any(x in h for x in ('наименован', ...))` тоже
матчила её на `name`, потому что порядок elif решал первым делом `name`, и то,
что «Категория товара» физически СОДЕРЖИТ подстроку из списка совпадений
`name` в конкретной комбинации заголовков файла, забирало колонку раньше,
чем реальный заголовок «Наименование». Итог — 1022 товара с именами-категориями
в БД (план dreamy-booping-piglet.md, задача B, дефект №2).

Подсказка — это ТОЛЬКО подсказка: возвращается клиенту для проверки/правки в
мастере маппинга и не применяется сама по себе (см.
routers/products_import.py::products_import_preview /
products_import_mapped — реальные индексы колонок передаёт клиент явно).
"""
import re as _re

# Дословно перенесено из routers/products_import.py:136-166 (до правки) —
# единственный источник соответствия «заголовок → поле Product» для подсказки.
COLUMN_MAP = {
    "наименование": "name",
    "название": "name",
    "наименование товара": "name",
    "товар": "name",
    "name": "name",
    "описание": "description",
    "description": "description",
    "категория": "category",
    "category": "category",
    "вид": "product_type",
    "тип": "product_type",
    "type": "product_type",
    "цена": "price",
    "цена, руб": "price",
    "цена, ₽": "price",
    "цена (руб)": "price",
    "стоимость": "price",
    "price": "price",
    "фото (url)": "photo_link",
    "фото": "photo_link",
    "photo": "photo_link",
    "ссылка на фото": "photo_link",
    "многоразовое": "is_reusable",
    "активен": "is_active",
    "активна": "is_active",
    "active": "is_active",
    "категория фэо": "feo_category_name",
    "фэо": "feo_category_name",
    "направление фэо": "feo_category_name",
}

_LINK_URL_RE = _re.compile(r"ссылка (\d+)$")
_LINK_PRICE_RE = _re.compile(r"цена ссылки (\d+)$")


def suggest_products_column_mapping(headers: list) -> dict:
    """headers — заголовки КАК ЕСТЬ (регистр/пробелы неважны, нормализуются
    внутри). Возвращает {field: column_index} — только точные совпадения из
    `COLUMN_MAP` (первое вхождение поля побеждает при дублирующихся
    заголовках) плюс динамические `link_url_N` / `link_price_N` для колонок
    «Ссылка N» / «Цена ссылки N». Никакой догадки сверх этого."""
    col_idx: dict = {}
    for i, h in enumerate(headers):
        norm = str(h).strip().lower() if h is not None else ""
        if not norm:
            continue
        field = COLUMN_MAP.get(norm)
        if field and field not in col_idx:
            col_idx[field] = i
        m = _LINK_URL_RE.match(norm)
        if m:
            col_idx[f"link_url_{m.group(1)}"] = i
        m2 = _LINK_PRICE_RE.match(norm)
        if m2:
            col_idx[f"link_price_{m2.group(1)}"] = i
    return col_idx
