"""Генерирует e2e/fixtures/vehicle_owner_org_import.xlsx — тестовый файл для
e2e/33-vehicle-owner-org-import.spec.ts (замена пути в scratchpad чужой сессии,
см. TODO фронта). Две строки, оба гос. номера заведомо не существуют в БД:

  1. Организация-собственник пустая, «ИНН собственника» = 9729333100
     (АНО "ЦЕНТРПОИСК", org_id=5 в локальном dev-стенде) — проверяет
     сопоставление владельца ПО ИНН.
  2. «Организация-собственник» = точное название «ХРО ВСКС» (org_id=28) —
     проверяет сопоставление владельца ПО НАЗВАНИЮ.

Заголовки взяты из backend/app/services/vehicle_fields.py (реестр полей) +
«ИНН собственника» — распознаваемый, но не входящий в стандартный шаблон
алиас (backend/app/services/fleet_import_columns.py, _COL_MAP: "инн
собственника" -> owner_inn). Запуск: python gen_vehicle_owner_org_import.py
(из любого cwd — путь вывода вычисляется относительно этого файла).
"""
from pathlib import Path

from openpyxl import Workbook

OUT_PATH = Path(__file__).parent / "vehicle_owner_org_import.xlsx"

HEADERS = ["Гос. рег. знак", "Организация-собственник", "Состояние", "ИНН собственника"]

ROWS = [
    ["У000ТТ099", "", "Рабочее", "9729333100"],
    ["У111ТТ099", "ХРО ВСКС", "Рабочее", ""],
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Транспорт"
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(row)
    wb.save(OUT_PATH)
    print(f"written: {OUT_PATH}")


if __name__ == "__main__":
    main()
