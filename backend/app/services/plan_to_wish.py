"""«Из плана — в заявку» (plan-to-wish): один клик на плановой позиции ФЭО
(FeoPlannedItem) заводит заявку (Wish) на её остаток, с подсказками товара из
каталога. Сервисный слой для тонкого роутера app/routers/plan_to_wish.py.

ПРАВИЛО №6 — источники, которые эта логика ЧИТАЕТ, а не пересчитывает заново:
  - остаток плановой позиции — ТОЛЬКО app.services.feo_plan_fact.planned_item_consumption
    (тот же источник, что и GET /feo-planned-items/residuals, GET
    /feo-categories/plan-positions — единственное место, считающее used/used_qty/
    linked_purchase_ids по PurchaseItem.feo_planned_item_id);
  - сопоставление по имени (score/normalize/SCORE_AUTO/SCORE_SUGGEST) — ТОЛЬКО
    app.services.text_match (через app.routers.products_match._score_product_candidates,
    тот же SELECT+bulk_match+freshness, что у POST /products/match, не вторая копия);
  - суммы позиций (total_price = quantity × unit_price) — ТОЛЬКО
    app.services.item_amounts.line_total;
  - создание заявки — ТОЛЬКО app.routers.wishes.create_wish (вызывается напрямую с
    готовыми db/current_user/WishCreate — не копия его тела).

by_type — отдельный, сознательно НЕ fuzzy механизм (спецификация задачи): точное
совпадение normalize(Product.product_type) с normalize(имени плановой позиции)
целиком ИЛИ с любым её словом длиной ≥4 после text_match.tokenize. Использует
ту же normalize/tokenize, что и text_match (единая точка нормализации), просто
другое правило сравнения — второй механизм СЧЁТА score не заводится, score
кандидата by_type считается той же text_match.score(...), что и everywhere else.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.dictionaries import STATUS_LABELS
from app.services.feo_plan_fact import planned_item_consumption
from app.services.item_amounts import line_total
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.product_snapshot import resolve_photo_url
from app.services.text_match import normalize, tokenize, score as text_score, SCORE_AUTO, SCORE_SUGGEST


_BY_TYPE_MIN_WORD_LEN = 4


def _candidate_from_type_row(row, score_value: float, freshness_ctx) -> dict:
    """Тот же candidate-shape, что и _score_product_candidates в products_match.py —
    но строится из ЛЁГКОГО column-select (см. by_type ниже), не из полного ORM-
    объекта Product: тот же приём, что и в products_match._score_product_candidates
    (Product.photo_data не выбирается вовсе, только boolean-флаг has_bytea_photo)
    — деферренная колонка на ORM-инстансе внутри синхронного list-comprehension
    иначе триггерит ленивую подгрузку и падает MissingGreenlet вне await-контекста.
    `row` — Row из select() с колонками id/name/price/description/photo_url/
    has_bytea_photo/product_type/category/unit/price_updated_at/price_source/
    price_source_ref/price_ttl_days/item_kind (см. by_type-запрос ниже);
    evaluate_freshness читает эти поля через getattr(..., default) — совместимо
    с Row (та же схема доступа, что и everywhere else в этом файле, например
    products_match.match_products читает `r.id`/`r.name` с Row)."""
    return {
        "product_id": row.id,
        "name": row.name,
        "price": float(row.price) if row.price is not None else None,
        "score": round(score_value, 4),
        "description": row.description,
        "photo_url": resolve_photo_url(row.photo_url, row.has_bytea_photo, row.id),
        "item_type": row.product_type,
        "category": row.category,
        "product_type": row.product_type,
        "unit": row.unit,
        "price_updated_at": row.price_updated_at.isoformat() if row.price_updated_at else None,
        "price_source": row.price_source,
        "price_source_ref": row.price_source_ref,
        "price_freshness": evaluate_freshness(row, freshness_ctx),
    }


async def build_plan_to_wish_candidates(
    db: AsyncSession,
    planned_item_ids: list[int],
    limit: int,
) -> list[dict]:
    """POST /feo-planned-items/plan-to-wish/candidates — см. докстринг модуля
    и контракт в задаче сессии (форма ответа "items": [...])."""
    if not planned_item_ids:
        return []
    limit = max(1, min(limit or 6, 50))

    rows = (await db.execute(
        select(FeoPlannedItem, FeoCategory)
        .join(FeoCategory, FeoCategory.id == FeoPlannedItem.feo_category_id)
        .where(FeoPlannedItem.id.in_(planned_item_ids))
    )).all()
    by_id: dict[int, tuple[FeoPlannedItem, FeoCategory]] = {pi.id: (pi, cat) for pi, cat in rows}
    # Сохраняем порядок запроса; несуществующие id молча пропускаются (эндпоинт
    # только для подсказок, не гейт — 404 тут не нужен, в отличие от /plan-to-wish/create).
    ordered_ids = [iid for iid in planned_item_ids if iid in by_id]
    if not ordered_ids:
        return []

    consumption = await planned_item_consumption(db, ordered_ids)

    # --- linked_purchases: покупатель + подпись статуса + сколько этой плановой
    # позиции ушло в конкретную закупку. Тот же набор фильтров (PLANNED_STATUSES +
    # stopped_at IS NULL), что использует planned_item_consumption для used/used_qty —
    # иначе «остаток» и «куда делось» разъехались бы по разным правилам (Правило №6).
    from app.routers.purchase_budget import PLANNED_STATUSES

    link_rows = (await db.execute(
        select(
            PurchaseItem.feo_planned_item_id,
            PurchaseItem.purchase_id,
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(ordered_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .group_by(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
    )).all()

    purchase_ids = {r.purchase_id for r in link_rows}
    purchases_by_id: dict[int, Purchase] = {}
    if purchase_ids:
        purchases_by_id = {
            p.id: p for p in (await db.execute(
                select(Purchase).where(Purchase.id.in_(purchase_ids))
            )).scalars().all()
        }

    initiator_ids = {
        (p.service_note_by if p.service_note_by is not None else p.assigned_user_id)
        for p in purchases_by_id.values()
        if (p.service_note_by is not None or p.assigned_user_id is not None)
    }
    users_by_id: dict[int, User] = {}
    if initiator_ids:
        users_by_id = {
            u.id: u for u in (await db.execute(
                select(User).where(User.id.in_(initiator_ids))
            )).scalars().all()
        }

    linked_by_item: dict[int, list[dict]] = {}
    for r in link_rows:
        p = purchases_by_id.get(r.purchase_id)
        if p is None:
            continue
        initiator_id = p.service_note_by if p.service_note_by is not None else p.assigned_user_id
        initiator = users_by_id.get(initiator_id) if initiator_id is not None else None
        linked_by_item.setdefault(r.feo_planned_item_id, []).append({
            "purchase_id": p.id,
            "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "status": p.status,
            "status_label": STATUS_LABELS.get(p.status, p.status),
            "quantity": float(r.qty or 0),
            "initiator_user_id": initiator_id,
            "initiator_name": (initiator.full_name if initiator else None),
        })

    # --- сопоставление по имени: батчем на все запрошенные позиции одним вызовом
    # общего сборщика (products_match._score_product_candidates) — Правило №6.
    from app.routers.products_match import _score_product_candidates

    names = [by_id[iid][0].name or "" for iid in ordered_ids]
    name_results = await _score_product_candidates(
        db, org_id=None, queries=names, limit=max(limit, 10), prefix=False, active_only=True,
    )
    name_results_by_index = {i: r for i, r in enumerate(name_results)}

    # --- by_type: каталог активных товаров с product_type, загружен один раз.
    # Column-select (не select(Product)) — та же причина, что у _score_product_candidates
    # в products_match.py: photo_data НЕ выбирается вовсе (только boolean-флаг),
    # чтобы не тащить BLOB на весь каталог и не оставлять деферренную колонку,
    # которая иначе ленивo подгружается вне await-контекста (MissingGreenlet)
    # прямо в синхронном сравнении ниже (_sort_key).
    type_rows = (await db.execute(
        select(
            Product.id, Product.name, Product.price, Product.description,
            Product.photo_url,
            (Product.photo_data.isnot(None)).label('has_bytea_photo'),
            Product.product_type, Product.category, Product.unit,
            Product.price_updated_at, Product.price_source, Product.price_source_ref,
            Product.price_ttl_days, Product.item_kind,
        )
        .where(Product.is_active.is_(True))
        .where(Product.product_type.isnot(None))
        .where(Product.product_type != "")
    )).all()
    products_by_type_norm: dict[str, list] = {}
    for prod in type_rows:
        key = normalize(prod.product_type or "")
        if key:
            products_by_type_norm.setdefault(key, []).append(prod)

    freshness_ctx = await load_freshness_context(db, org_id=None)

    out: list[dict] = []
    for idx, iid in enumerate(ordered_ids):
        planned, cat = by_id[iid]
        cons = consumption.get(iid, {"used": 0.0, "used_qty": 0.0, "linked_purchase_ids": []})

        plan_quantity = planned.quantity
        residual_quantity = None
        if plan_quantity is not None:
            residual_quantity = max(plan_quantity - Decimal(str(cons["used_qty"] or 0)), Decimal("0"))
        residual_amount = None
        if planned.amount is not None:
            residual_amount = max(planned.amount - Decimal(str(cons["used"] or 0)), Decimal("0"))

        name_res = name_results_by_index.get(idx, {"candidates": []})
        cands = name_res["candidates"]
        exact = None
        rest = cands
        if cands and cands[0]["score"] >= SCORE_AUTO:
            exact = cands[0]
            rest = cands[1:]
        by_name = [c for c in rest if SCORE_SUGGEST <= c["score"] < SCORE_AUTO][:limit]

        used_product_ids = {c["product_id"] for c in ([exact] if exact else []) + by_name}

        item_name = planned.name or ""
        name_norm = normalize(item_name)
        match_targets = {t for t in ({name_norm} | {t for t in tokenize(item_name) if len(t) >= _BY_TYPE_MIN_WORD_LEN}) if t}

        by_type_products: list = []
        seen_type_ids: set[int] = set()
        for target in match_targets:
            for prod in products_by_type_norm.get(target, []):
                if prod.id in used_product_ids or prod.id in seen_type_ids:
                    continue
                seen_type_ids.add(prod.id)
                by_type_products.append(prod)

        def _sort_key(prod):
            fresh = evaluate_freshness(prod, freshness_ctx)
            is_stale = bool(fresh.get("is_stale"))
            return (is_stale, (prod.name or "").lower())

        by_type_products.sort(key=_sort_key)
        by_type = [
            _candidate_from_type_row(prod, text_score(item_name, prod.name or ""), freshness_ctx)
            for prod in by_type_products[:limit]
        ]

        out.append({
            "planned_item_id": planned.id,
            "name": planned.name,
            "unit": planned.unit,
            "feo_category_id": cat.id,
            "feo_category_name": cat.name,
            "plan_quantity": plan_quantity,
            "plan_unit_price": planned.unit_price,
            "plan_amount": planned.amount,
            "used_quantity": Decimal(str(cons["used_qty"] or 0)),
            "residual_quantity": residual_quantity,
            "residual_amount": residual_amount,
            "linked_purchases": linked_by_item.get(iid, []),
            "exact": exact,
            "by_name": by_name,
            "by_type": by_type,
        })

    return out


@dataclass
class PlanToWishItemInput:
    feo_planned_item_id: int
    quantity: Decimal
    product_id: Optional[int] = None
    item_name: Optional[str] = None
    unit_price: Optional[Decimal] = None
    price_source: Optional[str] = None  # 'catalog' | 'plan'


async def create_wish_from_plan(
    db: AsyncSession,
    current_user,
    subsidy_id: int,
    title: Optional[str],
    items: list[PlanToWishItemInput],
) -> dict:
    """POST /feo-planned-items/plan-to-wish/create — заводит заявку (Wish) на
    остаток плановых позиций. Создание САМОЙ заявки идёт через
    app.routers.wishes.create_wish (та же функция, что у POST /wishes/, вызвана
    напрямую с готовыми db/current_user/WishCreate) — не копия её тела."""
    from app.routers.wishes import create_wish
    from app.schemas.wishes import WishCreate

    if not items:
        raise HTTPException(422, "Список позиций пуст")

    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(404, "Субсидия не найдена")

    planned_ids = [it.feo_planned_item_id for it in items]
    planned_rows = (await db.execute(
        select(FeoPlannedItem, FeoCategory)
        .join(FeoCategory, FeoCategory.id == FeoPlannedItem.feo_category_id)
        .where(FeoPlannedItem.id.in_(planned_ids))
    )).all()
    planned_by_id: dict[int, tuple[FeoPlannedItem, FeoCategory]] = {pi.id: (pi, cat) for pi, cat in planned_rows}

    missing = [pid for pid in planned_ids if pid not in planned_by_id]
    if missing:
        raise HTTPException(404, f"Плановые позиции не найдены: {missing}")

    foreign = [pid for pid, (_pi, cat) in planned_by_id.items() if cat.subsidy_id != subsidy_id]
    if foreign:
        raise HTTPException(
            422,
            f"Плановые позиции {foreign} принадлежат другой субсидии, а не выбранной ({subsidy_id})",
        )

    consumption = await planned_item_consumption(db, planned_ids)

    product_ids = [it.product_id for it in items if it.product_id is not None]
    products_by_id: dict[int, Product] = {}
    if product_ids:
        products_by_id = {
            p.id: p for p in (await db.execute(
                select(Product).where(Product.id.in_(product_ids))
            )).scalars().all()
        }

    purchase_ids_all = {pid for c in consumption.values() for pid in (c.get("linked_purchase_ids") or [])}
    purchases_by_id: dict[int, Purchase] = {}
    if purchase_ids_all:
        purchases_by_id = {
            p.id: p for p in (await db.execute(
                select(Purchase).where(Purchase.id.in_(purchase_ids_all))
            )).scalars().all()
        }

    categories_used: set[int] = set()
    item_dicts: list[dict] = []
    warnings: list[str] = []

    for it in items:
        planned, cat = planned_by_id[it.feo_planned_item_id]
        categories_used.add(cat.id)
        product = products_by_id.get(it.product_id) if it.product_id is not None else None

        if product is not None:
            item_name = product.name
        else:
            item_name = (it.item_name or "").strip()
            if not item_name:
                raise HTTPException(
                    422,
                    f"Название позиции обязательно, если товар не выбран из каталога "
                    f"(плановая позиция {planned.id})",
                )

        unit = (product.unit if product and product.unit else None) or planned.unit or "шт"

        price_fallback = False
        if it.unit_price is not None:
            unit_price = it.unit_price
        elif it.price_source == "catalog":
            if product is not None and product.price is not None:
                unit_price = product.price
            else:
                unit_price = planned.unit_price
                price_fallback = True
        else:  # price_source == 'plan' (или не передан) — плановая цена
            unit_price = planned.unit_price
        unit_price = unit_price if unit_price is not None else Decimal("0")

        total_price = line_total(it.quantity, unit_price)

        # item_type: собственный тип плановой позиции, иначе item_kind выбранного
        # товара каталога, иначе дефолт 'товар' (create_wish/WishItem дефолт тоже
        # 'товар' — здесь просто не оставляем поле пустым раньше времени).
        item_type = planned.item_type or (product.item_kind if product else None) or "товар"

        item_dicts.append({
            "product_id": it.product_id,
            "item_name": item_name,
            "item_type": item_type,
            "quantity": it.quantity,
            "unit": unit,
            "unit_price": unit_price,
            "total_price": total_price,
            "feo_category_id": cat.id,
            "feo_planned_item_id": planned.id,
        })

        if price_fallback:
            warnings.append(f"«{item_name}»: цена каталога не задана — использована плановая цена")

        cons = consumption.get(planned.id, {"used_qty": 0.0, "linked_purchase_ids": []})
        plan_quantity = planned.quantity
        if plan_quantity is not None:
            residual_quantity = max(plan_quantity - Decimal(str(cons["used_qty"] or 0)), Decimal("0"))
            if it.quantity > residual_quantity:
                linked_ids = cons.get("linked_purchase_ids") or []
                descr = ", ".join(
                    f"№{purchases_by_id[pid].purchase_number}"
                    for pid in linked_ids
                    if pid in purchases_by_id and purchases_by_id[pid].purchase_number is not None
                ) or "уже действующей закупке"
                warnings.append(
                    f"«{item_name}»: запрошено {it.quantity}, остаток {residual_quantity} "
                    f"— уже привязано в закупке {descr}"
                )

    feo_category_id = next(iter(categories_used)) if len(categories_used) == 1 else None
    # Владелец (2026-09-20, блокер): позиции из НЕСКОЛЬКИХ категорий ФЭО —
    # заявка должна открываться в режиме «своя категория у каждого товара»
    # (WishCreate.feo_per_item, то же поле, что и ручное создание заявки),
    # иначе шапка заявки остаётся без категории, а позиции с уже проставленным
    # per-item feo_category_id (см. item_dicts выше) визуально выглядят как
    # ошибка несинхронизированности. Один источник категории каждой позиции —
    # cat.id, посчитанный в цикле выше; здесь просто включается режим показа.
    feo_per_item = len(categories_used) > 1

    if title:
        wish_title = title
    else:
        wish_title = f"Закупка по плану: {subsidy.name}, {date.today().strftime('%d.%m.%Y')}"

    wish_body = WishCreate(
        title=wish_title,
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        feo_per_item=feo_per_item,
        items=item_dicts,
    )
    wish_out = await create_wish(body=wish_body, db=db, current_user=current_user)

    return {
        "wish_id": wish_out.id,
        "title": wish_out.title,
        "items_count": len(item_dicts),
        "warnings": warnings,
    }
