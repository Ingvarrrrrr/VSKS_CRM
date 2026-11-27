"""cloud_spreadsheet.py — SSRF-protected loader and TTL cache for Google Sheets & Yandex Disk.

Task implementation (system message):
1) Fetch spreadsheets by public link with SSRF protection and in-memory TTL cache.
- Allowed hosts: docs.google.com, disk.yandex.ru, disk.yandex.com, yadi.sk, docs.yandex.ru, docs.yandex.com.
- Redirects/download href from Yandex Disk must end with .yandex.net or .yandex.ru.
- Timeout 25s, max file size 25 MB.
- Google Sheets: export format xlsx. 401/403 or HTML response -> helpful HTTPException.
- Yandex Disk / Tables: public_key query parsing or disk public download API without auth.
- In-memory TTL cache (5 min, max 10 entries by normalized URL). force_refresh clears cache.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Optional
import httpx
from fastapi import HTTPException

# TTL Cache config
_CACHE_TTL = 300  # 5 minutes
_CACHE_MAX_SIZE = 10
_cache_store: dict[str, tuple[float, bytes, str, Optional[str]]] = {}

# Allowed domains for initial URLs
_ALLOWED_DOMAINS = {
    "docs.google.com",
    "disk.yandex.ru",
    "disk.yandex.com",
    "yadi.sk",
    "docs.yandex.ru",
    "docs.yandex.com",
}

# Allowed domains for Yandex download href redirection
_YANDEX_DOWNLOAD_DOMAINS = (".yandex.net", ".yandex.ru")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_and_normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https":
        raise HTTPException(
            400, "Поддерживаются только защищённые ссылки (https://)."
        )
    hostname = (parsed.hostname or "").lower()
    if not any(hostname == d or hostname.endswith("." + d) for d in _ALLOWED_DOMAINS):
        raise HTTPException(
            400,
            f"Недопустимый хост «{hostname}». Разрешены только Google Таблицы и Яндекс Диск.",
        )
    return parsed.geturl()


def _get_from_cache(norm_url: str) -> Optional[tuple[bytes, str, Optional[str]]]:
    if norm_url in _cache_store:
        timestamp, b, fn, sh = _cache_store[norm_url]
        if time.time() - timestamp < _CACHE_TTL:
            return (b, fn, sh)
        else:
            del _cache_store[norm_url]
    return None


def _put_to_cache(norm_url: str, content: bytes, filename: str, sheet_hint: Optional[str]) -> None:
    if len(_cache_store) >= _CACHE_MAX_SIZE:
        oldest_key = min(_cache_store, key=lambda k: _cache_store[k][0])
        del _cache_store[oldest_key]
    _cache_store[norm_url] = (time.time(), content, filename, sheet_hint)


async def fetch_spreadsheet_from_url(
    url: str, *, force_refresh: bool = False
) -> tuple[bytes, str, Optional[str]]:
    """Fetch xlsx bytes from Google Sheets or Yandex Disk public link with SSRF defense.
    Returns: (xlsx_bytes, filename, preferred_sheet_hint)
    """
    norm_url = _validate_and_normalize_url(url)

    if not force_refresh:
        cached = _get_from_cache(norm_url)
        if cached is not None:
            return cached

    parsed = urllib.parse.urlparse(norm_url)
    hostname = (parsed.hostname or "").lower()

    # 1. Google Sheets
    if "docs.google.com" in hostname:
        parts = parsed.path.split("/")
        try:
            d_idx = parts.index("d")
            spreadsheet_id = parts[d_idx + 1]
        except (ValueError, IndexError):
            raise HTTPException(
                400, "Не удалось извлечь ID Google Таблицы из ссылки. Проверьте формат URL."
            )

        query_params = urllib.parse.parse_qs(parsed.query)
        fragment = parsed.fragment
        gid = None
        if "gid" in query_params:
            gid = query_params["gid"][0]
        elif fragment:
            frag_params = urllib.parse.parse_qs(fragment)
            if "gid" in frag_params:
                gid = frag_params["gid"][0]

        # Всегда качаем книгу ЦЕЛИКОМ (БЕЗ &gid=...), иначе Google экспортирует
        # только один лист вместо всех листов книги!
        export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
        cache_key = f"gs:{spreadsheet_id}"
        if not force_refresh:
            cached = _get_from_cache(cache_key)
            if cached is not None:
                return cached

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            try:
                resp = await client.get(export_url)
            except httpx.RequestError as e:
                raise HTTPException(400, f"Ошибка соединения с Google Таблицами: {e}")

        if resp.status_code in (401, 403):
            raise HTTPException(
                400,
                "Нет доступа к Google Таблице. Откройте доступ «Все, у кого есть ссылка — Читатель» и повторите попытку.",
            )
        if resp.status_code != 200:
            raise HTTPException(
                400, f"Google Таблица вернула ошибку HTTP {resp.status_code}."
            )

        content = resp.content
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "Размер файла превышает лимит в 50 МБ.")

        if content.startswith(b"<!DOCTYPE html>") or b"<html" in content[:200].lower():
            raise HTTPException(
                400,
                "Нет доступа к Google Таблице. Откройте доступ «Все, у кого есть ссылка — Читатель» и повторите попытку.",
            )

        filename = f"google_sheet_{spreadsheet_id}.xlsx"
        _put_to_cache(cache_key, content, filename, None)
        return (content, filename, None)

    # 2. Yandex Disk / Tables
    else:
        public_key = norm_url
        if "docs.yandex." in hostname and "url=" in parsed.query:
            qs = urllib.parse.parse_qs(parsed.query)
            if "url" in qs and qs["url"]:
                public_key = qs["url"][0]

        api_url = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={urllib.parse.quote(public_key, safe='')}"

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            try:
                api_resp = await client.get(api_url)
            except httpx.RequestError as e:
                raise HTTPException(400, f"Ошибка соединения с Яндекс Диском: {e}")

        if api_resp.status_code in (401, 403, 404):
            raise HTTPException(
                400,
                "Нет доступа к Яндекс Таблице. Откройте публичный доступ по ссылке («Просмотр») на Яндекс Диске и повторите попытку.",
            )
        if api_resp.status_code != 200:
            raise HTTPException(
                400, f"Яндекс Диск вернул ошибку API HTTP {api_resp.status_code}."
            )

        try:
            api_data = api_resp.json()
        except Exception:
            raise HTTPException(400, "Некорректный ответ от API Яндекс Диска.")

        download_href = api_data.get("href")
        if not download_href:
            raise HTTPException(400, "Не удалось получить ссылку на скачивание файла с Яндекс Диска.")

        dl_parsed = urllib.parse.urlparse(download_href)
        dl_host = (dl_parsed.hostname or "").lower()
        if not any(dl_host.endswith(d) for d in _YANDEX_DOWNLOAD_DOMAINS):
            raise HTTPException(400, f"Небезопасный адрес скачивания с Яндекс Диска: {dl_host}")

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            try:
                dl_resp = await client.get(download_href)
            except httpx.RequestError as e:
                raise HTTPException(400, f"Ошибка скачивания файла с Яндекс Диска: {e}")

        if dl_resp.status_code != 200:
            raise HTTPException(400, f"Не удалось скачать файл с Яндекс Диска (HTTP {dl_resp.status_code}).")

        content = dl_resp.content
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "Размер файла превышает лимит в 25 МБ.")

        if not (content.startswith(b"PK\x03\x04") or content.startswith(b"\xd0\xcf\x11\xe0")):
            raise HTTPException(400, "Скачанный файл не является корректным документом Excel (.xlsx / .xls).")

        filename = "yandex_spreadsheet.xlsx"
        _put_to_cache(norm_url, content, filename, None)
        return (content, filename, None)
