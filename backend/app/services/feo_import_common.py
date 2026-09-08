"""Чистые хелперы разбора ячеек импорта ФЭО — общие для feo_import_apply.py и
feo_import_plan.py (Правило №6: один источник, не дублировать в каждом
файле-этапе). Вынесены из тела `_do_feo_import` (были ~строки 160–202 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики — только сняты с закрытия функции (были вложенными def,
не обращались ни к чему, кроме своих аргументов и импорта normalize_feo_name).
"""
from decimal import Decimal

from app.utils.text import normalize_feo_name

ZERO = Decimal("0")
QUANT = Decimal("0.01")


def get_cell(row, col: int | None) -> str | None:
    if col is None or col < 0:
        return None
    if col >= len(row):
        return None
    v = row[col]
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ('none', 'null'):
        return None
    return s


def to_bool(v: str | None) -> bool:
    if v is None:
        return True
    return v.lower() in ("да", "yes", "true", "1", "+")


def to_dec(v: str | None):
    if not v:
        return None
    s = str(v).strip()
    if not s or s in ('-', '—', '–', 'None', 'null', 'н/д', 'N/A'):
        return None
    s = s.replace(" ", "").replace("\xa0", "").replace(" ", "")
    s = s.replace("₽", "").replace("руб", "").replace("р.", "").replace("р", "")
    s = s.replace(",", ".")
    s = s.rstrip(".")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def fmt(v) -> str:
    """Число с разделителями разрядов для читаемых предупреждений."""
    try:
        return f"{float(v):,.2f}".replace(",", " ")
    except Exception:
        return str(v)


def norm(s: str) -> str:
    """Нормализация имени уровня для сравнения."""
    return normalize_feo_name(s)
