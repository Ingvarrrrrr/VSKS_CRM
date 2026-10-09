# -*- coding: utf-8 -*-
"""test_set_plan_changed_at_script.py — scripts/set_plan_changed_at.py,
владелец 09.10.2026 (прогон на проде): --at со смещением часового пояса
(«+03:00») падал asyncpg DataError — колонка plan_changed_at TIMESTAMP
WITHOUT TIME ZONE. _to_naive_local должна перевести aware datetime в
наивное локальное время (как у created_at), а наивное — вернуть как есть."""
import datetime as _dt

import pytest

from scripts.set_plan_changed_at import _to_naive_local


def test_naive_datetime_passed_through():
    dt = _dt.datetime(2026, 10, 7, 12, 0, 0)
    assert _to_naive_local(dt) == dt
    assert _to_naive_local(dt).tzinfo is None


def test_tz_aware_datetime_converted_to_naive():
    dt = _dt.datetime(2026, 10, 7, 12, 0, 0, tzinfo=_dt.timezone(_dt.timedelta(hours=3)))
    result = _to_naive_local(dt)
    assert result.tzinfo is None
    # Момент времени сохранён (не просто обрезано смещение) — сравнение через
    # исходный aware объект с локальным tz процесса.
    assert result == dt.astimezone().replace(tzinfo=None)


@pytest.mark.parametrize("offset_hours", [0, -5, 3, 11])
def test_tz_aware_datetime_various_offsets_do_not_raise(offset_hours):
    dt = _dt.datetime(2026, 10, 7, 12, 0, 0, tzinfo=_dt.timezone(_dt.timedelta(hours=offset_hours)))
    result = _to_naive_local(dt)
    assert result.tzinfo is None
