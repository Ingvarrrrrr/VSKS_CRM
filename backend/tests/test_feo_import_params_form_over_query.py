"""Баг владельца 2026-09-17: импорт в субсидию «Центрпоиск_3» падал с
HTTP 414 (URI Too Long) — фронт (useFeoImport.ts::doFeoMappedImport) собирал
~70 параметров `col_*` + `remap` + `duplicate_resolutions` (кириллические
ключи, по группе на КАЖДУЮ категорию) в query-строку POST-запроса на
/api/feo-categories/import-mapped; на крупной субсидии URL уходил на десятки
КБ — выше дефолтного лимита nginx (large_client_header_buffers, 8 КБ).

Фикс: эти же параметры теперь идут в тело multipart-формы вместе с файлом;
backend принимает и то, и другое — сначала форма, при отсутствии поля откат
на query (обратная совместимость со старым фронтом из PWA-кеша). Единый
механизм — app/services/request_params.py::merge_form_over_query,
app/services/feo_import_params.py::resolve_feo_import_mapped_params
(Правило №6 — один парсер, не ветвление в каждом из ~70 параметров).

Тест НЕ поднимает HTTP/DB/приложение целиком — конструирует Starlette
Request напрямую с multipart-телом и проверяет ТОЛЬКО логику слияния
form/query, которая и была источником бага. Как и другие тесты импорта ФЭО
в этом проекте, гонять по одному узлу за вызов pytest (см. docstring
test_feo_import_target_subsidy.py про «different loop»)."""
from starlette.requests import Request

from app.services.request_params import merge_form_over_query
from app.services.feo_import_params import resolve_feo_import_mapped_params


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


async def test_form_overrides_query_for_named_fields():
    """Новый фронт кладёт параметры В ФОРМУ — они обязаны победить дефолты
    Query(...), а поле, не пришедшее в форме, остаётся тем, что уже
    разобрал FastAPI из query-строки (сейчас — статический URL без данных)."""
    request = _multipart_request({
        "col_lvl2": "5",
        "dry_run": "true",
        "duplicate_resolutions": '{"budget::Пожарное": "sum"}',
    })
    query_values = dict(col_lvl2=-1, col_lvl3=-1, dry_run=False, duplicate_resolutions="")
    resolved = await merge_form_over_query(
        request, query_values,
        bool_fields=frozenset({"dry_run"}), int_fields=frozenset({"col_lvl2", "col_lvl3"}),
    )
    assert resolved["col_lvl2"] == 5
    assert resolved["col_lvl3"] == -1  # not in form → query default kept
    assert resolved["dry_run"] is True
    assert "budget::" in resolved["duplicate_resolutions"]


async def test_query_only_request_keeps_backward_compatibility():
    """Старый фронт (PWA-кеш на проде) шлёт эти параметры ТОЛЬКО в query —
    форма содержит только файл, ни одно текстовое поле не перекрывает
    query-значения, backend обязан продолжать работать как раньше."""
    request = _multipart_request({})  # ни одного текстового поля кроме файла
    query_values = dict(col_lvl2=7, dry_run=True)
    resolved = await merge_form_over_query(
        request, query_values, bool_fields=frozenset({"dry_run"}), int_fields=frozenset({"col_lvl2"}),
    )
    assert resolved == query_values


async def test_resolve_feo_import_mapped_params_wrapper():
    """resolve_feo_import_mapped_params — обёртка, реально используемая
    app/routers/feo_import.py::import_feo_mapped; проверка на паре ключевых
    полей (полный список ~50 полей уже перечислен в feo_import_params.py,
    дублировать его здесь незачем — Правило №6)."""
    request = _multipart_request({"col_lvl2": "3", "default_subsidy_id": "42", "apply_remap": "true"})
    resolved = await resolve_feo_import_mapped_params(
        request,
        sheet_name="", header_row_offset=0, col_subsidy=-1, col_lvl2=-1, col_lvl3=-1, col_lvl4=-1,
        col_lvl5=-1, col_code=-1, col_appendix=-1, col_budget=-1, col_quantity=-1, col_unit=-1,
        col_item_amt=-1, col_active=-1, col_qty_lvl2=-1, col_qty_lvl3=-1, col_qty_lvl4=-1,
        col_unit_lvl2=-1, col_unit_lvl3=-1, col_unit_lvl4=-1, col_amt_lvl2=-1, col_amt_lvl3=-1,
        col_amt_lvl4=-1, col_feo_qty_lvl2=-1, col_feo_qty_lvl3=-1, col_feo_qty_lvl4=-1,
        col_feo_unit_lvl2=-1, col_feo_unit_lvl3=-1, col_feo_unit_lvl4=-1, col_feo_amount_lvl2=-1,
        col_feo_amount_lvl3=-1, col_feo_amount_lvl4=-1, col_feo_sum_lvl2=-1, col_feo_sum_lvl3=-1,
        col_feo_sum_lvl4=-1, col_plan_sum_lvl2=-1, col_plan_sum_lvl3=-1, col_plan_sum_lvl4=-1,
        col_item_price=-1, col_row_feo_qty=-1, col_row_feo_unit=-1, col_row_feo_price=-1,
        col_row_feo_sum=-1, col_row_plan_qty=-1, col_row_plan_unit=-1, col_row_plan_price=-1,
        col_row_plan_sum=-1, col_item_type=-1, default_subsidy_id=-1, dry_run=False, remap="",
        apply_remap=False, duplicate_resolutions="",
    )
    assert resolved["col_lvl2"] == 3
    assert resolved["default_subsidy_id"] == 42
    assert resolved["apply_remap"] is True
    assert resolved["col_lvl3"] == -1
