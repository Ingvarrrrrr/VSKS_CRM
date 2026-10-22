"""Подсказки «Категория»/«Тип товара» по ВСЕМУ каталогу (Правило №5 —
products.py уже 612 строк, сюда не дописывать).

Баг владельца (22.10.2026): в карточке товара, открытой НЕ со страницы
«Товары» (ProductEditorDialog.vue), подсказки строились из ≤20 товаров,
найденных поиском по названию РЕДАКТИРУЕМОГО товара (routers/products.py
GET / с search=<имя>, limit=20) — там обычно только сам товар, подсказывать
нечего. Этот роутер отдаёт DISTINCT category/product_type по всему каталогу
(без per-org фильтра — каталог общий, project_products_catalog_shared,
тот же contract, что и у GET /api/products/), читая ТОЛЬКО нужные колонки
(без загрузки строк Product целиком).

GET /options — ОДИН литеральный сегмент на префиксе /api/products, поэтому,
как и products_summary.py/products_avg_price.py и другие products_*-соседи,
регистрируется в app/routes.py ДО products.router (его GET "/{product_id}"
без явного int-конвертера совпадает по форме с любым односегментным
литералом).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.user import User

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/options")
async def get_product_options(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """{"categories": [...], "types": [...]} — непустые (после strip)
    значения Product.category/Product.product_type по всему каталогу,
    без дублей, отсортированные."""
    categories = (await db.execute(
        select(func.trim(Product.category)).distinct()
        .where(Product.category.isnot(None))
    )).scalars().all()
    types = (await db.execute(
        select(func.trim(Product.product_type)).distinct()
        .where(Product.product_type.isnot(None))
    )).scalars().all()
    return {
        "categories": sorted({c for c in categories if c}),
        "types": sorted({t for t in types if t}),
    }
