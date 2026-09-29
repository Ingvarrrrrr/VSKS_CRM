# -*- coding: utf-8 -*-
"""Баг 2026-09-29 (авансовый отчёт РЕЕ-2026-00960, purchase.id=960): PDF-чек
(распечатка письма с QR внутри) раньше сразу уходил в fallback-прикрепление
файлом — ни один код-путь даже не пытался найти в нём QR. Проверяем
app.services.receipt_pdf_qr на реальном PDF, сгенерированном тем же способом,
что и настоящий чек (картинка QR ФНС, вклеенная в PDF-страницу reportlab) —
не на моках, а на настоящем рендере через pdf2image (poppler-utils уже в
образе, никаких новых системных зависимостей — см. докстринг модуля).
"""
import io

import pytest

from app.services.receipt_pdf_qr import (
    extract_qr_from_pdf_bytes,
    extract_qr_from_receipt_upload,
    NO_CLIENT_QR_EXTS,
)

QR_STRING = "t=20260929T1200&s=6510.00&fn=9999078900001234&i=123456&fp=1234567890&n=1"


def _mk_receipt_pdf(qr_string: str = QR_STRING) -> bytes:
    """Реальный PDF (не мок) — картинка QR ФНС, наклеенная на страницу A4,
    ровно как реальный случай (Gmail-распечатка письма с чеком)."""
    import qrcode
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader

    img = qrcode.make(qr_string)
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    c.drawString(50, 800, "Gmail - Чек + (1) подарок. 6 510,00 ₽.")
    c.drawImage(ImageReader(img_buf), 50, 600, width=150, height=150)
    c.showPage()
    c.save()
    return pdf_buf.getvalue()


def test_extract_qr_from_real_pdf_with_embedded_qr_image():
    pdf_bytes = _mk_receipt_pdf()
    qr = extract_qr_from_pdf_bytes(pdf_bytes)
    assert qr == QR_STRING


def test_extract_qr_from_pdf_without_qr_returns_none():
    """PDF без QR (просто текст) — не должен ни бросать, ни находить мусор."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    c.drawString(50, 800, "Обычное письмо без чека и без QR-кода.")
    c.showPage()
    c.save()

    assert extract_qr_from_pdf_bytes(pdf_buf.getvalue()) is None


def test_extract_qr_from_pdf_corrupted_bytes_returns_none_not_raise():
    """Битый/не-PDF файл — деградация, не 500."""
    assert extract_qr_from_pdf_bytes(b"not a real pdf at all") is None


def test_extract_qr_from_pdf_empty_bytes_returns_none():
    assert extract_qr_from_pdf_bytes(b"") is None


def test_dispatcher_routes_pdf_extension_to_pdf_extractor():
    pdf_bytes = _mk_receipt_pdf()
    qr = extract_qr_from_receipt_upload("Gmail - Чек.pdf", pdf_bytes)
    assert qr == QR_STRING


def test_dispatcher_routes_non_pdf_extension_to_direct_decoder():
    """TIFF/HEIC (и любой не-PDF) — напрямую в _try_decode_qr, не в pdf2image.
    Проверяем на PNG (тот же декодер, что уже покрыт для .tif/.heic —
    _try_decode_qr не разбирает по расширению, только по содержимому)."""
    import qrcode

    img = qrcode.make(QR_STRING)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr = extract_qr_from_receipt_upload("chek.tiff", buf.getvalue())
    assert qr == QR_STRING


def test_no_client_qr_exts_matches_frontend_list():
    """Один источник списка форматов «браузер сам не декодирует» — сверка с
    комментарием isServerQrFile в usePurchaseReceipts.ts (текст, не импорт —
    TS и Python не делят модуль, но обе стороны обязаны перечислять одно и то
    же ПРАВИЛО №6 подмножество)."""
    assert set(NO_CLIENT_QR_EXTS) == {".pdf", ".tif", ".tiff", ".heic", ".heif"}
