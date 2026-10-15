# -*- coding: utf-8 -*-
"""Юнит-тест для единственного источника initiator_phone/initiator_email
(app/services/documents/initiator_contacts.py, ПРАВИЛО №6).

initiator_phone — User.phone (мобильный, НЕ work_phone).
initiator_email — User.email; если пуст, а username содержит «@» — username
(тот же порядок, что при логине, app/routers/auth.py::login). Иначе "".
user=None → обе пустые.
"""
from types import SimpleNamespace

from app.services.documents.initiator_contacts import initiator_contacts


def _user(**kw):
    base = dict(phone=None, work_phone=None, email=None, username="user")
    base.update(kw)
    return SimpleNamespace(**base)


def test_phone_and_email_present():
    u = _user(phone="+7 900 123-45-67", email="ivanov@example.ru", username="ivanov")
    ctx = initiator_contacts(u)
    assert ctx == {
        "initiator_phone": "+7 900 123-45-67",
        "initiator_email": "ivanov@example.ru",
    }


def test_work_phone_is_not_used():
    u = _user(phone=None, work_phone="+7 495 000-00-00", email="ivanov@example.ru")
    ctx = initiator_contacts(u)
    assert ctx["initiator_phone"] == ""


def test_email_falls_back_to_username_with_at():
    u = _user(phone="+7 900 111-22-33", email=None, username="ivanov@example.ru")
    ctx = initiator_contacts(u)
    assert ctx["initiator_email"] == "ivanov@example.ru"


def test_email_empty_when_username_has_no_at():
    u = _user(phone="+7 900 111-22-33", email=None, username="ivanov")
    ctx = initiator_contacts(u)
    assert ctx["initiator_email"] == ""


def test_user_none_returns_empty_strings():
    ctx = initiator_contacts(None)
    assert ctx == {"initiator_phone": "", "initiator_email": ""}
