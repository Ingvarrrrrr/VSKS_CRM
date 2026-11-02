"""GET /api/products/store-search — этап 1 «живой поиск товара в магазинах»
(владелец, 28.10.2026): в нашу базу НИЧЕГО не пишем (этап 2), только
параллельный живой запрос в магазины и возврат предложений. Вся логика
HTTP/кэша/лимита частоты/ранжирования — app/services/store_search/service.py
(ПРАВИЛО №6); этот роутер только валидирует вход (ПРАВИЛО №8 п.6 — лимиты/
формат ДО похода в сеть) и отдаёт результат.

Путь "/store-search" — ОДИН литеральный сегмент на префиксе /api/products,
регистрируется в app/routes.py ДО products.router (тот несёт catch-all
GET "/{product_id}" без int-конвертера — тот же принцип, что у products_
summary.py/products_page.py/соседей).

Доступ — ЗАКРЫТО ПО УМОЛЧАНИЮ (ПРАВИЛО №8 п.1): Depends(get_current_user),
как у всех соседних products_*-роутеров — без явного публичного списка этот
путь требует вход сам по себе."""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import ProductOut
from app.schemas.store_search import StoreSearchOut, StoreTakeIn, StoreTakeOut
from app.services.store_search.registry import ADAPTERS
from app.services.store_search.service import search_stores
from app.services.store_search.take import take_offer

router = APIRouter(prefix="/api/products", tags=["products"])

MAX_QUERY_LEN = 200
_HAS_ALNUM_RE = re.compile(r"[0-9a-zA-Zа-яёА-ЯЁ]")


@router.get("/store-search", response_model=StoreSearchOut)
async def store_search(
    q: str = Query(..., description="Поисковая фраза"),
    stores: Optional[List[str]] = Query(None, description="Ограничить список магазинов (ключи из реестра)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (q or "").strip()[:MAX_QUERY_LEN]
    if not q or not _HAS_ALNUM_RE.search(q):
        raise HTTPException(400, "Параметр q: непустая строка с буквами или цифрами")

    store_keys: Optional[list[str]] = None
    if stores:
        requested: list[str] = []
        for raw in stores:
            requested.extend(part.strip() for part in raw.split(",") if part.strip())
        unknown = [s for s in requested if s not in ADAPTERS]
        if unknown:
            raise HTTPException(400, f"Неизвестные магазины: {', '.join(unknown)}")
        store_keys = requested or None

    return await search_stores(q, stores=store_keys, db=db)


@router.post("/store-take", response_model=StoreTakeOut)
async def store_take(
    body: StoreTakeIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """«Взять» предложение живого поиска в каталог (этап 2, владелец,
    29.10.2026) — вся логика (валидация домена/SSRF, дедуп, цена) в
    app/services/store_search/take.py (ПРАВИЛО №5/№6), этот роутер только
    проверяет вход на литеральном формате (store_key — непустая строка, тут
    дальше проверяет сам take_offer по реестру ADAPTERS) и отдаёт результат.

    Ответ — ProductOut + `created` (StoreTakeOut, см. схему): страница
    «Товары» использует этот флаг для текста тоста («добавлен в каталог» /
    «обновлена цена»); ProductPickerDialog.vue/useItemsCatalog.ts просто
    игнорируют поле, которого не ждут.

    Права — те же, что у обычного создания товара (POST /api/products/,
    get_current_user без доп. роли): владелец явно потребовал не строже,
    иначе сотрудник в заявке не сможет взять товар из магазина."""
    store_key = (body.store_key or "").strip()
    url = (body.url or "").strip()
    if not store_key or not url:
        raise HTTPException(400, "store_key и url обязательны")

    product, created = await take_offer(
        db, current_user, store_key=store_key, url=url, query=body.query or "",
    )
    data = ProductOut.model_validate(product).model_dump()
    data["created"] = created
    return data
