"""Дедуп/матчинг товаров — вынесено из products.py (Правило №5, сессия
2026-09-08). POST /match и POST /deduplicate — литеральные односегментные
пути на префиксе /api/products, метод POST; products.router (ядро) не несёт
ни одного catch-all POST-маршрута на форме "/{product_id}", поэтому
конфликта по форме пути нет — регистрируется рядом с products.router по
аналогии с остальными products_* соседями.

ПРАВИЛО №6 / память проекта: дедуп — ТОЛЬКО точное совпадение имени после
нормализации (никакого fuzzy — token-set/char-ratio ложно сливал разные SKU,
см. `app.product_matcher._normalize`). Матчинг (`/match`, бэкенд —
`app.services.product_matcher.bulk_match`) — отдельный, специально нечёткий
механизм для подсказок при вводе позиции; это НЕ дублирование дедупа, у них
разные цели (подсказать похожее vs. слить идентичное), сливать не нужно.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_single_org_id
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.schemas import PriceFreshnessOut
from app.services.product_matcher import bulk_match
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.product_snapshot import resolve_photo_url

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/products", tags=["products"])


# ---------------------------------------------------------------------------
# Token-based product matching (Phase 27.4-25)
# ---------------------------------------------------------------------------

class _MatchCandidate(BaseModel):
    product_id: int
    name: str
    price: Optional[float]
    score: float
    description: Optional[str] = None
    photo_url: Optional[str] = None
    item_type: Optional[str] = None
    category: Optional[str] = None
    # Актуализация цены (владелец, 2026-08-29)
    price_updated_at: Optional[str] = None
    price_source: Optional[str] = None
    price_source_ref: Optional[str] = None
    price_freshness: Optional[PriceFreshnessOut] = None
    # plan-to-wish (2026-09-20): product_type/unit добавлены для переиспользования
    # этой ЖЕ candidate-формы в POST /feo-planned-items/plan-to-wish/candidates
    # (app/services/plan_to_wish.py) — item_type выше исторически уже несёт
    # значение Product.product_type (см. _score_product_candidates ниже), эти
    # два поля — те же данные под их настоящими именами, плюс unit, которого
    # раньше в кандидате не было вовсе.
    product_type: Optional[str] = None
    unit: Optional[str] = None


class _MatchResultItem(BaseModel):
    query: str
    status: str  # 'auto' | 'suggest' | 'create'
    candidates: List[_MatchCandidate]


class _MatchRequest(BaseModel):
    queries: List[str]
    limit: int = 3
    # Интерактивный набор в строке позиции: включает префиксное сопоставление
    # стемов (см. text_match._stem_hits), чтобы подсказки появлялись раньше
    # 6-го символа для слов длиннее 6 букв. По умолчанию выключено — пакетный
    # импорт/дедуп не должен становиться нечётким.
    prefix: bool = False


class _MatchResponse(BaseModel):
    results: List[_MatchResultItem]


async def _score_product_candidates(
    db: AsyncSession,
    org_id: Optional[int],
    queries: List[str],
    limit: int,
    prefix: bool = False,
    active_only: bool = False,
) -> List[dict]:
    """Общий сборщик кандидатов-товаров: SELECT каталога → bulk_match (text_match) →
    доактуализация цены (freshness), одним SELECT+один freshness-контекст на весь
    запрос. Вынесено из POST /match (был единственным местом, где жил этот код) —
    ПРАВИЛО №6: POST /api/products/match ниже и POST
    /api/feo-planned-items/plan-to-wish/candidates (app/services/plan_to_wish.py)
    вызывают ЭТУ функцию, не заводят вторую копию SELECT/bulk_match/freshness.

    `active_only=True` — фильтр Product.is_active (нужен plan-to-wish: «кандидаты
    только is_active»); /products/match исторически такого фильтра не имел и
    продолжает без него (active_only=False по умолчанию — поведение не менялось).

    Возвращает список dict (НЕ pydantic) в том же порядке, что `queries`:
    [{"query": str, "status": 'auto'|'suggest'|'create', "candidates": [candidate_dict, ...]}]
    candidate_dict несёт все поля формы _MatchCandidate (см. класс выше), включая
    product_type/unit.
    """
    # 27.4-29: photo_url из БД ИЛИ /api/products/{id}/photo если фото в bytea (photo_data)
    q = select(
        Product.id,
        Product.name,
        Product.price,
        Product.description,
        Product.photo_url,
        (Product.photo_data.isnot(None)).label('has_bytea_photo'),
        Product.product_type,
        Product.category,
    )
    if org_id:
        q = q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    if active_only:
        q = q.where(Product.is_active.is_(True))
    rows = (await db.execute(q)).all()
    catalog = [
        (
            r.id,
            r.name or '',
            float(r.price) if r.price is not None else None,
            r.description,
            resolve_photo_url(r.photo_url, r.has_bytea_photo, r.id),
            r.product_type,
            r.category,
        )
        for r in rows
    ]

    # Потолок поднят с 10 до 200: инлайновый поиск в строке позиции (InlineProductMatch)
    # должен показывать весь список совпадений с прокруткой, а не top-3/top-10.
    # Пакетный импорт по-прежнему не шлёт limit явно и получает дефолт 3.
    top_k = max(1, min(limit, 200))
    results = bulk_match(queries, catalog, top_k=top_k, prefix_match=prefix)

    # Актуализация цены (владелец, 2026-08-29): bulk_match не трогаем (сигнатура
    # зафиксирована) — донабираем метаданные вторым проходом по product_id
    # уже полученных кандидатов, одним SELECT + один контекст на весь запрос.
    candidate_ids = {c.product_id for r in results for c in r.candidates}
    freshness_by_id: dict[int, dict] = {}
    meta_by_id: dict[int, Product] = {}
    if candidate_ids:
        meta_rows = (await db.execute(
            select(Product).options(defer(Product.photo_data)).where(Product.id.in_(candidate_ids))
        )).scalars().all()
        freshness_ctx = await load_freshness_context(db, org_id)
        for prod in meta_rows:
            meta_by_id[prod.id] = prod
            freshness_by_id[prod.id] = evaluate_freshness(prod, freshness_ctx)

    _log.info(
        "products_match._score_product_candidates: %d queries, catalog_size=%d, "
        "auto=%d suggest=%d create=%d",
        len(queries),
        len(catalog),
        sum(1 for r in results if r.status == 'auto'),
        sum(1 for r in results if r.status == 'suggest'),
        sum(1 for r in results if r.status == 'create'),
    )

    out: List[dict] = []
    for r in results:
        candidates = []
        for c in r.candidates:
            meta = meta_by_id.get(c.product_id)
            candidates.append({
                "product_id": c.product_id,
                "name": c.name,
                "price": c.price,
                "score": c.score,
                "description": c.description,
                "photo_url": c.photo_url,
                "item_type": c.item_type,
                "category": c.category,
                "product_type": meta.product_type if meta else None,
                "unit": meta.unit if meta else None,
                "price_updated_at": (
                    meta.price_updated_at.isoformat() if meta and meta.price_updated_at else None
                ),
                "price_source": meta.price_source if meta else None,
                "price_source_ref": meta.price_source_ref if meta else None,
                "price_freshness": freshness_by_id.get(c.product_id),
            })
        out.append({"query": r.query, "status": r.status, "candidates": candidates})
    return out


@router.post("/match", response_model=_MatchResponse)
async def match_products(
    body: _MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Score a list of product name queries against the catalog using token-based fuzzy matching.

    Returns top-k candidates per query with status: 'auto' (score>=0.95),
    'suggest' (0.60<=score<0.95), or 'create' (no match found).
    """
    org_id = get_single_org_id(current_user)
    results = await _score_product_candidates(db, org_id, body.queries, body.limit, prefix=body.prefix)

    return _MatchResponse(results=[
        _MatchResultItem(
            query=r["query"],
            status=r["status"],
            candidates=[_MatchCandidate(**c) for c in r["candidates"]],
        )
        for r in results
    ])


@router.post("/deduplicate")
async def deduplicate_products(
    dry_run: bool = False,
    threshold: float = 0.8,
    skip_ids: Optional[str] = None,  # CSV: дубликаты, которые пользователь снял с галочкой
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('products')),
):
    """Удалить дубликаты товаров. Группировка через fuzzy-матчинг по имени
    (token-set + char-ratio, то же что и при импорте). Единый общий каталог.

    `dry_run=true` — вернуть найденные группы без удаления (для preview UI).
    `threshold` — порог сходства (по умолчанию 0.8).
    `skip_ids` — CSV id'шников, которые пользователь снял с галочкой и НЕ хочет удалять.
    """
    from app.product_matcher import name_similarity, _normalize
    from collections import defaultdict
    from sqlalchemy import update as sa_update
    from app.models.purchase_item import PurchaseItem

    skipped_ids = set()
    if skip_ids:
        try:
            skipped_ids = {int(x) for x in skip_ids.split(',') if x.strip()}
        except ValueError:
            pass

    result = await db.execute(
        select(Product, Product.photo_data.isnot(None)).options(defer(Product.photo_data))
    )
    _rows = result.all()
    all_products: list[Product] = [r[0] for r in _rows]
    has_photo_blob: dict[int, bool] = {r[0].id: bool(r[1]) for r in _rows}

    def priority_score(p: Product) -> tuple:
        has_price_links = bool(p.price_links)
        has_photo = bool(has_photo_blob.get(p.id) or p.photo_url or p.photo_link)
        has_desc = bool((p.description or '').strip())
        contract_date_ts = p.contract_date.toordinal() if p.contract_date else 0
        return (has_price_links, has_photo, has_desc, contract_date_ts, p.id)

    duplicate_groups: list[dict] = []

    # Единый общий каталог — дедупликация по всей базе без деления по org_id
    org_products = all_products
    n = len(org_products)
    if n >= 2:
        # Union-find для транзитивного объединения
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Дубликат = ТОЛЬКО точное совпадение имени (после нормализации регистра/
        # пробелов/ё). Похожие названия с РАЗНЫМИ характеристиками — это разные
        # товары (Гофрокороб д600/Т24 ≠ д500/Т22; ZenBook 14 i7 ≠ ZenBook 13 i5).
        # Никакого fuzzy (token-set / char-ratio): он ложно сливал разные SKU.
        norms = [_normalize(p.name or '') for p in org_products]
        by_norm: dict[str, int] = {}
        for i, key in enumerate(norms):
            if not key:
                continue
            prev = by_norm.get(key)
            if prev is not None:
                union(i, prev)
            else:
                by_norm[key] = i

        groups_map: dict[int, list[Product]] = defaultdict(list)
        for i, p in enumerate(org_products):
            groups_map[find(i)].append(p)

        for ps in groups_map.values():
            if len(ps) < 2:
                continue
            ps.sort(key=priority_score, reverse=True)
            winner = ps[0]
            dups = ps[1:]
            dup_dicts = []
            for p in dups:
                sim = name_similarity(winner.name or '', p.name or '')
                match = "exact" if sim >= 0.999 else "fuzzy"
                score = round(sim * 100)
                dup_dicts.append({
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "product_type": p.product_type,
                    "has_photo": bool(has_photo_blob.get(p.id) or p.photo_url or p.photo_link),
                    "has_description": bool((p.description or '').strip()),
                    "score": score,
                    "match": match,
                })
            duplicate_groups.append({
                "winner": {
                    "id": winner.id,
                    "name": winner.name,
                    "category": winner.category,
                    "product_type": winner.product_type,
                    "has_photo": bool(has_photo_blob.get(winner.id) or winner.photo_url or winner.photo_link),
                    "has_description": bool((winner.description or '').strip()),
                },
                "duplicates": dup_dicts,
            })

    if dry_run:
        return {
            "dry_run": True,
            "groups": duplicate_groups,
            "total_groups": len(duplicate_groups),
            "total_to_delete": sum(len(g["duplicates"]) for g in duplicate_groups),
            "kept": len(all_products),
        }

    deleted = 0
    for grp in duplicate_groups:
        winner_id = grp["winner"]["id"]
        dup_ids = [dup["id"] for dup in grp["duplicates"] if dup["id"] not in skipped_ids]
        if not dup_ids:
            continue
        await db.execute(
            sa_update(PurchaseItem)
            .where(PurchaseItem.product_id.in_(dup_ids))
            .values(product_id=winner_id)
        )
        await db.execute(
            Product.__table__.delete().where(Product.id.in_(dup_ids))
        )
        deleted += len(dup_ids)

    await db.commit()
    return {
        "dry_run": False,
        "deleted": deleted,
        "kept": len(all_products) - deleted,
        "groups": duplicate_groups,
    }
