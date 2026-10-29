"""Тонкая обёртка для обратной совместимости существующих импортов
(app/services/roseltorg/items.py: `from .okei import okei_for_unit`).

Справочник и приведение названий единиц измерения живут в
app/services/units_okei.py (ПРАВИЛО №6 — единый источник; раньше здесь был
отдельный, неполный и местами неверный словарь ОКЕИ — разработчик живой
проверкой площадки 29.10.2026 выяснил, что она принимает не то, что было
здесь зашито, см. докстринг units_okei.py)."""
from app.services.units_okei import okei_for_unit as _okei_for_unit


def okei_for_unit(unit_name: str | None) -> str | None:
    """Название единицы измерения позиции → код ОКЕИ, либо None, если
    единица не распознана (не выдумываем код, которого нет)."""
    _canonical, code = _okei_for_unit(unit_name)
    return code
