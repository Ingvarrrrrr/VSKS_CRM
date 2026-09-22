"""Разбор параметров `/api/feo-categories/import-mapped` — вынесено из
`app/routers/feo_import.py` (Правило №5: ~70 параметров эндпоинта плюс
логика приёма формы/query раздували бы роутер).

Единственное место, знающее, какие из ~50 полей `import-mapped` — целые
(`col_*`, `header_row_offset`, `default_subsidy_id`), какие — булевы
(`dry_run`, `apply_remap`), а остальные — строки (`sheet_name`, `remap`,
`duplicate_resolutions`). Использует общий `merge_form_over_query`
(app/services/request_params.py, тот же механизм и у импорта позиций
закупки — Правило №6, второй парсер формы не заводим)."""
from fastapi import Request

from app.services.request_params import merge_form_over_query

# Все int-параметры import-mapped, кроме служебных header_row_offset/
# default_subsidy_id (перечислены отдельно ниже вместе с ними в вызывающем
# коде) — единственное место, где перечислены имена col_*-полей эндпоинта.
_COL_INT_FIELDS = frozenset({
    "col_subsidy", "col_lvl2", "col_lvl3", "col_lvl4", "col_lvl5",
    "col_code", "col_appendix", "col_budget", "col_quantity", "col_unit",
    "col_item_amt", "col_active",
    "col_qty_lvl2", "col_qty_lvl3", "col_qty_lvl4",
    "col_unit_lvl2", "col_unit_lvl3", "col_unit_lvl4",
    "col_amt_lvl2", "col_amt_lvl3", "col_amt_lvl4",
    "col_feo_qty_lvl2", "col_feo_qty_lvl3", "col_feo_qty_lvl4",
    "col_feo_unit_lvl2", "col_feo_unit_lvl3", "col_feo_unit_lvl4",
    "col_feo_amount_lvl2", "col_feo_amount_lvl3", "col_feo_amount_lvl4",
    "col_feo_sum_lvl2", "col_feo_sum_lvl3", "col_feo_sum_lvl4",
    "col_plan_sum_lvl2", "col_plan_sum_lvl3", "col_plan_sum_lvl4",
    "col_item_price",
    "col_row_feo_qty", "col_row_feo_unit", "col_row_feo_price", "col_row_feo_sum",
    "col_row_plan_qty", "col_row_plan_unit", "col_row_plan_price", "col_row_plan_sum",
    "col_item_type",
    "col_num1", "col_num2", "col_num3", "col_num4",
})

INT_FIELDS = _COL_INT_FIELDS | {"header_row_offset", "default_subsidy_id"}
BOOL_FIELDS = frozenset({"dry_run", "apply_remap"})


async def resolve_feo_import_mapped_params(request: Request, **query_values) -> dict:
    """`query_values` — ВСЕ параметры `import_feo_mapped`, уже разобранные
    FastAPI из Query (значения по умолчанию, если фронт ничего не передал).
    Возвращает тот же набор ключей, с приоритетом значений из multipart-формы
    текущего запроса (см. merge_form_over_query)."""
    return await merge_form_over_query(
        request, query_values, bool_fields=BOOL_FIELDS, int_fields=INT_FIELDS,
    )
