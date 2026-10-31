"""SQL-сужение кандидатов каталога для батчевого матчинга (POST
/api/products/match и, через него, POST /feo-planned-items/plan-to-wish/candidates,
ПРАВИЛО №6 — единая точка, см. app/routers/products_match.py::_score_product_candidates).

Повод (владелец, 2026-10-26): _score_product_candidates грузил ВЕСЬ каталог
(в проде 53 797 строк, растёт к 250+ тыс.) в Python на КАЖДЫЙ вызов, чтобы
потом app.product_matcher.bulk_match (прогрессивное сужение по стемам слов,
app/services/text_match.py) искало совпадения. Сам bulk_match — ядро не
трогаем (владелец закрепил его алгоритм, ПРАВИЛО №6), но каталог, который ему
подаётся, теперь не "все товары", а SQL-предвыборка по trigram-похожести
ИЛИ ILIKE-словам (та же пара условий и экранирование, что
app/services/product_search.py — переиспользуем _escape_like/_search_words/
_word_condition, второй механизм поиска не пишем).

Почему именно trigram+ILIKE, а не точное совпадение стемов в SQL: стемы
text_match режут слово до 6 символов и используют собственный список
NOISE_TOKENS — переносить эту логику в SQL означало бы завести ВТОРУЮ
реализацию той же идеи (прогрессивное сужение), а не сузить пул для первой.
trigram-индекс (ix_products_name_trgm, миграция
r5s7u9w1y3a5_product_search_indexes) — это СУПЕРМНОЖЕСТВО кандидатов bulk_match
на реальных данных (похожие по буквам строки почти всегда делят хотя бы один
стем); ILIKE по словам query — отдельная OR-ветка на случай, когда trigram-
похожесть короткой/редкой строки ниже порога similarity_threshold (0.3), но
слово всё равно буквально входит в название. Расхождения (если появятся)
измерены в tests/test_products_catalog_scale.py и описаны в отчёте сессии.
"""
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.product import Product
from app.services.product_search import MIN_TRIGRAM_WORD_LEN, _search_words, _word_condition
from app.services.text_match import stem, tokenize

PER_QUERY_CANDIDATE_LIMIT = 200


def _candidate_condition(query: str) -> Optional[ColumnElement]:
    query = (query or "").strip()
    if not query:
        return None
    conds: list[ColumnElement] = [Product.name.op("%")(query)]
    words = _search_words(query)
    if words:
        from sqlalchemy import and_
        conds.append(and_(*(_word_condition(w, search_description=False) for w in words)))
    # Плановые позиции часто записаны во множественном числе («Ножи канцелярские»,
    # «Степлеры канцелярские», «Карандаши простые», «Папки-регистраторы»), тогда
    # как товары каталога — в единственном с длинным уточнением модели/размера
    # (trigram similarity всей строки < 0.3, а буквальный ILIKE по полному слову
    # с окончанием мн. ч. их отсекает ДО передачи в bulk_match). Вторая OR-ветка
    # по стемам text_match.stem (>= MIN_TRIGRAM_WORD_LEN=3 символов, работает по
    # тому же GIN trgm-индексу) подаёт эти товары в bulk_match.
    stems = [stem(t) for t in tokenize(query)]
    trgm_stems = [s for s in stems if len(s) >= MIN_TRIGRAM_WORD_LEN]
    if trgm_stems:
        from sqlalchemy import and_
        conds.append(and_(*(_word_condition(s, search_description=False) for s in trgm_stems)))
    return or_(*conds)


async def fetch_match_candidates(
    db: AsyncSession,
    queries: Sequence[str],
    *,
    org_id: Optional[int],
    active_only: bool = False,
    per_query_limit: int = PER_QUERY_CANDIDATE_LIMIT,
) -> list:
    """Возвращает список Row (id, name, price, description, photo_url,
    has_bytea_photo, item_kind, category) — объединение (по id, без
    дублей) SQL-сжатых кандидатов КАЖДОГО query из `queries` (trigram % ИЛИ
    AND-ILIKE по словам запроса, см. `_candidate_condition`), вместо полного
    SELECT каталога. Один SELECT на query — отдельные запросы недороги
    благодаря GIN trgm-индексу (ix_products_name_trgm), но при большом числе
    queries (батч /match, /deduplicate не сюда) это N round-trip'ов; вызывающая
    сторона (_MatchRequest) ограничивает queries разумным пределом (422 при
    превышении) именно по этой причине.

    Пустой/бессмысленный query (после strip — "") не даёт кандидатов отдельно
    (как и раньше: bulk_match сам вернёт для него status='create')."""
    from sqlalchemy import func

    cols = (
        Product.id, Product.name, Product.price, Product.description,
        Product.photo_url, (Product.photo_size.isnot(None)).label("has_bytea_photo"),
        Product.item_kind, Product.category,
    )
    merged: dict[int, object] = {}
    for query in queries:
        cond = _candidate_condition(query)
        if cond is None:
            continue
        q = select(*cols).where(cond)
        if org_id:
            q = q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
        if active_only:
            q = q.where(Product.is_active.is_(True))
        q = q.order_by(func.similarity(Product.name, query.strip()).desc()).limit(per_query_limit)
        rows = (await db.execute(q)).all()
        for r in rows:
            merged[r.id] = r
    return list(merged.values())
