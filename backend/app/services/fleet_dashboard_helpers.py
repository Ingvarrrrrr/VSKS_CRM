"""
Общие хелперы дашборда автопарка — видимость (multi-tenancy D-06), дедупликация
ТС и справочники состояний.

ПЕРЕНЕСЕНО (не изменено) из app/routers/vehicles_dashboard.py при разрезании
монолитного роутера (Правило №5/№6, сессия 2026-09-08): эти функции и словари
использовались во ВСЕХ endpoint-группах файла (kpi, drill, all-vehicles-summary,
by-region, filter-counts и т.д.) — единый источник вместо копий в каждом
роутере-соседе (vehicles_dashboard.py / vehicles_dashboard_drill.py /
vehicles_dashboard_summary.py).
"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_

from app.auth.jwt import get_org_filter
from app.models.user import User
from app.models.vehicle import Vehicle


def _current_month_range():
    """Return (first_day, last_day) of the current calendar month."""
    today = date.today()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first, last


def _parse_date(value: Optional[str], fallback: date) -> date:
    """Parse ISO date string; return fallback on any parse error."""
    if not value:
        return fallback
    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return fallback


def _visibility_filter(user: User):
    """
    Returns a SQLAlchemy WHERE clause for Vehicle multi-tenancy (D-06).
    Returns None when user has global visibility (superadmin / account_owner).
    """
    org_ids = get_org_filter(user)
    if org_ids is None:
        return None
    return or_(
        Vehicle.owner_org_id.in_(org_ids),
        Vehicle.assigned_org_id.in_(org_ids),
    )


def _apply_visibility(q, user: User):
    """Apply visibility filter to a query that selects from vehicles."""
    clause = _visibility_filter(user)
    if clause is not None:
        q = q.where(clause)
    return q


def _dedup_key(vin: Optional[str], plate: Optional[str], fallback_id: int) -> str:
    """Phase 29.3-R3 (pt-dedup): нормализованный ключ дедубликации.
    Приоритет: VIN (если есть) → plate (нормализованный) → __id_<n>.
    """
    if vin and vin.strip():
        return ("vin:" + vin.upper().replace(" ", "").strip())
    if plate and plate.strip():
        return ("plate:" + plate.upper().replace(" ", "").strip())
    return f"__id_{fallback_id}"


_STATE_PRIORITY = {
    "broken": 4, "destroyed": 4, "utilized": 4, "needs_repair": 3,
    "in_repair": 3, "working": 1, "unknown": 0, "": 0, None: 0,
}
def _state_rank(s):
    return _STATE_PRIORITY.get(s, 2)


# Color mapping for known VehicleState values (state-donut chart)
_STATE_COLORS = {
    "working": "#22c55e",      # green
    "broken": "#ef4444",       # red
    "in_repair": "#f97316",    # orange
    "needs_repair": "#eab308", # yellow
    "destroyed": "#6b7280",    # gray
    "utilized": "#a855f7",     # purple
}

_STATE_LABELS = {
    "working": "Работает",
    "broken": "Сломан",
    "in_repair": "В ремонте",
    "needs_repair": "Требует ремонта",
    "destroyed": "Уничтожен",
    "utilized": "Утилизирован",
}
