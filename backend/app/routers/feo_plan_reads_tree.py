"""Read-only агрегаты плана ФЭО — per-node числа дерева (обёртки над compute_feo_plan_tree).

Сосед feo_plan_reads.py, вынесенный из него в волне 3a (2026-09-08, Правило №5:
исходный feo_plan_reads.py разросся до 1016 строк). Несёт /plan-tree и
/plan-positions — оба строятся вокруг app.services.feo_plan.compute_feo_plan_tree
и отдают per-узел (или per-плановая-позиция) картину «план/заказано/факт/
превышение», в отличие от «сырых» агрегатов Purchase/PurchaseItem в
feo_plan_reads.py и бюджет/остаток по листу/направлению в
feo_plan_reads_budget.py.

Оба пути статичные (без {cat_id}) и, как и соседи, ОБЯЗАНЫ регистрироваться в
app/routes.py ДО feo_categories.router (несёт catch-all GET/PUT/DELETE
"/{cat_id}"). Гейт прав — через `from app.routers import feo_categories as fc;
fc._has_feo_action(...)`, чтобы monkeypatch в тестах продолжал работать
независимо от файла-обработчика.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user
from app.routers import feo_categories as fc

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


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

    # ПРАВИЛО №6 (волна 4b-2d): PLANNED_STATUSES включает и стадии ПОСЛЕ
    # договора (work_in_progress/contracted/ordered/delivered/paid) — раньше
    # здесь читался голый Purchase.planned_total_price (застывший план), из-за
    # чего «Ведётся работа» и подобные закупки без категории ФЭО показывали
    # плановую, а не актуальную по стадии сумму. Единый источник — та же
    # effective_amount_expr(), что и get_purchase_totals() в feo_plan_reads.py
    # (SQL-агрегат, без доп. запросов на Σ contract_items/purchase_items —
    # см. её докстринг про этот компромисс).
    from app.services.purchase_amounts import effective_amount_expr
    unassigned_stmt = (
        select(Purchase.id, effective_amount_expr().label("effective_amount"))
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
        "amount": sum(float(r.effective_amount or 0) for r in unassigned_rows),
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
    # отображаться?» — раньше запрос ниже брал FeoPlannedItem ТОЛЬКО под leaves (конечными
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
