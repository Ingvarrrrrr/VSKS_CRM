from __future__ import annotations

import pytest
from fastapi import HTTPException
import io
import openpyxl

from app.services.cloud_spreadsheet import _validate_and_normalize_url
from app.services.unified_template import build_unified_template_bytes
from app.services.historical_fact_import.columns import detect_format_and_header, build_columns


def test_validate_and_normalize_url():
    # Valid urls
    assert _validate_and_normalize_url("https://docs.google.com/spreadsheets/d/123/edit") == "https://docs.google.com/spreadsheets/d/123/edit"
    assert _validate_and_normalize_url("https://disk.yandex.ru/i/abcdef") == "https://disk.yandex.ru/i/abcdef"
    assert _validate_and_normalize_url("https://docs.yandex.ru/docs/view?url=ya-disk-public://123") == "https://docs.yandex.ru/docs/view?url=ya-disk-public://123"

    # Invalid schemes or domains (SSRF protection)
    with pytest.raises(HTTPException) as exc:
        _validate_and_normalize_url("http://docs.google.com/spreadsheets/d/123/edit")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _validate_and_normalize_url("https://evil.com/file.xlsx")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _validate_and_normalize_url("https://127.0.0.1/x")
    assert exc.value.status_code == 400


def test_unified_template_generation():
    import asyncio
    wb_bytes = asyncio.run(build_unified_template_bytes())
    assert isinstance(wb_bytes, bytes)
    wb = openpyxl.load_workbook(io.BytesIO(wb_bytes))
    expected = [
        "Как выбрать лист",
        "План ФЭО (и факт)",
        "Выгрузка ФЭО (правки)",
        "Факт — 1 колонка",
        "Факт — этапы Да_Нет",
    ]
    assert wb.sheetnames == expected
    assert "Sheet" not in wb.sheetnames
    for name in expected[1:]:
        sheet = wb[name]
        assert sheet.max_row >= 2, f"{name}: too few rows ({sheet.max_row})"
        assert sheet.max_column >= 13, f"{name}: too few columns ({sheet.max_column})"


def test_historical_fact_import_header_row():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ХРО Импорт"
    
    ws.cell(row=1, column=18, value=100000)
    ws.cell(row=2, column=18, value=1)
    ws.cell(row=3, column=5, value="Уровень 2")
    ws.cell(row=3, column=7, value="Плановая позиция")
    ws.cell(row=3, column=18, value="Факт")
    ws.cell(row=3, column=21, value="Оплачено")
    ws.cell(row=3, column=25, value="Правильный статус")
    ws.cell(row=4, column=5, value="Субсидия")
    ws.cell(row=4, column=7, value="Тестовая позиция")
    ws.cell(row=4, column=18, value=5000)
    ws.cell(row=4, column=21, value=5000)
    ws.cell(row=4, column=25, value="Оплачено")

    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    detected = detect_format_and_header(content, "test.xlsx", None)
    assert detected["header_row"] == 3
    cols = build_columns(detected)
    assert any(c.get("field") == "plan_item_name" for c in cols)
