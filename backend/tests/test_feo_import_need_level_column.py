"""Колонка «Нужность» шаблона импорта ФЭО (задача владельца 2026-10-04, ревизия
p1q3r5s7t9v1 — другой агент добавил `FeoPlannedItem.need_level` String(20),
значения 'likely' (умолчание) | 'nice_to_have'). Подписи/коды — ЕДИНЫЙ источник
`app/services/plan_need_level.py::NEED_LEVEL_LABELS` (Правило №6).

Парсер (`find_col` внутри `import_feo_from_excel`, app/routers/feo_import.py +
`normalize_need_level_cell`, app/services/feo_import_common.py) обязан:
  - принимать И код, И русскую подпись (регистр/пробелы не важны);
  - пустую ячейку превращать в 'likely' (DEFAULT);
  - нераспознанное значение — завести ОШИБКУ строки (`result["errors"]`) с
    номером строки и текстом «допустимо: ...», но НЕ ронять импорт строки
    целиком — позиция создаётся с 'likely'.

Идёт через РЕАЛЬНЫЙ роутер `import_feo_from_excel` (как и
test_feo_import_item_type_column.py) — только так проверяется сам `find_col`
и склейка в FeoPlannedItem.

Гонять по одному узлу за вызов pytest в контейнере (флейк pytest-asyncio
«different loop» — project_pytest_asyncio_loop_flake, Lessons.md VSKS_CRM).
"""
import io
import uuid

import pytest
from fastapi import UploadFile
from openpyxl import Workbook

from app.routers.feo_import import import_feo_from_excel
from app.services.plan_need_level import NEED_LEVEL_LABELS
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


async def _import_one_row(db_session, superadmin_user, item_name: str, lvl2_name: str, need_level_cell):
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия", "Уровень 2", "Плановая позиция", "Плановое количество", "Плановая цена за единицу", "Нужность"]
    row = [subsidy.name, lvl2_name, item_name, "1", "100", need_level_cell]
    upload = _mk_xlsx_upload(headers, row)
    result = await import_feo_from_excel(
        file=upload, dry_run=False, remap="", apply_remap=False,
        duplicate_resolutions="", item_type_decisions="",
        db=db_session, current_user=superadmin_user,
    )
    return subsidy, result


@pytest.mark.asyncio
async def test_need_level_label_resolves_to_code(db_session, superadmin_user):
    """Русская подпись в ячейке -> код need_level (а не записана как есть)."""
    subsidy, result = await _import_one_row(
        db_session, superadmin_user,
        "Позиция — подпись в ячейке", "Направление — подпись в ячейке",
        NEED_LEVEL_LABELS["nice_to_have"],
    )
    try:
        assert result["errors"] == [], result["errors"]
        cats = await _get_categories(db_session, subsidy.id)
        lvl2_cat = next(c for c in cats if c.name == "Направление — подпись в ячейке")
        items = await _get_items(db_session, lvl2_cat.id)
        assert len(items) == 1
        assert getattr(items[0], "need_level", None) == "nice_to_have", (
            f"need_level={getattr(items[0], 'need_level', '<нет атрибута>')!r} — "
            "подпись «Хотелось бы, но можно и отказаться» не распознана парсером"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_need_level_empty_cell_defaults_to_likely(db_session, superadmin_user):
    """Пустая ячейка колонки «Нужность» -> 'likely' (умолчание)."""
    subsidy, result = await _import_one_row(
        db_session, superadmin_user,
        "Позиция — пустая ячейка", "Направление — пустая ячейка", "",
    )
    try:
        assert result["errors"] == [], result["errors"]
        cats = await _get_categories(db_session, subsidy.id)
        lvl2_cat = next(c for c in cats if c.name == "Направление — пустая ячейка")
        items = await _get_items(db_session, lvl2_cat.id)
        assert len(items) == 1
        assert getattr(items[0], "need_level", None) == "likely"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_need_level_unknown_value_is_a_row_error_but_item_still_created(db_session, superadmin_user):
    """Нераспознанное значение -> построчная ошибка с номером строки и
    текстом «допустимо: ...»; позиция всё равно создаётся с 'likely' (одна
    неверная подпись не должна ронять весь импорт файла)."""
    subsidy, result = await _import_one_row(
        db_session, superadmin_user,
        "Позиция — мусор в ячейке", "Направление — мусор в ячейке", "полная чушь",
    )
    try:
        assert len(result["errors"]) == 1, result["errors"]
        err = result["errors"][0]
        assert err["row"] == 2
        assert "допустимо" in err["message"].lower()
        for label in NEED_LEVEL_LABELS.values():
            assert label in err["message"], f"в тексте ошибки нет подписи «{label}»: {err['message']!r}"

        cats = await _get_categories(db_session, subsidy.id)
        lvl2_cat = next(c for c in cats if c.name == "Направление — мусор в ячейке")
        items = await _get_items(db_session, lvl2_cat.id)
        assert len(items) == 1
        assert getattr(items[0], "need_level", None) == "likely"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
