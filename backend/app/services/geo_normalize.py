"""
Geo normalization helpers — фактическая география парка (2026-09).

Распоряжение владельца: география эксплуатации привязана к месту нахождения
машины (Vehicle.location_city), а не к организации-собственнику/эксплуатанту.
location_city приходит из листа владельца свободным текстом
("ДНР г. Донецк", "Курск", "Ростов-на-Дону" и т.п.) — здесь его нормализация
и best-effort метка филиала вынесены отдельно от роутера (Правило №5: модульность,
не размазывать по vehicles_dashboard.py).
"""
from typing import Optional

# Подстрока (lower-case) → метка филиала/группы. Не точное совпадение —
# location_city может содержать префикс региона перед городом ("ДНР г. Донецк").
_REGION_KEYWORDS: dict[str, str] = {
    "днр": "ФПГ ДНР",
    "лнр": "ФПГ ЛНР",
    "запорож": "ФПГ Запорожье",
}

_CITY_KEYWORDS: dict[str, str] = {
    "ростов-на-дону": "филиал РНД, СТО",
    "москва": "филиал ЦУ",
    "луганск": "ФПГ ЛНР",
    "донецк": "ФПГ ДНР",
    "запорожье": "ФПГ Запорожье",
    "иркутск": "ФПГ Иркутск",
}


def normalize_city(raw: Optional[str]) -> str:
    """Trim a free-text location_city value. None/empty → ''."""
    return (raw or "").strip()


def shtab_label_for_city(city: str) -> str:
    """
    Best-effort метка филиала для конкретного места нахождения (для UI-подписи).
    Не блокирует отображение — при отсутствии совпадения возвращает ''
    (тихого фолбэка на организацию нет: непонятная география лучше, чем неверная).
    """
    if not city:
        return ""
    low = city.lower()
    for keyword, label in _REGION_KEYWORDS.items():
        if keyword in low:
            return label
    for keyword, label in _CITY_KEYWORDS.items():
        if keyword in low:
            return label
    return ""
