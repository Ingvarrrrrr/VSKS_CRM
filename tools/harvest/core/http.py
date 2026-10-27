"""HTTP-клиент для сборщиков каталогов — единственное место, решающее КАК
делать запросы (httpx, если установлен, иначе urllib.request), троттлинг по
домену и backoff при 429/5xx. Модули магазинов (stores/*.py) вызывают только
HttpClient.fetch() / fetch(), сами запросы не формируют (ПРАВИЛО №6)."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - зависит от окружения
    httpx = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

BACKOFF_SECONDS = (30, 60, 120)
MAX_ATTEMPTS = 3
MAX_CONSECUTIVE_FAILURES = 20


class StoreAbortedError(Exception):
    """Подряд (без успеха между ними) накопилось ≥20 отказов по URL для
    одного магазина — сбор этого магазина останавливается."""

    def __init__(self, store: str, stats: "FailureStats"):
        self.store = store
        self.stats = stats
        super().__init__(
            f"{store}: остановлен после {stats.consecutive_failures} подряд "
            f"отказов (всего отказов за прогон: {len(stats.failed_urls)})"
        )


@dataclass
class FailureStats:
    failed_urls: list = field(default_factory=list)  # [(url, reason), ...]
    consecutive_failures: int = 0

    def record_failure(self, url: str, reason: str) -> None:
        self.failed_urls.append((url, reason))
        self.consecutive_failures += 1

    def record_success(self) -> None:
        self.consecutive_failures = 0


def _urllib_get(url: str, headers: dict) -> tuple[Optional[int], Optional[str]]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def _httpx_get(url: str, headers: dict) -> tuple[Optional[int], Optional[str]]:
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        return resp.status_code, resp.text
    except Exception:
        return None, None


def _raw_get(url: str, headers: dict) -> tuple[Optional[int], Optional[str]]:
    if httpx is not None:
        return _httpx_get(url, headers)
    return _urllib_get(url, headers)


class HttpClient:
    """Троттлинг per-domain (не глобальный) + экспоненциальный backoff при
    429/503/5xx (30/60/120 сек, максимум 3 попытки на URL) + журнал отказов
    для текущего магазина."""

    def __init__(
        self,
        store: str,
        pause_per_domain: float = 1.0,
        headers: Optional[dict] = None,
    ):
        self.store = store
        self.pause_per_domain = pause_per_domain
        self.headers = headers or DEFAULT_HEADERS
        self._last_request_at: dict[str, float] = {}
        self.stats = FailureStats()

    def _throttle(self, domain: str) -> None:
        last = self._last_request_at.get(domain)
        if last is not None:
            wait = self.pause_per_domain - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[domain] = time.monotonic()

    def fetch(self, url: str) -> Optional[str]:
        domain = urlparse(url).netloc

        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle(domain)
            status, body = _raw_get(url, self.headers)

            if status is not None and 200 <= status < 300 and body is not None:
                self.stats.record_success()
                return body

            retriable = status is None or status in (429, 503) or (status is not None and status >= 500)
            if retriable and attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue
            break

        self.stats.record_failure(url, f"status={status}")
        if self.stats.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            raise StoreAbortedError(self.store, self.stats)
        return None


def fetch(url: str, headers: Optional[dict] = None) -> Optional[str]:
    """Разовый запрос без троттлинга/backoff — только для единичных скачиваний
    (например, фикстур тестов). Основной сбор идёт через HttpClient.fetch()."""
    status, body = _raw_get(url, headers or DEFAULT_HEADERS)
    if status is not None and 200 <= status < 300:
        return body
    return None
