"""normalize_person_name — каноническая форма ФИО для точного (не fuzzy)
сравнения «это один и тот же человек?».

ПРАВИЛО №6: единственное место этой нормализации. Вынесено из
scripts/fadm_sheet_load/advance.py (жила там первой — распознавание
авансовых отчётов при историческом импорте: контрагент строки/группы на
самом деле сотрудник) в app/services/, чтобы тем же правилом мог
воспользоваться app/services/purchase_from_bank_payment.py («Создать закупку
по платёжке» — владелец, план .planning/quick/2026-10-05-payment-control/
PLAN.md: получатель платежа — сотрудник → авансовый отчёт, не обычная
закупка у поставщика). Скрипт импортирует эту функцию вместо собственной
копии (см. scripts/fadm_sheet_load/advance.py) — поведение скрипта не
изменилось ни на йоту.

Без сведения ОПФ (здесь не организация, а человек) — в отличие от
normalize_contractor_name (lesson feedback_dedup_exact_only, тоже точное
сравнение, без нечёткого сопоставления)."""
from __future__ import annotations

import re
from typing import Optional

_WS_RE = re.compile(r"\s+")


def normalize_person_name(raw: Optional[str]) -> str:
    """ФИО → каноническая строка: trim, lowercase, ё→е, схлопнутые пробелы."""
    if not raw:
        return ""
    s = str(raw).strip().lower().replace("ё", "е")
    return _WS_RE.sub(" ", s)
