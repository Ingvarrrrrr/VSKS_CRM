"""Разрезание feo_planned_items.py (Правило №5, сессия 2026-09-08): сопоставление
позиций закупок/заявок с плановыми позициями ФЭО — product-hint (подсказка при
создании плановой позиции из каталога), map (ручная привязка purchase_item),
match (нечёткий поиск кандидатов по имени для заявки) и confirm-wish-plan-match
(флаг «подтверждено человеком»). Все пути статические/литеральные на префиксе
/api/feo-planned-items — регистрируется рядом с feo_planned_items.router (см.
app/routes.py), порядок относительно его catch-all "/{item_id}" (PUT/DELETE)
некритичен (другие методы/формы пути), но выдержан для единообразия с
contractors_*/feo_*_reads-соседями.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.product import Product
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.text_match import tokenize, stem, generic_progressive_match

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


@router.get("/product-hint")
async def get_product_hint(
    product_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Подсказка для диалога «Добавить плановую позицию» (SubsidiesView.vue) при
    выборе товара из каталога — единица измерения + цена/её происхождение,
    ОДНИМ запросом.

    Переименован из product-unit-hint (владелец, 2026-09-01): изначально отдавал
    только unit, читая из истории закупок (см. ниже) — цену/дату/источник фронт
    брал из кандидата POST /products/match (useItemMatching.ts::MatchCandidate).
    НО те поля (price_updated_at/price_source/price_source_ref) в /products/match
    добавила ПАРАЛЛЕЛЬНАЯ сессия и ещё НЕ закоммитила (backend/app/routers/products.py
    — файл специально не трогаем, см. правила задачи) — на проде, где working tree
    чистый, кандидат отдаёт только price/photo_url, и подпись о цене всегда молчала
    бы («дата актуализации не указана»). Колонки price/price_updated_at/price_source/
    price_source_ref НА САМОЙ МОДЕЛИ Product УЖЕ закоммичены (app/models/product.py:
    25,40-42) — читаем их прямо оттуда, без зависимости от чужого незакоммиченного
    кода. Фронт использует ЭТОТ эндпоинт как основной источник цены/даты/источника,
    candidate.price — только запасной вариант на случай сетевой ошибки.

    unit (владелец, 2026-09-01): теперь у Product ЕСТЬ своё поле unit —
    приоритет ему (заполняется бэкфиллом/импортом/карточкой товара, см.
    app/services/product_unit.py). Если оно пусто — прежний фолбэк на
    последнюю единицу измерения, с которой товар фигурировал в позиции
    закупки (PurchaseItem.unit по product_id, самая свежая по id); null, если
    ни разу не покупался с явно указанной единицей — фронт тогда оставляет
    поле пустым."""
    # Колонки price_updated_at/price_source/price_source_ref появляются вместе с
    # отдельной работой по свежести цен и на момент этого кода могут ещё не
    # существовать ни в модели, ни в БД (прод отдавал 500: «type object 'Product'
    # has no attribute 'price_updated_at'»). Поэтому выбираем их ТОЛЬКО если они
    # реально объявлены в модели: цена и единица работают всегда, а дата/источник
    # появятся сами, как только колонки приедут — без правок здесь.
    _optional = [c for c in ("price_updated_at", "price_source", "price_source_ref")
                 if hasattr(Product, c)]
    _cols = [Product.price, Product.contract_price, Product.unit] + [getattr(Product, c) for c in _optional]
    product = (await db.execute(select(*_cols).where(Product.id == product_id))).first()

    # Приоритет (владелец, 2026-09-01): собственная Product.unit, если заполнена;
    # иначе — прежний фолбэк на самую свежую единицу из истории закупок.
    unit_val = (product.unit or None) if product is not None else None
    if not unit_val:
        unit_val = (await db.execute(
            select(PurchaseItem.unit)
            .where(
                PurchaseItem.product_id == product_id,
                PurchaseItem.unit.isnot(None),
                PurchaseItem.unit != "",
            )
            .order_by(PurchaseItem.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    if product is None:
        return {"unit": unit_val, "price": None, "price_updated_at": None, "price_source": None, "price_source_ref": None}

    best_price = product.contract_price if product.contract_price is not None else product.price
    _updated = getattr(product, "price_updated_at", None)
    return {
        "unit": unit_val,
        "price": float(best_price) if best_price is not None else None,
        "price_updated_at": _updated.isoformat() if _updated else None,
        "price_source": getattr(product, "price_source", None),
        "price_source_ref": getattr(product, "price_source_ref", None),
    }


@router.post("/map")
async def map_purchase_item_to_planned(
    purchase_item_id: int,
    planned_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Сопоставить purchase_item с плановой позицией. planned_item_id=null — снять сопоставление."""
    pi = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.id == purchase_item_id)
    )).scalar_one_or_none()
    if not pi:
        raise HTTPException(404, "Позиция закупки не найдена")

    if planned_item_id is not None:
        planned = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == planned_item_id)
        )).scalar_one_or_none()
        if not planned:
            raise HTTPException(404, "Плановая позиция не найдена")

        purchase = (await db.execute(
            select(Purchase).where(Purchase.id == pi.purchase_id)
        )).scalar_one_or_none()
        effective_cat_id = pi.feo_category_id if pi.feo_category_id is not None else (
            purchase.feo_category_id if purchase else None
        )

        # Этап 3 (владелец, 2026-09-02): до 2026-08-18 несовпадение категорий тут
        # отклонялось с 409; с 2026-08-18 по 2026-09-02 этот путь молча ПЕРЕНОСИЛ
        # позицию закупки в категорию плановой позиции — сумма не исчезала, но
        # ровно этим переносом создавалось расхождение «категория позиции ≠
        # категория шапки» (при feo_per_item=False), которое PATCH
        # /purchases/{id}/items/{item_id} для явного выбора плановой позиции как
        # раз запрещает — правило разъезжалось по двум путям. Приведено к тому
        # же правилу через общий хелпер (см. app/services/plan_autoassign.py):
        # обычному пользователю — отказ с объяснением, суперадмину — разрешение
        # + уведомление согласовавших/ответственного; категория позиции закупки
        # больше НЕ переносится молча — привязка живёт поверх существующей
        # категории, как и в PATCH.
        from app.services.plan_autoassign import check_planned_item_category_link
        await check_planned_item_category_link(
            db,
            purchase=purchase,
            item=pi,
            item_category_id=effective_cat_id,
            planned_category_id=planned.feo_category_id,
            planned_item_name=planned.name,
            current_user=current_user,
        )

        # НЕ вызываем здесь assert_no_unapproved_excess/другие гейты превышения:
        # это действие сопоставления факта с планом, а не новая трата денег.
    else:
        planned = None

    pi.feo_planned_item_id = planned_item_id

    # Зеркалим привязку в связанную позицию заявки — иначе заявка и закупка
    # расходятся (ровно баг с прода: wish_items.id=2583 остался с
    # feo_planned_item_id=123/категория 3688, пока purchase_items.id=2897
    # уехал на несуществующую плановую позицию 809/категорию 3710).
    if pi.wish_item_id is not None:
        wi = (await db.execute(
            select(WishItem).where(WishItem.id == pi.wish_item_id)
        )).scalar_one_or_none()
        if wi:
            wi.feo_planned_item_id = planned_item_id
            # Категорию позиции заявки больше не переносим следом за плановой
            # (см. комментарий выше про этап 3) — она следует тем же правилам,
            # что и категория позиции закупки: своя категория не переписывается
            # молча привязкой к плану.

    await db.commit()
    return {
        "ok": True,
        "purchase_item_id": purchase_item_id,
        "planned_item_id": planned_item_id,
        # Оставлено для обратной совместимости фронта (SubsidiesView.vue читает
        # это поле) — молчаливый перенос категории убран, поле теперь всегда null.
        "moved_to_category_id": None,
    }


# ---------------------------------------------------------------------------
# Похожая плановая позиция с подтверждением (Шаг 4 плана
# zany-fluttering-mountain.md): при заведении заявки, если в субсидии уже есть
# плановые позиции, предлагать похожие по имени и давать подтвердить/отвергнуть —
# ровно как сопоставление позиции с товаром каталога (products.py /match,
# InlineProductMatch.vue + useItemMatching.ts). Движок — общий
# app.services.text_match (вынесен из app.services.product_matcher, тот же
# алгоритм нормализации+токенов+стемминга+прогрессивного сужения).
# ---------------------------------------------------------------------------

async def _load_plan_catalog(db: AsyncSession, subsidy_id: int) -> list[dict]:
    """Каталог кандидатов для матчинга — тот же состав, что и в
    GET /feo-categories/plan-positions (единый источник «плановых позиций»,
    см. её докстринг): конечные категории ФЭО (лист дерева) с заполненным
    planned_quantity×planned_amount > 0 (kind='plan_position'|'feo_article'),
    плюс активные FeoPlannedItem этих листьев (kind='planned_item') — «может
    быть запланирована в ФЭО, а может только планово» (формулировка владельца).

    Не вызывает сам эндпоинт /plan-positions (тот считает ещё consumption/tree —
    не нужно для матчинга по имени), а строит облегчённую версию тех же строк:
    id/name/path/category_id/ancestor_ids/kind. path/ancestor_ids — те же
    хелперы app.services.feo_plan.build_category_path/build_ancestor_ids
    (read-only импорт, не дублируем).
    """
    from app.services.feo_plan import build_category_path, build_ancestor_ids

    all_cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]

    catalog: list[dict] = []
    for c in leaves:
        qty = float(c.planned_quantity) if c.planned_quantity is not None else 0.0
        unit_price = float(c.planned_amount) if c.planned_amount is not None else 0.0
        if qty * unit_price <= 0:
            continue
        kind = "plan_position" if (c.budget is None and c.feo_amount is None) else "feo_article"
        catalog.append({
            "id": c.id,
            "name": c.name or "",
            "path": build_category_path(c, cat_by_id),
            "category_id": c.id,
            "ancestor_ids": build_ancestor_ids(c, cat_by_id),
            "kind": kind,
        })

    if leaves:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem)
            .where(FeoPlannedItem.feo_category_id.in_([c.id for c in leaves]))
            .where(FeoPlannedItem.is_active == True)
        )).scalars().all()
        for it in fpi_rows:
            cat = cat_by_id.get(it.feo_category_id)
            catalog.append({
                "id": it.id,
                "name": it.name or "",
                "path": build_category_path(cat, cat_by_id) if cat else "",
                "category_id": it.feo_category_id,
                "ancestor_ids": build_ancestor_ids(cat, cat_by_id) if cat else [],
                "kind": "planned_item",
            })

    return catalog


class _FeoMatchCandidate(BaseModel):
    kind: str            # 'plan_position' | 'feo_article' | 'planned_item'
    id: int               # id FeoCategory (plan_position/feo_article) или FeoPlannedItem (planned_item)
    key: str               # `${kind}:${id}` — тот же составной ключ, что и в /plan-positions (фронт)
    name: str
    path: str
    category_id: int
    score: float
    # Требование /feo-planned-items/map (совпадение категорий обязательно) — кандидаты
    # из ЧУЖОЙ (относительно feo_category_id запроса) категории/ветки помечаются явно,
    # а не подмешиваются молча (см. докстринг match_planned_items).
    same_category: bool


class _FeoMatchResultItem(BaseModel):
    query: str
    status: str  # 'auto' | 'suggest' | 'create' — см. text_match.generic_progressive_match
    candidates: List[_FeoMatchCandidate]


class _FeoMatchRequest(BaseModel):
    queries: List[str]
    subsidy_id: int
    feo_category_id: Optional[int] = None
    limit: int = 5


class _FeoMatchResponse(BaseModel):
    results: List[_FeoMatchResultItem]


@router.post("/match", response_model=_FeoMatchResponse)
async def match_planned_items(
    body: _FeoMatchRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Score a list of wish-item name queries against the subsidy's plan positions
    (FeoCategory leaves with a plan + FeoPlannedItem) using the same token-based
    fuzzy matching as /api/products/match.

    Владелец: «когда заявки заведены, и если в субсидии уже есть плановая позиция,
    предлагать плановые позиции, похожие по имени... человек может подтвердить, что
    позиция выбрана правильно, а может отвергнуть и выбрать свою». Это ТОЛЬКО источник
    предложений — привязка (feo_planned_item_id/feo_category_id заявки) остаётся,
    как и раньше, через обычное сохранение заявки; см. POST /confirm-wish-plan-match
    для фиксации флага «подтверждено человеком».

    Кандидаты из ЧУЖОЙ (по отношению к feo_category_id запроса — включая её ветку
    предков) категории НЕ отфильтровываются молча — они присутствуют в том же списке
    candidates с same_category=false, фронт обязан показать их отдельной группой с
    пометкой (правило: /feo-planned-items/map требует совпадения категорий для
    фактической привязки purchase_item, так что «чужой» кандидат — это в лучшем
    случае наведение на существующую плановую позицию другой категории, а не то,
    что можно тихо подставить).
    """
    catalog = await _load_plan_catalog(db, body.subsidy_id)
    if not catalog:
        return _FeoMatchResponse(results=[
            _FeoMatchResultItem(query=q, status='create', candidates=[]) for q in body.queries
        ])

    indexed = [
        (entry, {stem(t) for t in tokenize(entry["name"])})
        for entry in catalog
    ]
    target_cat = body.feo_category_id
    top_k = max(1, min(body.limit, 10))

    results: list[_FeoMatchResultItem] = []
    for q in body.queries:
        if not q or not q.strip():
            results.append(_FeoMatchResultItem(query=q, status='create', candidates=[]))
            continue
        status, scored = generic_progressive_match(q, indexed)
        candidates: list[_FeoMatchCandidate] = []
        for entry, sc in scored[:top_k]:
            same_cat = True
            if target_cat is not None:
                same_cat = entry["category_id"] == target_cat or target_cat in (entry["ancestor_ids"] or [])
            candidates.append(_FeoMatchCandidate(
                kind=entry["kind"],
                id=entry["id"],
                key=f"{entry['kind']}:{entry['id']}",
                name=entry["name"],
                path=entry["path"],
                category_id=entry["category_id"],
                score=sc,
                same_category=same_cat,
            ))
        results.append(_FeoMatchResultItem(query=q, status=status, candidates=candidates))

    return _FeoMatchResponse(results=results)


class _ConfirmWishPlanMatchBody(BaseModel):
    wish_id: int
    kind: str            # 'plan_position' | 'feo_article' | 'planned_item'
    target_id: int


@router.post("/confirm-wish-plan-match")
async def confirm_wish_plan_match(
    body: _ConfirmWishPlanMatchBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Фиксирует флаг «плановую позицию подтвердил человек» (wish_items
    .feo_planned_item_match_confirmed, по образцу purchase_items.match_confirmed)
    после того, как заявка уже сохранена обычным путём (POST/PUT /wishes/ —
    ТОТ роутер не трогаем, см. план zany-fluttering-mountain.md шаг 4).

    feo_planned_item_id/feo_category_id сама заявка получает через обычное
    сохранение (WishesView.vue уже шлёт их в payload — см. wishFeoPlanSelection);
    этот эндпоинт — ТОЛЬКО про флаг подтверждения, прямой UPDATE в обход большого
    create_wish/update_wish (мирроит паттерн /feo-planned-items/map для purchase_item).

    kind='planned_item': подтверждаем ТОЛЬКО позиции заявки, у которых
    feo_planned_item_id уже равен target_id (защита от простановки флага не на ту
    строку, если что-то разошлось между сохранением и этим вызовом).
    kind='plan_position'|'feo_article': категория хранится на уровне самой заявки
    (wish.feo_category_id), а не на каждой позиции — подтверждаем все позиции заявки
    без per-item фильтра (per-item ФЭО в это состояние вообще не должен попадать,
    см. WishesView.vue — кнопка доступна только вне режима «разные ФЭО»).

    _auto_assign_planned_items (wishes.py, другой исполнитель) уже НЕ трогает позиции
    с непустым feo_planned_item_id независимо от этого флага — сам факт подтверждения
    человеком физически защищён до вызова этого эндпоинта; флаг — только видимый
    признак «откуда взялась привязка» (для UI/аудита), не гейт бизнес-логики.
    """
    wish = (await db.execute(select(Wish).where(Wish.id == body.wish_id))).scalar_one_or_none()
    if not wish:
        raise HTTPException(404, "Заявка не найдена")

    if body.kind == "planned_item":
        stmt = (
            sql_update(WishItem)
            .where(WishItem.wish_id == body.wish_id, WishItem.feo_planned_item_id == body.target_id)
            .values(feo_planned_item_match_confirmed=True)
        )
    else:
        stmt = (
            sql_update(WishItem)
            .where(WishItem.wish_id == body.wish_id)
            .values(feo_planned_item_match_confirmed=True)
        )
    result = await db.execute(stmt)
    await db.commit()
    return {"ok": True, "wish_id": body.wish_id, "updated": result.rowcount}
