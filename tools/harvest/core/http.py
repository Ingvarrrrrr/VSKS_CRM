"""HTTP-клиент для сборщиков каталогов — единственное место, решающее КАК
делать запросы (httpx, если установлен, иначе urllib.request), троттлинг по
домену, concurrency и backoff при 429/5xx. Модули магазинов (stores/*.py)
вызывают только HttpClient.fetch()/fetch_many() / fetch(), сами запросы не
формируют (ПРАВИЛО №6).

Concurrency (владелец, 27.10.2026 — "новый сборщик не медленнее старого"):
каждый stores/<store>.py объявляет StoreSpec.concurrency по образцу СТАРОГО
сборщика этого магазина в C:\\Users\\1\\.gemini\\antigravity-ide\\scratch\\
(ThreadPoolExecutor(max_workers=N) там, где он был; иначе concurrency=1 —
старый сборщик был однопоточным). При concurrency>1 поминутный троттлинг по
домену (минимальный зазор между запросами) НЕ применяется — старые
многопоточные сборщики (medtehno/safe/magazin01/ice_age/baucenter/
k_spasatel) троттлили исключительно через max_workers пула, без доп. sleep
между одиночными запросами; добавлять сюда ещё и троттлинг означало бы быть
медленнее эталона. При concurrency==1 троттлинг работает как раньше (это
поведение однопоточных старых сборщиков kuvalda/regard/kns/promalper,
которые держали sleep между запросами)."""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# При первом 429/503 concurrency делится на 2 (минимум 1) и пауза между
# запросами (при concurrency==1) удваивается (максимум 10с) — автоматическое
# снижение темпа (ПРАВИЛО задания п.4). Если RECOVERY_SECONDS прошло без
# НОВЫХ отказов — темп возвращается к исходному (base_concurrency/base_pause).
RECOVERY_SECONDS = 300.0
MAX_BACKOFF_PAUSE = 10.0


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
    """Троттлинг per-domain (не глобальный, только при concurrency==1) +
    параллельные запросы per-domain (concurrency>1) + экспоненциальный
    backoff при 429/503/5xx (30/60/120 сек, максимум 3 попытки на URL) +
    автоснижение темпа при отказах (см. докстринг модуля) + журнал отказов
    для текущего магазина."""

    def __init__(
        self,
        store: str,
        pause_per_domain: float = 1.0,
        concurrency: int = 1,
        headers: Optional[dict] = None,
    ):
        self.store = store
        self.base_pause_per_domain = pause_per_domain
        self.base_concurrency = max(1, concurrency)
        self.pause_per_domain = pause_per_domain
        self.concurrency = self.base_concurrency
        self.headers = headers or DEFAULT_HEADERS
        self._last_request_at: dict[str, float] = {}
        self._last_failure_at: Optional[float] = None
        self._rate_lock = threading.Lock()
        self.stats = FailureStats()

    def _throttle(self, domain: str) -> None:
        # При concurrency>1 троттлинг по минимальному зазору не применяется
        # (см. докстринг модуля) — темп держит max_workers пула.
        if self.concurrency > 1:
            return
        last = self._last_request_at.get(domain)
        if last is not None:
            wait = self.pause_per_domain - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[domain] = time.monotonic()

    def _maybe_recover(self) -> None:
        with self._rate_lock:
            if (
                self._last_failure_at is not None
                and time.monotonic() - self._last_failure_at >= RECOVERY_SECONDS
            ):
                self.concurrency = self.base_concurrency
                self.pause_per_domain = self.base_pause_per_domain
                self._last_failure_at = None

    def _trigger_backoff(self) -> None:
        with self._rate_lock:
            self.concurrency = max(1, self.concurrency // 2)
            self.pause_per_domain = min(self.pause_per_domain * 2, MAX_BACKOFF_PAUSE)
            self._last_failure_at = time.monotonic()

    def fetch(self, url: str) -> Optional[str]:
        self._maybe_recover()
        domain = urlparse(url).netloc
        status = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle(domain)
            status, body = _raw_get(url, self.headers)

            if status is not None and 200 <= status < 300 and body is not None:
                self.stats.record_success()
                return body

            retriable = status is None or status in (429, 503) or (status is not None and status >= 500)
            if status in (429, 503):
                self._trigger_backoff()
            if retriable and attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue
            break

        self.stats.record_failure(url, f"status={status}")
        if self.stats.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            raise StoreAbortedError(self.store, self.stats)
        return None

    def fetch_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        """Параллельно (до self.concurrency потоков, снимок на момент вызова)
        скачивает несколько URL через fetch() — для батча товарных страниц
        одного раздела. StoreAbortedError из любого потока останавливает
        весь батч и пробрасывается наверх (сбор магазина прекращается, как
        при последовательном fetch())."""
        results: dict[str, Optional[str]] = {}
        if not urls:
            return results
        workers = max(1, self.concurrency)
        if workers == 1:
            for u in urls:
                results[u] = self.fetch(u)
            return results

        aborted: Optional[StoreAbortedError] = None
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(self.fetch, u): u for u in urls}
            for fut in as_completed(future_map):
                u = future_map[fut]
                try:
                    results[u] = fut.result()
                except StoreAbortedError as e:
                    aborted = e
                    results[u] = None
        if aborted is not None:
            raise aborted
        return results


def fetch(url: str, headers: Optional[dict] = None) -> Optional[str]:
    """Разовый запрос без троттлинга/backoff — только для единичных скачиваний
    (например, фикстур тестов). Основной сбор идёт через HttpClient.fetch()."""
    status, body = _raw_get(url, headers or DEFAULT_HEADERS)
    if status is not None and 200 <= status < 300:
        return body
    return None
