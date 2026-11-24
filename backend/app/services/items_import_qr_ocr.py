"""QR-декодирование (включая многостраничный TIFF/JTIF/JFIF/HEIC) и OCR изображений чеков.

Вынесено из items_import_parsing.py по Правилу №5 (< 500 строк на файл).
Единый декодер _try_decode_qr используется и в smart-импорте позиций, и в
receipt_pdf_qr.py (/receipts/from-file-qr) — Правило №6.
"""
from __future__ import annotations

import io
import re
from fastapi import HTTPException


def _try_decode_qr(image_bytes: bytes) -> str | None:
    """Попытаться декодировать QR-код из изображения (JPG/PNG/WEBP/TIFF/JTIF/JFIF/HEIC).

    1) Открывает все кадры через Pillow ImageSequence (многостраничные .tif/.tiff/.jtif),
       применяет EXIF-ориентацию и приводит цветовые режимы (CMYK, 1, P, I;16) к RGB/L.
    2) Пробует pyzbar на оригинале, уменьшенной копии (2000px), увеличенной (< 900px)
       и автоконтрастной версии (для бледных термочеков).
    3) Fallback на cv2.QRCodeDetector как по сконвертированным кадрам, так и по сырым байтам.
    """
    if not image_bytes:
        return None

    try:
        import pillow_heif as _pillow_heif
        _pillow_heif.register_heif_opener()
    except Exception:
        pass

    from app.utils.pdf_ocr import HEAVY_VISION_SEMAPHORE

    with HEAVY_VISION_SEMAPHORE:
        im_orig = None
        pil_frames: list = []
        extra_images: list = []
        try:
            try:
                from PIL import Image as _PILImage, ImageOps as _ImageOps, ImageSequence as _ImageSequence
                im_orig = _PILImage.open(io.BytesIO(image_bytes))
                for idx, frame in enumerate(_ImageSequence.Iterator(im_orig)):
                    if idx >= 10:
                        break
                    f_img = frame.copy()
                    try:
                        t_img = _ImageOps.exif_transpose(f_img)
                        if t_img is not f_img:
                            f_img.close()
                            f_img = t_img
                    except Exception:
                        pass
                    if f_img.mode not in ("RGB", "RGBA", "L"):
                        conv = f_img.convert("RGB")
                        f_img.close()
                        f_img = conv
                    pil_frames.append(f_img)
            except Exception:
                pass

            # 1) pyzbar по всем кадрам и вариантам масштаба/контраста
            try:
                from pyzbar.pyzbar import decode as _pyzbar_decode
                from PIL import Image as _PILImage, ImageOps as _ImageOps
            except Exception:
                _pyzbar_decode = None

            if _pyzbar_decode is not None:
                for im in pil_frames:
                    variants = [im]
                    if max(im.size) > 2000:
                        thumb = im.copy()
                        thumb.thumbnail((2000, 2000))
                        extra_images.append(thumb)
                        variants.append(thumb)
                    elif max(im.size) < 900:
                        try:
                            zoomed = im.resize(
                                (im.width * 2, im.height * 2),
                                _PILImage.Resampling.LANCZOS,
                            )
                            extra_images.append(zoomed)
                            variants.append(zoomed)
                        except Exception:
                            pass
                    try:
                        gray = _ImageOps.autocontrast(im.convert("L"))
                        extra_images.append(gray)
                        variants.append(gray)
                    except Exception:
                        pass

                    for var_img in variants:
                        try:
                            for d in _pyzbar_decode(var_img):
                                data = d.data
                                if isinstance(data, bytes):
                                    data = data.decode("utf-8", errors="replace")
                                if data:
                                    return data
                        except Exception:
                            pass

            # 2) cv2.QRCodeDetector fallback по сконвертированным кадрам (TIFF/JTIF/HEIC) и сырым байтам
            try:
                import cv2 as _cv2
                import numpy as _np
                detector = _cv2.QRCodeDetector()
                for im in pil_frames:
                    rgb = im if im.mode == "RGB" else im.convert("RGB")
                    try:
                        bgr = _np.array(rgb)[:, :, ::-1].copy()
                        data, _, _ = detector.detectAndDecode(bgr)
                        if data:
                            return data
                    finally:
                        if rgb is not im:
                            rgb.close()

                arr = _np.frombuffer(image_bytes, dtype=_np.uint8)
                img_cv = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
                if img_cv is not None:
                    data, _, _ = detector.detectAndDecode(img_cv)
                    if data:
                        return data
            except Exception:
                pass

            return None
        finally:
            for extra in extra_images:
                try:
                    extra.close()
                except Exception:
                    pass
            for frm in pil_frames:
                try:
                    frm.close()
                except Exception:
                    pass
            if im_orig is not None:
                try:
                    im_orig.close()
                except Exception:
                    pass


def _smart_import_image_ocr(content: bytes, filename: str) -> dict:
    """Stage 1 OCR для изображений: tesseract → regex-парсинг строк чека."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Не удалось открыть изображение: {e}")

    try:
        import pytesseract
        from app.utils.pdf_ocr import HEAVY_VISION_SEMAPHORE
        with HEAVY_VISION_SEMAPHORE:
            ocr_text = pytesseract.image_to_string(img, lang="rus+eng")
    except Exception as e:
        raise HTTPException(
            400,
            f"Ошибка OCR (tesseract установлен?): {e}. "
            "Попробуйте QR-чек ФНС или загрузите Excel/PDF.",
        )
    finally:
        try:
            img.close()
        except Exception:
            pass

    if not ocr_text or not ocr_text.strip():
        raise HTTPException(
            400,
            "На изображении не распознан текст. "
            "Попробуйте QR-чек ФНС или загрузите Excel/PDF с позициями.",
        )

    items = []
    lines = [ln.strip() for ln in ocr_text.splitlines() if ln.strip()]
    price_re = re.compile(
        r"(?P<name>.+?)\s+"
        r"(?:(?P<qty>\d+(?:[.,]\d+)?)\s*(?:шт|кг|л|м|уп|уп\.|ед|ед\.)\s*)?"
        r"(?:x|х|×)?\s*"
        r"(?P<price>\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:руб|₽|р\.?)?",
        re.IGNORECASE | re.UNICODE,
    )
    skip_words = re.compile(
        r"^(итого|total|сумма|кассир|кассa|чек|receipt|дата|дата:|inn|инн|"
        r"тел|телефон|спасибо|магазин|адрес|режим|номер|фн:|фд:|фпд:|"
        r"кку|ккт|ооо|ип |ооо )",
        re.IGNORECASE,
    )

    for line in lines:
        if skip_words.match(line):
            continue
        m = price_re.search(line)
        if not m:
            continue
        name = m.group("name").strip(" -–•·")
        if len(name) < 3:
            continue
        qty_raw = m.group("qty")
        price_raw = m.group("price")
        try:
            price_val = float(price_raw.replace(" ", "").replace(",", "."))
        except Exception:
            price_val = None
        try:
            qty_val = float((qty_raw or "1").replace(",", "."))
        except Exception:
            qty_val = 1.0

        items.append({
            "item_name": name[:500],
            "item_type": "товар",
            "quantity": qty_val,
            "unit": "шт",
            "unit_price": price_val,
            "total_price": round(price_val * qty_val, 2) if price_val else None,
        })

    if not items:
        raise HTTPException(
            400,
            "На изображении текст распознан, но позиции товаров не обнаружены. "
            "Качество OCR для чеков невысокое — рекомендуем использовать QR-код ФНС "
            "(приложение «Проверка чека ФНС России») или загрузить Excel/PDF.",
        )

    return {
        "preview": items,
        "total_rows": len(items),
        "file_type": "image_ocr",
        "columns_found": ["item_name", "quantity", "unit_price", "total_price"],
        "warning": (
            "Распознавание через OCR имеет ограниченную точность. "
            "Рекомендуется проверить позиции перед сохранением. "
            "Для лучшего результата используйте QR-код ФНС на чеке."
        ),
    }
