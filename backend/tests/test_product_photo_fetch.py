"""Тесты product_photo_fetch (владелец, пункт «С25», 2026-10-07): ссылки
владельца в основном ведут на страницы (маркетплейсы, Я.Диск), не на прямые
файлы картинок — старый urllib с белым списком Content-Type падал на всех
них. Сеть замокана — проверяем разбор og:image, резолв Яндекс Диска/Google
Drive и определение формата по magic bytes, без реальных HTTP-запросов."""
import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.services.product_photo_fetch import (
    PhotoFetchError,
    _detect_magic,
    _extract_og_image,
    _google_drive_download_url,
    _yandex_disk_download_url,
    fetch_photo_bytes,
    normalize_url,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 20
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20


def _mock_response(raw: bytes, content_type: str, final_url: str = "https://example.com/x"):
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.headers = {"Content-Type": content_type}
    resp.geturl.return_value = final_url
    resp.read.return_value = raw
    return resp


class TestNormalizeUrl:
    def test_strips_wrapping_quotes_and_space(self):
        # На проде встречалась ссылка '"https://www.vseinstrumenti.ru/..." ' —
        # кавычки из Excel-экспорта ломали проверку http(s)-префикса.
        assert normalize_url('"https://a.ru/x "') == "https://a.ru/x"

    def test_plain_url_unchanged(self):
        assert normalize_url("https://a.ru/x") == "https://a.ru/x"


class TestMagicBytes:
    @pytest.mark.parametrize("raw,expected", [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
        (b"GIF89a" + b"\x00" * 10, "image/gif"),
        (b"not an image at all", None),
    ])
    def test_detect(self, raw, expected):
        assert _detect_magic(raw) == expected


class TestOgImageExtraction:
    def test_og_image_property_first(self):
        html = '<html><head><meta property="og:image" content="/img/x.jpg"></head></html>'
        assert _extract_og_image(html, "https://shop.ru/p/1") == "https://shop.ru/img/x.jpg"

    def test_twitter_image_fallback(self):
        html = '<html><head><meta name="twitter:image" content="https://cdn.ru/a.png"></head></html>'
        assert _extract_og_image(html, "https://shop.ru/p/1") == "https://cdn.ru/a.png"

    def test_link_image_src_fallback(self):
        html = '<html><head><link rel="image_src" href="/a.jpg"></head></html>'
        assert _extract_og_image(html, "https://shop.ru/p/1") == "https://shop.ru/a.jpg"

    def test_reversed_attribute_order(self):
        html = '<meta content="/b.jpg" property="og:image">'
        assert _extract_og_image(html, "https://shop.ru/p/1") == "https://shop.ru/b.jpg"

    def test_no_image_meta_returns_none(self):
        html = "<html><head><title>Товар</title></head></html>"
        assert _extract_og_image(html, "https://shop.ru/p/1") is None


class TestYandexDiskResolve:
    def test_non_yandex_url_returns_none(self):
        assert _yandex_disk_download_url("https://shop.ru/x") is None

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_resolves_public_key_to_href(self, mock_urlopen):
        resp = _mock_response(b'{"href": "https://downloader.disk.yandex.ru/real/file.jpg"}', "application/json")
        mock_urlopen.return_value = resp
        href = _yandex_disk_download_url("https://disk.yandex.ru/d/abcDEF123")
        assert href == "https://downloader.disk.yandex.ru/real/file.jpg"
        called_url = mock_urlopen.call_args[0][0].full_url
        assert called_url.startswith(
            "https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key="
        )

    def test_yadi_sk_short_link_recognized(self):
        # yadi.sk без API-мока — проверяем только что ветка не отбрасывается
        # как "не яндекс", реальный запрос замокан отдельно выше.
        from app.services.product_photo_fetch import _YANDEX_DISK_RE
        assert _YANDEX_DISK_RE.search("https://yadi.sk/i/abc123")


class TestGoogleDriveResolve:
    def test_file_d_id_form(self):
        url = _google_drive_download_url("https://drive.google.com/file/d/1aBcD3fG/view?usp=sharing")
        assert url == "https://drive.google.com/uc?export=download&id=1aBcD3fG"

    def test_open_id_query_form(self):
        url = _google_drive_download_url("https://drive.google.com/open?id=1aBcD3fG")
        assert url == "https://drive.google.com/uc?export=download&id=1aBcD3fG"

    def test_non_drive_url_returns_none(self):
        assert _google_drive_download_url("https://shop.ru/x") is None


class TestFetchPhotoBytes:
    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_direct_image_url_returns_bytes(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(PNG_BYTES, "image/png")
        raw, mime = fetch_photo_bytes("https://cdn.shop.ru/a.png")
        assert raw == PNG_BYTES
        assert mime == "image/png"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_html_page_with_og_image_follows_through(self, mock_urlopen):
        html = b'<html><head><meta property="og:image" content="https://cdn.shop.ru/real.jpg"></head></html>'
        mock_urlopen.side_effect = [
            _mock_response(html, "text/html", final_url="https://shop.ru/product/1"),
            _mock_response(JPEG_BYTES, "image/jpeg", final_url="https://cdn.shop.ru/real.jpg"),
        ]
        raw, mime = fetch_photo_bytes("https://shop.ru/product/1")
        assert raw == JPEG_BYTES
        assert mime == "image/jpeg"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_html_page_without_og_image_raises_html_no_image(self, mock_urlopen):
        html = "<html><head><title>Товар без картинки</title></head></html>".encode("utf-8")
        mock_urlopen.return_value = _mock_response(html, "text/html")
        with pytest.raises(PhotoFetchError) as exc:
            fetch_photo_bytes("https://shop.ru/product/2")
        assert exc.value.reason == "html_no_image"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_http_403_maps_to_reason(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://shop.ru/x", 403, "Forbidden", {}, io.BytesIO(b"")
        )
        with pytest.raises(PhotoFetchError) as exc:
            fetch_photo_bytes("https://shop.ru/x")
        assert exc.value.reason == "http_403"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_http_404_maps_to_reason(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://shop.ru/x", 404, "Not Found", {}, io.BytesIO(b"")
        )
        with pytest.raises(PhotoFetchError) as exc:
            fetch_photo_bytes("https://shop.ru/x")
        assert exc.value.reason == "http_404"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_timeout_maps_to_reason(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with pytest.raises(PhotoFetchError) as exc:
            fetch_photo_bytes("https://shop.ru/x")
        assert exc.value.reason == "timeout"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_unsupported_format_without_magic_or_known_ct(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"not an image", "application/octet-stream")
        with pytest.raises(PhotoFetchError) as exc:
            fetch_photo_bytes("https://shop.ru/x.bin")
        assert exc.value.reason == "unsupported_format"

    @patch("app.services.product_photo_fetch.urllib.request.urlopen")
    def test_quoted_url_is_normalized_before_fetch(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(PNG_BYTES, "image/png")
        raw, mime = fetch_photo_bytes('"https://cdn.shop.ru/a.png "')
        assert raw == PNG_BYTES
        called_url = mock_urlopen.call_args[0][0].full_url
        assert called_url == "https://cdn.shop.ru/a.png"
