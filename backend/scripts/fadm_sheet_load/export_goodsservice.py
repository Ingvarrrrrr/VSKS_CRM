"""Экспорт листа GoodsService из xlsx в CSV в ТОЧНО том же формате, что
текущий backend/scripts/data/fadm_2026_goodsservice.csv (разделитель ';',
CRLF, числа как есть (точка-разделитель, без тысячных), даты как
YYYY-MM-DD для настоящих date/datetime-ячеек, остальное — str(value) без
изменений). Формулы читаются как посчитанные значения (data_only=True) —
иначе получим саму формулу вместо числа.

Запуск (владелец даёт путь к свежей выгрузке Google Sheets):
    python export_goodsservice.py <путь_к.xlsx> [--out <путь.csv>] [--sheet GoodsService]

По умолчанию перезаписывает backend/scripts/data/fadm_2026_goodsservice.csv.
ПРАВИЛО №6: один формат CSV — сверяется с уже существующим файлом построчно
по количеству столбцов, не вводится второй incompatible формат.
"""
from __future__ import annotations

import argparse
import csv
import datetime
from pathlib import Path

import openpyxl

DEFAULT_SHEET = "GoodsService"
DEFAULT_HEADER_ROW = 3  # 1-based, как в самом xlsx (заголовки — строка 3)
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "fadm_2026_goodsservice.csv"


def _cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        if value.hour or value.minute or value.second:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # openpyxl отдаёт целые числа как float (1.0, 43.0) — в текущем
        # CSV они записаны без ".0" (экспорт Google Sheets так не делает).
        # round(value, 6) убирает бинарный шум float-вычитаний формул
        # (напр. 157365.65000000127 вместо 157365.65); на обычных суммах
        # с копейками (11870.6, 94695.8) ничего не меняет.
        value = round(value, 6)
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def export(xlsx_path: Path, out_path: Path, sheet_name: str = DEFAULT_SHEET,
           header_row: int = DEFAULT_HEADER_ROW) -> int:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise SystemExit(f"Лист {sheet_name!r} не найден. Доступные листы: {wb.sheetnames}")
    ws = wb[sheet_name]

    rows_iter = ws.iter_rows(min_row=header_row)
    header = [_cell_to_str(c.value) for c in next(rows_iter)]
    # Отрезаем пустые хвостовые столбцы листа (лишние колонки Excel без
    # заголовка и без данных) — старый CSV их не содержит.
    while header and header[-1] == "":
        header.pop()
    ncols = len(header)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)
        for row in rows_iter:
            values = [_cell_to_str(c.value) for c in row]
            # пропускаем полностью пустые хвостовые строки листа
            if not any(v.strip() for v in values[:8]):
                continue
            if len(values) < ncols:
                values += [""] * (ncols - len(values))
            elif len(values) > ncols:
                values = values[:ncols]
            writer.writerow(values)
            written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xlsx_path", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sheet", default=DEFAULT_SHEET)
    ap.add_argument("--header-row", type=int, default=DEFAULT_HEADER_ROW)
    args = ap.parse_args()

    n = export(args.xlsx_path, args.out, args.sheet, args.header_row)
    print(f"Записано строк данных: {n} -> {args.out}")


if __name__ == "__main__":
    main()
