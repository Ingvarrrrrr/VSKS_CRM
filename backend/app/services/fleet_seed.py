"""
Fleet seed from Голичков xlsx — Phase 30-PR1.

Импортирует данные из Передача и Лист4 листов xlsx.

СТРУКТУРА ФАЙЛА (из inspect 2026-05-21):
  Лист2       — полный реестр на ранние даты (22 ТС), уже импортирован в Phase 29
  09.04.2026  — текущий реестр 51 ТС, уже импортирован в Phase 29 vehicles_seed.py
  20.05.24    — срез пробегов на 20.05.24 (гос.знак, VIN, пробег, дата ТО)
  25.06.2024  — срез пробегов на 25.06.24
  01.07.2024  — срез пробегов на 01.07.24
  2025        — срез пробегов на 2025 (без пробегов, только статус)
  Лист4       — 5 колонок: Штаб, Марка/Модель, Тип, VIN, Гос.рег.знак
               НЕТ явных полей документов — TODO: уточнить назначение листа
  Передача    — Организация, Марка, Модель, Год, VIN, Гос.рег.знак, Статус, доп.данные
               Это реестр текущего распределения по штабам, а НЕ история передач
               TODO: выяснить у Голичкова есть ли отдельная история передач

NOTE: Кириллица в шапках читается в mojibake при read_only=True. Используем позиционный
парсинг по индексу колонки, а не по имени заголовка.
"""
import os
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Путь к xlsx (bundled seed_data копия)
XLSX_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', 'seed_data', 'vehicles_golichkov.xlsx'
)


async def seed_fleet_from_xlsx(db, xlsx_path: Optional[str] = None) -> dict:
    """
    Идемпотентно импортирует данные из листов Передача и Лист4.

    Возвращает dict с ключами:
      - reason: str (если пропущено)
      - transfers_imported: int
      - documents_imported: int
      - lист4_rows: int (количество строк в Лист4 для ревью)
    """
    path = xlsx_path or XLSX_PATH
    if not os.path.exists(path):
        log.warning(f"fleet_seed: xlsx не найден: {path}")
        return {'reason': 'xlsx_not_found', 'path': path}

    try:
        import openpyxl
    except ImportError:
        log.warning("fleet_seed: openpyxl не установлен — пропускаем seed")
        return {'reason': 'openpyxl_not_installed'}

    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        log.warning(f"fleet_seed: не удалось открыть xlsx: {e}")
        return {'reason': f'xlsx_open_error: {e}'}

    transfers_imported = 0
    documents_imported = 0
    lист4_rows = 0

    # ── Лист "Передача" (последний лист в sheetnames) ─────────────────────────
    # Структура: номер, Организация(штаб), Марка, Модель, Год, VIN, Гос.рег.знак,
    #            Статус(работает/не работает), доп.значение
    # Это реестр текущего закрепления ТС, НЕ история передач.
    # TODO: уточнить структуру с Голичковым — нужна история передач с датами/основанием.
    # Пока пишем диагностику:
    передача_sheet = None
    for sname in wb.sheetnames:
        # Ищем лист с "Передача" (с учётом mojibake — последний непонятный лист)
        # По позиции в sheetnames: wb.sheetnames[-1] — "Передача"
        pass
    передача_sheet = wb.sheetnames[-1]  # последний лист = "Передача"

    if передача_sheet in wb.sheetnames:
        ws = wb[передача_sheet]
        row_count = 0
        for row in ws.iter_rows(min_row=1, max_row=1000, values_only=True):
            if any(c is not None for c in row):
                row_count += 1
        log.info(
            f"fleet_seed: лист '{передача_sheet}' содержит {row_count} строк. "
            f"Парсер истории передач — TODO (нет полей from_org/to_org/date/basis). "
            f"Ручное ревью: нужна история с датами и основанием."
        )
        # TODO: реализовать парсер когда Голичков предоставит файл с историей передач
        # Пример структуры которую ожидаем:
        # Номер | Дата передачи | Гос.знак | VIN | Откуда (орг) | Куда (орг) | Основание | Документ
        transfers_imported = 0

    # ── Лист "Лист4" (предпоследний лист) ────────────────────────────────────
    # Структура: Штаб | Марка/Модель | Тип | VIN | Гос.рег.знак
    # 5 колонок. Это перечень ТС по штабам без документов.
    # TODO: уточнить у Голичкова — документы ли это? или просто ещё один срез реестра?
    лист4_sheet = None
    for sname in wb.sheetnames:
        pass
    # По позиции в sheetnames: wb.sheetnames[-2] — "Лист4"
    if len(wb.sheetnames) >= 2:
        лист4_sheet = wb.sheetnames[-2]
        ws4 = wb[лист4_sheet]
        rows4 = []
        for row in ws4.iter_rows(min_row=1, max_row=500, values_only=True):
            if any(c is not None for c in row):
                rows4.append(row)
        lист4_rows = len(rows4)
        log.info(
            f"fleet_seed: лист '{лист4_sheet}' содержит {lист4_rows} строк. "
            f"Структура: 5 колонок (Штаб/Марка+Модель/Тип/VIN/Гос.знак). "
            f"Это перечень ТС по штабам — НЕ история документов. "
            f"Импорт документов — TODO."
        )
        documents_imported = 0

    wb.close()

    result = {
        'transfers_imported': transfers_imported,
        'documents_imported': documents_imported,
        'лист4_rows': lист4_rows,
        'note': (
            'Парсеры истории передач и документов — TODO: '
            'структура листов не содержит полей from/to/дата/основание для transfers. '
            'Нужен файл с историческими передачами от Голичкова.'
        ),
    }
    log.info(f"fleet_seed: результат: {result}")
    return result
