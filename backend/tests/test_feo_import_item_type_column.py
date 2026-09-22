"""Владелец (21.09, раздел W2 плана corrections-21-09.md): заголовок колонки
«Тип» плановой позиции в шаблоне импорта ФЭО переименован
«Товар/услуга» -> «Тип (товар/услуга/работа)» (app/routers/feo_import_template.py).

Парсер (`find_col` внутри `import_feo_from_excel`, app/routers/feo_import.py)
обязан находить И новый заголовок, И старые («Товар/услуга», «Тип позиции»,
generic «Тип») — файлы, выгруженные до переименования, не должны перестать
импортироваться. Единственный ДРУГОЙ заголовок шаблона, содержащий «тип» —
«Уровень 3 (Тип расходов по ФЭО)» — обязан оставаться за c_lvl3 (заявлен
раньше в find_col и потому забирает свою колонку первым); тест держит эту
колонку заполненной пустой строкой в каждом сценарии, чтобы явно проверить
отсутствие коллизии.

Идёт через РЕАЛЬНЫЙ роутер `import_feo_from_excel` (не через `_do_feo_import`
напрямую, как остальные тесты ФЭО-импорта — им заголовки не нужны, они
передают `c_*`-индексы руками) — только так проверяется сам `find_col`.
Depends(...) в сигнатуре роутера — значения по умолчанию, вызывается
напрямую в обход FastAPI DI (тот же приём, что и в
test_planned_item_link_rules.py); Query(...)-парам обязаны передаваться
явно — их дефолт (FieldInfo-объект) не годится как обычный bool/str.

Гонять по одному узлу за вызов pytest в контейнере (флейк pytest-asyncio
«different loop» — project_pytest_asyncio_loop_flake).
"""
import io
import uuid

import pytest
from fastapi import UploadFile
from openpyxl import Workbook

from app.routers.feo_import import import_feo_from_excel
from tests.test_feo_import_tree import _cleanup_subsidy, _get_categories, _get_items, _make_subsidy


def _mk_xlsx_upload(headers, row) -> UploadFile:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return UploadFile(file=bio, filename=f"import-{uuid.uuid4().hex[:6]}.xlsx")


@pytest.mark.asyncio
async def test_new_and_legacy_type_column_headers_all_resolve(db_session, superadmin_user):
    subsidy = await _make_subsidy(db_session)
    try:
        # (заголовок колонки типа, имя направления Ур.2, имя позиции, введённое
        # значение, ожидаемый нормализованный item_type)
        cases = [
            ("Тип (товар/услуга/работа)", "Направление — новый заголовок", "Позиция новая", "Работа", "работа"),
            ("Товар/услуга", "Направление — старый заголовок", "Позиция старая", "Услуга", "услуга"),
            ("Тип позиции", "Направление — легаси заголовок", "Позиция легаси", "Товар", "товар"),
            ("Тип", "Направление — голый заголовок «Тип»", "Позиция голый тип", "работа", "работа"),
        ]
        for type_header, lvl2_name, item_name, raw_type, expected in cases:
            headers = [
                "Субсидия", "Уровень 2", "Уровень 3 (Тип расходов по ФЭО)",
                "Плановая позиция", type_header, "Плановое количество", "Плановая цена за единицу",
            ]
            row = [subsidy.name, lvl2_name, "", item_name, raw_type, "1", "100"]
            upload = _mk_xlsx_upload(headers, row)

            result = await import_feo_from_excel(
                file=upload, dry_run=False, remap="", apply_remap=False,
                duplicate_resolutions="", item_type_decisions="",
                db=db_session, current_user=superadmin_user,
            )
            assert result["errors"] == [], f"заголовок «{type_header}»: {result['errors']}"

            cats = await _get_categories(db_session, subsidy.id)
            lvl2_cat = next((c for c in cats if c.name == lvl2_name), None)
            assert lvl2_cat is not None, f"заголовок «{type_header}»: направление Ур.2 не создано — «уровень 3» перехватил чужую колонку?"

            items = await _get_items(db_session, lvl2_cat.id)
            assert len(items) == 1, f"заголовок «{type_header}»: ожидалась ровно одна плановая позиция"
            assert items[0].name == item_name
            assert items[0].item_type == expected, (
                f"заголовок «{type_header}» не распознан парсером (find_col) — "
                f"item_type={items[0].item_type!r}, ожидалось {expected!r}"
            )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
