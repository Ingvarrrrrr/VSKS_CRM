"""Read-only агрегаты плана/факта по дереву категорий ФЭО.

Разрезано из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения. Все семь путей — статичные (без {cat_id}) и обязаны
регистрироваться в app/routes.py ДО feo_categories.router (несёт catch-all
GET/PUT/DELETE "/{cat_id}") — иначе Starlette матчит их на catch-all раньше.

Ядро (гейты/чистые хелперы) зовётся через `from app.routers import
feo_categories as fc` — так monkeypatch `fc._has_feo_action`/
`fc._require_feo_category_write` в тестах продолжает работать независимо от
того, в каком файле реально живёт вызывающий обработчик.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user
from app.routers import feo_categories as fc
# Правило №6: рекурсия «budget узла = собственный, иначе сумма детей» —
# единственная реализация, см. app.services.subsidy_budget (та же формула,
# что app.routers.subsidies.calculate_budget_from_categories).
from app.services.subsidy_budget import compute_budget_map

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


@router.get("/plan-tree")
async def get_feo_plan_tree(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Числа по КАЖДОМУ узлу дерева ФЭО (и листу, и группе) — единый источник для
    фронта (сессия 2026-08-05, задача «формула только на бэкенде»: раньше
    SubsidiesView.vue пересчитывал «Плановую сумму»/«Плановое количество» сам
    (feoPlannedDisplayRaw/feoQtyDisplayRaw, MAX(план, выбрано) + сверх_плана —
    СТАРАЯ формула), а KPI «Запланировано» на дашборде/в списке субсидий считал
    _calculate_feo_planned_tree_bulk по НОВОЙ формуле compute_feo_plan_tree —
    два разных числа на одном экране. Теперь фронт только читает готовое отсюда.

    Обёртка над app.services.feo_plan.compute_feo_plan_tree — просто отдаёт её
    per-node словарь наружу, ничего не пересчитывая (см. её подробный docstring
    за формулой «заказ замещает план, когда количество набрано полностью»).

    Response: {cat_id: {plan_manual, ordered_qty, ordered_sum, over, over_quantity,
                         plan, display, residual, forecast, forecast_over,
                         consumed, consumed_quantity, qty_plan, display_quantity}}
    display — то самое число, которое обязано совпасть с KPI «Запланировано»
    (сумма display корневых узлов == _calculate_feo_planned_tree_bulk[subsidy_id]).
    display_quantity — аналог display, но для «Планового количества» узла.

    Плюс АДДИТИВНЫЙ ключ "unassigned" (строкой, не числовой id — чтобы не
    столкнуться с id категории): {amount, purchase_count, purchase_ids} — деньги
    закупок субсидии в PLANNED_STATUSES, у которых НИ сама закупка, НИ одна её
    позиция не привязаны к категории ФЭО (баг «Ведётся работа» видит деньги,
    дерево — нет, см. сессию 2026-08-05). Не участвует в дереве/ИТОГО — чисто
    справочная сумма для отдельной строки на фронте. Отдаётся всегда (нули, если
    таких закупок нет), чтобы фронт не городил доп. ветвление на отсутствие ключа.

    "budget" (задача владельца 2026-08-06, «остаток по каждой категории ФЭО в
    дереве выбора») — финансирование по ФЭО узла (то же значение, что уже
    участвует в формуле display/excess_amount выше), null если не задано.
    free = budget − display считает фронт (см. FeoTreeSelect nodeAmounts).

    "excess_culprit" (задача владельца, план zany-fluttering-mountain.md п.4,
    2026-08-10) — закупка-«виновник», из-за которой узел вышел за ФЭО: null,
    если превышения нет/оно согласовано, иначе {purchase_id, purchase_number,
    item_id, item_name, amount_before, amount_at_crossing, cumulative_after} —
    см. app.services.feo_plan.find_excess_culprit за методом определения.

    Право feo_budget.view_tree_amounts (см. backend/app/__init__.py) гейтит ВСЕ
    денежные поля узла (plan_manual, ordered_sum, over, plan, budget, display,
    residual, forecast, forecast_over, consumed, excess_amount) — без права они
    приходят null (структура ответа не меняется, количественные/булевы поля
    остаются). superadmin — всегда видит.

    Задача владельца, сессия 2026-08-12 («план ≠ факт», продолжение) — три
    дополнительных поля узла (см. app.services.feo_plan.compute_feo_plan_tree
    docstring за формулой):
      manual_plan_entered/excess_plan_over_manual/excess_plan_approved/
      excess_plan_pending/excess_plan_items — ТРЕТИЙ вид превышения: Σ ВСЕХ
      плановых позиций листа/подветки больше «ручного» плана (поля категории
      старого формата + Σ позиций без auto_created). excess_plan_items —
      [{name, amount}] автоматически заведённых позиций, из-за которых вылезли.
      excess_approval_amount/excess_approval_at/excess_approval_by_id/
      excess_approval_by_name — «превышение согласовано»: данные последнего
      approved-запроса PlanExcessApproval по категории (висит, даже если узел
      всё ещё формально в превышении — display включает его целиком).

    Задача владельца, план zany-fluttering-mountain.md (2026-08-13, переключатель
    способа расчёта плана): plan_source ('planned_items' | 'manual_sum') и
    manual_plan_amount — форма категории читает/пишет эту пару (POST/PUT
    /feo-categories). excess_plan_items теперь в новом виде — [{id, name, amount,
    purchases: [{id, registry_number, purchase_number, status, status_label,
    amount, stopped_at}]}], клик по виновнику открывает его закупку(и).
    excess_approval_plan_before/excess_approval_plan_after — «план был X → стал
    Y» для excess_kind='plan_over_manual' (см. app.services.feo_plan и
    app.routers.plan_excess), null для остальных видов превышения.
    """
    from app.services.feo_plan import compute_feo_plan_tree, find_excess_culprit
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_budget import PLANNED_STATUSES
    from sqlalchemy import exists, and_

    can_view_amounts = await fc._has_feo_action(current_user, db, "feo_budget.view_tree_amounts")

    tree = await compute_feo_plan_tree(db, [subsidy_id])
    result: dict = {
        cat_id: {
            "plan_manual": node["plan_manual"],
            "ordered_qty": node["ordered_qty"],
            "ordered_sum": node["ordered_sum"],
            "over": node["over"],
            "over_quantity": node["over_quantity"],
            "plan": node["plan"],
            "budget": node["budget"],
            "display": node["display"],
            "residual": node["residual"],
            "forecast": node["forecast"],
            "forecast_over": node["forecast_over"],
            "consumed": node["consumed"],
            "consumed_quantity": node["consumed_quantity"],
            "qty_plan": node["qty_plan"],
            "display_quantity": node["display_quantity"],
            # Согласование превышения плана над финансированием ФЭО (задача владельца
            # «блокировать пока не согласовано», 2026-08-05) — см. compute_feo_plan_tree
            # и app.routers.plan_excess. excess_amount>0 — есть превышение над node.budget;
            # excess_pending — есть незакрытый запрос на согласование; excess_approved —
            # превышение легализовано (display включает его полностью).
            "excess_amount": node["excess_amount"],
            "excess_pending": node["excess_pending"],
            "excess_approved": node["excess_approved"],
            # Задача владельца «план ≠ факт» (2026-08-06): факт со стадии «Ведётся
            # работа» + независимое превышение «факт дороже плана» — см.
            # compute_feo_plan_tree docstring (шаг C). Отсутствовали здесь —
            # эндпоинт отдавал только явный whitelist полей и терял их молча.
            "fact": node["fact"],
            "fact_quantity": node["fact_quantity"],
            "excess_over_feo": node["excess_over_feo"],
            "excess_fact_over_plan": node["excess_fact_over_plan"],
            "excess_fact_approved": node["excess_fact_approved"],
            "excess_fact_pending": node["excess_fact_pending"],
            # Задача владельца п.2 (2026-08-12, сессия «план ≠ факт», продолжение):
            # ТРЕТИЙ вид превышения — Σ плановых позиций против «ручного» плана,
            # см. compute_feo_plan_tree docstring.
            "manual_plan_entered": node["manual_plan_entered"],
            "excess_plan_over_manual": node["excess_plan_over_manual"],
            "excess_plan_approved": node["excess_plan_approved"],
            "excess_plan_pending": node["excess_plan_pending"],
            "excess_plan_items": node["excess_plan_items"],
            # Владелец, план zany-fluttering-mountain.md (2026-08-13): переключатель
            # способа расчёта плана узла — форма категории читает/пишет эту пару.
            "plan_source": node["plan_source"],
            "manual_plan_amount": node["manual_plan_amount"],
            # Задача владельца п.4 (2026-08-12): «превышение согласовано» — данные
            # последнего approved-запроса по категории (см. compute_feo_plan_tree).
            "excess_approval_amount": node["excess_approval_amount"],
            "excess_approval_at": node["excess_approval_at"],
            "excess_approval_by_id": node["excess_approval_by_id"],
            "excess_approval_by_name": node["excess_approval_by_name"],
            # Владелец, план zany-fluttering-mountain.md (2026-08-13): «план был X →
            # стал Y» на постоянной плашке — см. compute_feo_plan_tree.
            "excess_approval_plan_before": node["excess_approval_plan_before"],
            "excess_approval_plan_after": node["excess_approval_plan_after"],
            # Виновник превышения (задача владельца, план zany-fluttering-mountain.md
            # п.4, 2026-08-10) заполняется НИЖЕ, точечно только для узлов с
            # неснятым excess_amount — find_excess_culprit не бесплатна (доп. запрос),
            # гнать её на каждый узел дерева на каждый вызов (в т.ч. KPI-дашборд) не нужно.
            "excess_culprit": None,
        }
        for cat_id, node in tree.items()
    }

    # Виновник превышения плана над ФЭО — «должна отображаться данная закупка и
    # показать, что из-за неё всё превысило» (владелец). Считаем только для узлов
    # с непогашенным excess_amount (обычно единицы, не весь тысячестрочный тред).
    for cat_id, node in tree.items():
        if (node.get("excess_amount") or 0) > 0.005 and not node.get("excess_approved"):
            result[cat_id]["excess_culprit"] = await find_excess_culprit(db, cat_id, node.get("budget"))

    unassigned_stmt = (
        select(Purchase.id, Purchase.planned_total_price)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.feo_category_id.is_(None))
        .where(~exists().where(and_(
            PurchaseItem.purchase_id == Purchase.id,
            PurchaseItem.feo_category_id.isnot(None),
        )))
    )
    unassigned_rows = (await db.execute(unassigned_stmt)).all()
    result["unassigned"] = {
        "amount": sum(float(r.planned_total_price or 0) for r in unassigned_rows),
        "purchase_count": len(unassigned_rows),
        "purchase_ids": [r.id for r in unassigned_rows[:50]],
    }

    if not can_view_amounts:
        MONEY_FIELDS = (
            "plan_manual", "ordered_sum", "over", "plan", "budget", "display",
            "residual", "forecast", "forecast_over", "consumed", "excess_amount",
            "fact", "excess_over_feo", "excess_fact_over_plan", "excess_culprit",
            "manual_plan_entered", "excess_plan_over_manual", "excess_plan_items",
            "excess_approval_amount", "manual_plan_amount",
            "excess_approval_plan_before", "excess_approval_plan_after",
        )
        for cat_id, node in result.items():
            if cat_id == "unassigned":
                node["amount"] = None
                continue
            for f in MONEY_FIELDS:
                if f in node:
                    node[f] = None

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


@router.get("/leaves")
async def get_feo_leaves(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns leaf FeoCategory nodes (без детей) with aggregated used_amount via feo_category_id.

    Response: [{id, name, parent_id, level, budget, used_amount, residual, path}]
    where path = "Direction › Subcategory › LeafName".

    Право feo_budget.view_leaf (см. backend/app/__init__.py, дефолт — все роли,
    включая employee) гейтит денежные поля (budget, contracted_used, planned_used,
    uncontracted_remaining, spendable_remaining, used_amount, residual) — без права
    приходят 0, структура ответа не меняется (закрытие дыры: раньше эндпоинт вообще
    не проверял права, см. задачу владельца 2026-08-06).
    """
    can_view_leaf = await fc._has_feo_action(current_user, db, "feo_budget.view_leaf")
    from sqlalchemy import select, func as sqlfunc, case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES, PLANNED_STATUSES

    # Все FeoCategory для subsidy
    cats_q = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    all_cats = (await db.execute(cats_q)).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1

    # Leaves = категории у которых нет детей в feo_categories
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]
    if not leaves:
        return []

    leaf_ids = [c.id for c in leaves]

    # Aggregate contracted_used and planned_used per feo_category_id via conditional sums
    used_q = (
        select(
            PurchaseItem.feo_category_id,
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            sqlfunc.coalesce(
                sqlfunc.sum(case((_Purchase.status.in_(list(PLANNED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(PurchaseItem.feo_category_id.in_(leaf_ids))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(PurchaseItem.feo_category_id)
    # leaf_used_map: {feo_category_id: (contracted_used, planned_used)}
    leaf_used_map: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        leaf_used_map[r.feo_category_id] = (float(r.contracted_used), float(r.planned_used))

    # Build path "Direction › Subcategory › Leaf"
    def build_path(cat) -> str:
        names = [cat.name]
        cur = cat
        while cur.parent_id is not None and cur.parent_id in cat_by_id:
            cur = cat_by_id[cur.parent_id]
            names.append(cur.name)
        return " \u203a ".join(reversed(names))

    result = []
    for c in leaves:
        budget = float(c.budget or 0)
        contracted_used, planned_used = leaf_used_map.get(c.id, (0.0, 0.0))
        uncontracted_remaining = budget - contracted_used
        spendable_remaining = budget - planned_used
        if not can_view_leaf:
            budget = contracted_used = planned_used = uncontracted_remaining = spendable_remaining = 0.0
        result.append({
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "level": c.level,
            "budget": budget,
            # New metrics
            "contracted_used": contracted_used,
            "planned_used": planned_used,
            "uncontracted_remaining": uncontracted_remaining,
            "spendable_remaining": spendable_remaining,
            # Legacy fields (kept for backward compat): used_amount = planned_used, residual = spendable_remaining
            "used_amount": planned_used,
            "residual": spendable_remaining,
            "path": build_path(c),
        })

    # Сортировка по path для удобства autocomplete
    result.sort(key=lambda x: x["path"])
    return result


@router.get("/plan-positions")
async def get_plan_positions(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Единый источник «плановых позиций» субсидии.

    Плановая позиция — конечный элемент дерева ФЭО (FeoCategory без детей) с
    заполненными planned_quantity/planned_amount (произведение > 0). Плюс —
    отдельными записями kind='planned_item' — существующие FeoPlannedItem
    (Ур.5, необязательная более глубокая детализация внутри элемента).

    kind:
      'plan_position' — budget IS NULL AND feo_amount IS NULL (план без статьи ФЭО,
                         «мы сами запланировали купить именно это»)
      'feo_article'    — budget и/или feo_amount заполнены (план = статья ФЭО)
      'planned_item'   — FeoPlannedItem внутри элемента

    Response: [{id, name, path, category_id, ancestor_ids, kind, planned_quantity, unit,
                planned_amount, unit_price, consumed, consumed_quantity,
                residual, residual_quantity}]
    planned_amount — ИТОГОВАЯ сумма плана (quantity × unit_price); unit_price —
    цена за единицу (= FeoCategory.planned_amount / FeoPlannedItem.amount per unit).
    ancestor_ids — id всех предков category_id (от корня до непосредственного родителя),
    см. app.services.feo_plan.build_ancestor_ids. Фронт (FeoPlannedItemsSelect.vue)
    матчит категорию, выбранную в дереве заявки/закупки, по `category_id === selected
    || ancestor_ids.includes(selected)` — НАПРЯМУЮ по этому полю, а не обходом
    props.nodes/useFeoLeaves (тот массив обрезан filterFundedNodes: конечные категории
    без собственного budget вырезаются из дерева, даже если у них есть
    planned_quantity/planned_amount — баг «В этой категории нет плановых позиций»,
    сессия 2026-08-05).

    Дополнительно на строках kind='plan_position'/'feo_article' (сессия 2026-08-05,
    формула v2 — «заказ замещает план, пока не набрано количество», см.
    app.services.feo_plan.compute_feo_plan_tree): `ordered_qty`, `ordered_sum`,
    `plan_manual`, `ordered_residual`, `forecast`, `forecast_over`. Существующие
    `consumed`/`consumed_quantity`/`residual`/`residual_quantity` НЕ трогаем (старая
    семантика — используются FeoPlannedItemsSelect.vue/PurchaseItemsEditor.vue для
    предотвращения повторного выбора уже занятого плана); `ordered_residual` — НОВЫЙ
    остаток по формуле v2 (план − ordered_sum), под другим именем, чтобы не столкнуть
    с уже существующим `residual`.

    kind='planned_item' — ВАЖНО (владелец, сессия 2026-08-18): FeoPlannedItem может
    жить не только под конечной категорией (листом), но и на НАПРАВЛЕНИИ/подкатегории
    (FeoCategory с детьми) — так заводят позицию, если решили не спускаться до листа.
    Раньше запрос ниже брал FeoPlannedItem только по leaf_ids — такая позиция участвовала
    в деньгах (compute_feo_plan_tree считает собственные FeoPlannedItem групп, см. его
    докстринг — «Бинт марлевый Навтекс Life» там боевой пример именно такого случая),
    но пропадала из списка выбора: UI показывал «Выбрать плановую позицию», будто
    привязки нет, хотя закупка уже была привязана к существующей записи. Обязаны
    показывать её всегда — иначе пользователь не может понять, куда делась позиция,
    на которую сама система ссылается. path/ancestor_ids для таких строк строятся тем
    же build_category_path/build_ancestor_ids, что и для листьев — они просто идут
    вверх по parent_id, им всё равно, лист cat или группа.

    exclude_purchase_id/exclude_wish_id (сессия 2026-08-17): редактирование
    существующей закупки/заявки — её собственные строки не должны выглядеть
    занявшими план (иначе позиция сравнивается сама с собой: остаток 0, и UI
    повторно вычитает ту же сумму — баг «план 54 318 · выбрано 54 318 · не
    хватает 54 318»). Ровно то же уже делает GET /api/feo-planned-items/residuals.
    Поля `ordered_qty`/`ordered_sum`/`plan_manual`/`ordered_residual`/`forecast`/
    `forecast_over` приходят из compute_feo_plan_tree и исключение НЕ учитывают —
    это осознанно, в UI-подписи «не хватает» они не участвуют.

    `unlinked_actual_amount` (владелец, сессия 2026-08-31, «план ≠ факт» продолжение)
    — Σ позиций закупок ЭТОЙ категории (по COALESCE(PurchaseItem.feo_category_id,
    Purchase.feo_category_id)), у которых feo_planned_item_id IS NULL (ни к одной
    плановой позиции не привязаны), в PLANNED_STATUSES (от «План закупок» и дальше,
    черновики не считаются), Purchase.stopped_at IS NULL, БЕЗ over_plan=true — см.
    app.services.feo_plan.unlinked_actual_by_category. exclude_purchase_id/
    exclude_wish_id применяются так же, как и к consumed/residual выше (редактируемый
    документ не считает сам себя). Одно и то же число повторено на КАЖДОЙ строке
    данной категории (и kind='plan_position'/'feo_article', и все её 'planned_item'),
    т.к. это свойство категории целиком, а не отдельной плановой позиции — фронт
    прибавляет его к Σ плановых позиций категории, получая «занято по статье»
    (владелец: «занято = плановые позиции + непривязанные фактические, показывать
    отдельно, сколько из этого не привязано»).
    """
    from app.models.feo_planned_item import FeoPlannedItem
    from app.services.feo_plan import (
        plan_consumption_by_category, planned_item_consumption, build_category_path,
        build_ancestor_ids, compute_feo_plan_tree, unlinked_actual_by_category,
    )

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

    consumption = await plan_consumption_by_category(
        db, [subsidy_id], exclude_purchase_id=exclude_purchase_id, exclude_wish_id=exclude_wish_id
    )
    tree = await compute_feo_plan_tree(db, [subsidy_id])
    # Владелец (сессия 2026-08-31): «занято по статье» = плановые позиции + непривязанные
    # фактические (позиции закупок этой категории без своей плановой строки) — см.
    # unlinked_actual_by_category. exclude_purchase_id/exclude_wish_id — та же логика,
    # что и в consumption выше: редактируемый документ не должен считать сам себя.
    unlinked_actual = await unlinked_actual_by_category(
        db, [subsidy_id], exclude_purchase_id=exclude_purchase_id, exclude_wish_id=exclude_wish_id
    )

    result = []
    for c in leaves:
        qty = float(c.planned_quantity) if c.planned_quantity is not None else 0.0
        unit_price = float(c.planned_amount) if c.planned_amount is not None else 0.0
        planned_total = qty * unit_price
        if planned_total <= 0:
            continue
        cons = consumption.get(c.id, {"consumed": 0.0, "consumed_quantity": 0.0})
        consumed = cons["consumed"]
        consumed_qty = cons["consumed_quantity"]
        kind = "plan_position" if (c.budget is None and c.feo_amount is None) else "feo_article"
        node = tree.get(c.id, {})
        result.append({
            "id": c.id,
            "name": c.name,
            "path": build_category_path(c, cat_by_id),
            "category_id": c.id,
            # Предки категории (от корня до непосредственного родителя) — фронт
            # сопоставляет позицию с выбранной в дереве категорией через
            # category_id == selected ИЛИ selected in ancestor_ids, без обхода
            # обрезанного props.nodes (см. build_ancestor_ids).
            "ancestor_ids": build_ancestor_ids(c, cat_by_id),
            "kind": kind,
            "planned_quantity": qty,
            "unit": c.unit,
            "planned_amount": planned_total,
            "unit_price": unit_price,
            "consumed": consumed,
            "consumed_quantity": consumed_qty,
            "residual": planned_total - consumed,
            "residual_quantity": qty - consumed_qty,
            "ordered_qty": node.get("ordered_quantity", 0.0),
            "ordered_sum": node.get("ordered", 0.0),
            "plan_manual": node.get("plan_manual", planned_total),
            "ordered_residual": node.get("residual", planned_total),
            "forecast": node.get("forecast", planned_total),
            "forecast_over": node.get("forecast_over", 0.0),
            # Владелец (сессия 2026-08-31): непривязанные фактические позиции ЭТОЙ
            # категории — см. unlinked_actual_by_category. Отдельно от plan_manual/
            # consumed выше (те считают только сами плановые позиции) — фронт
            # прибавляет это число к «уже запланировано» и показывает отдельной
            # строкой «в том числе не привязано к плану».
            "unlinked_actual_amount": unlinked_actual.get(c.id, 0.0),
        })

    # + FeoPlannedItem (Ур.5) — детализация внутри элементов. Владелец 2026-08-18:
    # «"Бинт марлевый Навтекс Life" написано, что находится на уровне "Окружные" —
    # но на уровне "Окружные" его нет. Если пишет, что он там, должен же он как-то
    # отображаться?» — раньше запрос брал FeoPlannedItem ТОЛЬКО под leaves (конечными
    # категориями), но FeoPlannedItem может жить и на НАПРАВЛЕНИИ/группе (категория с
    # детьми) — владельцы заводят такие позиции напрямую на узле верхнего уровня, не
    # спускаясь до листа. compute_feo_plan_tree уже умеет считать деньги по таким
    # группам (см. его докстринг — «Бинт марлевый» там же боевой пример), т.е. в
    # расчётах позиция участвовала всегда; баг был только в том, что её не было видно
    # в списке выбора — интерфейс показывал «Выбрать плановую позицию», будто привязки
    # нет вовсе. Поэтому здесь фильтр по all_cats (вся субсидия), а не по leaf_ids.
    if all_cats:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem)
            .where(FeoPlannedItem.feo_category_id.in_([c.id for c in all_cats]))
            .where(FeoPlannedItem.is_active == True)
            .order_by(FeoPlannedItem.id)
        )).scalars().all()
        if fpi_rows:
            fpi_ids = [it.id for it in fpi_rows]
            fpi_cons = await planned_item_consumption(db, fpi_ids, exclude_purchase_id, exclude_wish_id)
            for it in fpi_rows:
                cat = cat_by_id.get(it.feo_category_id)
                planned_total = float(it.amount or 0)
                qty = float(it.quantity or 0)
                c_cons = fpi_cons.get(it.id, {"used": 0.0, "used_qty": 0.0})
                consumed = c_cons["used"]
                consumed_qty = c_cons["used_qty"]
                result.append({
                    "id": it.id,
                    "name": it.name,
                    "path": build_category_path(cat, cat_by_id) if cat else "",
                    "category_id": it.feo_category_id,
                    "ancestor_ids": build_ancestor_ids(cat, cat_by_id) if cat else [],
                    "kind": "planned_item",
                    "planned_quantity": qty,
                    "unit": it.unit,
                    "planned_amount": planned_total,
                    # Владелец (2026-09-02, см. модель FeoPlannedItem.unit_price): цена за
                    # единицу — САМОСТОЯТЕЛЬНОЕ поле, не деление суммы на количество. Если
                    # оно NULL, план «мягкий» — количество ориентировочное, делить нельзя
                    # (получалось бы выдуманное число вроде «200000/50=4000», которое потом
                    # ошибочно ограничивало закупку). Отдаём None — фронт обязан не
                    # подставлять его как факт (см. PurchaseItemsEditor.vue).
                    "unit_price": float(it.unit_price) if it.unit_price is not None else None,
                    "consumed": consumed,
                    "consumed_quantity": consumed_qty,
                    "residual": planned_total - consumed,
                    "residual_quantity": qty - consumed_qty,
                    # См. комментарий на строках kind='plan_position'/'feo_article' выше —
                    # то же число (per-категория, не per-плановая-позиция), чтобы фронт
                    # мог прочитать его с ЛЮБОЙ строки этой категории независимо от того,
                    # план введён на листе целиком или отдельными Ур.5 позициями (именно
                    # этот случай — контрольный пример владельца, категория без собственных
                    # planned_quantity/planned_amount, план только в FeoPlannedItem).
                    "unlinked_actual_amount": unlinked_actual.get(it.feo_category_id, 0.0),
                })

    result.sort(key=lambda x: x["path"])
    return result


@router.get("/budget-residuals")
async def feo_budget_residuals(
    subsidy_id: int = Query(...),
    category_ids: str = Query("", description="comma-separated leaf FeoCategory ids"),
    exclude_purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Остатки бюджета по ФЭО для формы закупки.

    Для пользователей с feo_budget.view_all_levels возвращает направления (ур.1)
    и ancestors предков в каждом листе. Без этого права: directions=[],
    ancestors=[] — только сам листовой остаток.

    budget листа = FeoCategory.budget; used = SUM(PurchaseItem.total_price) по feo_category_id листа.
    Узел выше: budget = собственный .budget если задан, иначе сумма budget детей;
    used = сумма used всех листьев-потомков. residual = budget - used.
    Ответ: {directions:[{id,name,level,path,budget,used,residual}],
            leaves:[{id,name,level,path,budget,used,residual,ancestors:[...]}]}
    (ancestors — сверху вниз: ур.1 первым).
    """
    from app.auth.permissions import _get_effective, _active_org
    effective = await _get_effective(current_user, db, _active_org(current_user))
    can_view_all_levels = (current_user.role == "superadmin") or ("feo_budget.view_all_levels" in effective)
    from sqlalchemy import select as _sel, func as _f, case as _case
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase as _Purchase
    from app.routers.purchase_budget import CONTRACTED_STATUSES, PLANNED_STATUSES

    ids = [int(x) for x in category_ids.split(",") if x.strip().isdigit()]
    all_cats = (await db.execute(
        _sel(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return {"directions": [], "leaves": []}
    cat_by_id = {c.id: c for c in all_cats}
    children: dict[int, list] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children.setdefault(c.parent_id, []).append(c.id)
    leaf_ids_all = [c.id for c in all_cats if not children.get(c.id)]

    used_q = (
        _sel(
            PurchaseItem.feo_category_id,
            _f.coalesce(
                _f.sum(_case((_Purchase.status.in_(list(CONTRACTED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("contracted_used"),
            _f.coalesce(
                _f.sum(_case((_Purchase.status.in_(list(PLANNED_STATUSES)), PurchaseItem.total_price), else_=0)),
                0,
            ).label("planned_used"),
        )
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(PurchaseItem.feo_category_id.in_(leaf_ids_all))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = used_q.group_by(PurchaseItem.feo_category_id)
    # leaf_used: {feo_category_id: (contracted_used, planned_used)}
    leaf_used: dict[int, tuple[float, float]] = {}
    for r in (await db.execute(used_q)).all():
        leaf_used[r.feo_category_id] = (float(r.contracted_used), float(r.planned_used))

    def descendant_leaves(cid):
        ch = children.get(cid)
        if not ch:
            return [cid]
        out = []
        for x in ch:
            out.extend(descendant_leaves(x))
        return out

    # Правило №6: budget по каждому узлу — общая рекурсия (compute_budget_map),
    # не отдельная копия. Вычисляется один раз для всего дерева субсидии.
    budget_map = compute_budget_map(all_cats)

    def contracted_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[0] for l in descendant_leaves(cid))

    def planned_of(cid):
        return sum(leaf_used.get(l, (0.0, 0.0))[1] for l in descendant_leaves(cid))

    def node_info(cid):
        c = cat_by_id[cid]
        b = budget_map.get(cid, 0.0)
        cu = contracted_of(cid)
        pu = planned_of(cid)
        return {
            "id": cid, "name": c.name, "level": c.level,
            "budget": b,
            "contracted_used": cu,
            "planned_used": pu,
            "uncontracted_remaining": b - cu,
            "spendable_remaining": b - pu,
            # Legacy fields (backward compat): used = planned_used, residual = spendable_remaining
            "used": pu,
            "residual": b - pu,
        }

    def path_of(cid):
        names = []
        cur = cat_by_id.get(cid)
        while cur is not None:
            names.append(cur.name)
            cur = cat_by_id.get(cur.parent_id) if cur.parent_id else None
        return " \u203a ".join(reversed(names))

    # Направления (ур.1) субсидии — только для пользователей с view_all_levels.
    directions = []
    if can_view_all_levels:
        # Порядок как во вкладке субсидии: sort_order, затем id (не алфавит)
        roots = [c for c in all_cats if c.level == 1 or c.parent_id is None]
        roots.sort(key=lambda c: (c.sort_order is None, c.sort_order or 0, c.id))
        for c in roots:
            d = node_info(c.id)
            d["path"] = path_of(c.id)
            directions.append(d)

    leaves = []
    for lid in ids:
        if lid not in cat_by_id:
            continue
        leaf = node_info(lid)
        leaf["path"] = path_of(lid)
        # ancestors только для пользователей с view_all_levels
        if can_view_all_levels:
            ancestors = []
            cur = cat_by_id[lid]
            while cur.parent_id and cur.parent_id in cat_by_id:
                cur = cat_by_id[cur.parent_id]
                ancestors.append(node_info(cur.id))
            leaf["ancestors"] = list(reversed(ancestors))
        else:
            leaf["ancestors"] = []
        leaves.append(leaf)
    return {"directions": directions, "leaves": leaves}
