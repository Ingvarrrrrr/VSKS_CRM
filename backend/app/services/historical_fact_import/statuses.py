"""Нормализация «Правильный статус» → РОВНО один из 6 статусов GALA.

🔵 Правка 3 (02.10, план breezy-mixing-lovelace.md часть 2): импорт больше не
придумывает свои промежуточные состояния — только 6 кодов, подписи которых
переиспользованы из `app.routers.purchase_transitions.STATUS_LABELS`
(ПРАВИЛО №6 — один источник подписей статуса, не вторая копия строк):
  plan_schedule     «План закупок»     — закупку не создавать
  work_in_progress  «Ведётся работа»
  contracted        «Заключён договор»
  ordered           «Заказано»
  delivered         «Поставлено»       — отчёт «чего не хватает»: «нет акта»
  paid              «Оплачено»         — + платёж «по отметке»

Старые значения из файлов (владелец, план): «план» → План закупок; «В
работе» → Ведётся работа; «Заключён»/«Заключено»/«Заключнено» → Заключён
договор; «Оплачено частично» → Заключён договор (частичность видна суммой —
оплачено меньше договора, отдельного статуса не заводим); «Возмещено» →
Оплачено. КАЖДАЯ строка, где сырой текст отличается от официальной подписи,
получает `correction` — preview.py кладёт его в row.warnings («статус
приведён: «...» → «...»»).

Неизвестное значение — `recognized=False`, `target_status=None`; preview.py
ставит `needs_status=True` и НЕ создаёт строку, пока `decisions.row_overrides
[row].status` не придёт с одним из этих 6 кодов (см. STATUS_CHOICES).
"""
from __future__ import annotations

from typing import Optional

from app.routers.purchase_transitions import STATUS_LABELS

STATUS_CODES = ("plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid")

# [{code, label}] — для выпадающего списка на фронте (contract: POST /preview
# возвращает `statuses`) и для шаблона экспорта (DataValidation).
STATUS_CHOICES = [{"code": c, "label": STATUS_LABELS[c]} for c in STATUS_CODES]

_NEEDS_PAYMENT = {
    "plan_schedule": False,
    "work_in_progress": False,
    "contracted": False,
    "ordered": False,
    "delivered": False,
    "paid": True,
}


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return str(s).strip().lower().replace("ё", "е")


# Нормализованный сырой текст файла → (код из STATUS_CODES, needs_payment
# override|None). override задан ТОЛЬКО там, где «нужен платёж» зависит от
# исходной формулировки, а не от итогового кода — «Заключён» → contracted
# БЕЗ намёка на оплату, но «Оплачено частично» → тоже contracted, а платёж
# при этом ожидается (частичность видна суммой, не отдельным статусом).
_RAW_TO_CODE: dict[str, tuple[str, Optional[bool]]] = {
    "": ("plan_schedule", None),
    "план": ("plan_schedule", None),
    "план закупок": ("plan_schedule", None),
    "в работе": ("work_in_progress", None),
    "ведется работа": ("work_in_progress", None),
    "на стадии заключения договора": ("work_in_progress", None),
    "заключен": ("contracted", None),
    "заключён": ("contracted", None),
    "заключено": ("contracted", None),
    "заключнено": ("contracted", None),  # опечатка в образце владельца
    "заключен договор": ("contracted", None),
    "заключён договор": ("contracted", None),
    "заказано": ("ordered", None),
    "поставлено": ("delivered", None),
    "оплачено частично": ("contracted", True),
    "частично оплачено": ("contracted", True),
    "возмещено": ("paid", None),
    "оплачено": ("paid", None),
}


def resolve_status(status_raw: Optional[str]) -> dict:
    """{target_status: код из STATUS_CODES|None, needs_payment, recognized,
    correction: str|None}.

    target_status=None при recognized=True — это сам код 'plan_schedule'
    («не создавать закупку»), возвращается как None для совместимости со
    старым контрактом preview.py (строка пропускается). correction — текст
    предупреждения, когда сырое значение файла ≠ официальная подпись
    статуса (владелец: «всё приведённое помечено в предпросмотре»); None,
    если файл уже использовал официальную подпись буква-в-букву."""
    norm = _norm(status_raw)
    entry = _RAW_TO_CODE.get(norm)
    if entry is None:
        return {"target_status": None, "needs_payment": False, "recognized": False, "correction": None}
    code, needs_payment_override = entry

    label = STATUS_LABELS[code]
    raw_text = (status_raw or "").strip()
    correction = None
    if raw_text and _norm(raw_text) != _norm(label):
        correction = f'статус приведён: «{raw_text}» → «{label}»'

    target = None if code == "plan_schedule" else code
    needs_payment = needs_payment_override if needs_payment_override is not None else _NEEDS_PAYMENT[code]
    return {
        "target_status": target,
        "needs_payment": needs_payment,
        "recognized": True,
        "correction": correction,
    }


def resolve_status_by_code(code: str) -> dict:
    """Тот же формат ответа, что и resolve_status(), но для явного выбора
    пользователя (decisions.row_overrides[row].status) — без «приведения»,
    пользователь уже выбрал код из STATUS_CHOICES напрямую."""
    if code not in STATUS_CODES:
        return {"target_status": None, "needs_payment": False, "recognized": False, "correction": None}
    target = None if code == "plan_schedule" else code
    return {"target_status": target, "needs_payment": _NEEDS_PAYMENT[code], "recognized": True, "correction": None}


def is_payroll_path(path: list, name: str) -> bool:
    """ФОТ (зарплата, НДФЛ, взносы, командировочные) — исключены по
    умолчанию (decisions.include_payroll включает обратно). Признак —
    ключевые слова уровня «ФОТ/Заработная плата и иные выплаты» в пути или
    имени листовой позиции (владелец, план часть 2)."""
    haystack = " ".join([*(path or []), name or ""]).lower().replace("ё", "е")
    keywords = (
        "заработн", "зарплат", "ндфл", "оплата труда", "страхов",
        "командировоч", "фот",
    )
    return any(k in haystack for k in keywords)
