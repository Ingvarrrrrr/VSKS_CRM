"""Value-coercion helpers for vehicles Excel import — extracted from
app/routers/vehicles_import.py (Правило №5, разрезание 2026-09-08).

Чистые функции "сырое значение ячейки → типизированное значение поля",
без HTTP/DB. Используются app/services/fleet_import_parser.py.
"""
from datetime import datetime
from typing import Any, Optional, Tuple

from app.services.vehicle_enum_labels import (
    FUEL_TYPE_LABELS,
    TYPE_LABELS,
    label_to_code,
    resolve_vehicle_state,
)
from app.services.fleet_import_columns import _MAX_LEN

def _coerce_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("1", "да", "yes", "true", "+", "есть", "имеется", "имеются", "исправно", "имеются в наличии"):
        return True
    if s in ("0", "нет", "no", "false", "-", "отсутствует", "отсуствует", "неисправно"):  # "отсуствует" — опечатка исходника
        return False
    return None


def _coerce_repair_required(val: Any) -> Optional[bool]:
    """Требуется ремонт: реальные данные — не "да/нет", а текст описания
    неисправности ("Необходим кузовной ремонт" и т.п.). Presence-эвристика:
    известное да/нет-слово имеет приоритет, иначе непустой текст = True."""
    if val is None:
        return None
    known = _coerce_bool(val)
    if known is not None:
        return known
    return bool(str(val).strip())


def _coerce_pts_kind(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s.startswith("бумаж"):
        return "paper"
    if s.startswith("электрон"):
        return "electronic"
    return None


# Обратное сопоставление подпись→код для полей типа/топлива (Автоблок:
# «шаблон импорта транспорта»). Раньше эти поля попадали в общий "else"-текстовый
# путь и сохранялись как есть — если бы пользователь выбрал русскую подпись из
# выпадающего списка шаблона ("Легковой"), в БД лёг бы сырой текст вместо кода
# ("car_light"), которого ждут фильтры/экспорт (_EXPORT_TYPE_LABEL и т.п. в
# vehicles.py). label_to_code регистронезависим и не блокирует нестандартный
# ввод — если подпись не распознана, возвращает исходный текст как есть.
#
# "state" сюда НЕ входит — у него отдельная, более строгая коэрсия
# (см. _coerce_state_value / resolve_vehicle_state в vehicle_enum_labels.py):
# в отличие от type/fuel_type, для state сырой нераспознанный текст никогда
# не должен попадать в колонку (Lesson 2026-08-31: "В надлежайщем состоя" —
# обрезанный по VARCHAR(20) сырой текст с опечаткой исходника, не совпадающий
# ни с одним кодом; карточка ТС показывала «Неизвестно», фильтр не находил).
_ENUM_LABEL_FIELDS = {
    "type": TYPE_LABELS,
    "fuel_type": FUEL_TYPE_LABELS,
}


def _coerce_enum_label(field: str, val: Any) -> Optional[str]:
    labels = _ENUM_LABEL_FIELDS[field]
    coerced = label_to_code(labels, val)
    max_len = _MAX_LEN.get(field)
    if coerced and max_len:
        coerced = coerced[:max_len]
    return coerced


def _coerce_state_value(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """Состояние ТС: НИКОГДА не пишет сырой текст в state (в отличие от
    _coerce_enum_label выше) — только один из 6 кодов STATE_LABELS либо None.
    Возвращает (код, заметка_для_tech_condition_info | None); заметка
    непустая, если текст не распознан целиком, либо содержит доп. сведения
    в скобках (место, а не состояние) — см. resolve_vehicle_state()."""
    return resolve_vehicle_state(val)


def _coerce_date(val: Any) -> Optional[str]:
    """Return ISO date string or None."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None



def _split_brand_model(val: str) -> tuple[Optional[str], Optional[str]]:
    """«CFMOTO CFORCE 600 EPS» → ('CFMOTO', 'CFORCE 600 EPS') — по первому пробелу (§6)."""
    s = val.strip()
    if not s:
        return None, None
    parts = s.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]



