"""Опциональный блок «Факт» шаблона ФЭО (решение владельца, 05.10.2026):
субсидию, у которой часть закупок уже прошла, грузят ОДНИМ файлом — план
через обычный импорт ФЭО (app/routers/feo_import.py) + 8 необязательных
колонок справа («Правильный статус», «Факт: Количество/Цена/Сумма»,
«Оплачено», «Законтрактовано», «Поставщик», «№ закупки»), см. шаблон
app/routers/feo_import_template.py.

ПРАВИЛО №6 — второй механизм загрузки факта здесь НЕ заводится: этот модуль
только (1) находит индексы колонок блока «Факт» по заголовку файла и
(2) считает, сколько строк реально несут факт — сам факт пишет только
существующий «Импорт факта» (app/services/historical_fact_import/*,
app/routers/fact_import.py), куда фронт предлагает перейти с ТЕМ ЖЕ файлом
(см. useFactImport.ts::openWizardWithFile). `_do_feo_import` эти колонки не
принимает и не видит вовсе — они физически не передаются в его параметры
(c_subsidy..c_need_level), поэтому не влияют на построение дерева/плана ни
единой веткой кода.

Детекция по заголовку — ОДНА функция для обоих эндпоинтов импорта ФЭО
(/import — автоопределение, /import-mapped — ручной маппинг, но заголовок
файла всё равно известен до вызова _do_feo_import), чтобы не разойтись в
двух копиях ключевых слов.
"""
from __future__ import annotations

from typing import Optional

from app.services.feo_import_common import get_cell
from app.services.historical_fact_import.statuses import status_code_from_raw

# Порядок — слева направо, как в шаблоне (feo_import_template.py). Ключевые
# слова ищутся в заголовке, уже нормализованном (strip + lower) вызывающим
# кодом — тем же приёмом, что find_col в app/routers/feo_import.py.
FACT_FIELDS = (
    "c_fact_status", "c_fact_qty", "c_fact_price", "c_fact_amount",
    "c_fact_paid", "c_fact_contracted", "c_fact_supplier", "c_fact_purchase_no",
)

_FACT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "c_fact_status": ("правильный статус",),
    "c_fact_qty": ("факт: количество", "факт количество"),
    "c_fact_price": ("факт: цена", "факт цена"),
    "c_fact_amount": ("факт: сумма", "факт сумма"),
    "c_fact_paid": ("оплачено",),
    "c_fact_contracted": ("законтрактовано",),
    "c_fact_supplier": ("поставщик",),
    "c_fact_purchase_no": ("№ закупки", "номер закупки"),
}


def detect_fact_columns_by_header(raw_headers: list[str]) -> dict[str, Optional[int]]:
    """`raw_headers` — заголовки файла, уже strip().lower() (как
    `raw_headers` в import_feo_from_excel / строка заголовка import-mapped).
    Возвращает {поле: индекс|None} — НЕ резервирует индексы (блок «Факт» не
    пересекается словами с колонками плана/ФЭО, которые разбирает find_col в
    app/routers/feo_import.py, поэтому отдельного `_used_cols` здесь не
    нужно)."""
    result: dict[str, Optional[int]] = {}
    for field in FACT_FIELDS:
        idx: Optional[int] = None
        for kw in _FACT_KEYWORDS[field]:
            for i, h in enumerate(raw_headers):
                if kw in h:
                    idx = i
                    break
            if idx is not None:
                break
        result[field] = idx
    return result


def has_fact_columns(fact_cols: dict[str, Optional[int]]) -> bool:
    return any(v is not None for v in fact_cols.values())


def count_fact_rows(rows: list, c_fact_status: Optional[int]) -> int:
    """Строки файла, где «Правильный статус» заполнен распознанным статусом,
    ОТЛИЧНЫМ от «План закупок» (plan_schedule — это ещё план, не факт).
    Нераспознанный текст статуса не считается — такая строка владельцу
    предложит разобраться сам мастер «Импорт факта» (needs_status), здесь
    достаточно консервативной оценки «есть ли смысл предлагать переход»."""
    if c_fact_status is None:
        return 0
    count = 0
    for row in rows:
        raw = get_cell(row, c_fact_status)
        if not raw:
            continue
        code = status_code_from_raw(raw)
        if code is not None and code != "plan_schedule":
            count += 1
    return count
