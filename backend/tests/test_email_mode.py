"""Выбор режима отправки почты (backend/app/utils/email.py, _effective_email_mode) —
единственное место, где это решается (Правило №6 CLAUDE.md). Три режима: "console" (dev,
в лог), "login" (STARTTLS+пароль, внешний провайдер типа Яндекса), "relay" (свой контейнер
mail/ внутри docker-сети, без логина). Явный settings.EMAIL_MODE побеждает; если он пуст —
старое поведение по наличию SMTP_USER (обратная совместимость с .env без EMAIL_MODE).

Не требует БД — db_session/client fixtures из conftest.py не используются.
"""
import smtplib

import pytest

from app.config import settings
from app.utils import email as email_utils


@pytest.fixture(autouse=True)
def _restore_email_settings():
    """Каждый тест правит settings.* напрямую (не через env) — вернуть исходные значения,
    чтобы тесты не утекали друг в друга и не влияли на остальной набор (settings — общий
    синглтон модуля app.config)."""
    original = {
        "EMAIL_MODE": settings.EMAIL_MODE,
        "SMTP_USER": settings.SMTP_USER,
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_PORT": settings.SMTP_PORT,
        "SMTP_PASSWORD": settings.SMTP_PASSWORD,
        "SMTP_FROM": settings.SMTP_FROM,
    }
    yield
    for key, value in original.items():
        setattr(settings, key, value)


def test_mode_auto_console_when_no_smtp_user():
    settings.EMAIL_MODE = ""
    settings.SMTP_USER = ""
    assert email_utils._effective_email_mode() == "console"


def test_mode_auto_login_when_smtp_user_set():
    settings.EMAIL_MODE = ""
    settings.SMTP_USER = "z@vsks.ru"
    assert email_utils._effective_email_mode() == "login"


def test_mode_explicit_relay_wins_even_without_smtp_user():
    # Режим relay не требует логина — SMTP_USER пуст, но явный флаг главнее автоопределения.
    settings.EMAIL_MODE = "relay"
    settings.SMTP_USER = ""
    assert email_utils._effective_email_mode() == "relay"


def test_mode_explicit_console_wins_even_with_smtp_user_set():
    settings.EMAIL_MODE = "console"
    settings.SMTP_USER = "z@vsks.ru"
    assert email_utils._effective_email_mode() == "console"


def test_mode_explicit_login():
    settings.EMAIL_MODE = "login"
    settings.SMTP_USER = ""
    assert email_utils._effective_email_mode() == "login"


def test_mode_unknown_value_falls_back_to_auto():
    # Опечатка в .env (например "LOGIN " с пробелом не подходит — нормализуем strip/lower,
    # но полная бессмыслица типа "rely" должна падать назад в автоопределение, а не молча
    # выбирать случайный режим).
    settings.EMAIL_MODE = "rely"
    settings.SMTP_USER = "z@vsks.ru"
    assert email_utils._effective_email_mode() == "login"

    settings.SMTP_USER = ""
    assert email_utils._effective_email_mode() == "console"


def test_mode_case_and_whitespace_insensitive():
    settings.EMAIL_MODE = "  RELAY  "
    assert email_utils._effective_email_mode() == "relay"


def test_smtp_send_login_mode_uses_starttls_and_login(monkeypatch):
    settings.EMAIL_MODE = "login"
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_PORT = 587
    settings.SMTP_USER = "user@example.com"
    settings.SMTP_PASSWORD = "secret"
    settings.SMTP_FROM = "user@example.com"

    calls = []

    class FakeServer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append("starttls")

        def login(self, user, password):
            calls.append(("login", user, password))

        def has_extn(self, name):  # pragma: no cover - not expected to be called in login mode
            calls.append(("has_extn", name))
            return True

        def sendmail(self, from_addr, to_addr, msg):
            calls.append(("sendmail", from_addr, to_addr))

    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout=10: FakeServer())

    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    email_utils._smtp_send(msg, "to@example.com")

    assert calls[0] == "starttls"
    assert calls[1] == ("login", "user@example.com", "secret")
    assert calls[2] == ("sendmail", "user@example.com", "to@example.com")


def test_smtp_send_relay_mode_skips_login_and_tries_starttls_if_offered(monkeypatch):
    settings.EMAIL_MODE = "relay"
    settings.SMTP_HOST = "mail"
    settings.SMTP_PORT = 25
    settings.SMTP_USER = ""
    settings.SMTP_PASSWORD = ""
    settings.SMTP_FROM = "noreply@galaa.ru"

    calls = []

    class FakeServer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append("starttls")

        def login(self, user, password):  # pragma: no cover - must not be called in relay mode
            calls.append(("login", user, password))

        def has_extn(self, name):
            calls.append(("has_extn", name))
            return True

        def sendmail(self, from_addr, to_addr, msg):
            calls.append(("sendmail", from_addr, to_addr))

    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout=10: FakeServer())

    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    email_utils._smtp_send(msg, "to@example.com")

    assert ("login", "", "") not in calls
    assert ("has_extn", "starttls") in calls
    assert "starttls" in calls
    assert ("sendmail", "noreply@galaa.ru", "to@example.com") in calls


def test_smtp_send_relay_mode_without_starttls_offer_sends_plain(monkeypatch):
    settings.EMAIL_MODE = "relay"
    settings.SMTP_HOST = "mail"
    settings.SMTP_PORT = 25
    settings.SMTP_FROM = "noreply@galaa.ru"

    calls = []

    class FakeServer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):  # pragma: no cover - must not be called when not offered
            calls.append("starttls")

        def login(self, user, password):  # pragma: no cover
            calls.append(("login", user, password))

        def has_extn(self, name):
            return False

        def sendmail(self, from_addr, to_addr, msg):
            calls.append(("sendmail", from_addr, to_addr))

    monkeypatch.setattr(smtplib, "SMTP", lambda host, port, timeout=10: FakeServer())

    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    email_utils._smtp_send(msg, "to@example.com")

    assert "starttls" not in calls
    assert ("sendmail", "noreply@galaa.ru", "to@example.com") in calls
