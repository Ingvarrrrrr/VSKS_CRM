"""Read-only агрегаты плана/факта по дереву категорий ФЭО — «сырые» суммы заявок/закупок.

Разрезано из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения. Волна 2 (2026-09-05) вынесла эти 7 путей из
feo_categories.py в единый feo_plan_reads.py; волна 3a (2026-09-08) режет
разросшийся feo_plan_reads.py (1016 строк) дальше на три соседа с общим
префиксом /api/feo-categories:
- feo_plan_reads.py (этот файл) — /purchase-totals, /planned-purchase-totals,
  /planned-purchase-items: «сырые» агрегаты по Purchase/PurchaseItem;
- feo_plan_reads_tree.py — /plan-tree, /plan-positions: обёртки над
  app.services.feo_plan.compute_feo_plan_tree, per-node числа для
  FeoTreeSelect/SubsidiesView;
- feo_plan_reads_budget.py — /leaves, /budget-residuals: бюджет/остаток по
  листу и направлению (CONTRACTED_STATUSES/PLANNED_STATUSES + compute_budget_map).

Все семь путей — статичные (без {cat_id}) и обязаны регистрироваться в
app/routes.py ДО feo_categories.router (несёт catch-all GET/PUT/DELETE
"/{cat_id}") — иначе Starlette матчит их на catch-all раньше. Порядок ТРЁХ
файлов друг относительно друга не важен — все пути строго статичные и не
пересекаются между файлами.

Ядро (гейты/чистые хелперы) зовётся через `from app.routers import
feo_categories as fc` — так monkeypatch `fc._has_feo_action`/
`fc._require_feo_category_write` в тестах продолжает работать независимо от
того, в каком файле реально живёт вызывающий обработчик. Этот конкретный файл
`fc` не использует (её эндпоинты без gate по правам) — импортирован в
feo_plan_reads_tree.py/feo_plan_reads_budget.py, где он реально нужен.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


@router.get("/purchase-totals")
async def get_purchase_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Фактическая сумма per feo_category_id: только поставленное/оплаченное (по актам).

    ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки —
    app.services.purchase_amounts.effective_amount_expr() (та же формула,
    что dashboard.py/GET /api/purchases/*), вместо отдельной COALESCE(final_
    total_amount, planned_total_price) — final_total_amount не участвует ни в
    одном другом расчёте суммы закупки в проекте.

    Владелец (2026-09-06) — решение по рамочным договорам в итогах: голова с
    предельной суммой несёт «законтрактовано» целиком (её effective уже =
    Contract.max_amount), «заказано» — ТОЛЬКО по её детям; накопительная
    голова (без предела) сама не несёт суммы. Чтобы GROUP BY feo_category_id
    не задваивал голову и детей — доп. фильтр aggregate_scope_expr() (см. её
    докстринг, тот же предикат применён в dashboard.py::subsidy_q и
    subsidies.py::_calculate_spent(_bulk)).
    """
    from app.models.purchase import Purchase
    from app.services.purchase_amounts import effective_amount_expr, aggregate_scope_expr
    stmt = (
        select(
            Purchase.feo_category_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("total_planned"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .where(aggregate_scope_expr())
        .where(Purchase.status.in_(["delivered", "paid"]))
        .group_by(Purchase.feo_category_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r.feo_category_id: float(r.total_planned) for r in rows}


@router.get("/planned-purchase-totals")
async def get_planned_purchase_totals(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Плановая сумма и количество из заявок per feo_category_id: позиции закупок в статусах плана закупок и дальше.

    exclude_purchase_id/exclude_wish_id (план crystalline-soaring-heron.md, п.1):
    та же исключающая логика, что и в plan_consumption_by_category/planned_item_consumption
    (см. app.services.feo_plan.apply_wish_item_exclusion) — редактируемая сейчас
    закупка/заявка не должна выглядеть потребителем самой себя.

    `total`/`qty` — ВСЕ позиции (для обратной совместимости, режим отображения «из заявок»).
    `total_linked`/`qty_linked` — подмножество позиций, привязанных к плановой позиции
    (`PurchaseItem.feo_planned_item_id IS NOT NULL`): они РАСХОДУЮТ ручной план листа
    (Ур.5), а не складываются с ним поверх — фронт вычитает linked из total, чтобы не
    задваивать план в дереве ФЭО.
    `total_over`/`qty_over` — подмножество НЕпривязанных позиций с `over_plan=true`:
    расход «сверх плана» элемента, прибавляется к плановой сумме безусловно (не входит
    в MAX(план, выбрано) — см. feoPlannedDisplayFor в SubsidiesView.vue и
    app.services.feo_plan.compute_feo_plan_tree). Партиция чистая: total = total_linked +
    total_over + «обычный» расход (total − total_linked − total_over), пересечения
    linked∩over_plan сознательно отнесены к total_linked (привязанные к Ур.5 позиции не
    участвуют в схеме over_plan этого эндпоинта).

    Дополнительно (сессия 2026-08-05, формула v2 — «заказ замещает план, пока не набрано
    количество»): `plan_manual`, `ordered_qty`, `ordered_sum`, `residual`, `forecast`,
    `forecast_over` — из app.services.feo_plan.compute_feo_plan_tree (единый источник,
    та же формула, что и в KPI «Запланировано»/«Свободно»). Присутствуют для КАЖДОЙ
    категории субсидии (и листа, и группы), даже без единой позиции закупки — в отличие
    от total/qty/... выше, которые есть только при наличии хотя бы одной позиции.
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.services.feo_plan import compute_feo_plan_tree, apply_wish_item_exclusion
    from sqlalchemy import case, and_, not_

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    is_linked = PurchaseItem.feo_planned_item_id.isnot(None)
    is_over_unlinked = and_(PurchaseItem.over_plan.is_(True), not_(is_linked))
    stmt = (
        select(
            cat_col.label("cat_id"),
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("total"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("qty"),
            func.coalesce(func.sum(case((is_linked, PurchaseItem.total_price), else_=0)), 0).label("total_linked"),
            func.coalesce(func.sum(case((is_linked, PurchaseItem.quantity), else_=0)), 0).label("qty_linked"),
            func.coalesce(func.sum(case((is_over_unlinked, PurchaseItem.total_price), else_=0)), 0).label("total_over"),
            func.coalesce(func.sum(case((is_over_unlinked, PurchaseItem.quantity), else_=0)), 0).label("qty_over"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        # Выравниваем с app.services.feo_plan.py — остановленные закупки не считаются
        # (решение владельца 2026-08-13).
        .where(Purchase.stopped_at.is_(None))
        .where(cat_col.isnot(None))
    )
    if exclude_purchase_id is not None:
        stmt = stmt.where(PurchaseItem.purchase_id != exclude_purchase_id)
    stmt = apply_wish_item_exclusion(stmt, exclude_wish_id)
    stmt = stmt.group_by(cat_col)
    rows = (await db.execute(stmt)).all()
    result = {
        r.cat_id: {
            "total": float(r.total),
            "qty": float(r.qty),
            "total_linked": float(r.total_linked),
            "qty_linked": float(r.qty_linked),
            "total_over": float(r.total_over),
            "qty_over": float(r.qty_over),
        }
        for r in rows
    }

    # Аддитивно: формула v2 плановой суммы (см. docstring) — на КАЖДУЮ категорию
    # субсидии, а не только на те, где уже есть позиции закупок.
    tree = await compute_feo_plan_tree(db, [subsidy_id])
    for cat_id, node in tree.items():
        entry = result.setdefault(cat_id, {
            "total": 0.0, "qty": 0.0, "total_linked": 0.0, "qty_linked": 0.0,
            "total_over": 0.0, "qty_over": 0.0,
        })
        entry["plan_manual"] = node["plan_manual"]
        entry["ordered_qty"] = node["ordered_quantity"]
        entry["ordered_sum"] = node["ordered"]
        entry["residual"] = node["residual"]
        entry["forecast"] = node["forecast"]
        entry["forecast_over"] = node["forecast_over"]

    return result


@router.get("/planned-purchase-items")
async def get_planned_purchase_items(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Позиции закупок «из заявок» per feo_category_id (статусы плана закупок и дальше).

    Задача владельца «план ≠ факт» (сессия 2026-08-06, шаг 5): панель «Позиции: план
    vs факт» (SubsidiesView.vue, таблица источников группы «из заявок») обязана
    показывать ЗАМОРОЖЕННЫЙ снимок ТЗ (planned_quantity/planned_unit_price/planned_total,
    см. Шаг 1/2 «план ≠ факт») и реальный факт (fact_amount/fact_confirmed) — раньше
    отдавались только «текущие» quantity/unit_price/total_price (которые задним числом
    подменяются ценой по итогам закупки) и фактических данных не было вовсе (фронт
    печатал жёсткую заглушку «ещё не поставлено»). Формула факта — та же единая
    purchase_item_fact_amount, что и в /feo-planned-items/comparison (Table A), чтобы
    два соседних UI-блока не показывали разные числа по одной и той же позиции.
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.contract import Contract
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.services.feo_plan import (
        purchase_item_fact_amount,
        FACT_CONFIRMED_STATUSES,
        _contract_item_totals,
        _purchase_item_totals,
    )

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            cat_col.label("cat_id"),
            PurchaseItem.id,
            PurchaseItem.item_name,
            PurchaseItem.quantity,
            PurchaseItem.unit,
            PurchaseItem.unit_price,
            PurchaseItem.total_price,
            PurchaseItem.planned_quantity,
            PurchaseItem.planned_unit_price,
            PurchaseItem.planned_total,
            PurchaseItem.final_total,
            PurchaseItem.purchase_id,
            PurchaseItem.product_id,
            PurchaseItem.feo_planned_item_id,
            PurchaseItem.wish_item_id,
            Purchase.purchase_number,
            Purchase.registry_number,
            Purchase.status.label("purchase_status"),
            Purchase.wish_id,
            Purchase.contract_id,
            Purchase.purchase_contract_type,
            Purchase.contract_price,
            Contract.contract_type.label("contract_type"),
            Contract.status.label("contract_status"),
            Contract.number.label("contract_number"),
            Product.category.label("product_category"),
            Product.product_type.label("product_type"),
            Product.photo_data.isnot(None).label("product_has_photo"),
            Product.photo_url,
            Product.photo_link,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(Product, PurchaseItem.product_id == Product.id)
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        # Выравниваем с app.services.feo_plan.py — остановленные закупки не считаются
        # (решение владельца 2026-08-13).
        .where(Purchase.stopped_at.is_(None))
        .where(cat_col.isnot(None))
        .order_by(cat_col, PurchaseItem.item_name)
    )
    rows = (await db.execute(stmt)).all()

    # Факт: та же формула, что и в /feo-planned-items/comparison — точное сопоставление
    # через ContractItem.source_item_id, иначе пропорция от purchases.contract_price.
    _item_ids = [r.id for r in rows]
    _purchase_ids = {r.purchase_id for r in rows}
    _ci_totals = await _contract_item_totals(db, _item_ids)
    _purchase_totals = await _purchase_item_totals(db, _purchase_ids)
    # Кол-во/цена факта (не только сумма): берём напрямую из ТОЧНО сопоставленной строки
    # договора (source_item_id), если она есть — та же строка, что дала _ci_totals.
    from app.models.contract_item import ContractItem as _ContractItem
    _ci_qty_price: dict[int, tuple] = {}
    if _item_ids:
        _ci_rows = (await db.execute(
            select(_ContractItem.source_item_id, _ContractItem.quantity, _ContractItem.unit_price)
            .where(_ContractItem.source_item_id.in_(_item_ids))
        )).all()
        for _row in _ci_rows:
            if _row.source_item_id not in _ci_qty_price:
                _ci_qty_price[_row.source_item_id] = (_row.quantity, _row.unit_price)
    # Легковесные объекты-обёртки под purchase_item_fact_amount (принимает ORM-подобные
    # PurchaseItem/Purchase — здесь только Row, поэтому оборачиваем нужные атрибуты).
    class _PiShim:
        __slots__ = ("total_price", "final_total")
    class _PShim:
        __slots__ = ("status", "contract_price", "acceptance_doc_amount")

    result: dict[int, list] = {}
    for r in rows:
        if r.product_id is not None and r.product_has_photo:
            product_photo = f"/api/products/{r.product_id}/photo"
        elif r.product_id is not None:
            product_photo = r.photo_url or r.photo_link or None
        else:
            product_photo = None

        items_count, items_sum = _purchase_totals.get(r.purchase_id, (1, Decimal(str(r.total_price or 0))))
        item_total = Decimal(str(r.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)

        pi_shim = _PiShim()
        pi_shim.total_price = r.total_price
        pi_shim.final_total = r.final_total
        p_shim = _PShim()
        p_shim.status = r.purchase_status
        p_shim.contract_price = r.contract_price
        p_shim.acceptance_doc_amount = None  # не выбирается этим запросом — не нужен для FACT_PRICED_STATUSES
        fact_amount, fact_allocated = purchase_item_fact_amount(
            pi_shim, p_shim, ratio, items_count, contract_item_total=_ci_totals.get(r.id)
        )
        fact_confirmed = r.purchase_status in FACT_CONFIRMED_STATUSES

        # Кол-во/цена факта: из точно сопоставленной строки договора, если есть;
        # иначе (пропорциональное распределение или факта ещё нет) — кол-во берём
        # как у ТЗ (обычно не меняется договором), цену — делением суммы на кол-во.
        _ci_qty, _ci_price = _ci_qty_price.get(r.id, (None, None))
        if _ci_qty is not None:
            fact_quantity = float(_ci_qty)
        elif fact_amount is not None:
            fact_quantity = float(r.quantity or 0)
        else:
            fact_quantity = None
        if _ci_price is not None:
            fact_unit_price = float(_ci_price)
        elif fact_amount is not None and fact_quantity:
            fact_unit_price = float(fact_amount) / fact_quantity
        else:
            fact_unit_price = None

        result.setdefault(r.cat_id, []).append({
            "id": r.id,
            "item_name": r.item_name,
            "quantity": float(r.quantity or 0),
            "unit": r.unit,
            "unit_price": float(r.unit_price or 0),
            "total_price": float(r.total_price or 0),
            # Снимок плана (Шаг 1/2 «план ≠ факт») — заморожен с момента объявления
            # закупки; фолбэк на текущие значения для старых позиций без снимка.
            "planned_quantity": float(r.planned_quantity) if r.planned_quantity is not None else float(r.quantity or 0),
            "planned_unit_price": float(r.planned_unit_price) if r.planned_unit_price is not None else float(r.unit_price or 0),
            "planned_total": float(r.planned_total) if r.planned_total is not None else float(r.total_price or 0),
            "fact_amount": float(fact_amount) if fact_amount is not None else None,
            "fact_quantity": fact_quantity,
            "fact_unit_price": fact_unit_price,
            "fact_confirmed": fact_confirmed,
            "fact_allocated": fact_allocated,
            "purchase_id": r.purchase_id,
            "feo_planned_item_id": r.feo_planned_item_id,
            "wish_item_id": r.wish_item_id,
            "purchase_number": r.purchase_number,
            "registry_number": r.registry_number,
            "purchase_status": r.purchase_status,
            "wish_id": r.wish_id,
            "contract_id": r.contract_id,
            "purchase_contract_type": r.purchase_contract_type,
            "contract_type": r.contract_type,
            "contract_status": r.contract_status,
            "contract_number": r.contract_number,
            "category": r.product_category or "Без категории",
            "product_type": r.product_type or "Без вида",
            "product_photo": product_photo,
        })
    return result
