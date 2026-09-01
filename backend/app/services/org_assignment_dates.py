"""Единые правила проставления dept_assigned_at / position_assigned_at.

Владелец (2026-09-01), дословно:
  «Первая дата назначения на должность должна равняться дате принятия на
  работу. А далее уже можно менять. По умолчанию пусть меняется при
  перетягивании человека из отдела в отдел дата назначения, чтобы удобно
  было изменения вносить, а не перебивать каждый раз руками. И
  соответственно можно корректировать руками.»

Правила:
  1. Приём на работу / первая строка user_organizations для пары
     (user_id, org_id) — dept_assigned_at и position_assigned_at равны дате
     приёма (hired_at), а НЕ «сегодня».
  2. Перевод в другой отдел (у пары уже была строка с отделом) —
     dept_assigned_at = переданная дата, иначе сегодня.
  3. Смена должности в существующей записи — если явная дата не передана,
     position_assigned_at = сегодня; если должность не менялась — не
     трогать текущее значение.
  4. Явно переданное значение (с фронта/API) всегда побеждает автоматику.

Собрано в одном месте, чтобы правило не расползалось по роутерам
(departments.py, hierarchy.py, users.py) и не разъезжалось между ними —
см. CLAUDE.md ПРАВИЛО №5 (модульность).
"""
from datetime import date, datetime
from typing import Optional, Union

DateLike = Union[date, datetime, None]


def _as_date(value: DateLike) -> Optional[date]:
    """datetime|date|None → date|None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def first_row_assignment_dates(
    hired_at: DateLike,
    *,
    has_position: bool,
    has_dept: bool,
    explicit_dept_assigned_at: Optional[date] = None,
    explicit_position_assigned_at: Optional[date] = None,
) -> dict:
    """Даты для ПЕРВОЙ-ЕВЕР строки user_organizations пары (user_id, org_id).

    По умолчанию = дате приёма на работу (hired_at). Если hired_at ещё
    неизвестна (не передана явно и колонка получит серверный default
    func.now() при INSERT) — используем date.today() как приближение,
    так как в этот момент строка ещё не вставлена и точное значение
    server_default недоступно; для «сегодня» разницы нет.
    """
    hired_date = _as_date(hired_at) or date.today()
    out: dict = {}
    if has_dept:
        out["dept_assigned_at"] = explicit_dept_assigned_at or hired_date
    if has_position:
        out["position_assigned_at"] = explicit_position_assigned_at or hired_date
    return out


def dept_transfer_date(explicit: Optional[date] = None) -> date:
    """Дата перевода в другой отдел — по умолчанию сегодня, явная побеждает."""
    return explicit or date.today()


def position_change_date(
    *,
    position_changed: bool,
    current: Optional[date],
    explicit: Optional[date] = None,
) -> Optional[date]:
    """Дата смены должности.

    Если должность не менялась — возвращаем текущее значение без изменений
    (руками поправленную дату трогать нельзя просто потому, что PATCH
    переслал ту же должность повторно). Если менялась — явная дата
    побеждает, иначе сегодня.
    """
    if not position_changed:
        return current
    return explicit or date.today()
