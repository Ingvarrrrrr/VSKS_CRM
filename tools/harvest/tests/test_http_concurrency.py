"""Тесты core/http.py: fetch_many (concurrency) и автоснижение темпа при
429/503 — без живых запросов, HttpClient._raw_get подменяется моком."""
import time

from tools.harvest.core import http as http_module
from tools.harvest.core.http import HttpClient


def test_fetch_many_single_worker_is_sequential(monkeypatch):
    calls = []

    def fake_raw_get(url, headers):
        calls.append(url)
        return 200, f"body-{url}"

    monkeypatch.setattr(http_module, "_raw_get", fake_raw_get)
    client = HttpClient("test", pause_per_domain=0.0, concurrency=1)
    urls = ["https://x.ru/1", "https://x.ru/2", "https://x.ru/3"]
    results = client.fetch_many(urls)
    assert results == {u: f"body-{u}" for u in urls}
    assert sorted(calls) == sorted(urls)


def test_fetch_many_parallel_fetches_all_urls(monkeypatch):
    def fake_raw_get(url, headers):
        time.sleep(0.01)
        return 200, f"body-{url}"

    monkeypatch.setattr(http_module, "_raw_get", fake_raw_get)
    client = HttpClient("test", pause_per_domain=1.0, concurrency=10)
    urls = [f"https://x.ru/{i}" for i in range(10)]
    started = time.monotonic()
    results = client.fetch_many(urls)
    elapsed = time.monotonic() - started
    assert all(results[u] == f"body-{u}" for u in urls)
    # 10 запросов по 0.01с параллельно должны занять заметно меньше, чем
    # 10 * pause_per_domain(1.0с) последовательно (троттлинг отключён при
    # concurrency>1 — см. docstring HttpClient._throttle).
    assert elapsed < 2.0


def test_throttle_applies_only_when_concurrency_is_one(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    def fake_raw_get(url, headers):
        return 200, "ok"

    monkeypatch.setattr(http_module, "_raw_get", fake_raw_get)

    client = HttpClient("test", pause_per_domain=5.0, concurrency=5)
    client.fetch("https://x.ru/a")
    client.fetch("https://x.ru/b")
    assert sleeps == []  # concurrency>1 — троттлинг по зазору не применяется

    client2 = HttpClient("test", pause_per_domain=5.0, concurrency=1)
    client2._last_request_at["x.ru"] = time.monotonic()
    client2.fetch("https://x.ru/c")
    assert sleeps and sleeps[0] > 0


def test_429_halves_concurrency_and_doubles_pause(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    statuses = iter([429, 429, 429, 200])

    def fake_raw_get(url, headers):
        status = next(statuses)
        return status, ("ok" if status == 200 else None)

    monkeypatch.setattr(http_module, "_raw_get", fake_raw_get)
    client = HttpClient("test", pause_per_domain=1.0, concurrency=8)
    client.fetch("https://x.ru/a")
    assert client.concurrency < 8
    assert client.pause_per_domain > 1.0


def test_recovers_after_recovery_window(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def fake_raw_get(url, headers):
        return 200, "ok"

    monkeypatch.setattr(http_module, "_raw_get", fake_raw_get)
    client = HttpClient("test", pause_per_domain=1.0, concurrency=8)
    client._trigger_backoff()
    assert client.concurrency == 4
    # Подделываем время последнего отказа так, будто RECOVERY_SECONDS прошло.
    client._last_failure_at = time.monotonic() - http_module.RECOVERY_SECONDS - 1
    client.fetch("https://x.ru/a")
    assert client.concurrency == client.base_concurrency == 8
    assert client.pause_per_domain == client.base_pause_per_domain == 1.0
