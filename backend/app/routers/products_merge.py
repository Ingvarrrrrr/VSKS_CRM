"""Слияние карточек каталога и подсказка похожих карточек (владелец,
27.10.2026, Правило №5 — новая логика в своём файле, рядом с products_match.py
по аналогии). Право — то же products.edit_catalog, та же единственная
проверка, что у остальных операций над общим каталогом (ПРАВИЛО №6,
app/services/product_catalog_guard.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.product_catalog_guard import assert_can_edit_catalog
from app.services.product_merge import MAX_LOSER_IDS, merge_products
from app.services.product_similar import DEFAULT_LIMIT_GROUPS, MIN_QUERY_LEN, find_similar_groups

router = APIRouter(prefix="/api/products", tags=["products"])


class _MergeRequest(BaseModel):
    winner_id: int
    loser_ids: list[int] = Field(..., min_length=1, max_length=MAX_LOSER_IDS)


@router.post("/merge")
async def merge_products_endpoint(
    body: _MergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Слить дубли каталога в одну карточку `winner_id` — см. докстринг
    app.services.product_merge (история цен/фото/описаний переносится,
    пустые поля winner'а дозаполняются, ничего не теряется). ПРАВИЛО №8:
    право (products.edit_catalog) проверено ниже тем же единственным
    механизмом, что и у PUT/PATCH/DELETE товара; id валидируются ДО похода
    в БД merge_products (422/404 вместо 500)."""
    await assert_can_edit_catalog(current_user, db)

    if body.winner_id in body.loser_ids:
        raise HTTPException(422, "winner_id не может входить в loser_ids")
    if len(set(body.loser_ids)) != len(body.loser_ids):
        raise HTTPException(422, "loser_ids содержит повторы")

    try:
        report = await merge_products(db, body.winner_id, body.loser_ids, current_user)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(404 if "не найден" in msg else 422, msg)
    await db.commit()
    return report


@router.get("/similar-groups")
async def get_similar_groups(
    q: str = Query(..., min_length=MIN_QUERY_LEN),
    limit: int = Query(DEFAULT_LIMIT_GROUPS, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Группы карточек, похожих по бренду+коду модели, среди товаров, чьё
    название содержит `q` — подсказка для ручного слияния (POST /merge),
    ничего в БД не меняет. Право — products.edit_catalog (та же защита
    общего каталога, что и у самого слияния)."""
    await assert_can_edit_catalog(current_user, db)
    try:
        groups = await find_similar_groups(db, q, limit_groups=limit)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {
        "groups": [
            {
                "brand": g.brand,
                "base_model": g.base_model,
                # Исходное написание модели/артикула winner'а для заголовка
                # (владелец, 27.10.2026, п.1 приёмки) — «ОП-2»/«DF332DWME»,
                # не свёрнутое base_model «оп2»/«df332dwme».
                "model_display": g.model_display or g.base_model,
                "confidence": g.confidence,
                "match_key": g.match_key,
                "suggested_winner_id": g.suggested_winner_id,
                "cards": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "manufacturer": c.manufacturer,
                        "price": c.price,
                        "contractor_id": c.contractor_id,
                        "source_ref": c.source_ref,
                        "history_count": c.history_count,
                        "has_photo": c.has_photo,
                        "has_description": c.has_description,
                        "diff_tokens": list(c.diff_tokens),
                        # Карточка того же магазина, что winner — такие
                        # заведомо РАЗНЫЕ товары (владелец, 27.10.2026, п.3),
                        # фронт не должен предлагать её к слиянию с winner.
                        "same_store_as_winner": c.same_store_as_winner,
                    }
                    for c in g.cards
                ],
            }
            for g in groups
        ],
    }
