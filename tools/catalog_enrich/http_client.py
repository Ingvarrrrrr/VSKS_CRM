"""Вежливый HTTP-клиент для дособора данных со страниц товаров магазинов:
1 запрос в секунду НА МАГАЗИН (не глобально — kuvalda и regard гоняются двумя
параллельными процессами, лимит у каждого свой), экспоненциальный backoff на
429/503 (30с, 60с, 120с), User-Agent браузера. stdlib-only (urllib), чтобы не
зависеть от наличия httpx в окружении.
"""
import gzip
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BACKOFF_SECONDS = (30, 60, 120)


@dataclass
class FetchResult:
    ok: bool
    status: Optional[int]
    html: Optional[str]
    error: Optional[str]
    attempts_used: int


class PoliteFetcher:
    """Один экземпляр на процесс = один магазин. min_interval — минимальный
    зазор между НАЧАЛАМИ запросов (секунды), держит ~1 запрос/сек."""

    def __init__(self, min_interval: float = 1.0, timeout: float = 20.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_request_ts: float = 0.0
        self.consecutive_failures = 0

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    def _do_request(self, url: str) -> tuple[int, str]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = resp.status
            raw = resp.read()
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding == "gzip":
                raw = gzip.decompress(raw)
            elif encoding == "deflate":
                raw = zlib.decompress(raw)
            charset = "utf-8"
            ctype = resp.headers.get("Content-Type", "")
            if "charset=" in ctype:
                charset = ctype.split("charset=")[-1].strip()
            try:
                html = raw.decode(charset, errors="replace")
            except LookupError:
                html = raw.decode("utf-8", errors="replace")
            return status, html

    def fetch(self, url: str) -> FetchResult:
        """3 попытки: 429/503 → пауза по BACKOFF_SECONDS и повтор; другие
        ошибки сети тоже дают ещё попытку с той же паузой. После 3 неудач —
        возвращает ok=False, вызывающий код пишет строку в журнал пропусков."""
        last_error = None
        last_status = None
        for attempt in range(1, len(BACKOFF_SECONDS) + 2):
            self._throttle()
            try:
                status, html = self._do_request(url)
                if status == 200:
                    self.consecutive_failures = 0
                    return FetchResult(True, status, html, None, attempt)
                last_status = status
                last_error = f"HTTP {status}"
            except urllib.error.HTTPError as e:
                last_status = e.code
                last_error = f"HTTPError {e.code}"
            except Exception as e:  # noqa: BLE001 — сетевые ошибки разнородны
                last_error = f"{type(e).__name__}: {e}"

            self.consecutive_failures += 1
            if attempt <= len(BACKOFF_SECONDS):
                time.sleep(BACKOFF_SECONDS[attempt - 1])
            else:
                break
        return FetchResult(False, last_status, None, last_error, len(BACKOFF_SECONDS) + 1)
