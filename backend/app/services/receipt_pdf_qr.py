"""Извлечение QR-кода фискального чека из PDF-файла (сессия 2026-09-29,
авансовый отчёт РЕЕ-2026-00960, purchase.id=960).

Повод (владелец, дословно): «чек был с QR-кодом, но позиции не загрузились» —
чек загружен как PDF (распечатка письма с чеком, внутри картинка QR), система
не пыталась его распознать вовсе (см. usePurchaseReceipts.ts::onJsonReceiptUpload
до этой правки — PDF сразу уходил в fallback "прикрепить файлом").

ПРАВИЛО №6 (один источник истины) — этот модуль НЕ заводит второй QR-декодер:
  - рендер страниц PDF → PNG делает pdf2image.convert_from_bytes — та же
    библиотека, что уже используется для OCR PDF в app/utils/pdf_ocr.py,
    contracts_import.py, document_to_markdown.py (poppler-utils уже в
    backend/Dockerfile, НИКАКИХ новых системных зависимостей).
  - сам QR-декодер — app.services.items_import_parsing._try_decode_qr
    (pyzbar → cv2.QRCodeDetector fallback), тот же, что уже применяется к
    изображениям (purchase_items_import_smart.py). Здесь только рендерим
    страницы PDF в PNG-байты и прогоняем каждую через этот декодер.

Ничего не пишет в БД и не делает HTTP — чистая функция байты→строка|None,
по образцу receipts_parsing.py (докстринг модуля).
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Владелец (уточнение 2026-09-29): «поиск QR на всех страницах». Рендерим
# ВСЮ страницу целиком (не вытаскиваем embedded-картинку отдельно — отдельный
# экстрактор потребовал бы pymupdf/pikepdf, новую библиотеку, которой сейчас
# нет; полнорастровый рендер страницы и так закрашивает встроенную картинку
# с QR поверх — 300 DPI достаточно, чтобы мелкий QR с распечатки письма
# (реальный случай — Gmail-скрин с чеком) остался читаемым). Верхний предел
# страниц — не «все» буквально (upload лимит 50 МБ, см. purchase_files.py, не
# спасает от PDF с сотнями пустых страниц) — 20 страниц с запасом покрывает
# любой реальный чек/письмо, не давая обработке одного файла подвесить запрос.
_PDF_QR_DPI = 300
_PDF_QR_MAX_PAGES = 20


def extract_qr_from_pdf_bytes(pdf_bytes: bytes) -> str | None:
    """Отрендерить первые страницы PDF в изображения и найти QR-код на любой
    из них (тем же декодером, что и для обычных фото чека). Возвращает
    строку QR (`t=...&s=...&fn=...&i=...&fp=...&n=...`) или None, если QR не
    найден / PDF повреждён / библиотеки рендера недоступны — вызывающий код
    (purchase_receipts_import.py) в этом случае откатывается на обычное
    прикрепление файла, как и раньше."""
    if not pdf_bytes:
        return None

    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.warning("extract_qr_from_pdf_bytes: pdf2image недоступен")
        return None

    try:
        pages = convert_from_bytes(
            pdf_bytes, dpi=_PDF_QR_DPI, first_page=1, last_page=_PDF_QR_MAX_PAGES,
        )
    except Exception as e:
        logger.warning("extract_qr_from_pdf_bytes: convert_from_bytes failed: %s", e)
        return None

    from app.services.items_import_parsing import _try_decode_qr

    for page in pages:
        try:
            buf = io.BytesIO()
            page.save(buf, format="PNG")
            qr = _try_decode_qr(buf.getvalue())
            if qr:
                return qr
        except Exception as e:
            logger.warning("extract_qr_from_pdf_bytes: страница пропущена: %s", e)
            continue
    return None


# Расширения, для которых на фронте (usePurchaseReceipts.ts::onJsonReceiptUpload)
# QR НЕ декодируется в браузере (canvas/createImageBitmap не читает PDF/TIFF/
# HEIC) — единый список тоже на фронте (RECEIPT_FILE_ACCEPT минус png/jpg/webp,
# см. комментарий там). До сессии 2026-09-29 эти форматы сразу прикреплялись
# файлом без единой попытки распознать QR — владелец (уточнение той же сессии):
# «PDF/TIF/HEIC — тоже попробовать распознать, если умеем без новых тяжёлых
# системных зависимостей». TIFF/HEIC уже открываются Pillow (HEIC — через
# pillow-heif, см. _try_decode_qr) — сервер может декодировать их напрямую,
# не рендеря через pdf2image (это только для PDF).
NO_CLIENT_QR_EXTS = (".pdf", ".tif", ".tiff", ".heic", ".heif")


def extract_qr_from_receipt_upload(filename: str, content: bytes) -> str | None:
    """Единая точка входа для нового бэкенд-эндпоинта /receipts/from-file-qr:
    по расширению решает, рендерить ли PDF постранично или пробовать декодер
    напрямую (TIFF/HEIC — и на всякий случай любой другой формат, который
    браузер не смог прочитать сам). Возвращает строку QR или None."""
    if not content:
        return None
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_qr_from_pdf_bytes(content)

    from app.services.items_import_parsing import _try_decode_qr
    return _try_decode_qr(content)
