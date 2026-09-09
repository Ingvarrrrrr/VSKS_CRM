"""Сквозной тест мастера импорта товаров (план dreamy-booping-piglet.md,
задача B): POST /api/products/import-preview → подсказка маппинга → POST
/api/products/import-mapped с dry_run=true → построчный отчёт с номерами
строк и причинами. Файл-миниатюра повторяет РАСКЛАДКУ боевого файла
владельца («ТЗ для АПИ (4).xlsx», лист «ТЗ»): «Категория товара» стоит
раньше «Наименования», и есть строки без наименования (владелец: 220 таких
строк на боевом файле, номера 1019+) — здесь их две, чтобы проверить, что
отчёт даёт им action=skipped, reason и НОМЕР СТРОКИ, а не молча
пропускает (как было устроено `continue` до правки).

dry_run=true не пишет в БД; на всякий случай тест всё равно работает внутри
общей транзакции db_session/client (conftest.py) — ничего не переживёт
teardown, даже при ошибке в проверке.
"""
from io import BytesIO

import pytest

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None


def _build_tz_like_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "ТЗ"
    ws.append([
        "Номер", "фото", "Ссылка на фото", "Категория товара", "Вид",
        "Наименование", "Многоразовое или одноразовое", "Описание",
        "Ед. изм.", "Цена за ед.",
    ])
    ws.append([1, None, None, "Цифровая техника", "Ноутбук",
               "Ноутбук Lenovo IdeaPad", "Многоразовое", "Описание 1", "шт.", 50000])
    ws.append([2, None, None, "Сетевое оборудование", "Сетевой коммутатор",
               "Коммутатор D-Link DGS-1024D/J1A", "Многоразовое", "Описание 2", "шт.", 12000])
    ws.append([3, None, None, "Цифровая техника", "Принтер",
               None, "Многоразовое", "Описание 3", "шт.", 8000])  # нет наименования — row 4
    ws.append([4, None, None, "Мебель", "Стол",
               "Стол офисный", "Многоразовое", "Описание 4", "шт.", 15000])
    ws.append([5, None, None, "Мебель", "Стул",
               None, "Многоразовое", None, "шт.", 3000])  # нет наименования — row 6
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_preview_then_mapped_dry_run_reports_rows_and_reasons(client, auth_headers):
    if Workbook is None:
        pytest.skip("openpyxl не установлен")
    xlsx = _build_tz_like_workbook()

    r1 = await client.post(
        "/api/products/import-preview",
        headers=auth_headers,
        files={"file": ("tz.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r1.status_code == 200, r1.text
    preview = r1.json()
    sheets = [s for s in preview["sheets"] if s["name"] == "ТЗ"]
    assert sheets, f"Лист «ТЗ» не найден в предпросмотре: {preview['sheets']}"
    sheet = sheets[0]
    assert sheet["header_row_offset"] == 0
    hint = sheet["mapping_hint"]
    # Главная приёмка задачи B: name указывает на «Наименование» (индекс 5),
    # а не на «Категория товара» (индекс 3).
    assert hint["name"] == 5
    assert sheet["headers"][hint["name"]] == "Наименование"

    r2 = await client.post(
        "/api/products/import-mapped",
        headers=auth_headers,
        files={"file": ("tz.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params={
            "sheet_name": "ТЗ",
            "header_row_offset": 0,
            "dry_run": "true",
            "col_name": hint["name"],
            "col_description": hint.get("description", -1),
            "col_product_type": hint.get("product_type", -1),
        },
    )
    assert r2.status_code == 200, r2.text
    result = r2.json()

    assert result["created"] == 3
    assert result["updated"] == 0
    assert result["skipped"] == 2
    assert result["errors"] == []
    # dry_run=true — ничего не должно быть реально создано
    assert result["product_ids"] == []

    rows_by_num = {r["row"]: r for r in result["rows"]}
    assert set(rows_by_num.keys()) == {2, 3, 4, 5, 6}

    assert rows_by_num[2]["action"] == "created"
    assert rows_by_num[2]["name"] == "Ноутбук Lenovo IdeaPad"

    assert rows_by_num[3]["action"] == "created"
    assert rows_by_num[3]["name"] == "Коммутатор D-Link DGS-1024D/J1A"
    # Дефект №2: имя НЕ должно превратиться в значение колонки «Категория товара»
    assert rows_by_num[3]["name"] != "Сетевое оборудование"

    assert rows_by_num[4]["action"] == "skipped"
    assert rows_by_num[4]["reason"] == "нет наименования"

    assert rows_by_num[5]["action"] == "created"
    assert rows_by_num[5]["name"] == "Стол офисный"

    assert rows_by_num[6]["action"] == "skipped"
    assert rows_by_num[6]["reason"] == "нет наименования"
