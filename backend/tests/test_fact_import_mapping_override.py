# Тест багфикса 20.10.2026 (владелец: «карточки сдвинуты после смены
# листа») — apply_mapping_override должен принимать ОБЕ формы mapping:
# старую `{"columns": {индекс: поле}}` и реальную форму фронта
# `{поле: индекс|null}` (см. columns.py::apply_mapping_override).
# Чистые функции, без БД/фикстур.
from app.services.historical_fact_import import columns


def _cols(headers: list) -> list:
    return columns._map_columns_format(headers)


def test_old_form_columns_by_index_still_works():
    headers = ["Плановая позиция", "Ед. изм.", "Плановое количество"]
    cols = _cols(headers)
    result = columns.apply_mapping_override(cols, {"columns": {"2": "unit"}})
    by_index = {c["index"]: c["field"] for c in result}
    assert by_index[2] == "unit"


def test_frontend_form_moves_field_and_clears_old_column():
    # "unit" автоопределился на индекс 1 (заголовок "Ед. изм.") — человек
    # перетащил поле на индекс 2 ("Плановое количество" по заголовку, но
    # мы ставим туда "unit" принудительно).
    headers = ["Плановая позиция", "Ед. изм.", "Плановое количество"]
    cols = _cols(headers)
    assert next(c["field"] for c in cols if c["index"] == 1) == "unit"
    result = columns.apply_mapping_override(cols, {"unit": 2})
    by_index = {c["index"]: c["field"] for c in result}
    assert by_index[2] == "unit"
    assert by_index[1] is None  # снято со старой колонки


def test_frontend_form_null_clears_field():
    headers = ["Плановая позиция", "Ед. изм."]
    cols = _cols(headers)
    assert next(c["field"] for c in cols if c["index"] == 1) == "unit"
    result = columns.apply_mapping_override(cols, {"unit": None})
    by_index = {c["index"]: c["field"] for c in result}
    assert by_index[1] is None


def test_frontend_form_matching_autodetect_does_not_touch_second_column():
    # Поле "unit" автоопределилось на индексе 1; если человек явно шлёт то
    # же значение (idx=1) — вторая колонка с тем же полем (если бы была)
    # не должна быть тронута/снята просто потому, что мы "переустанавливаем"
    # то же самое поле. Проверяем через искусственную вторую колонку "unit",
    # которую override НЕ должен снять, т.к. совпадающее назначение (idx=1)
    # обрабатывается как "ничего не менять".
    headers = ["Плановая позиция", "Ед. изм."]
    cols = _cols(headers)
    cols.append({"index": 2, "letter": "C", "header": "Доп. ед.", "field": "unit"})
    result = columns.apply_mapping_override(cols, {"unit": 1})
    by_index = {c["index"]: c["field"] for c in result}
    assert by_index[1] == "unit"
    assert by_index[2] == "unit"  # не снято — совпадающее назначение не трогает остальные колонки


def test_unknown_key_and_out_of_range_index_ignored():
    headers = ["Плановая позиция", "Ед. изм."]
    cols = _cols(headers)
    before = [dict(c) for c in cols]
    result = columns.apply_mapping_override(cols, {"not_a_real_field": 0, "unit": 99})
    assert result == before
