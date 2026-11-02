"""Оркестрация живого поиска по магазинам (этап 1, владелец, 28.10.2026) —
единственное место, которое знает про HTTP/кэш/лимит частоты/параллелизм;
сами адаптеры (kuvalda.py, safe.py, ...) только парсят ответ своего магазина
(ПРАВИЛО №5/№6, см. docstring registry.py/base.py).

Очищенный запрос — ПЕРЕИСПОЛЬЗУЕТ app.services.product_query_parse.parse_query
(ПРАВИЛО №6, тот же разбор, что у встроенного поиска по своей базе): вид +
бренд + модель + величины, без стоп-слов; если разбор ничего не оставил
(required пуст) — уходит исходная строка целиком (короткие/непонятные
запросы не должны превращаться в пустой запрос к магазину).

Кэш — простой dict в памяти процесса (ключ (store_key, cleaned_query),
значение (built_at, result)), TTL CACHE_TTL_SECONDS. Лимит частоты — простой
токен-бакет в памяти (список времён запросов за последние RATE_WINDOW_SECONDS
на магазин); оба сбрасываются при перезапуске процесса — это НЕ персистентное
хранилище, что для живого поиска (не критичные данные) достаточно."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_name_signature import _split_words
from app.services.product_name_signature_props import ACCESSORY_MARKERS
from app.services.product_query_parse import (
    get_manufacturer_brand_dictionary,
    parse_query,
    product_type_synonyms,
)
from app.services.product_search import _looks_like_article_query
from app.services.store_search.base import StoreBlocked, StoreOffer
from app.services.store_search.registry import ADAPTERS, ARTICLE_ONLY_STORES
from app.services.store_search.relevance import filter_relevant_offers

# Имя магазина для stores[] даже когда он не дал ни одного предложения
# (таймаут/ошибка/лимит частоты) — читаем ОДИН И ТОТ ЖЕ источник, что и
# StoreOffer.store_name у каждого адаптера: атрибут adapter.display_name
# (= STORE_NAME_FALLBACK модуля адаптера, см. base.py::StoreAdapter,
# ПРАВИЛО №6). Дефект приёмки 29.10.2026: раньше здесь был fallback=key —
# строка статусов показывала «kuvalda»/«chipdip»/«sima_land» вместо
# человекочитаемых имён, потому что store_display_name(domain, fallback)
# просто возвращает fallback, а сюда передавался ключ, а не имя.
_STORE_DISPLAY_NAMES: dict[str, str] = {
    key: adapter.display_name for key, adapter in ADAPTERS.items()
}

PER_STORE_TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 60 * 60
RATE_LIMIT_PER_MINUTE = 20
RATE_WINDOW_SECONDS = 60.0
MAX_CONCURRENT_VISITS_PER_STORE = 5

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


class _StoreHttpClient:
    """Клиент, который видит адаптер — httpx.AsyncClient + ограничение
    параллельных довизитов (get_many) MAX_CONCURRENT_VISITS_PER_STORE
    (ПРАВИЛО задания п. «довизиты — не больше 5 параллельно»)."""

    def __init__(self, http: httpx.AsyncClient):
        self._http = http
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_VISITS_PER_STORE)

    async def get_text(self, url: str, headers: Optional[dict] = None) -> Optional[str]:
        req_headers = dict(DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)
        try:
            async with self._sem:
                resp = await self._http.get(url, headers=req_headers, follow_redirects=True)
            if 200 <= resp.status_code < 300:
                return resp.text
        except Exception:
            return None
        return None

    async def post_text(self, url: str, body: str, headers: Optional[dict] = None) -> Optional[str]:
        """POST с текстовым телом (regard.py — единственный адаптер,
        которому нужен POST, не GET; остальные магазины отдают поиск через
        GET). Та же семафорная защита параллелизма, что у get_text."""
        req_headers = dict(DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)
        try:
            async with self._sem:
                resp = await self._http.post(url, content=body.encode("utf-8"), headers=req_headers, follow_redirects=True)
            if 200 <= resp.status_code < 300:
                return resp.text
        except Exception:
            return None
        return None

    async def get_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        results = await asyncio.gather(*(self.get_text(u) for u in urls))
        return dict(zip(urls, results))


# ---------------------------------------------------------------------------
# Кэш в памяти процесса — (store_key, cleaned_query) -> (built_at, offers)
# ---------------------------------------------------------------------------
_cache: dict[tuple[str, str], tuple[float, list[StoreOffer]]] = {}

# Лимит частоты — store_key -> [timestamps запросов, которые РЕАЛЬНО ушли в
# магазин (кэш-хиты не считаются — они не нагружают магазин)]
_rate_log: dict[str, list[float]] = {}


def _cache_get(store_key: str, cleaned_query: str) -> Optional[list[StoreOffer]]:
    entry = _cache.get((store_key, cleaned_query))
    if not entry:
        return None
    built_at, offers = entry
    if time.monotonic() - built_at > CACHE_TTL_SECONDS:
        return None
    return offers


def _cache_set(store_key: str, cleaned_query: str, offers: list[StoreOffer]) -> None:
    _cache[(store_key, cleaned_query)] = (time.monotonic(), offers)


def _rate_limited(store_key: str) -> bool:
    now = time.monotonic()
    log = _rate_log.setdefault(store_key, [])
    # чистим старые записи окна
    cutoff = now - RATE_WINDOW_SECONDS
    while log and log[0] < cutoff:
        log.pop(0)
    if len(log) >= RATE_LIMIT_PER_MINUTE:
        return True
    log.append(now)
    return False


def clean_query(query: str, brand_dictionary=None) -> str:
    """Очищенный запрос для магазина — вид товара (как написал человек) +
    бренд + модель/коды + величины, без стоп-слов (правка 29.10.2026 —
    найден дефект: «монитор 27» уходил в магазины голым «27», потеряв
    главное слово «монитор», потому что parse_query().required несёт вид
    ТОЛЬКО когда он есть в словаре product_name_signature, а «монитор» там
    не заведён — required остался только цифрой).

    brand_dictionary — тот же контракт, что у parse_query/build_signature
    (`.find_in_name(name) -> str | None`); ПЕРЕИСПОЛЬЗУЕМ ТОТ ЖЕ словарь, что
    product_search.search_products получает через get_manufacturer_
    brand_dictionary (ПРАВИЛО №6 — второй механизм распознавания бренда не
    заводим) — search_stores() ниже передаёт его сюда уже построенным, иначе
    бренд из запроса не распознаётся вовсе (specific по бренду не сработает,
    остальной разбор работает).

    Правило: если вид распознан (parsed.product_type не None — словарь
    нашёл его, required уже несёт type_literal/бренд/модель/величины целиком,
    см. parse_query) — required и есть очищенный запрос. Если вид НЕ
    распознан — required может растерять обычные слова (как «монитор»,
    «магнитный» у «пускатель магнитный», если фраза не в словаре целиком) —
    тогда берём ВСЕ значимые слова исходной фразы по порядку (та же
    токенизация _split_words, что и внутри parse_query, ПРАВИЛО №6 — второй
    разбор не пишем), выбросив только предлоги/союзы (parsed.dropped_
    stopwords). Два исхода ("" или только цифры) всё равно уходят в
    исходную строку целиком — запрос из одних цифр магазину ничего не
    говорит лучше, чем вообще не чистить."""
    raw = (query or "").strip()
    if not raw:
        return raw
    parsed = parse_query(raw, brand_dictionary=brand_dictionary)
    if parsed.product_type is not None:
        tokens = list(parsed.required)
    else:
        dropped = set(parsed.dropped_stopwords)
        tokens = [w for w in _split_words(raw) if w not in dropped]
    cleaned = " ".join(tokens).strip()
    if not cleaned or all(tok.isdigit() for tok in cleaned.split()):
        return raw
    return cleaned


async def _search_one_store(
    client: _StoreHttpClient, store_key: str, cleaned_query: str, limit: int,
) -> dict:
    t0 = time.monotonic()
    cached = _cache_get(store_key, cleaned_query)
    if cached is not None:
        return {
            "key": store_key, "offers": cached, "status": "ok",
            "count": len(cached), "ms": 0,
        }

    if _rate_limited(store_key):
        return {"key": store_key, "offers": [], "status": "rate_limited", "count": 0, "ms": 0}

    adapter = ADAPTERS[store_key]
    try:
        offers = await asyncio.wait_for(
            adapter.search(client, cleaned_query, limit), timeout=PER_STORE_TIMEOUT_SECONDS,
        )
        _cache_set(store_key, cleaned_query, offers)
        status = "ok"
    except asyncio.TimeoutError:
        offers = []
        status = "timeout"
    except StoreBlocked:
        offers = []
        status = "blocked"
    except Exception:
        offers = []
        status = "error"

    ms = int((time.monotonic() - t0) * 1000)
    return {"key": store_key, "offers": offers, "status": status, "count": len(offers), "ms": ms}


_ACCESSORY_RE = re.compile(
    "|".join(re.escape(m) for m in ACCESSORY_MARKERS), re.IGNORECASE,
) if ACCESSORY_MARKERS else None


def _accessory_bucket(name_lower: str, parsed) -> int:
    """0 — вид товара запроса стоит В НАЧАЛЕ названия предложения, 2 — в
    названии есть маркер-принадлежность (ACCESSORY_MARKERS,
    product_name_signature_props.py — ТОТ ЖЕ словарь и та же идея, что
    _type_position_rank_term в product_search.py использует для своего
    каталога, Правило №6 — второй словарь/механизм «аксессуар ниже вида» не
    заводим, только переносим в Python-ранжирование предложений магазинов),
    1 — нейтрально (ни то, ни другое). Находка QA (владелец, 29.10.2026):
    «перфоратор makita» ранжировал аксессуары («Держатель для бит для
    перфораторов Makita») РЯДОМ с самими перфораторами — _rank_offer ниже
    считал долю required-токенов (бренд+вид), а у аксессуара оба слова тоже
    есть в названии, доля та же. Бакет — ПЕРВЫЙ член сортировки (важнее доли
    совпадения), как и у _type_position_rank_term там же."""
    product_type = getattr(parsed, "product_type", None)
    type_literal = getattr(parsed, "type_literal", None)
    if not product_type or not type_literal:
        return 1
    synonyms = product_type_synonyms(product_type)
    if not synonyms:
        return 1
    # «начало названия» — само первое слово ИЛИ второе (после одного
    # прилагательного) — то же упрощённое окно "1-2 слова", что в
    # _type_position_rank_term (product_search.py).
    syn_alt = "|".join(re.escape(s) for s in synonyms)
    start_re = re.compile(
        rf"^\s*(?:\S+\s+){{0,1}}(?:{syn_alt})(?![a-zа-яё0-9])", re.IGNORECASE,
    )
    if start_re.search(name_lower):
        return 0
    if _ACCESSORY_RE is not None and _ACCESSORY_RE.search(name_lower):
        return 2
    return 1


def _rank_offer(offer: StoreOffer, parsed) -> tuple:
    """Ранжирование — совпадение с разбором запроса (бренд/модель/величины,
    см. docstring службы выше): точнее совпал бренд/модель — выше. Простая
    эвристика (не product_name_signature.match(), который заточен под
    сравнение ДВУХ каталожных карточек, а не оценку одного текстового
    совпадения — усложнять через него не даёт выигрыша для простого
    ранжирования предложений одного запроса, см. задание «иначе — порядок
    магазина»): считаем долю required-токенов разбора, вошедших в название
    предложения (регистронезависимо), затем наличие цены (предложения с
    ценой выше предложений без неё).

    _accessory_bucket (см. docstring выше) — ПЕРВЫЙ член сортировки:
    аксессуар «для» вида товара не должен стоять рядом с самим видом только
    потому, что в названии аксессуара тоже упомянуты бренд и вид (владелец,
    29.10.2026, QA живого поиска)."""
    name_lower = (offer.name or "").lower()
    required = getattr(parsed, "required", []) or []
    if required:
        hits = sum(1 for tok in required if tok.lower() in name_lower)
        score = hits / len(required)
    else:
        score = 0.0
    has_price = 1 if offer.price is not None else 0
    return (_accessory_bucket(name_lower, parsed), -score, -has_price)


async def find_cached_offer(
    store_key: str, query: str, url: str, db: Optional[AsyncSession] = None, limit: int = 20,
) -> Optional[StoreOffer]:
    """Предложение по `url` для «Взять» (POST /api/products/store-take,
    app/services/store_search/take.py) — ПЕРЕИСПОЛЬЗУЕТ кэш/поиск этого же
    модуля (ПРАВИЛО №6, второй поход в магазин по другому пути не пишем):
    сперва смотрит в _cache по (store_key, clean_query(query)) — тот же ключ,
    что кладёт search_stores() выше; кэша нет (протух/ещё не искали) —
    повторяет поиск ОДНОГО магазина через _search_one_store (та же защита
    лимита частоты/таймаута/кэширования результата, что у обычного запроса).

    None — ни в кэше, ни в свежем поиске предложения с этим url не нашлось
    (вызывающий роутер отвечает 404 «предложение устарело»)."""
    if store_key not in ADAPTERS:
        return None
    brand_dictionary = await get_manufacturer_brand_dictionary(db) if db is not None else None
    cleaned_query = clean_query(query, brand_dictionary=brand_dictionary)

    offers = _cache_get(store_key, cleaned_query)
    if offers is None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(PER_STORE_TIMEOUT_SECONDS)) as http:
            client = _StoreHttpClient(http)
            result = await _search_one_store(client, store_key, cleaned_query, limit)
            offers = result["offers"]

    for offer in offers:
        if offer.url == url:
            return offer
    return None


async def search_stores(
    query: str, stores: Optional[list[str]] = None, limit_per_store: int = 10,
    db: Optional[AsyncSession] = None,
) -> dict:
    """Запрос во все (или выбранные) магазины параллельно — см. docstring
    модуля. Возвращает {"query_sent", "offers": [...], "stores": [...]}.

    db — сессия БД для get_manufacturer_brand_dictionary (ТОТ ЖЕ словарь,
    что product_search.search_products, ПРАВИЛО №6): роутер передаёт её,
    чтобы clean_query()/parse_query() ниже распознавали бренд в каноническом
    написании ("Makita", не "макита"), а не только вид/модель/величины.
    db=None (например, прямой вызов из теста без БД) — бренд из текста
    запроса просто не распознаётся, остальной разбор работает как раньше."""
    store_keys = [s for s in (stores or list(ADAPTERS.keys())) if s in ADAPTERS]
    # emex.ru (и любой другой ARTICLE_ONLY_STORES) ищет только по артикулу
    # (ПРАВИЛО №6 — тот же признак _looks_like_article_query, что у
    # встроенного поиска по своей базе, см. docstring emex.py) — на обычный
    # текстовый запрос магазин просто не запрашивается (не тратим бюджет
    # rate-limit/кэша на заведомо нулевой результат).
    if not _looks_like_article_query(query):
        store_keys = [s for s in store_keys if s not in ARTICLE_ONLY_STORES]
    brand_dictionary = await get_manufacturer_brand_dictionary(db) if db is not None else None
    cleaned_query = clean_query(query, brand_dictionary=brand_dictionary)
    parsed = parse_query(query, brand_dictionary=brand_dictionary)

    async with httpx.AsyncClient(timeout=httpx.Timeout(PER_STORE_TIMEOUT_SECONDS)) as http:
        client = _StoreHttpClient(http)
        results = await asyncio.gather(*(
            _search_one_store(client, key, cleaned_query, limit_per_store) for key in store_keys
        ))

    all_offers: list[StoreOffer] = []
    stores_meta: list[dict] = []
    for r in results:
        all_offers.extend(r["offers"])
        stores_meta.append({
            "key": r["key"],
            "name": _STORE_DISPLAY_NAMES.get(r["key"], r["key"]),
            "status": r["status"],
            "count": r["count"],
            "ms": r["ms"],
        })

    all_offers.sort(key=lambda o: _rank_offer(o, parsed))

    # Отбрасываем предложения без совпадения с запросом (QA 29.10.2026,
    # см. docstring relevance.py) — нишевые магазины (promalper/ice_age/
    # medtehno) на нераспознанный запрос отдают СЛУЧАЙНЫЕ товары своей
    # популярной выдачи. count в stores[] — ПОСЛЕ этого фильтра (не из
    # сырого ответа адаптера r["count"] выше — тот остаётся только для
    # диагностики таймаута/лимита частоты, не для показа пользователю).
    all_offers = await filter_relevant_offers(all_offers, parsed, db)
    counts_after_filter: dict[str, int] = {}
    for o in all_offers:
        counts_after_filter[o.store_key] = counts_after_filter.get(o.store_key, 0) + 1
    for meta in stores_meta:
        meta["count"] = counts_after_filter.get(meta["key"], 0)

    return {
        "query_sent": cleaned_query,
        "offers": all_offers,
        "stores": stores_meta,
    }
