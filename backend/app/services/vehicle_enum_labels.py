"""
Единый источник Russian-подписи ↔ код для строковых enum-подобных полей ТС
(type, state, fuel_type, pts_kind) — Автоблок «шаблон импорта транспорта».

Используется:
  - app/services/vehicle_import_template.py — построение списков для DataValidation
    на листе «Справочники» шаблона импорта.
  - app/routers/vehicles_import.py          — обратное сопоставление label → code
    при разборе заполненного пользователем файла (см. label_to_code()).

Значения дублируют _EXPORT_TYPE_LABEL / _EXPORT_STATE_LABEL / _EXPORT_PTS_KIND_LABEL
в app/routers/vehicles.py (экспорт). Не объединены в один источник специально —
vehicles.py не тронут по требованию задания (не рисковать работающим экспортом);
при добавлении нового кода/подписи поддерживать оба места синхронно.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

TYPE_LABELS: Dict[str, str] = {
    'car_light': 'Легковой', 'suv': 'Внедорожник', 'pickup': 'Пикап',
    'minivan': 'Минивэн', 'truck_van': 'Фургон', 'truck_board': 'Грузовой',
    'truck_tank': 'Цистерна', 'truck_metal': 'Металловоз', 'bus': 'Автобус',
    'special': 'Спецтехника', 'quadbike': 'Квадроцикл', 'snowmobile': 'Снегоход',
    'boat': 'Лодка', 'boat_motor': 'Лодка (мотор)', 'trailer': 'Прицеп', 'other': 'Другой',
}

STATE_LABELS: Dict[str, str] = {
    'working': 'Рабочее', 'in_repair': 'В ремонте', 'broken': 'Сломан',
    'needs_repair': 'Требует ремонта', 'destroyed': 'Уничтожен', 'utilized': 'Утилизирован',
}

FUEL_TYPE_LABELS: Dict[str, str] = {
    'AI-92': 'АИ-92', 'AI-95': 'АИ-95', 'AI-98': 'АИ-98', 'AI-100': 'АИ-100',
    'DT': 'Дизель', 'GAS': 'Газ', 'other': 'Другое',
}

PTS_KIND_LABELS: Dict[str, str] = {'paper': 'Бумажный', 'electronic': 'Электронный'}


def as_dd_list(labels: Dict[str, str]) -> List[Tuple[str, str]]:
    """(label, code) пары в порядке словаря — для DataValidation / листа «Справочники»."""
    return [(v, k) for k, v in labels.items()]


def label_to_code(labels: Dict[str, str], value: Optional[str]) -> Optional[str]:
    """Регистронезависимо превращает подпись (как в выпадающем списке) в код.

    Если значение не найдено среди известных подписей — возвращает исходную
    строку как есть (валидация Excel не блокирует нестандартный ввод, поэтому
    парсер тоже не должен его отбрасывать — просто сохранит текст пользователя).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    reverse = {label.strip().lower(): code for code, label in labels.items()}
    return reverse.get(s.lower(), s)
