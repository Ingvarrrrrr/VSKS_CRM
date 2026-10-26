"""Валидация/нормализация списка характеристик карточки товара перед
сохранением (владелец, задача «ручное заполнение характеристик», 26.10.2026).

ЕДИНСТВЕННОЕ место этой нормализации (ПРАВИЛО №6) — вызывается из
app/routers/products.py (PUT/PATCH) перед записью Product.characteristics;
второй такой нормализатор не писать. Правила (владелец, дословно задания):
список ≤200 строк, name ≤200 символов, value ≤2000, unit ≤50; строка с
пустым name ИЛИ пустым value отбрасывается целиком; in_description
сохраняется КАК ПРИШЛО (True/False/отсутствует → None) — дефолт НЕ
форсируется в False: в product_tech_description.py::_characteristic_line
ТОЛЬКО явное False исключает строку из описания, None/отсутствие там
означает «видна в описании» (как и у данных загрузчика поставщиков) — см.
докстринг ProductCharacteristic в app/schemas/products.py.
"""
from fastapi import HTTPException

MAX_ITEMS = 200
MAX_NAME_LEN = 200
MAX_VALUE_LEN = 2000
MAX_UNIT_LEN = 50


def normalize_characteristics(raw_items) -> list:
    """raw_items — список словарей/pydantic-моделей (уже прошедших схему
    ProductCharacteristic, то есть name/value/unit/in_description с верными
    типами) или None. Возвращает список ПЛОСКИХ dict для записи в JSONB,
    строки с пустым name или пустым value отбрасываются целиком. 400, если
    строк больше MAX_ITEMS (владелец: «≤200 строк» — явная проверка, не
    молчаливая обрезка)."""
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=400, detail="characteristics должен быть списком")
    if len(raw_items) > MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Характеристик больше {MAX_ITEMS} — разбейте на несколько сохранений.",
        )

    out = []
    for item in raw_items:
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            raise HTTPException(status_code=400, detail="Каждая характеристика должна быть объектом {name, value, unit}")
        name = str(data.get("name") or "").strip()
        value = str(data.get("value") or "").strip()
        if not name or not value:
            continue
        unit = str(data.get("unit") or "").strip() or None
        if len(name) > MAX_NAME_LEN:
            raise HTTPException(status_code=400, detail=f"Название характеристики длиннее {MAX_NAME_LEN} символов: «{name[:50]}…»")
        if len(value) > MAX_VALUE_LEN:
            raise HTTPException(status_code=400, detail=f"Значение характеристики «{name}» длиннее {MAX_VALUE_LEN} символов.")
        if unit and len(unit) > MAX_UNIT_LEN:
            raise HTTPException(status_code=400, detail=f"Единица характеристики «{name}» длиннее {MAX_UNIT_LEN} символов.")
        in_desc = data.get("in_description")
        out.append({
            "name": name,
            "value": value,
            "unit": unit,
            "in_description": bool(in_desc) if in_desc is not None else None,
        })
    return out


def _content_tuple(item: dict) -> tuple:
    """(name, value, unit) без in_description — старые записи каталога
    (загрузчик поставщика) не всегда несли этот ключ, а новая схема шлёт его
    всегда (дефолт False). Сравнение "реально ли поменялись характеристики"
    (нужно product_catalog_guard.py, чтобы не требовать products.edit_catalog
    на пустую пересохранением того же набора) не должно ложно считать
    изменением одно только появление/исчезновение этого ключа."""
    return (
        (item.get("name") or "").strip(),
        (item.get("value") or "").strip(),
        (item.get("unit") or "").strip(),
    )


def characteristics_changed(old_items, new_items) -> bool:
    """True, если список характеристик РЕАЛЬНО меняется по содержанию
    (name/value/unit), игнорируя одно лишь присутствие/значение
    in_description и порядок одинаковых элементов не учитывает (порядок
    важен — используется как список построчно, а не множество)."""
    old_list = [_content_tuple(i) for i in (old_items or [])]
    new_list = [_content_tuple(i) for i in (new_items or [])]
    return old_list != new_list
