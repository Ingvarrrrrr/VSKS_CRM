"""Единственное место, где фото товара сжимается в финальный формат хранения
(ПРАВИЛО №6). Владелец (26.10.2026): фото каталога — информационные, поэтому
ВСЕГДА хранятся сжатыми: длинная сторона ≤ MAX_SIDE_PX, формат WebP,
качество ~QUALITY, прозрачность на белый фон, EXIF-поворот учтён.

MAX_SIDE_PX=200 (владелец, 29.10.2026, повторное решение: для целей каталога
— опознать товар на глаз в карточке/списке — достаточно 200 px, 400 px
раздувало хранение/трафик без практической пользы). Старые уже сохранённые
фото с стороной >200 px НЕ пересжимаются сами — см.
backend/scripts/recompress_product_photos.py (разовый прогон, НЕ на проде
автоматически).

Без зависимостей от app.* / БД — этот модуль импортируется и внутри Docker
(product_photo_store.py), и локально, вне контейнера, скриптом
scripts/fetch_photos_local.py (там доступны только requests/httpx + Pillow,
никакого доступа к БД). Не плодить вторую копию сжатия — обе стороны вызывают
именно compress_product_photo().
"""
import io
from typing import Optional

MAX_SIDE_PX = 200
WEBP_QUALITY = 75
OUTPUT_MIME = "image/webp"


def compress_product_photo(raw: bytes) -> tuple[bytes, str]:
    """Сжать байты изображения под хранение каталога.

    Возвращает (bytes, mime). Идемпотентно для уже подходящего WebP: если
    входное изображение уже WebP, без альфа-канала и длинная сторона уже
    ≤ MAX_SIDE_PX — перекодирование всё равно происходит (чтобы гарантировать
    единый quality/формат), но результат не хуже исходного по размеру в
    типичных случаях из-за низкого веса метаданных WebP.

    EXIF-поворot учитывается через ImageOps.exif_transpose. Прозрачность
    (RGBA/LA/P с альфа-каналом) — расплющивается на белый фон перед сохранением,
    т.к. итоговый формат/контекст использования (каталог, docx, excel) не
    нуждается в альфа-канале.
    """
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))
    img.load()
    try:
        img = ImageOps.exif_transpose(img) or img
    except Exception:
        pass

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    long_side = max(w, h) or 1
    if long_side > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / long_side
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    return buf.getvalue(), OUTPUT_MIME


def is_already_compressed(raw: bytes, mime: Optional[str]) -> bool:
    """True если байты уже WebP и длинная сторона ≤ MAX_SIDE_PX — повторное
    сжатие не нужно (используется скриптами, которые не должны «портить»
    уже готовые файлы повторным проходом, например import_photos_dir.py)."""
    if (mime or "").split(";")[0].strip().lower() != OUTPUT_MIME:
        return False
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        return max(img.size) <= MAX_SIDE_PX
    except Exception:
        return False
