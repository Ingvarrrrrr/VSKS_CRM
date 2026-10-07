"""Нормализация «Правильный статус» → целевой статус закупки (таблица
решений владельца, план breezy-mixing-lovelace.md часть 2)."""
from app.services.historical_fact_import import statuses as statuses_mod


def test_plan_or_empty_not_created():
    for raw in (None, "", "план", "  План  "):
        res = statuses_mod.resolve_status(raw)
        assert res["target_status"] is None
        assert res["recognized"] is True


def test_in_progress():
    res = statuses_mod.resolve_status("В работе")
    assert res["target_status"] == "work_in_progress"
    assert res["needs_payment"] is False


def test_contracted():
    res = statuses_mod.resolve_status("Заключён")
    assert res["target_status"] == "contracted"
    res2 = statuses_mod.resolve_status("заключен")  # без ё
    assert res2["target_status"] == "contracted"


def test_paid_partially():
    res = statuses_mod.resolve_status("Оплачено частично")
    assert res["target_status"] == "contracted"
    assert res["needs_payment"] is True


def test_paid():
    res = statuses_mod.resolve_status("Оплачено")
    assert res["target_status"] == "paid"
    assert res["needs_payment"] is True


def test_unrecognized_status_flagged():
    res = statuses_mod.resolve_status("Непонятно что")
    assert res["recognized"] is False
    assert res["target_status"] is None
