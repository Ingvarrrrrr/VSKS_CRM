"""Фото товаров — вынесено из products.py (Правило №5, сессия 2026-09-08).

GET /photos/{filename} — легаси-путь, 2 сегмента; не конфликтует по форме с
products.router'ным catch-all GET /{product_id} (1 сегмент), но регистрируется
рядом с остальными products_* соседями ДО products.router для единообразия.
Остальные пути здесь ("/{product_id}/photo", "/download-photos",
"/{product_id}/download-photo") также минимум на сегмент длиннее или не
пересекаются по методу с catch-all — конфликтов по форме нет.
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.schemas import ProductOut
from app.services.product_photo_fetch import (
    REASON_LABELS,
    PhotoFetchError,
    fetch_photo_bytes,
    normalize_url,
)

PRODUCT_UPLOAD_DIR = "/app/uploads/products"
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/photos/{filename}")
async def serve_product_photo_legacy(filename: str):
    """Legacy filesystem endpoint. Phase 17.1-08 moved photos to bytea in DB;
    any surviving files on the volume are still served, but most will 404 now
    (prod volume lost its contents). Frontends should prefer the bytea
    endpoint GET /api/products/{product_id}/photo via `has_photo`.
    """
    filepath = os.path.join(PRODUCT_UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Фото не найдено (хранение перенесено в БД)")
    return FileResponse(filepath)


@router.get("/{product_id}/photo")
async def serve_product_photo_bytea(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the photo bytes stored in products.photo_data.

    Phase 17.1-08 — canonical photo serving path. Returns 404 if the product
    has no cached bytes yet (frontend should fall back to the external
    photo_url in that case).

    No auth dep: <img src> cannot send Authorization headers, and the legacy
    /api/products/photos/{filename} endpoint was already unauthenticated.
    Photo bytes are not sensitive — the product list itself requires auth.
    """
    product = await db.get(Product, product_id)
    if not product or not product.photo_data:
        raise HTTPException(404, "Фото не найдено")
    return Response(
        content=product.photo_data,
        media_type=product.photo_mime or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/{product_id}/photo")
async def delete_product_photo(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Clear the stored photo bytea + metadata + legacy local photo_url.

    Does NOT touch photo_link (the backup external URL the admin maintains
    as source of truth for re-download).
    """
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Товар не найден")
    product.photo_data = None
    product.photo_mime = None
    product.photo_size = None
    if product.photo_url and product.photo_url.startswith('/api/products/photos/'):
        product.photo_url = None
    await db.commit()
    return {"status": "ok", "product_id": product_id}


def _pick_external_url(p: Product) -> Optional[str]:
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


async def _download_and_save_photo(
    product_id: int, url: str, db: AsyncSession
) -> tuple[bool, Optional[str], Optional[str]]:
    """Download external URL and persist bytes to product.photo_data.

    Returns (success, reason_code, message). reason_code is one of
    product_photo_fetch.REASON_LABELS (None on success) — used to group
    failures for the owner in the download-photos response. The existing
    `photo_url` field is NOT cleared — it remains the source of truth for
    re-downloading the photo later.
    """
    import asyncio
    try:
        raw, mime = await asyncio.to_thread(fetch_photo_bytes, url)
    except PhotoFetchError as e:
        return False, e.reason, e.message
    except Exception as e:
        return False, "network_error", str(e)
    product = await db.get(Product, product_id)
    if not product:
        return False, "network_error", "Товар не найден"
    product.photo_data = raw
    product.photo_mime = mime
    product.photo_size = len(raw)
    # Do NOT clear photo_url — external URL stays as source of truth.
    await db.commit()
    return True, None, None


@router.post("/download-photos")
async def download_all_photos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скачать фото для всех активных товаров с внешней ссылкой, ещё не
    закэшированных в БД. Аудит безопасности 2026-09-29: требуем вход, как у
    соседних мутирующих эндпоинтов products.py (update_product и др.).

    Phase 17.1-08: cached copies live in `products.photo_data`. The correct
    guard is therefore "no photo_data yet" — NOT "no local filesystem URL"
    (old `/api/products/photos/*` URLs all point to a now-empty volume).
    """
    result = await db.execute(select(Product).where(Product.is_active == True))
    all_products = result.scalars().all()

    updated, skipped, errors = 0, 0, []
    by_reason: dict[str, int] = {}
    for p in all_products:
        # Already cached in DB → skip (idempotent re-runs are cheap).
        if p.photo_data is not None:
            skipped += 1
            continue
        # Find source URL: prefer photo_url (external), fallback to photo_link.
        # Legacy local `/api/products/photos/...` paths are filtered out by the
        # http(s) prefix check inside _pick_external_url.
        src = _pick_external_url(p)
        if not src:
            skipped += 1
            continue
        ok, reason, err = await _download_and_save_photo(p.id, src, db)
        if ok:
            updated += 1
        else:
            by_reason[reason] = by_reason.get(reason, 0) + 1
            errors.append({
                "id": p.id,
                "name": p.name,
                "error": err,
                "reason": reason,
                "reason_label": REASON_LABELS.get(reason, err),
            })

    errors_by_reason = [
        {"reason": r, "reason_label": REASON_LABELS.get(r, r), "count": c}
        for r, c in sorted(by_reason.items(), key=lambda kv: -kv[1])
    ]
    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "errors_by_reason": errors_by_reason,
    }


@router.post("/{product_id}/download-photo", response_model=ProductOut)
async def download_single_photo(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скачать фото одного товара по его внешней URL-ссылке в БД.
    Аудит безопасности 2026-09-29: требуем вход (как у update_product)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Товар не найден")
    src = _pick_external_url(product)
    if not src:
        raise HTTPException(400, "Нет внешней ссылки для скачивания")
    ok, reason, err = await _download_and_save_photo(product.id, src, db)
    if not ok:
        label = REASON_LABELS.get(reason, err)
        raise HTTPException(500, f"Ошибка скачивания: {label}")
    await db.refresh(product)
    return product


@router.post("/{product_id}/photo", response_model=ProductOut)
async def upload_product_photo(
    product_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузка фото товара пользователем. Phase 17.1-08 — сохраняем в БД
    (bytea), не в файловую систему.
    Аудит безопасности 2026-09-29: требуем вход (как у update_product)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    if file.content_type not in ALLOWED_IMAGE_MIME:
        raise HTTPException(400, f"Недопустимый тип файла: {file.content_type}")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "Файл > 10MB")
    product.photo_data = raw
    product.photo_mime = file.content_type or "image/jpeg"
    product.photo_size = len(raw)
    # photo_url is left untouched — user-uploaded photo doesn't need an
    # external source URL, but any pre-existing one stays as-is.
    await db.commit()
    await db.refresh(product)
    return product
