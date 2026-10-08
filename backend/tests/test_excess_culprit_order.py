# -*- coding: utf-8 -*-
"""test_excess_culprit_order.py — единое правило «кто перешёл лимит и всё,
что добавлено после» (app.services.excess_culprit_order.culprits_after_crossing),
владелец 08.10.2026, план binary-crunching-island.md раздел 1."""
import datetime as _dt
from decimal import Decimal

import pytest

from app.services.excess_culprit_order import culprits_after_crossing


def _row(id_, amount, plan_changed_at):
    return {"id": id_, "amount": amount, "plan_changed_at": plan_changed_at}


def test_single_culprit_over_limit():
    """600 (старая) + 300 + 200 (новая), лимит 1000 → виновник ТОЛЬКО 200,
    сверх 100."""
    rows = [
        _row(1, 600, _dt.datetime(2026, 1, 1, 10, 0, 0)),
        _row(2, 300, _dt.datetime(2026, 1, 2, 10, 0, 0)),
        _row(3, 200, _dt.datetime(2026, 1, 3, 10, 0, 0)),
    ]
    res = culprits_after_crossing(rows, 1000)
    assert res is not None
    assert [c["id"] for c in res.culprits] == [3]
    assert res.total_amount == Decimal("1100")
    assert res.total_excess == Decimal("100")
    assert res.batch_note is None


def test_adding_one_more_culprit_after():
    """Та же схема + ещё одна позиция 50, позже всех — виновники 200 и 50,
    Σ over = 150."""
    rows = [
        _row(1, 600, _dt.datetime(2026, 1, 1, 10, 0, 0)),
        _row(2, 300, _dt.datetime(2026, 1, 2, 10, 0, 0)),
        _row(3, 200, _dt.datetime(2026, 1, 3, 10, 0, 0)),
        _row(4, 50, _dt.datetime(2026, 1, 4, 10, 0, 0)),
    ]
    res = culprits_after_crossing(rows, 1000)
    assert [c["id"] for c in res.culprits] == [3, 4]
    assert res.total_amount == Decimal("1150")
    assert res.total_excess == Decimal("150")
    assert res.batch_note is None


def test_batch_crossing_same_timestamp():
    """3 позиции с ОДНОЙ датой (пачка), пересечение лимита происходит НА
    2-й — виновниками должна быть вся пачка (все 3), не только 2-я и 3-я,
    и batch_note должен сообщить про одну загрузку."""
    same_dt = _dt.datetime(2026, 10, 6, 12, 0, 0)
    rows = [
        _row(1, 400, same_dt),
        _row(2, 400, same_dt),
        _row(3, 400, same_dt),
    ]
    res = culprits_after_crossing(rows, 1000)
    # Пересечение случается на 3-й позиции (400+400+400=1200>1000), но она
    # в одной пачке со 2-й и 1-й (все одинаковое plan_changed_at) — виновники
    # вся пачка.
    assert sorted(c["id"] for c in res.culprits) == [1, 2, 3]
    assert res.batch_note is not None
    assert res.batch_note["count"] == 3
    assert "одной загрузкой" in res.batch_note["message"]
    assert res.total_excess == Decimal("200")


def test_batch_crossing_partial_pack_before_culprit():
    """Пачка из 2 одновременных старых позиций, затем отдельная новая,
    пересекающая границу: 300+300 (одна дата, итог 600, лимит 500 уже
    пересечён второй позицией пачки) → виновники обе позиции пачки."""
    same_dt = _dt.datetime(2026, 5, 1, 9, 0, 0)
    rows = [
        _row(1, 300, same_dt),
        _row(2, 300, same_dt),
    ]
    res = culprits_after_crossing(rows, 500)
    assert sorted(c["id"] for c in res.culprits) == [1, 2]
    assert res.batch_note is not None
    assert res.batch_note["count"] == 2


def test_no_excess_no_culprits():
    rows = [_row(1, 400, _dt.datetime(2026, 1, 1))]
    res = culprits_after_crossing(rows, 1000)
    assert res.culprits == []
    assert res.total_excess == Decimal("600") * -1 or res.total_excess == Decimal("-600")
    assert res.crossing_index is None


def test_empty_rows_returns_none():
    assert culprits_after_crossing([], 1000) is None


def test_none_limit_treated_as_zero():
    """limit=None (ФЭО/бюджет не задан) — любая положительная сумма считается
    превышением с лимитом 0 (вызывающий код сам решает, звать ли функцию при
    limit=None — здесь просто не падаем)."""
    rows = [_row(1, 100, _dt.datetime(2026, 1, 1))]
    res = culprits_after_crossing(rows, None)
    assert [c["id"] for c in res.culprits] == [1]
    assert res.total_excess == Decimal("100")
