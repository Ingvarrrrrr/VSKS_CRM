"""Доска закупок заявки для канбана — задача D (владелец, лист 2 №2/№3 вокруг
задач A-C, 2026-09-20): UI, показывающий ВСЕ закупки, на которые распределена
заявка (после Задачи A/C можно править состав/переносить позиции между ними),
единым списком колонок канбана.

GET /api/wishes/{wish_id}/purchases-board — подключён под-роутером в конце
app/routers/wish_items.py (`wish_items.router.include_router(router)`), тот же
приём, что wish_distribution_reset.py в этом же файле-хосте: ЭТОТ router БЕЗ
собственного prefix — путь складывается из префикса родителя ("/api/wishes")
+ полного пути декоратора ниже (include_router применяет self.prefix
родителя ПОВТОРНО — задавать здесь prefix="/api/wishes" тоже нельзя, см.
докстринг wish_distribution_reset.py).

Форма позиции согласована с тем, что уже отдаёт PurchaseSplitKanban.vue
(frontend/src/composables/purchase/usePurchaseSplit.ts:47-65) — тот же набор
полей (id/item_name/quantity/unit/total_price/product_id/_product_category),
плюс unit_price/feo_planned_item_id (нужны новому UI задач A-C, но не ломают
существующий канбан разбивки — он их просто не читает). `_product_category`
считается ТЕМ ЖЕ способом, что фронт считал сам (product_id → каталог,
иначе точное совпадение по имени, product.category) — раньше эту работу
проделывал frontend (два похода: GET /purchases/{id} + GET /products/?limit=10000),
здесь — один backend-запрос с уже присоединённым Product.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

router = APIRouter(tags=["wishes"])


@router.get("/{wish_id}/purchases-board")
async def get_wish_purchases_board(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.routers.wishes import _load_wish
    from app.routers.purchases import TZ_FROZEN_STATUSES
    from app.services.dictionaries import STATUS_LABELS as _STATUS_LABELS
    from app.services.product_catalog_match import normalize_product_name, find_products_by_normalized_names

    wish = await _load_wish(wish_id, db)

    purchases_res = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.wish_id == wish_id)
        .order_by(Purchase.id)
    )
    purchases = purchases_res.scalars().all()

    # Позиции без product_id/product.category — точное совпадение по имени
    # (normalize_product_name, тот же источник, что и wish_distribution.py::
    # backfill_wish_items_product_ids — Правило №6), а не второй заход в
    # каталог с иной нормализацией.
    _missing_names: set[str] = set()
    for p in purchases:
        for it in (p.items or []):
            if not (it.product_id and it.product and it.product.category) and (it.item_name or "").strip():
                _missing_names.add(it.item_name.strip())
    name_to_product: dict = {}
    if _missing_names:
        name_to_product = await find_products_by_normalized_names(db, _missing_names)

    def _category_of(it: PurchaseItem):
        if it.product_id and it.product and it.product.category:
            return it.product.category
        hit = name_to_product.get(normalize_product_name(it.item_name))
        if hit and hit.category:
            return hit.category
        return None

    board = []
    for p in purchases:
        board.append({
            "id": p.id,
            "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "subject": p.subject or p.item_name,
            "status": p.status,
            "status_label": _STATUS_LABELS.get(p.status, p.status),
            "frozen": p.status in TZ_FROZEN_STATUSES or p.status == "split",
            "items": [
                {
                    "id": it.id,
                    "item_name": it.item_name,
                    "quantity": float(it.quantity or 0),
                    "unit": it.unit,
                    "unit_price": float(it.unit_price or 0),
                    "total_price": float(it.total_price or 0),
                    "product_id": it.product_id,
                    "_product_category": _category_of(it),
                    "feo_planned_item_id": it.feo_planned_item_id,
                }
                for it in sorted(p.items or [], key=lambda x: x.id)
            ],
        })

    return {"wish_id": wish.id, "title": wish.title, "purchases": board}
