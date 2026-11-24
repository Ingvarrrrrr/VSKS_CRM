"""Целевые тесты клиента proverkacheka.com, реэкспортов items_import_parsing
и декодирования многостраничных TIFF / JTIF изображений.
"""
import io
import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

from app.services import proverkacheka_client
from app.services.items_import_parsing import (
    _looks_mojibake,
    _read_excel_rows,
    _smart_import_image_ocr,
    _smart_import_xlsx_direct,
    _try_decode_qr,
    find_upd_code_row,
)
from app.services.receipt_pdf_qr import extract_qr_from_receipt_upload


@pytest.mark.asyncio
async def test_proverkacheka_timeout_returns_non_empty_502(monkeypatch):
    """Пустой ConnectTimeout('') от httpx превращается в понятный 502 (без висящего двоеточия)."""
    monkeypatch.setenv("PROVERKACHEKA_TOKEN", "test_token_123")
    monkeypatch.setattr(proverkacheka_client, "_LAST_REQUEST_TIME", 0.0)

    async def fake_sleep(_sec):
        return None

    monkeypatch.setattr(proverkacheka_client.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectTimeout("")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(HTTPException) as exc_info:
        await proverkacheka_client.fetch_proverkacheka_check("t=20261124T1200&s=100.00&fn=1&i=2&fp=3&n=1")

    assert exc_info.value.status_code == 502
    assert calls["n"] == 2  # 1 основная + 1 повторная попытка
    assert "таймаут" in exc_info.value.detail.lower() or "превышено время ожидания" in exc_info.value.detail.lower()
    assert not exc_info.value.detail.strip().endswith(":")


@pytest.mark.asyncio
async def test_proverkacheka_retries_on_code_4_wait_interval(monkeypatch):
    """При ответе code=4 («Не вышло время ожидания перед повторным запросом») клиент ждёт и успешно повторяет."""
    monkeypatch.setenv("PROVERKACHEKA_TOKEN", "test_token_123")
    monkeypatch.setattr(proverkacheka_client, "_LAST_REQUEST_TIME", 0.0)

    slept: list[float] = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(proverkacheka_client.asyncio, "sleep", fake_sleep)

    responses = [
        {"code": 4, "data": "Не вышло время ожидания перед повторным запросом."},
        {"code": 1, "data": {"json": {"totalSum": 15000, "items": [{"name": "Бумага А4", "price": 15000, "quantity": 1, "sum": 15000}]}}},
    ]

    async def fake_post(self, url, **kwargs):
        body = responses.pop(0)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await proverkacheka_client.fetch_proverkacheka_check("t=20261124T1200&s=150.00&fn=1&i=2&fp=3&n=1")
    assert result["code"] == 1
    assert 2.0 in slept


def test_multipage_jtif_decode_handles_frames_safely():
    """Многостраничный TIFF с расширением .jtif проходит все кадры в _try_decode_qr без утечек и падений."""
    page1 = Image.new("CMYK", (300, 300), (0, 0, 0, 0))
    page2 = Image.new("1", (300, 300), 1)
    buf = io.BytesIO()
    page1.save(buf, format="TIFF", save_all=True, append_images=[page2])
    raw_tiff = buf.getvalue()

    # Без QR возвращает None без исключений на CMYK + 1-bit кадрах
    assert extract_qr_from_receipt_upload("scan_receipt.jtif", raw_tiff) is None
    assert callable(_looks_mojibake)
    assert callable(_read_excel_rows)
    assert callable(_smart_import_image_ocr)
    assert callable(_smart_import_xlsx_direct)
    assert callable(_try_decode_qr)
    assert callable(find_upd_code_row)
