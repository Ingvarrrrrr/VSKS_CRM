"""Скачивание фото товара по внешней ссылке — отдельный модуль (ПРАВИЛО №5
модульности; раньше вся логика жила внутри routers/products_photos.py).

Повод (владелец, пункт «С25», 2026-10-07): «почему в базе не на все товары
есть картинки, хотя я на все давал ссылки, процентов 95 точно должно быть
скачано». Старая `_fetch_photo_bytes` — простой `urllib.urlopen` с жёстким
белым списком Content-Type: ссылка на СТРАНИЦУ (карточка товара на
маркетплейсе, Яндекс Диск, сайт магазина) отдаёт `text/html` и падала с
«неподдерживаемый формат», хотя картинка на странице есть.

Этот модуль — единственное место, которое знает, как превратить такую
ссылку в байты картинки (ПРАВИЛО №6, один источник): routers/products_photos.py
только вызывает `fetch_photo_bytes()` и группирует `PhotoFetchError.reason`
для ответа владельцу.

Порядок попыток:
  1. Яндекс Диск (disk.yandex.*, yadi.sk) — публичный API получения ссылки
     на скачивание вместо скачивания HTML-страницы просмотра.
  2. Google Drive (drive.google.com/file/d/<id>/... или ?id=<id>) — прямая
     ссылка /uc?export=download&id=<id>.
  3. Обычный GET с браузерным User-Agent (иначе многие магазины отдают 403)
     и следованием редиректам (поведение urllib по умолчанию).
  4. Если итоговый ответ — HTML (страница товара, не картинка): ищем
     <meta property="og:image">, <meta name="twitter:image">,
     <link rel="image_src"> и скачиваем найденную картинку.

Формат картинки определяется по сигнатуре байт (magic bytes), а не только по
Content-Type — сервера часто присылают application/octet-stream или вообще
не присылают заголовок.
"""
from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 15
MAX_BYTES = 10 * 1024 * 1024

SUPPORTED_MIME = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/bmp", "image/tiff", "image/webp",
}

# Человеко-понятные причины отказа — группировка для ответа ручки
# POST /products/download-photos (владелец хочет видеть "почему", не только
# текст исключения).
REASON_LABELS = {
    "html_no_image": "Ссылка открывает страницу, картинку на ней не нашли (нет og:image)",
    "http_403": "Доступ запрещён (403) — ссылка требует авторизации/истекла",
    "http_404": "Страница или файл не найдены (404)",
    "http_error": "Сервер по ссылке ответил ошибкой",
    "timeout": "Сервер не ответил за отведённое время (таймаут)",
    "network_error": "Не удалось соединиться по ссылке",
    "unsupported_format": "По ссылке не картинка (неизвестный формат)",
    "too_large": "Файл больше 10 МБ",
    "no_source": "Нет ссылки на фото",
}


class PhotoFetchError(Exception):
    """reason — машинный код из REASON_LABELS, для группировки в ответе."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _detect_magic(raw: bytes) -> Optional[str]:
    """Формат по сигнатуре байт, не по заявленному Content-Type."""
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    if raw.startswith(b"BM"):
        return "image/bmp"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"II*\x00") or raw.startswith(b"MM\x00*"):
        return "image/tiff"
    return None


def normalize_url(url: str) -> str:
    """Срезать внешние кавычки/пробелы. На проде встречалась ссылка
    '"https://www.vseinstrumenti.ru/...​" ' (кавычки + пробел из экспорта),
    из-за которых проверка http(s)-префикса в роутере её не признавала."""
    u = (url or "").strip()
    if len(u) >= 2 and u[0] in "\"'" and u[-1] in "\"'":
        u = u[1:-1].strip()
    return u


_YANDEX_DISK_RE = re.compile(r"disk\.yandex\.|yadi\.sk")
_GOOGLE_DRIVE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)|[?&]id=([a-zA-Z0-9_-]+)")


def _yandex_disk_download_url(url: str) -> Optional[str]:
    if not _YANDEX_DISK_RE.search(url):
        return None
    api = (
        "https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key="
        + urllib.parse.quote(url, safe="")
    )
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise PhotoFetchError("http_404", "Яндекс Диск: файл по публичной ссылке не найден") from e
        raise PhotoFetchError("http_error", f"Яндекс Диск: HTTP {e.code}") from e
    except Exception as e:
        raise PhotoFetchError("network_error", f"Яндекс Диск: {e}") from e
    href = data.get("href")
    if not href:
        raise PhotoFetchError("http_error", "Яндекс Диск: API не вернул ссылку на файл")
    return href


def _google_drive_download_url(url: str) -> Optional[str]:
    if "drive.google.com" not in url:
        return None
    m = _GOOGLE_DRIVE_ID_RE.search(url)
    if not m:
        return None
    file_id = m.group(1) or m.group(2)
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _resolve_source_url(url: str) -> str:
    return (
        _yandex_disk_download_url(url)
        or _google_drive_download_url(url)
        or url
    )


# og:image / twitter:image могут идти в любом порядке атрибутов внутри <meta>.
_META_IMAGE_RE = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]*\scontent=["']([^"']+)["']""",
    re.IGNORECASE,
)
_META_IMAGE_RE_REV = re.compile(
    r"""<meta[^>]+content=["']([^"']+)["'][^>]*\s(?:property|name)=["'](?:og:image|twitter:image)["']""",
    re.IGNORECASE,
)
_LINK_IMAGE_SRC_RE = re.compile(
    r"""<link[^>]+rel=["']image_src["'][^>]+href=["']([^"']+)["']""",
    re.IGNORECASE,
)


def _extract_og_image(html: str, base_url: str) -> Optional[str]:
    for pattern in (_META_IMAGE_RE, _META_IMAGE_RE_REV, _LINK_IMAGE_SRC_RE):
        m = pattern.search(html)
        if m:
            return urllib.parse.urljoin(base_url, m.group(1))
    return None


def _http_get(url: str) -> tuple[bytes, str, str]:
    """GET с браузерным UA. urllib следует редиректам (301/302/303) сам.

    Returns (raw_bytes, content_type_lower, final_url).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
            ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            final_url = r.geturl()
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise PhotoFetchError("http_403", "Доступ запрещён (403)") from e
        if e.code == 404:
            raise PhotoFetchError("http_404", "Не найдено (404)") from e
        raise PhotoFetchError("http_error", f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", "") or e)
        if "timed out" in reason.lower():
            raise PhotoFetchError("timeout", "Таймаут") from e
        raise PhotoFetchError("network_error", reason) from e
    except TimeoutError as e:
        raise PhotoFetchError("timeout", "Таймаут") from e
    if len(raw) > MAX_BYTES:
        raise PhotoFetchError("too_large", "Файл > 10MB")
    return raw, ct, final_url


def _looks_like_html(ct: str, raw: bytes) -> bool:
    if "html" in ct or "xhtml" in ct:
        return True
    if ct:
        return False
    head = raw[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def fetch_photo_bytes(url: str) -> tuple[bytes, str]:
    """Скачать картинку по внешней ссылке. Блокирующая — вызывать через
    asyncio.to_thread. Возвращает (raw_bytes, mime). Бросает PhotoFetchError.
    """
    url = normalize_url(url)
    source_url = _resolve_source_url(url)
    raw, ct, final_url = _http_get(source_url)

    if _looks_like_html(ct, raw):
        html = raw.decode("utf-8", errors="ignore")
        image_url = _extract_og_image(html, final_url)
        if not image_url:
            raise PhotoFetchError(
                "html_no_image",
                "Ссылка открывает страницу, картинку на ней не нашли (нет og:image/twitter:image)",
            )
        raw, ct, final_url = _http_get(image_url)
        if _looks_like_html(ct, raw):
            raise PhotoFetchError("html_no_image", "og:image снова ведёт на страницу, не на картинку")

    mime = _detect_magic(raw) or (ct if ct in SUPPORTED_MIME else None)
    if not mime:
        raise PhotoFetchError(
            "unsupported_format",
            f"Неподдерживаемый формат (Content-Type={ct or '—'})",
        )

    if "webp" in mime:
        try:
            from PIL import Image as _Img
            img = _Img.open(io.BytesIO(raw)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            raw = buf.getvalue()
            mime = "image/jpeg"
        except Exception:
            mime = "image/webp"

    return raw, mime
