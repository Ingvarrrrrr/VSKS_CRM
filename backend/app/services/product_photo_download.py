"""Скачивание и сохранение фото ОДНОГО товара по внешней ссылке в БД —
вынесено из routers/products_photos.py (ПРАВИЛО №5, 2026-10-26: нужно то же
ядро в scripts/load_gala_catalog.py --photos, вторую копию не писать,
ПРАВИЛО №6). Поведение не менялось — буквальный перенос
`_pick_external_url`/`_download_and_save_photo`, роутер теперь только
импортирует их отсюда.

Собственно скачивание байт по URL делает app/services/product_photo_fetch.py
(fetch_photo_bytes) — этот модуль только: (1) выбирает, с какого поля товара
брать ссылку (photo_url приоритетнее photo_link), (2) кладёт результат в
product.photo_data/photo_mime/photo_size и коммитит."""
import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.product_photo_fetch import PhotoFetchError, fetch_photo_bytes, normalize_url
from app.services.product_photo_store import save_product_photo


def pick_external_url(p: Product) -> Optional[str]:
    """Return the best external http(s) URL to download from.

    Priority: photo_url (if http/https) → photo_link (if http/https) → None.

    `photo_link` acts as the "backup external link" — admin maintains it as a
    source of truth, while `photo_url` can get overwritten with legacy local
    `/api/products/photos/...` paths or other non-http values. Local paths and
    any non-http values are treated as invalid sources and skipped.

    Values are normalized first (normalize_url strips stray quotes/whitespace
    from pasted/exported links — on prod a value like '"https://...​" ' failed
    this check before trimming и товар считался «без ссылки»).
    """
    def _is_http(v: Optional[str]) -> Optional[str]:
        nv = normalize_url(v) if v else None
        return nv if nv and (nv.startswith("http://") or nv.startswith("https://")) else None
    return _is_http(p.photo_url) or _is_http(p.photo_link)


async def download_and_save_photo(
    product_id: int, url: str, db: AsyncSession
) -> tuple[bool, Optional[str], Optional[str]]:
    """Download external URL and persist bytes to product.photo_data.

    Returns (success, reason_code, message). reason_code is one of
    product_photo_fetch.REASON_LABELS (None on success) — used to group
    failures for the owner in the download-photos response. The existing
    `photo_url` field is NOT cleared — it remains the source of truth for
    re-downloading the photo later.
    """
    try:
        raw, mime = await asyncio.to_thread(fetch_photo_bytes, url)
    except PhotoFetchError as e:
        return False, e.reason, e.message
    except Exception as e:
        return False, "network_error", str(e)
    product = await db.get(Product, product_id)
    if not product:
        return False, "network_error", "Товар не найден"
    await save_product_photo(db, product, raw)
    # Do NOT clear photo_url — external URL stays as source of truth.
    await db.commit()
    return True, None, None
