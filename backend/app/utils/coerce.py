"""PATCH-body coercion helper shared across routers (Правило №6 — один источник истины).

Извлечено из purchases.py / vehicles.py / vehicle_repairs.py / external_drivers.py —
тела были идентичны с точностью до имени набора полей (_DATE_FIELDS/_DATETIME_FIELDS).
Наборы полей остаются в своих модулях; сюда передаются параметрами.
"""
from datetime import date, datetime


def coerce_patch_value(field: str, value, *, date_fields: set, datetime_fields: set):
    """Конвертирует ISO-строку в date/datetime для DATE/DATETIME-полей; пустые строки → None."""
    if value == "":
        return None
    if value is None:
        return None
    if field in date_fields and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    if field in datetime_fields and isinstance(value, str):
        try:
            # Поддержка и 'YYYY-MM-DD', и 'YYYY-MM-DDTHH:MM[:SS]'
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return date.fromisoformat(value[:10])
            except Exception:
                return None
    return value
