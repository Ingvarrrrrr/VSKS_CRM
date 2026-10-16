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


def status_code_from_raw(status_raw: Optional[str]) -> Optional[str]:
    """Сырой текст ячейки «Правильный статус» -> код из STATUS_CODES, либо
    None, если значение не распознано (или пусто). Единственное место,
    знающее сопоставление сырого текста файла коду (Правило №6) — и
    `resolve_status` ниже, и счётчик `fact_rows` шаблона ФЭО (см.
    app/services/feo_import_fact_summary.py) читают код ТОЛЬКО отсюда, не
    заводят свой разбор _RAW_TO_CODE по месту."""
    entry = _RAW_TO_CODE.get(_norm(status_raw))
    return entry[0] if entry is not None else None


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


# Лист GoodsService владельца (16.10.2026) — колонка «Товар заказан» несёт,
# помимо Да/Нет, два особых текста владельца, которые НЕ означают закупку:
_ORDERED_NOT_A_PURCHASE = {"скорее всего поставка потребуется", "непредвиденные расходы"}
_ORDERED_YES = {"да", "yes", "true", "1"}


def status_code_from_stage_flags(
    *, purchase_done: bool, contracted: bool, ordered_raw: Optional[str],
    delivered: bool, paid: bool,
) -> Optional[str]:
    """Статус из НЕСКОЛЬКИХ колонок Да/Нет (лист GoodsService владельца,
    16.10.2026) вместо одной «Статус»/«Правильный статус» — та же лестница
    6 кодов GALA, решает старшая заполненная стадия: Оплачено → paid;
    Товар поставлен → delivered; Товар заказан=«Да» → ordered; Договор
    заключён (или «Товар заказан» = «Еще не поставлено, но будет.
    Ежемесячная услуга» — это тоже контракт, владелец) → contracted; Закупка
    проведена → work_in_progress; иначе None (plan_schedule — закупку не
    создавать). «Товар заказан» = «Скорее всего поставка потребуется» /
    «Непредвиденные расходы» — это запланированные расходы владельца, НЕ
    закупка, побеждает любые другие стадии (решение владельца)."""
    ordered_norm = " ".join(str(ordered_raw).strip().lower().split()) if ordered_raw else ""
    if ordered_norm in _ORDERED_NOT_A_PURCHASE:
        return None
    if paid:
        return "paid"
    if delivered:
        return "delivered"
    if ordered_norm in _ORDERED_YES:
        return "ordered"
    if contracted or ordered_norm.startswith("еще не поставлено") or ordered_norm.startswith("ещё не поставлено"):
        return "contracted"
    if purchase_done:
        return "work_in_progress"
    return None


def status_label_from_stage_flags(
    *, purchase_done: bool, contracted: bool, ordered_raw: Optional[str],
    delivered: bool, paid: bool,
) -> str:
    """Та же лестница, что и status_code_from_stage_flags(), но возвращает
    официальную подпись (STATUS_LABELS) — чтобы rows.py положил её в
    status_raw и дальше статус разбирал ОДИН источник истины
    (statuses.resolve_status), не второй механизм (ПРАВИЛО №6)."""
    code = status_code_from_stage_flags(
        purchase_done=purchase_done, contracted=contracted, ordered_raw=ordered_raw,
        delivered=delivered, paid=paid,
    )
    return STATUS_LABELS[code or "plan_schedule"]


def resolve_status_by_code(code: str) -> dict:
    """Тот же формат ответа, что и resolve_status(), но для явного выбора
    пользователя (decisions.row_overrides[row].status) — без «приведения»,
    пользователь уже выбрал код из STATUS_CHOICES напрямую."""
    if code not in STATUS_CODES:
        return {"target_status": None, "needs_payment": False, "recognized": False, "correction": None}
    target = None if code == "plan_schedule" else code
    return {"target_status": target, "needs_payment": _NEEDS_PAYMENT[code], "recognized": True, "correction": None}
