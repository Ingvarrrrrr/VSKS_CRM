"""Отбрасывание нерелевантных предложений нишевых магазинов (QA живого
поиска в магазинах, владелец, 29.10.2026) — найдено: магазин с собственным
поиском по подстроке/популярности отдаёт СЛУЧАЙНЫЕ товары на нераспознанный
запрос («пускатель магнитный» у promalper/ice_age/medtehno отдавал по 10
штук магнитных игрушек/браслетов — ни одного пускателя — строка статусов
при этом показывала «10 найдено»).

Предложение остаётся, если в его названии нашёлся:
- вид товара запроса (с синонимами — product_query_parse.
  product_type_synonyms, тот же словарь, что parse_query, ПРАВИЛО №6), если
  вид распознан, ИЛИ
- бренд/цифровой-модельный токен/величина запроса (parsed.required, КРОМЕ
  type_literal — тот уже в предыдущем пункте) — ЛЮБОЙ ОДИН из них достаточен
  (это уже специфичный сигнал сам по себе, например «27» у «монитор 27» —
  найдено разведкой 29.10.2026: «монитор» не входит в словарь вида товара
  product_name_signature, из-за чего ОН попадает в «обычные» слова ниже, и
  требование совпадения ОБОИХ слов «монитор»+«27» гасило настоящие мониторы
  regard.ru, у которых в названии только модель/диагональ, без слова
  «монитор» буквально — см. docstring clean_query() в service.py про тот же
  пробел словаря), ИЛИ
- строгое большинство ОБЫЧНЫХ слов запроса (parsed.optional — то, что не
  попало ни в вид, ни в бренд/цифру/величину; ПО ОСНОВАМ СЛОВ) — ТОТ ЖЕ
  порог `len(parts)//2 + 1` и ТОТ ЖЕ способ сравнения (to_tsquery('russian',
  ...) комбинаторным OR групп AND поверх to_tsvector('russian', ...)), что
  app.services.product_search._at_least_k_tsquery использует для СВОЕГО
  каталога (там же находка — чистый OR по одному слову пропускал
  «Магнитную игру»/«Браслет магнитный» по слову «магнитный» у запроса
  «пускатель магнитный» — оба слова у этого запроса ПОПАДАЮТ В optional,
  раз «пускатель» тоже не распознан словарём вида, и порог требует ОБА).
  Второй стеммер/способ сравнения здесь НЕ заводим (ПРАВИЛО №6) —
  _tsquery_token/_tsquery_type_group ПЕРЕИСПОЛЬЗУЮТСЯ из product_search.py,
  просто применены к тексту названия предложения одним batched SQL
  (unnest), а не к колонке таблицы Product.

db=None (вызов без сессии БД — например, прямой юнит-тест адаптера без
постгреса) — Postgres-стемминг недоступен, фильтр ослабляется до
литерального сравнения слов (без стемминга, то же разбиение _split_words):
хуже распознаёт словоформы, но не ломает вызов совсем, тот же паттерн
деградации без db, что у clean_query()/parse_query(brand_dictionary=None)
в service.py."""
from __future__ import annotations

from itertools import combinations
from typing import Optional

from sqlalchemy import bindparam, String, text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_name_signature import _split_words
from app.services.product_query_parse import ParsedQuery, product_type_synonyms
from app.services.product_search import _tsquery_token, _tsquery_type_group
from app.services.store_search.base import StoreOffer


def _required_signal_words(parsed: ParsedQuery) -> list[str]:
    """required-токены, КРОМЕ type_literal (вид проверяется отдельно) —
    бренд/цифровой-модельный токен/величина, см. docstring модуля."""
    return [t for t in parsed.required if t != parsed.type_literal]


def _without_db_relevant(
    name: str, parsed: ParsedQuery, required_signals: list[str], ordinary_words: list[str],
) -> bool:
    """Деградация без БД (см. docstring модуля) — литеральное совпадение
    слов (без стемминга), ТА ЖЕ структура условий (вид / любой required-
    сигнал / большинство ordinary_words), что и DB-путь ниже."""
    name_words = set(_split_words(name))
    if parsed.product_type:
        for syn in product_type_synonyms(parsed.product_type):
            if set(syn.lower().split()) <= name_words:
                return True
    for sig in required_signals:
        if set(sig.lower().split()) <= name_words:
            return True
    if not ordinary_words:
        # Нет ни вида, ни required-сигналов, ни обычных слов (запрос был
        # пуст/целиком стоп-словами) — нет базы для решения, не отбрасываем.
        return not parsed.product_type and not required_signals
    hits = sum(1 for w in ordinary_words if set(w.lower().split()) <= name_words)
    threshold_k = len(ordinary_words) // 2 + 1
    return hits >= threshold_k


async def filter_relevant_offers(
    offers: list[StoreOffer], parsed: ParsedQuery, db: Optional[AsyncSession],
) -> list[StoreOffer]:
    """Отбрасывает предложения без совпадения с запросом — см. docstring
    модуля. Полностью нераспознанный+беззначимый запрос (ни вида, ни
    required-сигналов, ни обычных слов) — ничего не отбрасываем (нет базы
    для решения)."""
    if not offers:
        return offers

    required_signals = _required_signal_words(parsed)
    ordinary_words = list(parsed.optional)

    if db is None:
        if not parsed.product_type and not required_signals and not ordinary_words:
            return offers
        return [
            o for o in offers
            if _without_db_relevant(o.name or "", parsed, required_signals, ordinary_words)
        ]

    type_tsquery = _tsquery_type_group(parsed.product_type) if parsed.product_type else None

    required_tsquery = None
    required_parts = [p for p in (_tsquery_token(w, prefix=False) for w in required_signals) if p]
    if required_parts:
        required_tsquery = " | ".join(f"({p})" for p in required_parts)

    word_tsquery = None
    word_parts = [p for p in (_tsquery_token(w, prefix=False) for w in ordinary_words) if p]
    if word_parts:
        threshold_k = len(word_parts) // 2 + 1
        threshold_groups = [
            " & ".join(f"({p})" for p in combo) for combo in combinations(word_parts, threshold_k)
        ]
        word_tsquery = " | ".join(f"({g})" for g in threshold_groups)

    combined_parts = [p for p in (type_tsquery, required_tsquery, word_tsquery) if p]
    if not combined_parts:
        return offers
    combined_tsquery = " | ".join(f"({p})" for p in combined_parts)

    names = [o.name or "" for o in offers]
    stmt = sa_text(
        "SELECT (to_tsvector('russian', val) @@ to_tsquery('russian', :tsquery_w)) AS matched "
        "FROM unnest(:names_w) WITH ORDINALITY AS t(val, idx) ORDER BY idx"
    ).bindparams(bindparam("names_w", type_=PG_ARRAY(String)))
    rows = (await db.execute(stmt, {"names_w": names, "tsquery_w": combined_tsquery})).scalars().all()
    return [o for o, matched in zip(offers, rows) if matched]
