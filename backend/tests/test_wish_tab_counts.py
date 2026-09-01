"""Тест на накопительные множества статусов вкладок «Заявки на закупку».

Жалоба владельца (сессия 2026-09-01): вкладка «Все заявки» показывала меньше
записей, чем «Конвертированные» — GET /wishes/ без ``status`` по умолчанию
вырезает converted (так задумано для других потребителей эндпоинта), а фронт
использовал этот путь и для фильтра «Все» на вкладке заявок.

Решение — накопительная цепочка: каждая вкладка включает всё, что когда-либо
прошло через это состояние. Тест — чистая функция ``wish_tab_statuses``
(``app/services/wish_tabs.py``), без БД и без FastAPI — подставные объекты
не нужны вовсе, проверяем сами множества.
"""
from app.services.wish_tabs import WISH_TAB_STATUS_SETS, wish_tab_statuses

ALL_STATUSES = {"draft", "submitted", "approved", "rejected", "converted"}


def test_all_includes_draft_and_converted():
    s = wish_tab_statuses("all")
    assert "draft" in s
    assert "converted" in s
    assert s == ALL_STATUSES


def test_submitted_includes_downstream_but_not_draft():
    s = wish_tab_statuses("submitted")
    assert "approved" in s
    assert "rejected" in s
    assert "converted" in s
    assert "draft" not in s


def test_approved_includes_converted():
    s = wish_tab_statuses("approved")
    assert "converted" in s
    assert "draft" not in s
    assert "submitted" not in s
    assert "rejected" not in s


def test_rejected_does_not_include_converted():
    s = wish_tab_statuses("rejected")
    assert s == {"rejected"}
    assert "converted" not in s


def test_draft_is_exact():
    assert wish_tab_statuses("draft") == {"draft"}


def test_converted_is_exact():
    assert wish_tab_statuses("converted") == {"converted"}


def test_all_is_superset_of_every_other_tab():
    all_set = wish_tab_statuses("all")
    for tab, statuses in WISH_TAB_STATUS_SETS.items():
        assert statuses <= all_set, f"'all' must be a superset of '{tab}'"


def test_unknown_tab_falls_back_to_all():
    # Безопасный дефолт: неизвестное имя вкладки не прячет записи молча.
    assert wish_tab_statuses("__nonexistent__") == ALL_STATUSES
