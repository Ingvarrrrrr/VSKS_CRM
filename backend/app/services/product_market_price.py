"""Проверка актуальной рыночной цены товара (розница + за похожий объём).

Единственная точка логики (ПРАВИЛО №5/№6) для режима:
1) при выборе товара из каталога в закупку -> показываем актуальный ориентир;
2) при создании закупки из субсидии / ФЭО-плана -> по кнопке «Показать актуальную цену»
   актуализируем розницу (живой поиск + прямые ссылки) и считаем вторую цену за
   похожий объём (история сделок/КП в партии из product_price_stats.batch_label).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.visibility import get_account_contour_org_ids
from app.models.commercial_request import CommercialRequest, CommercialRequestOffer
from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.catalog_gala.stores import store_for_domain
from app.services.contractor_resolve import find_or_create_contractor
from app.services.price_actualization import actualize_product_price, record_price_point
from app.services.product_catalog_match import find_products_by_normalized_names
from app.services.product_name_signature import build_signature, match as match_signatures
from app.services.product_price_stats import batch_label, compute_price_stats
from app.services.product_protection import load_protected_product_ids
from app.services.product_query_parse import get_manufacturer_brand_dictionary
from app.services.product_search import ProductSearchFilters, search_products
from app.services.store_pages import get_parser as get_store_page_parser
from app.services.store_pages import product_page_fetch_url
from app.services.store_search.cross_store_prices import _norm_code, _offer_matches
from app.services.store_search.price_from_product_page import extract_product_details
from app.services.store_search.registry import ADAPTERS
from app.services.store_search.service import DEFAULT_HEADERS, search_stores
from app.utils.safe_url import UnsafeUrlError, assert_safe_url

RETAIL_STALE_DAYS = 3


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        n = float(val)
        return round(n, 2) if n > 0 else None
    except (TypeError, ValueError):
        return None


def _median_price(values: list[float]) -> Optional[float]:
    clean = sorted(v for v in values if v and v > 0)
    if not clean:
        return None
    return round(float(median(clean)), 2)


def _domain_of(url: Optional[str]) -> str:
    host = (urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _store_label(domain: str, fallback: str = "") -> str:
    info = store_for_domain(domain)
    return (info or {}).get("name") or fallback or domain or "Магазин"


async def _allowed_org_ids(db: AsyncSession, user: User) -> Optional[set[int]]:
    if user.role == "superadmin":
        return None
    if user.role == "account_owner":
        return await get_account_contour_org_ids(user, db)
    return {user.org_id} if user.org_id is not None else set()


async def _resolve_product(
    db: AsyncSession, product_id: Optional[int], item_name: Optional[str],
) -> Optional[Product]:
    if product_id is not None:
        return await db.get(Product, product_id)
    q = (item_name or "").strip()
    if not q:
        return None
    exact = await find_products_by_normalized_names(db, {q})
    if exact:
        return next(iter(exact.values()))
    candidates, _ = await search_products(db, ProductSearchFilters(q=q, limit=5))
    if not candidates:
        return None
    brand_dict = await get_manufacturer_brand_dictionary(db)
    sig_q = build_signature({"name": q}, brand_dict)
    for cand in candidates:
        sig_c = build_signature({"name": cand.name, "manufacturer": cand.manufacturer}, brand_dict)
        if match_signatures(sig_q, sig_c).get("decision") == "auto":
            return cand
    return None


async def _fetch_direct_link_offer(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    try:
        assert_safe_url(url)
        fetch_url = product_page_fetch_url(url) or url
        assert_safe_url(fetch_url)
        resp = await client.get(fetch_url, headers=DEFAULT_HEADERS)
        if not (200 <= resp.status_code < 300):
            return None
        parser = get_store_page_parser(url)
        parsed = parser(resp.text, url) if parser else extract_product_details(resp.text)
        price = _to_float((parsed or {}).get("price"))
        if not price:
            return None
        dom = _domain_of(url)
        return {
            "store_key": dom,
            "store_name": _store_label(dom, dom or "Магазин"),
            "price": price,
            "url": url,
            "is_live": True,
        }
    except (UnsafeUrlError, Exception):
        return None


async def _gather_live_offers(
    db: AsyncSession, product: Optional[Product], query_name: str,
) -> list[dict]:
    offers_by_dom: dict[str, dict] = {}
    q = ((product.name if product else None) or query_name or "").strip()

    async def _run_links() -> list[dict]:
        if not product or not isinstance(product.price_links, list):
            return []
        urls: list[str] = []
        seen_dom: set[str] = set()
        for ln in product.price_links:
            u = (ln.get("url") if isinstance(ln, dict) else None) or ""
            u = u.strip()
            d = _domain_of(u)
            if u.startswith("http") and d and d not in seen_dom:
                seen_dom.add(d)
                urls.append(u)
            if len(urls) >= 3:
                break
        if not urls:
            return []
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            res = await asyncio.gather(*(_fetch_direct_link_offer(client, u) for u in urls))
        return [r for r in res if r is not None]

    async def _run_stores() -> list[dict]:
        if len(q) < 3:
            return []
        brand_dict = await get_manufacturer_brand_dictionary(db)
        own_sig = build_signature({
            "name": q,
            "manufacturer": product.manufacturer if product else None,
            "characteristics": (product.characteristics or []) if product else [],
        }, brand_dict)
        own_brand_norm = _norm_code((product.manufacturer if product else None) or own_sig.brand)
        own_art_norm = _norm_code(product.article if product else None)
        res = await search_stores(q, limit_per_store=6, db=db)
        found: list[dict] = []
        for off in res.get("offers") or []:
            if not off.price or float(off.price) <= 0:
                continue
            if own_brand_norm:
                ok = _offer_matches(off, own_art_norm, own_brand_norm, own_sig, brand_dict)
            else:
                off_sig = build_signature({"name": off.name, "manufacturer": off.manufacturer}, brand_dict)
                ok = match_signatures(own_sig, off_sig).get("decision") == "auto"
            if ok:
                found.append({
                    "store_key": off.store_key,
                    "store_name": off.store_name,
                    "price": round(float(off.price), 2),
                    "url": off.url,
                    "store_article": off.store_article,
                    "is_live": True,
                })
        return found

    link_res, store_res = await asyncio.gather(_run_links(), _run_stores())
    for item in store_res + link_res:
        dom = _domain_of(item.get("url")) or item.get("store_key") or item["store_name"]
        if dom not in offers_by_dom:
            offers_by_dom[dom] = item
    return list(offers_by_dom.values())


def summarize_retail_offers(offers: list[dict], fallback_price: Optional[float] = None) -> dict:
    prices = [float(o["price"]) for o in offers if o.get("price") and float(o["price"]) > 0]
    if not prices and fallback_price and fallback_price > 0:
        prices = [float(fallback_price)]
    if not prices:
        return {"retail_price": None, "retail_min": None, "retail_max": None, "retail_count": 0}
    return {
        "retail_price": _median_price(prices),
        "retail_min": round(min(prices), 2),
        "retail_max": round(max(prices), 2),
        "retail_count": len(offers) or len(prices),
    }


def resolve_volume_pricing(
    *,
    contract_prices: list[float],
    stats: Any,
    quantity: Optional[float],
    unit: Optional[str],
    retail_summary: dict,
) -> dict:
    batch = batch_label(quantity if quantity and quantity >= 1 else 1) or "1-9"
    unit_suffix = f" {unit}" if unit else ""

    if contract_prices:
        avg_v = round(sum(contract_prices) / len(contract_prices), 2)
        return {
            "volume_price": avg_v,
            "volume_batch": batch,
            "volume_basis_count": len(contract_prices),
            "volume_source": "contracts",
            "volume_note": f"по {len(contract_prices)} дог./КП (партия {batch}{unit_suffix})",
        }
    if stats is not None and stats.avg_price is not None and stats.level in ("region_batch", "nearest_batch", "batch"):
        return {
            "volume_price": round(float(stats.avg_price), 2),
            "volume_batch": stats.batch or batch,
            "volume_basis_count": int(stats.basis_count or 0),
            "volume_source": "history_batch",
            "volume_note": f"история партия {stats.batch or batch}{unit_suffix} ({stats.basis_count} поз.)",
        }
    r_min = retail_summary.get("retail_min")
    r_cnt = retail_summary.get("retail_count") or 0
    if r_min is not None and r_cnt >= 2:
        return {
            "volume_price": r_min,
            "volume_batch": batch,
            "volume_basis_count": r_cnt,
            "volume_source": "min_retail",
            "volume_note": f"мин. среди {r_cnt} маг. (сделок на {batch}{unit_suffix} пока нет)",
        }
    if retail_summary.get("retail_price") is not None:
        return {
            "volume_price": retail_summary["retail_price"],
            "volume_batch": batch,
            "volume_basis_count": r_cnt,
            "volume_source": "retail_fallback",
            "volume_note": f"розничный ориентир (сделок на {batch}{unit_suffix} пока нет)",
        }
    return {
        "volume_price": None,
        "volume_batch": batch,
        "volume_basis_count": 0,
        "volume_source": "none",
        "volume_note": f"нет сделок для объёма {batch}{unit_suffix}",
    }


async def _persist_live_points(
    db: AsyncSession, product: Product, live_offers: list[dict], user: User,
) -> None:
    wrote_any = False
    for off in live_offers:
        dom = _domain_of(off.get("url"))
        s_info = store_for_domain(dom) if dom else None
        cid = None
        if s_info:
            cid = await find_or_create_contractor(
                db, s_info["name"], inn=s_info["inn"], ogrn=s_info["ogrn"], org_type=s_info["org_type"],
            )
        wrote = await record_price_point(
            db, product, price=Decimal(str(off["price"])), source="store",
            source_ref=off.get("url"), contractor_id=cid, user=user,
            store_article=off.get("store_article"),
        )
        wrote_any = wrote_any or wrote

    protected_ids = await load_protected_product_ids(db)
    if product.id not in protected_ids and live_offers:
        med = _median_price([float(o["price"]) for o in live_offers])
        if med:
            best_off = min(live_offers, key=lambda x: abs(float(x["price"]) - med))
            await actualize_product_price(
                db, product, price=Decimal(str(med)), source="store",
                source_ref=best_off.get("url"), user=user, write_history=False,
            )
            wrote_any = True
    if wrote_any:
        await db.commit()


async def check_market_price(
    db: AsyncSession,
    *,
    current_user: User,
    product_id: Optional[int] = None,
    item_name: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    refresh_live: bool = False,
) -> dict:
    product = await _resolve_product(db, product_id, item_name)
    is_stale = True
    if product and product.price_updated_at:
        updated_naive = product.price_updated_at.replace(tzinfo=None)
        is_stale = updated_naive < (datetime.utcnow() - timedelta(days=RETAIL_STALE_DAYS))

    live_offers: list[dict] = []
    if refresh_live or (product is not None and is_stale):
        live_offers = await _gather_live_offers(db, product, item_name or "")
        if product is not None and live_offers:
            await _persist_live_points(db, product, live_offers, current_user)

    offers_map: dict[str, dict] = {}
    for lo in live_offers:
        offers_map[_domain_of(lo.get("url")) or lo["store_name"]] = lo

    hist_rows = []
    allowed_orgs = await _allowed_org_ids(db, current_user)
    contract_prices: list[float] = []
    target_batch = batch_label(quantity if quantity and quantity >= 1 else 1)

    if product is not None:
        raw_hist = (await db.execute(
            select(ProductPriceHistory, Contractor.name, Subsidy.org_id, Contract.price_shared)
            .outerjoin(Contractor, Contractor.id == ProductPriceHistory.contractor_id)
            .outerjoin(PurchaseItem, PurchaseItem.id == ProductPriceHistory.purchase_item_id)
            .outerjoin(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id)
            .outerjoin(Contract, Contract.id == Purchase.contract_id)
            .where(ProductPriceHistory.product_id == product.id)
            .order_by(ProductPriceHistory.collected_at.desc(), ProductPriceHistory.id.desc())
        )).all()

        for h, c_name, p_org_id, c_price_shared in raw_hist:
            if h.source == "contract" and allowed_orgs is not None:
                is_shared = bool(c_price_shared or product.price_shared)
                if not is_shared and (p_org_id is not None and p_org_id not in allowed_orgs):
                    continue
            hist_rows.append(h)
            if h.source in ("store", "import", "monitoring") and h.price and float(h.price) > 0:
                dom = _domain_of(h.source_ref) or (f"c:{h.contractor_id}" if h.contractor_id else "")
                if dom and dom not in offers_map:
                    offers_map[dom] = {
                        "store_key": dom,
                        "store_name": c_name or _store_label(dom, dom),
                        "price": round(float(h.price), 2),
                        "url": h.source_ref,
                        "is_live": False,
                    }

        if isinstance(product.price_links, list):
            for ln in product.price_links:
                if not isinstance(ln, dict):
                    continue
                u = (ln.get("url") or "").strip()
                lp = _to_float(ln.get("price"))
                dom = _domain_of(u)
                if dom and lp and dom not in offers_map:
                    offers_map[dom] = {
                        "store_key": dom,
                        "store_name": _store_label(dom, dom),
                        "price": lp,
                        "url": u,
                        "is_live": False,
                    }

        ci_rows = (await db.execute(
            select(ContractItem.unit_price, ContractItem.quantity, Subsidy.org_id, Contract.price_shared)
            .join(Purchase, Purchase.id == ContractItem.purchase_id)
            .outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id)
            .outerjoin(Contract, Contract.id == Purchase.contract_id)
            .where(
                ContractItem.product_id == product.id,
                ContractItem.unit_price.isnot(None),
                Purchase.stopped_at.is_(None),
                Purchase.status != "cancelled",
            )
        )).all()
        for up, qty, org_id, c_price_shared in ci_rows:
            is_shared = bool(c_price_shared or product.price_shared)
            if allowed_orgs is not None and not is_shared and (org_id is not None and org_id not in allowed_orgs):
                continue
            p_val = _to_float(up)
            if p_val and batch_label(qty) == target_batch:
                contract_prices.append(p_val)

        cr_rows = (await db.execute(
            select(CommercialRequestOffer.unit_price, Subsidy.org_id)
            .join(CommercialRequest, CommercialRequest.id == CommercialRequestOffer.request_id)
            .join(Purchase, Purchase.id == CommercialRequest.purchase_id)
            .outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id)
            .where(
                CommercialRequestOffer.product_id == product.id,
                CommercialRequestOffer.unit_price.isnot(None),
                Purchase.stopped_at.is_(None),
            )
        )).all()
        for up, org_id in cr_rows:
            if allowed_orgs is not None and org_id not in allowed_orgs:
                continue
            p_val = _to_float(up)
            if p_val and target_batch in ("1-9", "10-99"):
                contract_prices.append(p_val)

    org_region = None
    if current_user.org_id is not None:
        org_region = (await db.execute(
            select(Organization.region).where(Organization.id == current_user.org_id)
        )).scalar_one_or_none()

    eff_unit = unit or (product.unit if product else None)
    stats = compute_price_stats(
        hist_rows, target_region=org_region, quantity=quantity or 1, product_unit=eff_unit,
    ) if hist_rows else None

    offers = sorted(offers_map.values(), key=lambda x: (not x.get("is_live"), float(x["price"])))
    retail = summarize_retail_offers(offers, _to_float(product.price if product else None))
    volume = resolve_volume_pricing(
        contract_prices=contract_prices,
        stats=stats,
        quantity=quantity,
        unit=eff_unit,
        retail_summary=retail,
    )
    return {
        "product_id": product.id if product else product_id,
        "product_name": product.name if product else item_name,
        "catalog_price": _to_float(product.price if product else None),
        "live_refreshed": bool(live_offers),
        **retail,
        **volume,
        "offers": offers[:6],
    }
