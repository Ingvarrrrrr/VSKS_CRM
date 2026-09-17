"""Тот же дефект HTTP 414 (URI Too Long), что чинил импорт ФЭО (см.
test_feo_import_params_form_over_query.py) — только для импорта позиций
ВНУТРИ закупки: `resolutions` (JSON {"<row_num>": "recalc_sum"|...}) на файле
с большим числом строк sum_mismatch способен раздуть query-строку тем же
образом. app/routers/purchase_items_import_mapped.py::import_items_mapped и
app/routers/purchase_items_import_smart.py::import_items_smart оба переведены
на тот же общий механизм — app/services/request_params.py::merge_form_over_query
(Правило №6: второй парсер формы/query здесь не заводится, ни один из этих
роутеров не выделяет собственный `*_params.py`, как feo_import_params.py —
поле-наборы просто перечислены inline в вызовах merge_form_over_query внутри
самих эндпоинтов).

Тест НЕ поднимает HTTP/DB/приложение целиком — конструирует Starlette Request
напрямую с multipart-телом и проверяет ТОЛЬКО логику слияния form/query с
ТОЧНО ТЕМИ ЖЕ наборами bool_fields/int_fields, что объявлены в реальных
вызовах merge_form_over_query внутри import_items_mapped и import_items_smart
(см. соответствующие строки в этих роутерах) — если набор полей там когда-то
разъедется с этим тестом, тест перестанет отражать реальное поведение
эндпоинта, а не даст ложный PASS. Как и другие тесты импорта в проекте,
гонять по одному узлу за вызов pytest (flake pytest-asyncio «different
loop»)."""
from starlette.requests import Request

from app.services.request_params import merge_form_over_query


def _multipart_request(fields: dict) -> Request:
    """Синтетический multipart/form-data запрос с текстовыми полями (без
    файла — merge_form_over_query читает только именованные текстовые поля,
    файл роутер получает отдельно через UploadFile)."""
    boundary = "testboundary123"
    body_parts = []
    for name, value in fields.items():
        body_parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        )
    body_parts.append(f'--{boundary}--\r\n')
    body = "".join(body_parts).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    return Request(scope, receive)


# ---------------------------------------------------------------------------
# import_items_mapped (purchase_items_import_mapped.py) — тот же набор полей,
# что и в реальном вызове merge_form_over_query внутри эндпоинта.
# ---------------------------------------------------------------------------

_MAPPED_INT_FIELDS = frozenset({
    "col_item_name", "col_description", "col_quantity", "col_unit_price", "col_total_price",
    "col_vat", "col_unit", "col_row_num", "col_vat_rate", "col_vat_amount", "col_total_with_vat",
    "col_category", "col_product_type", "header_row_offset",
})
_MAPPED_BOOL_FIELDS = frozenset({"confirm"})


async def test_mapped_import_form_overrides_query():
    """Новый фронт (useItemsImport.ts, _requestMappedImportPid) кладёт
    col_*/confirm/resolutions В ФОРМУ вместе с файлом — они обязаны победить
    дефолты Query(...) из старой сигнатуры эндпоинта."""
    request = _multipart_request({
        "col_item_name": "2",
        "confirm": "true",
        "resolutions": '{"5": "recalc_sum"}',
    })
    query_values = dict(
        col_item_name=-1, col_unit_price=-1, confirm=False, resolutions=None,
        header_row_offset=0,
    )
    resolved = await merge_form_over_query(
        request, query_values,
        bool_fields=_MAPPED_BOOL_FIELDS, int_fields=_MAPPED_INT_FIELDS,
    )
    assert resolved["col_item_name"] == 2
    assert resolved["confirm"] is True
    assert resolved["resolutions"] == '{"5": "recalc_sum"}'
    # Не пришедшее в форме поле — остаётся тем, что разобрал FastAPI из query.
    assert resolved["col_unit_price"] == -1
    assert resolved["header_row_offset"] == 0


async def test_mapped_import_query_only_keeps_backward_compatibility():
    """Старый фронт (PWA-кеш на проде) шлёт col_*/confirm/resolutions ТОЛЬКО
    в query-строке — форма содержит только файл, ни одно текстовое поле не
    подменяет query-значения, эндпоинт обязан продолжать работать как раньше
    (иначе старый фронт сломался бы этой же правкой)."""
    request = _multipart_request({})  # ни одного текстового поля кроме файла
    query_values = dict(
        col_item_name=3, col_unit_price=5, confirm=True, resolutions='{"1": "keep"}',
        header_row_offset=1,
    )
    resolved = await merge_form_over_query(
        request, query_values,
        bool_fields=_MAPPED_BOOL_FIELDS, int_fields=_MAPPED_INT_FIELDS,
    )
    assert resolved == query_values


# ---------------------------------------------------------------------------
# import_items_smart (purchase_items_import_smart.py) — тот же набор полей,
# что и в реальном вызове merge_form_over_query внутри эндпоинта.
# ---------------------------------------------------------------------------

_SMART_BOOL_FIELDS = frozenset({"confirm", "skip_catalog"})


async def test_smart_import_form_overrides_query():
    """useItemsImport.ts (doSmartImport) шлёт confirm/skip_catalog/resolutions
    в форме — форма обязана победить query-дефолты."""
    request = _multipart_request({
        "confirm": "true",
        "skip_catalog": "true",
        "resolutions": '{"2": "recalc_price"}',
    })
    query_values = dict(confirm=False, skip_catalog=False, resolutions=None)
    resolved = await merge_form_over_query(
        request, query_values, bool_fields=_SMART_BOOL_FIELDS,
    )
    assert resolved["confirm"] is True
    assert resolved["skip_catalog"] is True
    assert resolved["resolutions"] == '{"2": "recalc_price"}'


async def test_smart_import_query_only_keeps_backward_compatibility():
    """Старый фронт шлёт эти поля только в query — форма пуста (кроме
    файла) — значения из query обязаны остаться как есть."""
    request = _multipart_request({})
    query_values = dict(confirm=True, skip_catalog=False, resolutions='{"1": "keep"}')
    resolved = await merge_form_over_query(
        request, query_values, bool_fields=_SMART_BOOL_FIELDS,
    )
    assert resolved == query_values


async def test_form_value_wins_over_same_named_query_value():
    """Явная проверка ключевого смысла задачи: одноимённое значение из формы
    ПЕРЕКРЫВАЕТ значение из query, а не наоборот и не сливается с ним —
    беря поле, где query и форма расходятся, а не просто «форма задана,
    query дефолтна» (как в тестах выше)."""
    request = _multipart_request({"col_item_name": "9"})
    query_values = dict(col_item_name=1)
    resolved = await merge_form_over_query(
        request, query_values, int_fields=frozenset({"col_item_name"}),
    )
    assert resolved["col_item_name"] == 9
