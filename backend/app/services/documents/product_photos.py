"""Единственный резолвер фото товара для docx-документов (Правило №6).

Владелец (2026-09-17): «В шаблоне ТЗ должен быть столбец с фотографией
товара — я же не просто так их закачивал в БД». Канонический источник —
`products.photo_data`/`photo_mime` (bytea в БД, Phase 17.1-08), НЕ
`photo_url` (мёртвое поле почти везде — заполнено у 12 из 1445 товаров).

Порядок источников (первый непустой побеждает):
    1. products.photo_data + photo_mime — канонический bytea из БД;
    2. product.photo_url — старые ветки (локальный /api/products/photos/<f>,
       числовой id, внешний http(s)://) как запасные, на случай если
       photo_data почему-то пуст, а photo_url всё-таки указывает на
       что-то живое.

До этой правки резолвер `make_photo_resolver` (ранее только в
stages_template_engine.py) умел ТОЛЬКО photo_url — ветки чтения photo_data
не было вообще, поэтому 780 из 1445 товаров с фото в БД никогда не
попадали в документы. Второй, урезанный резолвер жил в
app/routers/wish_documents.py (`_resolve_local_product_photo`) — удалён,
все вызывающие переведены на этот модуль.

Каждое изображение перед вставкой ужимается Pillow (в requirements.txt,
Pillow>=10.0.0) под разумный размер — иначе документ с несколькими сотнями
позиций весит неподъёмно (пример: закупка #858, 107 позиций с фото,
~10 МБ сырых байт). Если Pillow недоступен/картинка не декодируется —
вставляется как есть (не роняем генерацию), см. `_resize_image_bytes`.
"""
import io
import logging
import os
import tempfile
from typing import Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm as _Cm

logger = logging.getLogger(__name__)

# Легаси-путь локальных фото (файлы на volume, Phase 17.1-08 отправила
# основное хранение в БД, но старые файлы на диске всё ещё могут быть).
UPLOADS_DIR = "/app/uploads/products"

# Целевой размер вставляемой картинки — с запасом под ширину ячейки 2.5 см
# (InlineImage сам масштабирует до width=2.5см, но исходный файл ужимается
# заранее, чтобы .docx не раздувался тяжёлыми оригиналами).
MAX_SIDE_PX = 400
JPEG_QUALITY = 82

_EXT_BY_MIME = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif", "image/bmp": ".bmp", "image/webp": ".webp",
    "image/tiff": ".tiff",
}


def _resize_image_bytes(raw: bytes, mime: Optional[str]) -> tuple[bytes, str]:
    """Ужать изображение под MAX_SIDE_PX по длинной стороне через Pillow.

    Возвращает (bytes, suffix_для_tempfile). При отсутствии Pillow или
    ошибке декодирования — оригинальные байты без изменений (битое фото
    не должно ронять генерацию документа, только логируется)."""
    suffix = _EXT_BY_MIME.get((mime or "").split(";")[0].strip().lower(), ".jpg")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.load()
        w, h = img.size
        long_side = max(w, h) or 1
        if long_side > MAX_SIDE_PX:
            scale = MAX_SIDE_PX / long_side
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue(), ".jpg"
    except Exception as e:
        logger.warning("product photo resize skipped (using original bytes): %s", e)
        return raw, suffix


def get_product_photo_path(
    product,
    uploads_dir: str = UPLOADS_DIR,
    cache: Optional[dict] = None,
) -> Optional[str]:
    """Резолвит объект Product в путь к локальному (временному) файлу фото.

    Единственная точка чтения photo_data/photo_url для документов —
    make_photo_resolver() ниже и стадия ручной сборки таблицы ТЗ
    (stages_contract_tz.py) оба вызывают эту функцию, чтобы не плодить
    вторую копию порядка источников (Правило №6).

    `cache` — опциональный dict {product_id: path_or_None}, чтобы один и
    тот же товар не перекодировался повторно в пределах одной генерации
    документа (у закупки #858 одна фотография может повторяться в
    десятках позиций).
    """
    if product is None:
        return None
    product_id = getattr(product, "id", None)
    if cache is not None and product_id is not None and product_id in cache:
        return cache[product_id]

    local_path: Optional[str] = None

    # 1) Канонический источник — bytea в БД.
    photo_data = getattr(product, "photo_data", None)
    if photo_data:
        try:
            raw, suffix = _resize_image_bytes(photo_data, getattr(product, "photo_mime", None))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.close()
            local_path = tmp.name
        except Exception as e:
            logger.warning("product %s: photo_data -> tempfile failed: %s", product_id, e)
            local_path = None

    # 2) Запасные ветки — photo_url (локальный legacy-путь / числовой id / http).
    if not local_path:
        photo_url = getattr(product, "photo_url", None)
        if photo_url:
            local_path = _resolve_from_photo_url(str(photo_url).strip(), uploads_dir)

    if cache is not None and product_id is not None:
        cache[product_id] = local_path
    return local_path


def _resolve_from_photo_url(url: str, uploads_dir: str) -> Optional[str]:
    if not url:
        return None
    if url.startswith("/api/products/photos/"):
        fname = url.split("/")[-1]
        pth = f"{uploads_dir}/{fname}"
        return pth if os.path.exists(pth) else None
    if url.isdigit():
        for ext in ("jpg", "jpeg", "png"):
            pth = f"{uploads_dir}/product_{url}.{ext}"
            if os.path.exists(pth):
                return pth
        return None
    if url.startswith("http://") or url.startswith("https://"):
        try:
            import urllib.request as _ur
            with _ur.urlopen(url, timeout=5) as r:
                ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                raw = r.read()
            raw, suffix = _resize_image_bytes(raw, ct)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.close()
            return tmp.name
        except Exception as e:
            logger.warning("photo download failed for %s: %s", url, e)
            return None
    return None


def make_photo_resolver(tpl: DocxTemplate, uploads_dir: str = UPLOADS_DIR):
    """Factory: returns resolve_photo(product) -> InlineImage|"" bound to `tpl`.

    Принимает объект Product (не url — см. модуль-докстринг про порядок
    источников). Для обратной совместимости также принимает голую строку
    (тогда работает только запасная ветка photo_url/http/local-file, без
    доступа к photo_data, т.к. строка не несёт bytea).
    """
    cache: dict = {}

    def _resolve_photo(product_or_url):
        if not product_or_url:
            return ""
        if isinstance(product_or_url, str):
            local_path = _resolve_from_photo_url(product_or_url.strip(), uploads_dir)
        else:
            local_path = get_product_photo_path(product_or_url, uploads_dir, cache)

        if not local_path or not os.path.exists(local_path):
            return ""
        try:
            return InlineImage(tpl, local_path, width=_Cm(2.5))
        except Exception as e:
            logger.warning("InlineImage failed for %s: %s", local_path, e)
            return ""

    return _resolve_photo
