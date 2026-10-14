"""«Ближайший регион» — расстояние между столицами субъектов РФ (по прямой,
формула гаверсинуса), для подбора соседнего региона, когда у целевого региона
нет своих точек цены (compute_price_stats, ПРАВИЛО №6: единственная функция
такого ранжирования, второй не заводить).

Источник координат — app/services/ru_regions.REGION_CAPITALS (единственная
копия, см. data/ru_regions.json). Регион без координат (имя не распознано)
просто не попадает в сравнение.
"""
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from app.services.ru_regions import REGION_CAPITALS

_EARTH_RADIUS_KM = 6371.0


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(h))


def nearest_regions(region_name: str, candidates: Iterable[str]) -> list[str]:
    """candidates (имена регионов, где ЕСТЬ данные для расчёта) отсортированные
    по расстоянию столицы candidate до столицы region_name, ближайший первым.
    region_name или элемент candidates без известных координат — пропускается
    (а не кидает исключение — регион мог быть нераспознанным текстом)."""
    origin = REGION_CAPITALS.get(region_name)
    if origin is None:
        return []
    scored = []
    for cand in candidates:
        if cand == region_name:
            continue
        coord = REGION_CAPITALS.get(cand)
        if coord is None:
            continue
        scored.append((_haversine_km(origin, coord), cand))
    scored.sort(key=lambda t: t[0])
    return [name for _, name in scored]
