"""Telegram полностью выключен (152-ФЗ, владелец 2026-10-14) — единственный
источник истины settings.TELEGRAM_ENABLED (app/config.py). При False отправка
в Telegram не должна выполняться НИКАКИМ путём, а MAX/push/e-mail должны
продолжать работать как прежде — см. app/notifications.py::notify_user.

Мокаем httpx.AsyncClient.post напрямую (без реальной сети) и проверяем, что
telegram.org никогда не вызывается, а botapi.max.ru — вызывается для
пользователя с обоими привязанными каналами.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app import notifications


class _FakeUserBoth:
    """Пользователь с привязанным и Telegram, и MAX."""
    telegram_id = "999111"
    max_chat_id = "888222"


class _FakeResp:
    status_code = 200

    def json(self):
        return {"result": {"message_id": 1}}


@pytest.mark.asyncio
async def test_send_telegram_noop_when_disabled(monkeypatch):
    """_send_telegram — единственная точка исходящей отправки в
    app/notifications.py — не должна дёргать httpx вовсе, когда выключено."""
    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(notifications, "TELEGRAM_BOT_TOKEN", "fake-token-for-test")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await notifications._send_telegram("123456", "привет")
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_send_telegram_still_noop_even_with_token_and_chat(monkeypatch):
    """Повторная проверка через notify_user (реальный путь вызова из
    роутеров/сервисов) — не только через приватную _send_telegram напрямую."""
    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(notifications, "TELEGRAM_BOT_TOKEN", "fake-token-for-test")
    monkeypatch.setattr(notifications, "MAX_BOT_TOKEN", "")  # MAX не настроен в этом кейсе

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await notifications.notify_user(_FakeUserBoth(), "привет")
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_max_still_sent_when_telegram_disabled(monkeypatch):
    """Ключевая гарантия задания: пользователь с ОБОИМИ привязанными каналами
    при выключенном Telegram получает уведомление через MAX, а не теряет его."""
    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(notifications, "TELEGRAM_BOT_TOKEN", "fake-token-for-test")
    monkeypatch.setattr(notifications, "MAX_BOT_TOKEN", "fake-max-token-for-test")

    called_urls: list[str] = []

    async def _fake_post(self, url, json=None, **kwargs):
        called_urls.append(url)
        return _FakeResp()

    with patch("httpx.AsyncClient.post", new=_fake_post):
        await notifications.notify_user(_FakeUserBoth(), "привет")

    assert not any("telegram.org" in u for u in called_urls), (
        f"Telegram не должен вызываться при TELEGRAM_ENABLED=False, вызваны: {called_urls}"
    )
    assert any("botapi.max.ru" in u for u in called_urls), (
        f"MAX обязан вызваться для пользователя с привязанным max_chat_id, вызваны: {called_urls}"
    )


@pytest.mark.asyncio
async def test_telegram_webhook_endpoint_returns_200_without_processing(monkeypatch):
    """Входящий вебхук Telegram при выключенном флаге — 200 без обработки
    тела запроса (п.3 задания)."""
    from app.routers import telegram_webhook as tw_module

    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", False)

    processed = {"called": False}

    async def _fake_process_update(update):
        processed["called"] = True

    monkeypatch.setattr(tw_module, "_process_update", _fake_process_update)

    class _FakeRequest:
        async def json(self):
            raise AssertionError("тело вебхука не должно читаться, когда Telegram выключен")

    result = await tw_module.telegram_webhook_endpoint(_FakeRequest())
    assert result == {"ok": True}
    assert processed["called"] is False
