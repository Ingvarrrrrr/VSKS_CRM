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
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_single_org_id
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.schemas import PriceFreshnessOut
from app.services.product_matcher import bulk_match
from app.services.product_match_candidates import fetch_match_candidates
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.product_snapshot import resolve_photo_url
from app.services.item_types import normalize_item_type
from app.services.product_catalog_guard import assert_can_edit_catalog

# Потолок числа queries в одном батче /match (владелец, 2026-10-26, задача
# сужения кандидатов — N round-trip'ов SQL-предвыборки на queries, см.
# app/services/product_match_candidates.py): выше — 422, не 500/таймаут.
MAX_MATCH_QUERIES = 500

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
    # (app/services/plan_to_wish.py) — unit, которого раньше в кандидате не было
    # вовсе. item_type НИЖЕ — единственный источник Product.item_kind (ПРАВИЛО
    # №6, app.services.item_types), нормализованный через normalize_item_type;
    # product_type — отдельное поле «Вид» (свободный текст), к типу позиции
    # («товар»/«услуга»/«работа») отношения не имеет (баг 2026-10-01: дублировал
    # item_type значением Product.product_type, из-за чего «Услуга по
    # организации проживания/питания» приходила в строку закупки типом «товар»).
    product_type: Optional[str] = None
    unit: Optional[str] = None


class _MatchResultItem(BaseModel):
    query: str
    status: str  # 'auto' | 'suggest' | 'create'
    candidates: List[_MatchCandidate]


class _MatchRequest(BaseModel):
    queries: List[str] = Field(..., max_length=MAX_MATCH_QUERIES)
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
    # Сужение SQL (владелец, 2026-10-26): раньше здесь был select ВСЕГО каталога
    # (54 тыс.+ строк на каждый вызов) — теперь только trigram/ILIKE-кандидаты
    # ПО ЭТИМ ЖЕ queries (app/services/product_match_candidates.py, ПРАВИЛО №6 —
    # один механизм SQL-предвыборки для /match и, через эту же функцию,
    # plan-to-wish/candidates). bulk_match (прогрессивное сужение по стемам)
    # ниже не меняется — ему подаётся суженный, а не весь каталог.
    rows = await fetch_match_candidates(db, queries, org_id=org_id, active_only=active_only)
    catalog = [
        (
            r.id,
            r.name or '',
            float(r.price) if r.price is not None else None,
            r.description,
            resolve_photo_url(r.photo_url, r.has_bytea_photo, r.id),
            normalize_item_type(r.item_kind) or r.item_kind,
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
            select(Product).where(Product.id.in_(candidate_ids))
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
    current_user: User = Depends(require_tab('products')),
):
    """Удалить дубликаты товаров. Группировка через fuzzy-матчинг по имени
    (token-set + char-ratio, то же что и при импорте). Единый общий каталог.

    `dry_run=true` — вернуть найденные группы без удаления (для preview UI).
    `threshold` — порог сходства (по умолчанию 0.8).
    `skip_ids` — CSV id'шников, которые пользователь снял с галочкой и НЕ хочет удалять.

    Защита каталога (Этап В, план item-tz-description.md, 14.10.2026):
    слияние/удаление СУЩЕСТВУЮЩИХ товаров каталога (не только dry_run=false —
    сама же find/merge-операция решает судьбу чужих карточек) требует
    products.edit_catalog, та же единственная проверка, что у PUT/PATCH/DELETE
    товара (app/services/product_catalog_guard.py, Правило №6 — второй
    механизм не заводим)."""
    await assert_can_edit_catalog(current_user, db)
    from app.product_matcher import name_similarity, _normalize
    from collections import defaultdict
    from sqlalchemy import func
    from app.services.product_dedup_sql import sql_dedup_normalized_name_expr
    from app.services.product_merge import merge_products

    skipped_ids = set()
    if skip_ids:
        try:
            skipped_ids = {int(x) for x in skip_ids.split(',') if x.strip()}
        except ValueError:
            pass

    # Сужение SQL (владелец, 2026-10-26): раньше здесь был select ВСЕГО
    # каталога (54 тыс.+ строк) в Python ради union-find по точному имени.
    # Дубликат = ТОЛЬКО точное совпадение имени после нормализации (см.
    # app.product_matcher._normalize и его докстринг выше в этом роутере —
    # похожие названия с РАЗНЫМИ характеристиками — разные товары, никакого
    # fuzzy). Группировка по точному ключу — не транзитивная похожесть,
    # поэтому union-find был избыточен и для него: GROUP BY в БД находит те
    # же группы (ключ — SQL-эквивалент _normalize, app/services/
    # product_dedup_sql.py), в приложение попадают ТОЛЬКО товары из групп с
    # count>1, не весь каталог.
    norm_expr = sql_dedup_normalized_name_expr()
    total_products = (await db.execute(select(func.count(Product.id)))).scalar_one()

    dup_key_rows = (await db.execute(
        select(norm_expr)
        .where(func.length(norm_expr) > 0)
        .group_by(norm_expr)
        .having(func.count() > 1)
    )).all()
    dup_keys = [r[0] for r in dup_key_rows]

    all_products: list[Product] = []
    has_photo_blob: dict[int, bool] = {}
    if dup_keys:
        result = await db.execute(
            select(Product, Product.photo_size.isnot(None))
            .where(norm_expr.in_(dup_keys))
        )
        _rows = result.all()
        all_products = [r[0] for r in _rows]
        has_photo_blob = {r[0].id: bool(r[1]) for r in _rows}

    def priority_score(p: Product) -> tuple:
        has_price_links = bool(p.price_links)
        has_photo = bool(has_photo_blob.get(p.id) or p.photo_url or p.photo_link)
        has_desc = bool((p.description or '').strip())
        contract_date_ts = p.contract_date.toordinal() if p.contract_date else 0
        return (has_price_links, has_photo, has_desc, contract_date_ts, p.id)

    duplicate_groups: list[dict] = []

    if all_products:
        # Перегруппировка в Python той же формулой _normalize (единый ключ,
        # см. докстринг product_dedup_sql.py — SQL-формула построена как её
        # зеркало) — товары уже сужены до групп с count>1, здесь только
        # раскладка по ключу, без union-find (равенство ключа не нуждается в
        # транзитивном связывании).
        groups_map: dict[str, list[Product]] = defaultdict(list)
        for p in all_products:
            key = _normalize(p.name or '')
            if key:
                groups_map[key].append(p)

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
            # "kept" — размер ВСЕГО каталога (как и раньше, когда all_products
            # был полным select) — total_products считается отдельным
            # count(*), не len() по суженной выборке дублей.
            "kept": total_products,
        }

    # Слияние — через app.services.product_merge.merge_products (ПРАВИЛО №6,
    # владелец 27.10.2026): раньше тут переносился только PurchaseItem.product_id
    # и дубль удалялся — история цен/фото/описания (CASCADE) терялись,
    # wish_items/contract_items/commercial_request получали NULL. Группировка
    # (точное совпадение имени, приоритет winner'а) НЕ меняется — merge_products
    # только переносит данные и дозаполняет пустые поля winner'а.
    deleted = 0
    for grp in duplicate_groups:
        winner_id = grp["winner"]["id"]
        dup_ids = [dup["id"] for dup in grp["duplicates"] if dup["id"] not in skipped_ids]
        if not dup_ids:
            continue
        await merge_products(db, winner_id, dup_ids, current_user)
        deleted += len(dup_ids)

    await db.commit()
    return {
        "dry_run": False,
        "deleted": deleted,
        "kept": total_products - deleted,
        "groups": duplicate_groups,
    }
