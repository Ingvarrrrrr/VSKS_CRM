"""Импорт товаров обязан читать УКАЗАННЫЙ лист по имени, а не `wb.active`
(план dreamy-booping-piglet.md, задача B, п.4 — приёмка (в теста)). До правки
POST /api/products/import читал только `wb.active` и не принимал sheet_name
вовсе; новый POST /api/products/import-mapped (и общий сервис
services/import_preview_sheets.py::read_full_sheet_rows) выбирает лист по
имени явно.

Сценарий: книга с ДВУМЯ листами, где первый (значит — активный по
умолчанию в openpyxl, `wb.active` без явного `wb.active = N`) — «Прочее» с
посторонними данными, а нужные товары лежат на втором листе «ТЗ». Если бы
код брал `wb.active`, он бы вернул строки «Прочее» и потерял бы товары
листа «ТЗ» — ровно так угадывание сломалось на боевом файле владельца.
"""
from io import BytesIO

import pytest

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

from app.services.import_preview_sheets import read_full_sheet_rows


def _build_two_sheet_workbook() -> bytes:
    wb = Workbook()
    ws_other = wb.active  # первый лист — создаётся активным по умолчанию
    ws_other.title = "Прочее"
    ws_other.append(["Мусорная колонка", "Ещё мусор"])
    ws_other.append(["не товар", "не товар"])

    ws_tz = wb.create_sheet("ТЗ")
    ws_tz.append(["Наименование", "Цена за ед."])
    ws_tz.append(["Коммутатор D-Link DGS-1024D/J1A", 12000])
    ws_tz.append(["Ноутбук Lenovo IdeaPad", 50000])

    assert wb.active.title == "Прочее", "тест должен проверять именно случай, когда wb.active — НЕ «ТЗ»"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_read_full_sheet_rows_picks_named_sheet_not_active():
    if Workbook is None:
        pytest.skip("openpyxl не установлен")
    content = _build_two_sheet_workbook()

    rows = read_full_sheet_rows(content, "two_sheets.xlsx", "ТЗ")

    assert rows[0][0] == "Наименование"
    names = [r[0] for r in rows[1:]]
    assert "Коммутатор D-Link DGS-1024D/J1A" in names
    assert "Ноутбук Lenovo IdeaPad" in names
    # Ничего от активного (но НЕ запрошенного) листа «Прочее» не просочилось
    assert "не товар" not in names


def test_read_full_sheet_rows_falls_back_to_first_sheet_when_name_missing():
    """Если запрошенного имени нет среди листов — берём первый лист файла
    (детерминированный fallback), а не что попало."""
    if Workbook is None:
        pytest.skip("openpyxl не установлен")
    content = _build_two_sheet_workbook()

    rows = read_full_sheet_rows(content, "two_sheets.xlsx", "Лист_которого_нет")

    assert rows[0][0] == "Мусорная колонка"


@pytest.mark.asyncio
async def test_import_mapped_uses_requested_sheet_via_http(client, auth_headers):
    if Workbook is None:
        pytest.skip("openpyxl не установлен")
    content = _build_two_sheet_workbook()

    resp = await client.post(
        "/api/products/import-mapped",
        headers=auth_headers,
        files={"file": ("two_sheets.xlsx", content,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params={
            "sheet_name": "ТЗ",
            "header_row_offset": 0,
            "dry_run": "true",
            "col_name": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    names = {r["name"] for r in result["rows"] if r.get("name")}
    assert "Коммутатор D-Link DGS-1024D/J1A" in names
    assert "Ноутбук Lenovo IdeaPad" in names
    assert "не товар" not in names
