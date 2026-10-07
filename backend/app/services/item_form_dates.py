"""Проверка дат у позиций со спец-формой «Перевозки»/«Авиабилеты»/«Железно-
дорожные билеты» (владелец, п. С4, 30.09.2026, дословно: «форма договора
перевозка автобусом позволяет сделать так, что дата отправления позже даты
окончания. Так быть не может»).

ЕДИНСТВЕННАЯ функция проверки (Правило №6) — вызывается из
app.services.item_amounts.apply_item_amounts, то есть автоматически на КАЖДОМ
сохранении позиции закупки (purchases.py/purchase_items_edit.py/
purchase_create_core.py) и заявки (wishes.py/wish_distribution.py), второй
копии проверки по отдельным роутерам не заводим.

Формат extra_attrs:
  - transport: depart_at/finish_at — datetime-local строки ("2026-10-12T08:00")
    либо datetime; лексикографическое сравнение ISO-строк совпадает с
    хронологическим (тот же формат, не нужен парсинг).
  - flight/train: date_to/date_back — date-строки ("2026-10-12"); date_back
    необязательна (поездка в одну сторону).

Пустая/отсутствующая дата ОБЕИХ сторон сравнения — проверка пропускается
(нечего сравнивать, обычная позиция без дат не должна падать)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException


def _extra(item: Any) -> dict:
    extra = getattr(item, "extra_attrs", None)
    return extra if isinstance(extra, dict) else {}


def _str_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()


def validate_item_form_dates(item: Any, item_form: Optional[str]) -> None:
    """422, если даты позиции противоречат друг другу. No-op для всех форм,
    кроме transport/flight/train, и для форм без обеих дат заполненными."""
    if item_form not in ("transport", "flight", "train"):
        return
    extra = _extra(item)
    if item_form == "transport":
        depart = _str_date(extra.get("depart_at"))
        finish = _str_date(extra.get("finish_at"))
        if depart and finish and depart > finish:
            raise HTTPException(
                422,
                "Дата отправления не может быть позже даты окончания — "
                f"отправление «{depart}» позже окончания «{finish}».",
            )
        return
    # flight / train
    date_to = _str_date(extra.get("date_to"))
    date_back = _str_date(extra.get("date_back"))
    if date_to and date_back and date_back < date_to:
        raise HTTPException(
            422,
            "Дата обратного рейса не может быть раньше даты туда — "
            f"обратно «{date_back}» раньше туда «{date_to}».",
        )
