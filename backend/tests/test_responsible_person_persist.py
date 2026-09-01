# -*- coding: utf-8 -*-
"""Владелец: «из листа согласования договора почему-то самовольно исчез
ответственный исполнитель, хотя был определён Лягин».

Диагноз: ответственный исполнитель выбирался ТОЛЬКО в диалоге при
формировании документа и уходил разовым query-параметром
?responsible_name= (generate_document, documents.py) — в БД он не сохранялся.
При следующей генерации приоритет уходил на assigned_user/автора служебной
записки, и выбранный ранее человек «терялся».

Решение — три места:
  1) generate_document запоминает непустой ?responsible_name= в
     Purchase.responsible_person через чистую функцию
     _resolve_responsible_person_update (без обращения к БД — тестируется
     офлайн, по образцу _build_approval_purchase_fields в
     test_contract_approval_purchase.py).
  2) responsible_person сделан PATCHABLE (можно сохранить из карточки
     закупки обычным путём); фантомное responsible_person_id (колонки нет)
     убрано из PATCHABLE_FIELDS.
  3) POST /api/contracts/{id}/approval-purchase предзаполняет
     responsible_person = ФИО текущего пользователя у свежесозданной
     рамочной головы (_build_approval_purchase_fields).

Offline, синхронно, без БД/HTTP — см. project_pytest_asyncio_loop_flake
(async-тесты в этом проекте флакуют при параллельном запуске).
"""
from types import SimpleNamespace

from app.routers.documents import _resolve_responsible_person_update, _format_initials
from app.routers.purchases import PATCHABLE_FIELDS


# ---------------------------------------------------------------------------
# _resolve_responsible_person_update — что писать в Purchase.responsible_person
# ---------------------------------------------------------------------------

def test_nonempty_responsible_name_is_written():
    """Непустой ?responsible_name= записывается в p.responsible_person."""
    new_value = _resolve_responsible_person_update(None, "Лягин Андрей Анатольевич")
    assert new_value == "Лягин Андрей Анатольевич"


def test_nonempty_responsible_name_overwrites_different_saved_value():
    new_value = _resolve_responsible_person_update("Администратор", "Лягин Андрей Анатольевич")
    assert new_value == "Лягин Андрей Анатольевич"


def test_empty_param_does_not_erase_saved_value():
    """Пустая строка/None НЕ должны затирать уже сохранённого человека."""
    assert _resolve_responsible_person_update("Лягин Андрей Анатольевич", None) is None
    assert _resolve_responsible_person_update("Лягин Андрей Анатольевич", "") is None
    assert _resolve_responsible_person_update("Лягин Андрей Анатольевич", "   ") is None


def test_unchanged_value_does_not_trigger_write():
    """Значение не изменилось — писать (и коммитить) не нужно."""
    assert _resolve_responsible_person_update("Лягин Андрей Анатольевич", "Лягин Андрей Анатольевич") is None


def test_unchanged_value_flag_on_stub_db_session():
    """Проверка «БД не трогается» флагом — на подставном объекте сессии,
    имитирующем поведение вызывающего кода в generate_document: commit()
    вызывается только когда _resolve_responsible_person_update вернул
    непустое новое значение."""
    class _StubPurchase:
        def __init__(self, responsible_person):
            self.responsible_person = responsible_person

    class _StubSession:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

    def _apply(p, session, responsible_name):
        new_value = _resolve_responsible_person_update(p.responsible_person, responsible_name)
        if new_value is not None:
            p.responsible_person = new_value
            session.commit()

    # Значение совпадает с уже сохранённым — commit НЕ вызывается.
    p = _StubPurchase("Лягин Андрей Анатольевич")
    db = _StubSession()
    _apply(p, db, "Лягин Андрей Анатольевич")
    assert db.committed is False
    assert p.responsible_person == "Лягин Андрей Анатольевич"

    # Параметр пуст — commit НЕ вызывается, сохранённое значение цело.
    p2 = _StubPurchase("Лягин Андрей Анатольевич")
    db2 = _StubSession()
    _apply(p2, db2, None)
    assert db2.committed is False
    assert p2.responsible_person == "Лягин Андрей Анатольевич"

    # Реальное изменение — commit вызывается, значение обновлено.
    p3 = _StubPurchase("Администратор")
    db3 = _StubSession()
    _apply(p3, db3, "Лягин Андрей Анатольевич")
    assert db3.committed is True
    assert p3.responsible_person == "Лягин Андрей Анатольевич"


# ---------------------------------------------------------------------------
# _format_initials — формат ФИО НЕ должен меняться (запрет владельца)
# ---------------------------------------------------------------------------

def test_format_initials_surname_full_name_and_patronymic_as_initials():
    assert _format_initials("Лягин Андрей Анатольевич") == "Лягин А.А."


def test_format_initials_two_word_name():
    assert _format_initials("Лягин Андрей") == "Лягин А."


def test_format_initials_drops_fourth_word():
    assert _format_initials("Кулиев Гасан Валех оглы") == "Кулиев Г.В."


def test_format_initials_empty_input():
    assert _format_initials("") == ""
    assert _format_initials(None) == ""


# ---------------------------------------------------------------------------
# PATCHABLE_FIELDS — поле сохраняемо, фантомное responsible_person_id убрано
# ---------------------------------------------------------------------------

def test_responsible_person_is_patchable():
    assert "responsible_person" in PATCHABLE_FIELDS


def test_phantom_responsible_person_id_removed():
    """responsible_person_id — колонки нет ни в БД, ни в модели Purchase
    (только responsible_person типа String); PATCH молча выбрасывал значение."""
    assert "responsible_person_id" not in PATCHABLE_FIELDS
