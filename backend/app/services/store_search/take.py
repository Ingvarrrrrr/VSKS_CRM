"""POST /api/products/store-take — «Взять» предложение живого поиска в
каталог (этап 2, вариант А, план .planning/quick/2026-10-27-live-search/
PLAN.md «Этап 2» + жалоба владельца 29.10.2026 «нет кнопки выбрать товар из
магазина»). Отдельный модуль (ПРАВИЛО №5) — роутер store_search.py только
валидирует вход и зовёт take_offer().

ПРАВИЛО №8 п.4 (деньги считает сервер): браузер присылает ТОЛЬКО
{store_key, url, query} — цену/название/фото/характеристики сервер берёт из
своего кэша поиска/повторного похода в магазин (find_cached_offer,
app/services/store_search/service.py), никогда из тела запроса.

Дедуп (ПРАВИЛО №6, один товар — одна карточка):
  1. уже есть ProductPriceHistory.source_ref == url этого же товара → берём
     его product_id;
  2. иначе, если есть и контрагент-магазин, и store_article предложения —
     тот же критерий (contractor_id, store_article), что использует импорт
     каталога (app.services.products_import_match.load_candidates_by_store_
     article, ПРАВИЛО №6 — второй критерий сопоставления не пишем);
  3. иначе — создаём новый Product (общий каталог, org_id=NULL, память
     проекта project_products_catalog_shared.md).

Цена (ПРАВИЛО №6, «найди, кто вызывает record_price_point, и повтори» —
тот же парный вызов, что products_import_apply.py использует для новых
товаров): record_price_point() пишет строку истории С ЗАЩИТОЙ ОТ ПОВТОРА
(contractor_id+price+collected_at+store_article — повторное «Взять» того же
предложения в тот же день не плодит вторую строку), затем
actualize_product_price(write_history=False) — ОН ЖЕ единственный писатель
Product.price/price_updated_at/price_source/price_source_ref — выставляет
«текущую» цену товара, не вставляя вторую строку истории (иначе её вставил
бы уже record_price_point выше).

Источник цены — "store" (не "import": владелец, 29.10.2026 — подпись должна
читаться «магазин kuvalda.ru», не «импорт kuvalda.ru», см.
VALID_PRICE_SOURCES/PRICE_SOURCE_LABELS, ПРАВИЛО №6).

Права — тот же уровень, что у создания товара из строки закупки/обычного
POST /api/products/ (только вход, get_current_user, без доп. роли) — владелец
явно потребовал «не строже», иначе сотрудник в заявке не сможет взять товар.
Кто занёс — current_user из токена (created_by в истории цены), store_key/
url/query из тела НИКОГДА не определяют личность.

Довизит за характеристиками/описанием/артикулом/картинкой (30.10.2026,
задача «перенос разбора страницы товара в бэкенд»): для магазинов, у
которых есть backend/app/services/store_pages/<магазин>.py (ПРАВИЛО №6,
тот же парсер, что у офлайн-сборщика tools/harvest) — используется он;
для остальных (avtoall/chipdip/emex — их харвест-сборщик трогать нельзя,
см. docstring store_pages/__init__.py) — общий JSON-LD-разбор
app/services/store_search/price_from_product_page.py. Отказ довизита
(таймаут/4xx/5xx/не распарсилось) — best-effort, товар всё равно создаётся
с тем, что было в offer (ПРАВИЛО №8 п.6). Характеристики/описание товара,
который УЖЕ существовал (повторное «Взять»), дозаполняются, только если
были пусты ИЛИ новые полнее (длиннее/больше характеристик) — не затираем
более полные данные более бедными (ПРАВИЛО, см. _merge_text/
_merge_characteristics ниже).

Цены того же товара в ДРУГИХ магазинах (план, «Этап 2, вариант А» — задача
«цены того же товара в других магазинах», 30.10.2026) — выполняется В ФОНЕ
ПОСЛЕ commit, см. app/services/store_search/cross_store_prices.py
(schedule_cross_store_price_lookup); не задерживает ответ этого эндпоинта."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import DEFAULT_PRODUCT_CATEGORY, Product
from app.models.product_price_history import ProductPriceHistory
from app.models.user import User
from app.services.catalog_gala.stores import store_for_domain
from app.services.contractor_resolve import find_or_create_contractor
from app.services.price_actualization import actualize_product_price, record_price_point
from app.services.product_characteristics_parse import _separate_unit
from app.services.product_name_signature import build_signature, grouping_key, match
from app.services.product_photo_autofetch import schedule_photo_fetch
from app.services.product_query_parse import get_manufacturer_brand_dictionary
from app.services.products_import_match import (
    load_candidates_by_brand_article,
    load_candidates_by_store_article,
)
from app.services.products_import_match_name_model import load_name_model_candidates
from app.services.store_pages import get_parser as get_store_page_parser
from app.services.store_pages import product_page_fetch_url as get_store_page_fetch_url
from app.services.store_search.base import StoreOffer
from app.services.store_search.cross_store_prices import schedule_cross_store_price_lookup
from app.services.store_search.price_from_product_page import extract_product_details
from app.services.store_search.registry import ADAPTERS
from app.services.store_search.service import DEFAULT_HEADERS, find_cached_offer
from app.utils.safe_url import UnsafeUrlError, assert_safe_url

STORE_PRICE_SOURCE = "store"

# Довизит за характеристиками/описанием/картинкой со страницы товара —
# best-effort, не должен тормозить «Взять» дольше, чем обычный поиск в одном
# магазине (service.PER_STORE_TIMEOUT_SECONDS, ПРАВИЛО №6 — то же число, не
# свой лимит).
_DETAIL_VISIT_TIMEOUT_SECONDS = 5.0


def _host_matches_domain(url: str, domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    domain = (domain or "").lower()
    return bool(host) and bool(domain) and (host == domain or host.endswith("." + domain))


def _jsonld_brand_to_name(raw) -> Optional[str]:
    """jsonld_brand у store_pages-модулей бывает строкой ИЛИ JSON-LD узлом
    {"@type":"Brand","name":"MAKITA"} (kuvalda/regard) — один разбор на оба
    случая, не второй по каждому вызывающему месту."""
    if isinstance(raw, dict):
        raw = raw.get("name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _normalize_store_page_result(raw: dict) -> dict:
    """Приводит разный набор полей, который возвращают
    backend/app/services/store_pages/<магазин>.py (каждый магазин несёт
    свои названия полей, см. докстринг каждого модуля), к ОДНОЙ форме,
    которую понимает take_offer(): {price, image_url, description, article,
    manufacturer, characteristics}. Контракт — тот же, что у
    price_from_product_page.extract_product_details()."""
    photos = raw.get("photos") or []
    image_url = raw.get("image_url") or (photos[0] if photos else None)
    article = (
        raw.get("manufacturer_article")
        or raw.get("store_sku")
        or raw.get("store_article")
    )
    manufacturer = _jsonld_brand_to_name(raw.get("jsonld_brand")) or raw.get("brand")
    return {
        "price": raw.get("price"),
        "image_url": image_url,
        "description": raw.get("description"),
        "article": article,
        "manufacturer": manufacturer,
        "characteristics": _force_in_description(raw.get("characteristics") or []),
    }


def _force_in_description(characteristics: list) -> list:
    """tools/harvest/stores/*.py (и, соответственно,
    backend/app/services/store_pages/*.py, перенесённые отсюда) пишут
    КАЖДУЮ характеристику с `"in_description": False` — для офлайн-сборщика
    каталога это намеренно (служебный флаг решает совсем другой пайплайн
    bulk-импорта, не этот). Но правило проекта для карточки товара
    («описание ДОЛЖНО содержать все технические параметры», см. задание и
    item_tz.py/build_tech_description) требует ОБРАТНОГО для «Взять»:
    характеристики со страницы товара — это и есть техническое описание,
    когда у товара нет своего текста `description`, поэтому здесь (и только
    здесь, не в самих store_pages-модулях — у них другой вызывающий)
    принудительно включаем in_description=True на каждой.
    Если единица не отделена ("0.1 кг"), _separate_unit разделяет её на value и unit."""
    out = []
    for c in characteristics:
        if not (isinstance(c, dict) and (c.get("name") or "").strip() and (c.get("value") or "").strip()):
            continue
        val = str(c.get("value") or "").strip()
        unit = str(c.get("unit") or "").strip() or None
        if not unit:
            val_part, unit_part = _separate_unit(val)
            val = val_part
            unit = unit_part
        out.append({
            **c,
            "value": val,
            "unit": unit,
            "in_description": True,
        })
    return out


async def _visit_product_page_best_effort(url: str, store_key: str) -> dict:
    """Довизит за описанием/артикулом/брендом/картинкой/характеристиками —
    любая ошибка (таймаут/4xx/5xx/не распарсилось) молча проглатывается,
    вызывающий код просто остаётся с тем, что было в предложении поиска
    (ПРАВИЛО №8 п.6: отказ ОДНОГО довизита не должен ронять «Взять»).

    Разбор — backend/app/services/store_pages/<store_key>.py, если он есть
    (ПРАВИЛО №6, тот же код, что у офлайн-сборщика tools/harvest); иначе —
    общий JSON-LD-разбор price_from_product_page.extract_product_details
    (avtoall/chipdip/emex, см. докстринг store_pages/__init__.py)."""
    try:
        fetch_url = get_store_page_fetch_url(store_key, url)
        async with httpx.AsyncClient(timeout=httpx.Timeout(_DETAIL_VISIT_TIMEOUT_SECONDS)) as http:
            resp = await http.get(fetch_url, headers=DEFAULT_HEADERS, follow_redirects=True)
        if not (200 <= resp.status_code < 300):
            return {}
        parser = get_store_page_parser(store_key)
        if parser is not None:
            return _normalize_store_page_result(parser(resp.text, url) or {})
        generic = extract_product_details(resp.text)
        generic["characteristics"] = _force_in_description(generic.get("characteristics") or [])
        return generic
    except Exception:
        return {}


async def _resolve_store_contractor_id(db: AsyncSession, domain: str) -> Optional[int]:
    """Контрагент-магазин по справочнику catalog_gala/stores.py (ПРАВИЛО №6 —
    тот же единственный справочник и резолвер find_or_create_contractor, что
    использует импорт каталога, app/services/products_import_apply.py). Домена
    нет в справочнике (магазин подключён к живому поиску, но не был источником
    загруженного каталога) — None, запись истории просто идёт без
    contractor_id (dedup по store_article в этом случае не сработает — см.
    docstring модуля, пункт 2 дедупа)."""
    info = store_for_domain(domain)
    if not info:
        return None
    return await find_or_create_contractor(
        db, info.get("name"), info.get("inn"),
        match_by_name=False, ogrn=info.get("ogrn"), org_type=info.get("org_type"),
    )


async def _find_existing_product(
    db: AsyncSession,
    offer: StoreOffer,
    contractor_id: Optional[int],
    *,
    manufacturer: Optional[str] = None,
    article: Optional[str] = None,
    characteristics: Optional[list] = None,
) -> Optional[Product]:
    # 1) та же страница товара уже когда-то попадала в историю цены.
    existing_id = (await db.execute(
        select(ProductPriceHistory.product_id)
        .where(ProductPriceHistory.source_ref == offer.url)
        .order_by(ProductPriceHistory.product_id)
        .limit(1)
    )).scalar_one_or_none()
    if existing_id is not None:
        return await db.get(Product, existing_id)

    # 2) тот же магазин + тот же номер товара магазина (ПРАВИЛО №6 — тот же
    # критерий, что использует импорт каталога).
    store_art = article or offer.store_article
    if contractor_id is not None and store_art:
        candidates = await load_candidates_by_store_article(db, [(contractor_id, store_art)])
        product = candidates.get((contractor_id, store_art))
        if product is not None:
            return product

    # 3) тот же бренд + артикул производителя в другом магазине (критерий 0.5
    # products_import_match.py, ПРАВИЛО №6 — одна карточка на товар).
    eff_mfg = manufacturer or offer.manufacturer
    if eff_mfg and store_art:
        ba_map = await load_candidates_by_brand_article(db, [(eff_mfg, store_art)])
        for cands in ba_map.values():
            valid = [c for c in cands if not c.conflicts_with_row_store(contractor_id, store_art)]
            if valid:
                valid.sort(key=lambda c: (-c.history_count, c.product.id))
                return valid[0].product

    # 4) совпадение сигнатуры названия + индекса модели в другом магазине
    # (критерий 0.75 products_import_match_name_model.py, ПРАВИЛО №6):
    # когда у разных магазинов разные внутренние SKU (например, ChipDip
    # 8040965460 и AvtoAll 307792), но название, бренд, числа и модель
    # ('140SPEA041') совпадают с decision == 'auto' — сводим в одну карточку
    # с ценами двух магазинов.
    brand_dictionary = await get_manufacturer_brand_dictionary(db)
    offer_sig = build_signature(
        {
            "name": offer.name,
            "manufacturer": eff_mfg,
            "characteristics": characteristics or [],
        },
        brand_dictionary=brand_dictionary,
    )
    if offer_sig.digit_tokens:
        nm_map = await load_name_model_candidates(
            db, [offer_sig], brand_dictionary=brand_dictionary,
        )
        key = grouping_key(offer_sig)
        cands = nm_map.get(key) or [] if key is not None else []
        matched = [
            c for c in cands
            if not c.conflicts_with_row_store(contractor_id, store_art)
            and match(offer_sig, c.signature).get("decision") == "auto"
        ]
        if len(matched) == 1:
            return matched[0].product
    return None


async def take_offer(
    db: AsyncSession,
    current_user: User,
    *,
    store_key: str,
    url: str,
    query: str,
) -> tuple[Product, bool]:
    """Берёт предложение из кэша/свежего поиска (find_cached_offer) и
    заносит его в каталог (или добавляет точку цены существующему товару).
    Возвращает (product, created) — created=True только когда карточка
    только что создана (роутер использует это для текста тоста, см.
    StoreTakeOut). Коммитит сам (единственная точка входа — остальные
    мутации products.py коммитят точно так же)."""
    adapter = ADAPTERS.get(store_key)
    if adapter is None:
        raise HTTPException(400, f"Неизвестный магазин: {store_key}")

    if not _host_matches_domain(url, adapter.domain):
        raise HTTPException(400, "Ссылка не относится к этому магазину")
    try:
        assert_safe_url(url)
    except UnsafeUrlError as e:
        raise HTTPException(400, e.message) from e

    offer = await find_cached_offer(store_key, query, url, db=db)
    if offer is None:
        raise HTTPException(404, "Предложение устарело, повторите поиск")

    details = await _visit_product_page_best_effort(url, store_key)
    offer_price = details.get("price") if details.get("price") is not None else offer.price
    image_url = details.get("image_url") or offer.image_url
    description = details.get("description")
    article = details.get("article") or offer.store_article
    manufacturer = details.get("manufacturer") or offer.manufacturer
    characteristics = details.get("characteristics") or []

    contractor_id = await _resolve_store_contractor_id(db, adapter.domain)
    product = await _find_existing_product(
        db,
        offer,
        contractor_id,
        manufacturer=manufacturer,
        article=article,
        characteristics=characteristics,
    )
    created = product is None
    if created:
        product = Product(
            name=offer.name,
            category=DEFAULT_PRODUCT_CATEGORY,
            item_kind="товар",
            org_id=None,
            photo_url=image_url,
            description=description,
            manufacturer=manufacturer,
            article=article,
            characteristics=characteristics or None,
            import_note=f"Взято из живого поиска в магазинах, {offer.store_name} ({current_user.full_name or current_user.email})",
        )
        db.add(product)
        await db.flush()  # нужен product.id для ProductPriceHistory.product_id (NOT NULL)
    else:
        # Товар уже в каталоге — дозаполняем ТОЛЬКО пустые поля (как и
        # остальной import/merge в проекте, ПРАВИЛО №6 — «не затирать то, что
        # было богаче», память проекта feo_description_is_tech_params.md),
        # не перезаписываем то, что уже заведено вручную/другим источником.
        if not product.photo_url and image_url:
            product.photo_url = image_url
        if description and (not product.description or len(description) > len(product.description)):
            # Сравнение по длине (владелец, задание) — не затираем более
            # полное описание более бедным, даже если оно непусто.
            product.description = description
        if not product.manufacturer and manufacturer:
            product.manufacturer = manufacturer
        if not product.article and article:
            product.article = article
        if characteristics and len(characteristics) > len(product.characteristics or []):
            # Та же логика «не затирать более полное» — по количеству
            # распознанных характеристик (ПРАВИЛО, см. докстринг модуля).
            product.characteristics = characteristics

    # Защита от повторного «Взять» того же предложения — record_price_point
    # (дедуп по contractor_id+price+collected_at+store_article). collected_at
    # не передаём (страница магазина не несёт дату сбора) — пишется как
    # "сегодня" внутри actualize_product_price/_parse_collected_date(None)=None,
    # тот же принцип, что у ручной актуализации цены.
    await record_price_point(
        db, product,
        price=offer_price,
        source=STORE_PRICE_SOURCE,
        source_ref=offer.url,
        contractor_id=contractor_id,
        user=current_user,
        store_article=article,
    )
    # Текущая цена товара — ЕДИНСТВЕННЫЙ писатель Product.price (ПРАВИЛО №6),
    # write_history=False: строку истории уже написал (или дедупнул) вызов
    # выше, вторую здесь не вставляем.
    await actualize_product_price(
        db, product,
        price=offer_price,
        source=STORE_PRICE_SOURCE,
        source_ref=offer.url,
        contractor_id=contractor_id,
        user=current_user,
        store_article=article,
        write_history=False,
    )

    # Автодокачка фото (владелец, 29.10.2026, ПРАВИЛО №6,
    # app/services/product_photo_autofetch.py) — товар получил photo_url из
    # магазина (image_url), скачиваем в фоне, не заставляя снабженца ждать.
    # ДО commit (см. комментарий в products.py::create_product про
    # queue_after_commit/after_commit).
    schedule_photo_fetch(db, [product.id])
    # Цены ТОГО ЖЕ товара в остальных магазинах (задача «Этап 2, вариант А»,
    # 30.10.2026) — тоже в фоне, ПОСЛЕ commit (см.
    # app/services/store_search/cross_store_prices.py), не задерживает ответ.
    schedule_cross_store_price_lookup(
        db,
        product_id=product.id,
        store_key=store_key,
        query=query,
        user_id=current_user.id,
        manufacturer=manufacturer,
        manufacturer_article=article,
        characteristics=characteristics,
    )
    await db.commit()
    await db.refresh(product)
    return product, created
