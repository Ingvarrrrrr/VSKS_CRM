"""Фон после «Взять» (POST /api/products/store-take, этап 2, вариант А,
задача «цены того же товара в других магазинах», владелец 29-30.10.2026):
находит ТОТ ЖЕ товар в ОСТАЛЬНЫХ магазинах живого поиска и дописывает их
цены точками истории (record_price_point) — БЕЗ создания новых Product
(ПРАВИЛО №6, одна карточка на товар).

Отложенный запуск — queue_after_commit (app/services/notify_after_commit.py),
ТОТ ЖЕ единственный механизм «выполнить после реального commit, в своей
сессии БД», которым это же take.py уже пользуется для docачки фото
(schedule_photo_fetch → product_photo_autofetch.py). Не заводим FastAPI
BackgroundTasks: в проекте он встречается только в routers/publications.py
(иной случай — там нет своей сессии БД и не нужно ждать commit); здесь
критично и ждать commit (иначе фон увидит товар, которого ещё нет в БД —
rollback запроса откатил бы и создание товара), и работать в НОВОЙ
сессии (сессия исходного запроса закрывается сразу после ответа) — это
ровно то, что queue_after_commit/async_session уже решают, второй механизм
не нужен.

«Тот же товар» — СТРОГО точное совпадение (ПРАВИЛО: никакого fuzzy,
feedback_dedup_exact_only.md), один из:
  (а) нормализованный артикул производителя совпал буквально
      (fold_brand_or_code + только буквы/цифры — тот же приём, что
      product_name_signature._brand_compare_key использует для кода/бренда,
      ПРАВИЛО №6, второй алгоритм нормализации не пишем) — И бренд совпал
      буквально той же нормализацией;
  (б) app.services.product_name_signature.match() вернул decision == "yes"
      (тот же алгоритм, что сведение каталога при импорте/дедупе —
      ПРАВИЛО №6, второй не пишем) — И бренд совпал буквально (match() уже
      требует этого внутри себя, когда бренд известен с обеих сторон;
      здесь требование продублировано явно, чтобы совпадение НИКОГДА не
      прошло с неизвестным/разным брендом, как явно потребовал владелец).

Источники кандидатов — ПЕРЕИСПОЛЬЗУЮТ app.services.store_search.service
целиком (ПРАВИЛО №6, тот же кэш/лимит частоты, второй поход в магазин не
заводим): один вызов search_stores() тем же запросом, которым был найден
исходный offer, по всем магазинам кроме того, из которого товар уже взят.
Суммарный бюджет времени — ~6 секунд (asyncio.wait_for), чтобы фон не
работал бесконечно, если какой-то магазин подвис."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from app.database import async_session
from app.models.product import Product
from app.models.user import User
from app.services.brand_code_fold import fold_brand_or_code
from app.services.notify_after_commit import queue_after_commit
from app.services.price_actualization import record_price_point
from app.services.product_name_signature import build_signature, match
from app.services.product_query_parse import get_manufacturer_brand_dictionary
from app.services.store_search.registry import ADAPTERS
from app.services.store_search.service import search_stores

# Импорт take.py ОТЛОЖЕН (внутри _run, не на уровне модуля) — take.py сам
# импортирует schedule_cross_store_price_lookup отсюда (вызывает ПЕРЕД
# db.commit(), см. его докстринг), импорт на уровне модуля в обе стороны
# дал бы циклический импорт.

logger = logging.getLogger(__name__)

TOTAL_BUDGET_SECONDS = 6.0

_NON_ALNUM_RE = re.compile(r"[^0-9a-zа-яё]")


def _norm_code(text: Optional[str]) -> Optional[str]:
    """Нормализация кода/бренда для СТРОГОГО (не fuzzy) сравнения — свёртка
    гомоглифов/регистра (fold_brand_or_code) + только буквы/цифры, тот же
    приём, что product_name_signature._brand_compare_key (ПРАВИЛО №6)."""
    if not text:
        return None
    norm = _NON_ALNUM_RE.sub("", fold_brand_or_code(text))
    return norm or None


def schedule_cross_store_price_lookup(
    db,
    *,
    product_id: int,
    store_key: str,
    query: str,
    user_id: int,
    manufacturer: Optional[str],
    manufacturer_article: Optional[str],
    characteristics: Optional[list],
) -> None:
    """Поставить поиск цены ЭТОГО ЖЕ товара в остальных магазинах в очередь —
    выполнится ПОСЛЕ commit (см. докстринг модуля). Вызывать из
    take_offer() ДО db.commit(), как и schedule_photo_fetch рядом."""
    queue_after_commit(db, lambda: _run_with_budget(
        product_id=product_id, store_key=store_key, query=query, user_id=user_id,
        manufacturer=manufacturer, manufacturer_article=manufacturer_article,
        characteristics=characteristics,
    ))


async def _run_with_budget(
    *, product_id: int, store_key: str, query: str, user_id: int,
    manufacturer: Optional[str], manufacturer_article: Optional[str],
    characteristics: Optional[list],
) -> None:
    try:
        await asyncio.wait_for(
            _run(
                product_id=product_id, store_key=store_key, query=query, user_id=user_id,
                manufacturer=manufacturer, manufacturer_article=manufacturer_article,
                characteristics=characteristics,
            ),
            timeout=TOTAL_BUDGET_SECONDS,
        )
    except Exception:
        logger.warning(
            "cross_store_prices: product_id=%s сбой фона поиска цен в других магазинах",
            product_id, exc_info=True,
        )


def _offer_matches(
    offer, own_article_norm: Optional[str], own_brand_norm: Optional[str], own_sig, brand_dictionary,
) -> bool:
    """brand_dictionary — см. докстринг _run ниже: offer.manufacturer часто
    пуст (chipdip/avtoall/emex не несут структурированного бренда ни в
    выдаче поиска, ни на странице товара, см. докстринг _run) — тогда бренд
    предложения ищем В ТЕКСТЕ НАЗВАНИЯ тем же словарём/механизмом
    (ManufacturerBrandDictionary.find_in_name), что build_signature уже умеет
    делать для СВОЕГО каталога (ПРАВИЛО №6 — тот же приём, второй не пишем)."""
    offer_brand = offer.manufacturer
    if not offer_brand and brand_dictionary is not None:
        offer_brand = brand_dictionary.find_in_name(offer.name or "")
    offer_brand_norm = _norm_code(offer_brand)
    brand_confirmed = bool(own_brand_norm) and bool(offer_brand_norm) and own_brand_norm == offer_brand_norm
    if not brand_confirmed:
        # ОБЯЗАТЕЛЬНО совпадение бренда в ОБОИХ случаях — ни артикул, ни
        # сигнатура названия сами по себе не решают (владелец, задание).
        return False

    if own_article_norm and offer.store_article:
        if _norm_code(offer.store_article) == own_article_norm:
            return True

    offer_sig = build_signature(
        {"name": offer.name, "manufacturer": offer_brand, "characteristics": []}, brand_dictionary,
    )
    decision = match(own_sig, offer_sig)
    # "auto" — ЕДИНСТВЕННОЕ положительное значение match() (ПРАВИЛО №6, тот
    # же критерий, что products_import_match_name_model.py/product_similar.py
    # используют для «уверенно, тот же товар»; match() никогда не возвращает
    # "yes" — найдено QA живого поиска 30.10.2026: этот код сравнивал decision
    # с "yes" и поэтому НИКОГДА не принимал совпадение по сигнатуре названия,
    # даже когда бренд/число/вид совпадали буквально — срабатывал только
    # пункт (а) дедупа по точному артикулу выше, а разные магазины почти
    # всегда несут РАЗНЫЕ собственные SKU, не производственный артикул).
    # "check" (неоднозначно, требует проверки человеком) НЕ принимается —
    # этот фон не задаёт вопросов, только точные совпадения.
    return decision.get("decision") == "auto"


async def _run(
    *, product_id: int, store_key: str, query: str, user_id: int,
    manufacturer: Optional[str], manufacturer_article: Optional[str],
    characteristics: Optional[list],
) -> None:
    from app.services.store_search.take import _resolve_store_contractor_id

    async with async_session() as db:
        product = await db.get(Product, product_id)
        user = await db.get(User, user_id)
        if product is None or user is None:
            return

        # Словарь брендов своей БД (ПРАВИЛО №6 — ТОТ ЖЕ источник, что
        # product_query_parse.parse_query/service.search_stores уже
        # используют): нужен ЗДЕСЬ тоже — manufacturer предложения/товара
        # часто пуст (chipdip/avtoall/emex не дают структурированного бренда
        # ни в выдаче поиска, ни со страницы товара — нет store_pages-
        # парсера, см. take.py), а бренд при этом ЕСТЬ прямо в названии
        # ("Перфоратор Makita HR2652"). Без словаря own_brand_norm/
        # offer_brand_norm оставались пустыми ВСЕГДА для таких магазинов —
        # найдено QA живого поиска 30.10.2026: «Взять» из chipdip не
        # приносило ни одной цены из других магазинов, хотя они реально
        # есть (бренд совпадает буквально) — ОБЯЗАТЕЛЬНОЕ совпадение бренда
        # (см. _offer_matches) просто не могло сработать с пустыми строками.
        brand_dictionary = await get_manufacturer_brand_dictionary(db)
        own_sig = build_signature({
            "name": product.name,
            "manufacturer": manufacturer or product.manufacturer,
            "characteristics": characteristics or product.characteristics or [],
        }, brand_dictionary)
        own_brand_norm = _norm_code(manufacturer or product.manufacturer) or _norm_code(own_sig.brand)
        own_article_norm = _norm_code(manufacturer_article or product.article)
        if not own_brand_norm:
            # Бренд не распознан вообще (ни в поле, ни по словарю в тексте
            # названия) — сравнивать не с чем (ОБЯЗАТЕЛЬНО совпадение бренда
            # в обоих критериях), фон бессмысленен.
            return

        other_keys = [k for k in ADAPTERS if k != store_key]
        if not other_keys:
            return
        result = await search_stores(query, stores=other_keys, limit_per_store=10, db=db)
        offers = result.get("offers") or []

        added_stores: list[str] = []
        for offer in offers:
            if offer.store_key == store_key or offer.price is None:
                continue
            if not _offer_matches(offer, own_article_norm, own_brand_norm, own_sig, brand_dictionary):
                continue
            adapter = ADAPTERS.get(offer.store_key)
            contractor_id = await _resolve_store_contractor_id(db, adapter.domain) if adapter else None
            wrote = await record_price_point(
                db, product,
                price=offer.price,
                source="store",
                source_ref=offer.url,
                contractor_id=contractor_id,
                user=user,
                store_article=offer.store_article,
            )
            if wrote:
                added_stores.append(offer.store_key)
        if added_stores:
            await db.commit()
            logger.info(
                "cross_store_prices: product_id=%s цены добавлены из %s",
                product_id, ", ".join(added_stores),
            )
