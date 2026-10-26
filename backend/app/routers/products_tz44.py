"""Предпросмотр ТЗ 44-ФЗ по товару каталога (владелец, 26.10.2026).

Единственный путь: POST /api/products/{product_id}/tz-44fz/preview — НИЧЕГО
не сохраняет, только считает текст через app.services.product_tz_44fz.
build_tz_44fz (ПРАВИЛО №6 — второй генератор не заводим). Сохранение
результата — обычным PUT/PATCH товара на поле description_44fz, тот путь
уже защищён product_catalog_guard (пустое поле может заполнить любой,
перезапись — только с правом) и пишет историю через
product_description_history.set_product_description; здесь второй
механизм записи не нужен.

Доступ — как у чтения карточки товара (GET /{product_id} в products.py):
любой авторизованный, личность только из токена (JWT), 404 на
несуществующий product_id. product_id — int, как у catch-all роутера
products.router (без явного int-конвертера в самом products.router, но
здесь путь на сегмент длиннее — конфликтов по форме нет, регистрируется
рядом с products_avg_price.py/product_description.py в app/routes.py, ДО
products.router, по тому же соглашению, что и остальные products_*
соседи — см. докстринг app/routers/products.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.services.product_tz_44fz import build_tz_44fz
from app.services.product_tz_44fz_brands import collect_catalog_brands

router = APIRouter(prefix="/api/products", tags=["products"])

# Каталожный набор брендов (ревью 26.10.2026, п.1) — кешируется НА ПРОЦЕСС
# (не на запрос): запрос, который заполнил пустой кэш, платит за один
# полный скан products; остальные запросы этого процесса читают готовый
# набор. Инвалидации по TTL нет — обновляется при перезапуске процесса
# (как и остальные process-level справочники в проекте); если бренды
# каталога заметно меняются чаще перезапуска бэкенда, это отдельная задача.
_catalog_brands_cache: frozenset | None = None


async def _get_catalog_brands(db: AsyncSession) -> frozenset:
    global _catalog_brands_cache
    if _catalog_brands_cache is None:
        _catalog_brands_cache = await collect_catalog_brands(db)
    return _catalog_brands_cache


class ProductTz44fzPreviewOut(BaseModel):
    text: str | None
    needs_review: bool


@router.post("/{product_id}/tz-44fz/preview", response_model=ProductTz44fzPreviewOut)
async def preview_tz_44fz(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    brands = await _get_catalog_brands(db)
    text, needs_review = build_tz_44fz(
        name=product.name,
        characteristics=product.characteristics,
        description=product.description,
        manufacturer=product.manufacturer,
        article=product.article,
        brands=brands,
    )
    return ProductTz44fzPreviewOut(text=text, needs_review=needs_review)
