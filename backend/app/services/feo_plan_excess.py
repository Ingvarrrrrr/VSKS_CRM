"""feo_plan_excess.py — виновник превышения плана и блокирующий контроль превышения.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). find_excess_culprit воспроизводит ТУ ЖЕ формулу
плана листа, что и compute_feo_plan_tree (через общий feo_plan_common.
_leaf_plan_manual, ПРАВИЛО №6) — не заводить вторую формулу плана здесь.

Владелец, Волна 1 п.8 (2026-09-13): «0» в feo_categories.budget трактуется как
«сумма не задана» наравне с NULL — весь узловой контроль ниже (excess_amount/
excess_over_feo и производный от него find_excess_culprit) читает уже
НОРМАЛИЗОВАННОЕ значение budget из node["budget"] (см. compute_feo_plan_tree.
_visit, ПРАВИЛО №6 — единственная точка нормализации 0→None). Эта нормализация
здесь НЕ дублируется: budget сюда приходит только через
compute_feo_plan_tree/assert_no_unapproved_excess, второй раз из FeoCategory.
budget напрямую в этом файле не читается.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_common import _leaf_plan_manual, _order_substituted_plan
from app.services.feo_plan_tree import compute_feo_plan_tree


async def find_excess_culprit(
    db: AsyncSession, feo_category_id: int, budget: Optional[float]
) -> Optional[dict]:
    """Находит «виновника» превышения плана над финансированием ФЭО узла
    feo_category_id (compute_feo_plan_tree.excess_amount) — задача владельца, план
    zany-fluttering-mountain.md п.4 «Превышение: показать виновника» (2026-08-10):
    «должна отображаться данная закупка и показать, что из-за неё всё превысило».

    ВАЖНО — что именно составляет full_display (plan + over), с которым
    сравнивается budget в compute_feo_plan_tree._visit (см. её docstring), и
    почему виновник ищется именно там, а не в сумме позиций закупок «в лоб»:
      «Плановая сумма» листа (plan_manual) — это НЕ сумма позиций закупок этой
      категории, а вычисляется ТЕМ ЖЕ переключателем FeoCategory.plan_source,
      что и в дереве (см. _leaf_plan_manual выше, зеркалит
      compute_feo_plan_tree._manual_plan_for): 'planned_items' (умолчание) —
      Σ amount активных FeoPlannedItem (Ур.5, «плановые позиции» — панель
      «Добавить плановую», из примера владельца «Great Wall POER · план
      2 шт × 4 000 000»); 'manual_sum' — ОДНО число FeoCategory.manual_plan_amount,
      пока накопленное превышение над ним не согласовано (после согласования —
      тоже Σ позиций). Плюс `over` — Σ сумм PurchaseItem с over_plan=true
      (сознательно сверх плана), прибавляется БЕЗУСЛОВНО поверх — вот это уже
      реальные позиции закупок.

    ═══ Владелец, Волна 1 п.13 (2026-09-13), дословно: «Написано, что сумма
    6 645 234,8 — Запланировано, при этом 4 000 000 было запланировано в ФЭО...
    надо убрать 2 645 234,48... но при этом дальше идёт справка, из-за чего
    произошло превышение: „Bosch 36 pro“... добавила 28 560,00 ₽, после неё
    выбрано 4 012 784,48 ₽ при ФЭО 4 000 000,00 ₽» — цифра в справке (4 012 784,48,
    «перебор» на 12 784,48) НИКАК не била с плашкой (превышение 2 645 234,48). ═══

    ПРИЧИНА (нашлась ДО правки, зафиксирована здесь, чтобы не повторить): эта
    функция считала Σ контрибьюторов ТОЛЬКО по _leaf_plan_manual (план листьев)
    + over_plan-позициям, ИГНОРИРУЯ два места, где реальная формула дерева
    (compute_feo_plan_tree) расходится с этим:
      1) замещение «заказ вместо плана» (_order_substituted_plan,
         feo_plan_common.py, задача владельца 2026-08-05) — когда узел заказан
         ПОЛНОСТЬЮ, его вклад в план становится фактической суммой заказа
         (ordered), а НЕ Σ FeoPlannedItem.amount. Эта функция раньше вообще не
         знала о нём — считала «план» голой Σ позиций, даже если реальный
         заказ (и, соответственно, реальный full_display дерева) был больше.
      2) СОБСТВЕННЫЕ плановые позиции узлов-НЕ-листьев (ФОРМУЛА v3
         compute_feo_plan_tree, «направление со временем может наполниться») —
         раньше проход шёл только по leaf_ids (конечным категориям), теряя
         вклад направлений/групп с собственными FeoPlannedItem.
    Из-за (1)+(2) Σ контрибьюторов этой функции почти всегда была МЕНЬШЕ
    настоящего full_display узла — «граница» пересекалась контрибьютором с
    маленьким вкладом (28 560), а не тем, что реально довело сумму до
    6 645 234,8. Теперь функция проходит ПО ВСЕМ узлам поддерева (не только
    листьям) и на каждом применяет ТУ ЖЕ _order_substituted_plan, что и дерево
    — Σ контрибьюторов гарантированно равна full_display узла (см. поле
    "total_plan_amount" в возврате, тест test_feo_excess_culprit_matches_control.py).

    Поэтому виновник ищется как ПЕРВЫЙ элемент, на котором нарастающая сумма по
    ДВУМ источникам (в порядке их вклада в формулу — сначала «план», потом
    «сверх плана») впервые пересекла budget:
      1) для узлов (листьев и направлений/групп с собственными позициями) в
         режиме 'planned_items' (и НЕ замещённых заказом «целиком») — активные
         FeoPlannedItem узла, по возрастанию `created_at` (у FeoPlannedItem ЕСТЬ
         created_at — реальное время появления плановой позиции, самый честный
         источник «времени попадания в план», который вообще есть в модели
         данных), tie-break — id. Каждая плановая позиция резолвится к
         закупке, которая на неё ссылается (PurchaseItem.feo_planned_item_id)
         — берётся САМАЯ РАННЯЯ (min Purchase.id), т.к. обычно именно она
         породила эту плановую позицию автозаведением
         (_auto_assign_planned_items, wishes.py); если ни одна закупка ещё не
         привязана — виновник этой строки безымянный (purchase_id=None,
         названа сама плановая позиция).
      1а) для узлов, ЗАМЕЩЁННЫХ заказом «целиком» (_order_substituted_plan
         вернула `ordered`, а не `plan_manual`) — сами позиции закупок,
         реально составляющие `ordered` (ORDERED_STATUSES, over_plan=false, БЕЗ
         валидной привязки к FeoPlannedItem — та же выборка, что и
         ordered_consumption_by_category), по возрастанию Purchase.id/id
         позиции. Плановые FeoPlannedItem такого узла в контрибьюторы НЕ идут
         — они больше не формируют его вклад в план (см. docstring выше).
      2) позиции закупок (PurchaseItem) с over_plan=true в PLANNED_STATUSES,
         по возрастанию Purchase.id (у Purchase НЕТ created_at — id это PK
         IDENTITY/serial, монотонно растёт при INSERT, надёжный прокси
         времени), tie-break — id позиции.
    Для узлов в режиме 'manual_sum' с ЕЩЁ НЕ согласованным превышением —
    план ОДНО число (manual_plan_amount), разбить его на закупки нельзя: в
    качестве «контрибьютора» подставляется синтетическая запись «плановое
    значение категории» без purchase_id — так превышение всё равно объясняется
    числом, даже если конкретной закупки-виновника формально не существует.

    Если превышение набралось несколькими контрибьюторами — виновником назван
    именно тот, кто ПЕРВЫМ пересёк границу budget (НЕ последний/крупнейший, и
    НЕ причина всего превышения целиком — см. "amount_before"/"amount_at_crossing"/
    "cumulative_after" ниже про то, как их читать честно; итоговое превышение
    называется отдельным полем "total_excess", тем же числом, что и
    compute_feo_plan_tree.excess_amount узла).

    Возвращает None, если budget не задан или контрибьюторов не нашлось (не
    должно случаться при excess_amount>0, но не падаем — просто нет данных для
    подсветки виновника). Поля возврата:
      purchase_id/purchase_number/item_name — позиция/закупка, ПОСЛЕ которой
        нарастающая сумма впервые вышла за budget (см. предупреждение выше —
        это НЕ обязательно причина всего превышения).
      amount_before — сколько было накоплено ДО неё.
      amount_at_crossing — её собственный вклад.
      cumulative_after — сколько стало ПОСЛЕ неё (обычно лишь немного больше
        budget — это НЕ итоговая плановая сумма узла).
      total_plan_amount — ИТОГОВАЯ плановая сумма узла (plan+over,
        compute_feo_plan_tree.full_display) — Σ ВСЕХ контрибьюторов, включая
        добавленные уже ПОСЛЕ пересечения границы.
      total_excess — total_plan_amount − budget, ТА ЖЕ величина, что
        compute_feo_plan_tree.excess_amount узла (плашка «требуется
        согласование») — задача владельца п.13: эти два числа ОБЯЗАНЫ
        совпадать, что и проверяет test_feo_excess_culprit_matches_control.py.
    """
    if budget is None:
        return None
    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        return None

    all_cats = (await db.execute(
        select(
            FeoCategory.id, FeoCategory.parent_id, FeoCategory.planned_quantity,
            FeoCategory.plan_source, FeoCategory.manual_plan_amount,
        ).where(FeoCategory.subsidy_id == cat.subsidy_id)
    )).all()
    by_id = {r.id: r for r in all_cats}
    children_map: dict[int, list[int]] = {}
    for r in all_cats:
        if r.parent_id is not None:
            children_map.setdefault(r.parent_id, []).append(r.id)

    # ВСЕ узлы поддерева feo_category_id, ВКЛЮЧАЯ его самого — не только
    # листья: направление/группа тоже может иметь СОБСТВЕННЫЕ активные
    # плановые позиции (ФОРМУЛА v3 compute_feo_plan_tree, «направление со
    # временем может наполниться») — их вклад в план иначе теряется молча (см.
    # docstring выше, пункт «ПРИЧИНА»).
    node_ids: list[int] = []
    stack = [feo_category_id]
    while stack:
        cur = stack.pop()
        if cur not in by_id or cur in node_ids:
            continue
        node_ids.append(cur)
        stack.extend(children_map.get(cur, []))
    if not node_ids:
        return None

    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.plan_excess_approval import PlanExcessApproval
    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle
    from app.services.feo_plan_fact import (  # local: avoid import cycle, ПРАВИЛО №6 — переиспользуем формулу факта
        ORDERED_STATUSES, _contract_item_totals, _purchase_item_totals,
        ordered_consumption_by_category, purchase_item_fact_amount,
    )

    contributors: list[dict] = []

    # Σ amount/Σ quantity активных FeoPlannedItem по КАЖДОМУ узлу поддерева
    # (не только листу) — items_total/qty-фолбэк для _leaf_plan_manual и для
    # решения о замещении «заказ вместо плана», тот же расчёт, что
    # leaf_item_amt/leaf_item_qty в compute_feo_plan_tree (то же is_active=True).
    items_total_by_node: dict[int, float] = {}
    items_qty_by_node: dict[int, float] = {}
    items_q = (
        select(
            FeoPlannedItem.feo_category_id,
            func.coalesce(func.sum(FeoPlannedItem.amount), 0).label("amt"),
            func.coalesce(func.sum(FeoPlannedItem.quantity), 0).label("qty"),
        )
        .where(FeoPlannedItem.feo_category_id.in_(node_ids))
        .where(FeoPlannedItem.is_active.is_(True))
        .group_by(FeoPlannedItem.feo_category_id)
    )
    for r in (await db.execute(items_q)).all():
        items_total_by_node[r.feo_category_id] = float(r.amt)
        items_qty_by_node[r.feo_category_id] = float(r.qty)

    # ПОСЛЕДНИЙ (по created_at) PlanExcessApproval КАЖДОГО узла — approval
    # привязан к КОНКРЕТНОЙ категории (feo_category_id), не к переданному сюда
    # feo_category_id узла с бюджетом (тот может быть предком-группой) — та же
    # семантика, что latest_approval_by_cat в compute_feo_plan_tree.
    node_approved: dict[int, bool] = {}
    appr_rows = (await db.execute(
        select(PlanExcessApproval.feo_category_id, PlanExcessApproval.status)
        .where(PlanExcessApproval.feo_category_id.in_(node_ids))
        .order_by(PlanExcessApproval.feo_category_id, PlanExcessApproval.created_at.desc())
    )).all()
    seen_appr: set = set()
    for ar in appr_rows:
        if ar.feo_category_id in seen_appr:
            continue
        seen_appr.add(ar.feo_category_id)
        node_approved[ar.feo_category_id] = (ar.status == "approved")

    # Собственные (БЕЗ рекурсии по детям) ordered/ordered_quantity каждого узла —
    # та же величина, что own_ordered/own_ordered_qty в compute_feo_plan_tree._visit,
    # нужна для _order_substituted_plan НЕЗАВИСИМО на каждом узле, как и там.
    ordered_by_node = await ordered_consumption_by_category(
        db, [cat.subsidy_id], exclude_planned_item_linked=True
    )

    # Узел попадает в itemized_node_ids, когда его план_manual == items_total
    # (режим 'planned_items' — всегда; режим 'manual_sum' — только когда
    # согласованное превышение уже «влило» план в Σ позиций) — тогда его можно
    # разложить на реальные FeoPlannedItem-строки. substituted_node_ids — узел
    # заказан ПОЛНОСТЬЮ (см. _order_substituted_plan) — его вклад уже НЕ
    # Σ позиций, а факт заказа; раскладывается на реальные PurchaseItem ниже.
    # Иначе (manual_sum, план == ОДНО число manual_plan_amount, НЕ замещённый
    # заказом) — единственный синтетический контрибьютор.
    itemized_node_ids: list[int] = []
    substituted_node_ids: list[int] = []
    for nid in node_ids:
        r = by_id[nid]
        items_total = items_total_by_node.get(nid, 0.0)
        _, plan_manual, _ = _leaf_plan_manual(
            r.plan_source, r.manual_plan_amount, items_total, node_approved.get(nid, False),
        )
        # ⚠️ Асимметрия листа/группы (compute_feo_plan_tree._visit, см. её
        # docstring — «planned_quantity ПОЛЯ группы по-прежнему НЕ учитывается»):
        # лист читает СВОЁ raw planned_quantity, с фолбэком на Σ количества
        # активных FeoPlannedItem только если оно 0; группа (узел с детьми)
        # planned_quantity ВООБЩЕ не читает — всегда Σ количества своих
        # FeoPlannedItem (own_qty = leaf_item_qty.get(cat_id) в дереве). Если
        # это здесь не воспроизвести — для группы с заполненным (но нерелевантным)
        # planned_quantity контроль замещения «заказ вместо плана» решит иначе,
        # чем дерево, и Σ контрибьюторов разойдётся с full_display.
        if nid in children_map:
            qty = items_qty_by_node.get(nid, 0.0)
        else:
            qty = float(r.planned_quantity) if r.planned_quantity is not None else 0.0
            if qty == 0.0:
                qty = items_qty_by_node.get(nid, 0.0)
        own_ord = ordered_by_node.get(nid) or {}
        ordered = own_ord.get("ordered", 0.0)
        ordered_qty = own_ord.get("ordered_quantity", 0.0)
        # Единая точка (feo_plan_common.py, ПРАВИЛО №6) — та же функция, что
        # использует compute_feo_plan_tree._own_plan_and_forecast. `substituted`
        # — узнаём, КАКУЮ ветку она выбрала (по определению contribution ==
        # ordered ⟺ узел заказан целиком), чтобы решить, КАКИМ способом
        # раскладывать вклад узла на контрибьюторов — построчно по
        # FeoPlannedItem (Источник №1) или построчно по реальным закупленным
        # позициям (Источник №1а).
        contribution = _order_substituted_plan(qty, ordered, ordered_qty, plan_manual)
        substituted = qty > 0 and ordered_qty >= qty

        if substituted:
            # Замещено заказом целиком — контрибьюторы этого узла ниже (Источник
            # №1а), а не его FeoPlannedItem (см. docstring выше).
            if ordered > 0:
                substituted_node_ids.append(nid)
            continue
        if abs(contribution - items_total) <= 0.005:
            itemized_node_ids.append(nid)
        elif contribution > 0:
            cat_row = await db.get(FeoCategory, nid)
            contributors.append({
                "amount": Decimal(str(contribution)), "purchase_id": None, "purchase_number": None,
                "item_name": f"плановое значение категории «{cat_row.name if cat_row else nid}»",
                "created_at": None, "sort_key": (0, nid),
            })

    if itemized_node_ids:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem.id, FeoPlannedItem.name, FeoPlannedItem.amount, FeoPlannedItem.created_at)
            .where(FeoPlannedItem.feo_category_id.in_(itemized_node_ids))
            .where(FeoPlannedItem.is_active.is_(True))
            .order_by(FeoPlannedItem.created_at.asc(), FeoPlannedItem.id.asc())
        )).all()
        fpi_ids = [r.id for r in fpi_rows]
        linked_purchase_by_fpi: dict[int, tuple] = {}
        if fpi_ids:
            link_rows = (await db.execute(
                select(PurchaseItem.feo_planned_item_id, Purchase.id, Purchase.purchase_number)
                .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
                .where(PurchaseItem.feo_planned_item_id.in_(fpi_ids))
                .order_by(PurchaseItem.feo_planned_item_id, Purchase.id.asc())
            )).all()
            for _fpi_id, _pur_id, _pur_num in link_rows:
                if _fpi_id not in linked_purchase_by_fpi:
                    linked_purchase_by_fpi[_fpi_id] = (_pur_id, _pur_num)
        for i, r in enumerate(fpi_rows):
            pur_id, pur_num = linked_purchase_by_fpi.get(r.id, (None, None))
            amt = Decimal(str(r.amount or 0))
            if amt <= 0:
                continue
            contributors.append({
                "amount": amt, "purchase_id": pur_id, "purchase_number": pur_num,
                "item_name": r.name, "created_at": r.created_at, "sort_key": (1, i),
            })

    # ── Источник №1а: узлы, ЗАМЕЩЁННЫЕ заказом целиком — сами позиции закупок,
    # составляющие `ordered` (та же выборка/формула факта, что и
    # ordered_consumption_by_category, но по РЯДАМ, не агрегатом — нужна
    # разбивка по конкретным позициям для виновника) ───────────────────────
    if substituted_node_ids:
        cat_col_ord = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
        _fpi_ord = aliased(FeoPlannedItem)
        ord_rows = (await db.execute(
            select(PurchaseItem, Purchase)
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .outerjoin(_fpi_ord, _fpi_ord.id == PurchaseItem.feo_planned_item_id)
            .where(cat_col_ord.in_(substituted_node_ids))
            .where(Purchase.status.in_(list(ORDERED_STATUSES)))
            .where(Purchase.stopped_at.is_(None))
            .where(PurchaseItem.over_plan.is_(False))
            .where(Purchase.subsidy_id == cat.subsidy_id)
            .where(sqlor(
                PurchaseItem.feo_planned_item_id.is_(None),
                _fpi_ord.id.is_(None),
                _fpi_ord.is_active.is_(False),
                _fpi_ord.feo_category_id != cat_col_ord,
            ))
            .order_by(Purchase.id.asc(), PurchaseItem.id.asc())
        )).all()
        if ord_rows:
            purchase_ids_ord = {r.Purchase.id for r in ord_rows}
            purchase_totals_ord = await _purchase_item_totals(db, purchase_ids_ord)
            contract_totals_ord = await _contract_item_totals(db, (r.PurchaseItem.id for r in ord_rows))
            for k, r in enumerate(ord_rows):
                pi, p = r.PurchaseItem, r.Purchase
                items_count, items_sum = purchase_totals_ord.get(p.id, (1, Decimal(str(pi.total_price or 0))))
                item_total = Decimal(str(pi.total_price or 0))
                if items_count > 1 and items_sum > 0:
                    ratio = item_total / items_sum
                elif items_count > 1:
                    ratio = Decimal(1) / Decimal(items_count)
                else:
                    ratio = Decimal(1)
                fact_amount, _allocated = purchase_item_fact_amount(
                    pi, p, ratio, items_count, contract_item_total=contract_totals_ord.get(pi.id)
                )
                if fact_amount is None or fact_amount <= 0:
                    continue
                contributors.append({
                    "amount": fact_amount, "purchase_id": p.id, "purchase_number": p.purchase_number,
                    "item_name": pi.item_name, "created_at": None, "sort_key": (1.5, k),
                })

    # ── Источник №2: «сверх плана» — PurchaseItem.over_plan=true, прибавляется
    # безусловно ПОВЕРХ плана (см. compute_feo_plan_tree.over), по ВСЕМ узлам
    # поддерева (не только листьям — группа тоже может иметь такие позиции
    # напрямую). Purchase.stopped_at.is_(None) — та же остановка, что и
    # plan_consumption_by_category.over (раньше здесь не фильтровалась,
    # расхождение с деревом на остановленных закупках) ─────────────────────
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    amount_expr = func.coalesce(PurchaseItem.planned_total, PurchaseItem.total_price)
    over_rows = (await db.execute(
        select(
            PurchaseItem.id.label("item_id"), PurchaseItem.item_name.label("item_name"),
            amount_expr.label("amount"), Purchase.id.label("purchase_id"),
            Purchase.purchase_number.label("purchase_number"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(cat_col.in_(node_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(Purchase.subsidy_id == cat.subsidy_id)
        .where(PurchaseItem.over_plan.is_(True))
        .order_by(Purchase.id.asc(), PurchaseItem.id.asc())
    )).all()
    for j, r in enumerate(over_rows):
        amt = Decimal(str(r.amount or 0))
        if amt <= 0:
            continue
        contributors.append({
            "amount": amt, "purchase_id": r.purchase_id, "purchase_number": r.purchase_number,
            "item_name": r.item_name, "created_at": None, "sort_key": (2, j),
        })

    if not contributors:
        return None

    budget_d = Decimal(str(budget))
    total_plan_amount = sum((c["amount"] for c in contributors), Decimal("0"))
    total_excess = total_plan_amount - budget_d
    cumulative = Decimal("0")
    for c in contributors:
        before = cumulative
        cumulative += c["amount"]
        if cumulative - budget_d > Decimal("0.005"):
            return {
                "purchase_id": c["purchase_id"],
                "purchase_number": c["purchase_number"],
                "item_name": c["item_name"],
                "amount_before": float(before),
                "amount_at_crossing": float(c["amount"]),
                "cumulative_after": float(cumulative),
                # Задача владельца п.13: та же итоговая сумма/превышение, что
                # compute_feo_plan_tree.full_display/excess_amount узла — см.
                # docstring выше и test_feo_excess_culprit_matches_control.py.
                "total_plan_amount": float(total_plan_amount),
                "total_excess": float(total_excess),
            }
    return None


async def assert_no_unapproved_excess(
    db: AsyncSession, feo_category_id: int, adding_amount: Decimal = Decimal("0")
) -> list[dict]:
    """Бросает HTTPException 409 ТОЛЬКО в ДВУХ случаях теперь (см. правку
    владельца 2026-09-03 ниже) — ЛИБО жёсткий потолок субсидии в целом
    (PLAN_OVER_SUBSIDY_CEILING, см. ниже), ЛИБО факт дороже плана узла
    (excess_fact_over_plan > 0 и НЕ excess_fact_approved — задача владельца
    «план ≠ факт», шаг C, сессия 2026-08-06), ЛИБО Σ плановых позиций дороже
    вручную заданного плана узла (excess_plan_over_manual, задача владельца
    п.2, 2026-08-12). См. compute_feo_plan_tree и app.models.plan_excess_approval.

    ═══ Владелец продукта (2026-09-03), дословно: «я просил не с отдельной
    категорией жёсткий предел делать, который требовал перераспределения, а со
    всем ФЭО суммарно». Уточнение на вопрос «что делать с переизбытком в одной
    ветке, если суммарно по ФЭО есть место» — «Суммарно, но с предупреждением:
    перебор в ветке не блокирует, но виден как пометка». ═══

    ПОСЛЕДСТВИЕ (осознанное, зафиксировано в коде): план в ОТДЕЛЬНОЙ ветке/
    категории теперь МОЖЕТ превышать её собственное финансирование по ФЭО
    (excess_over_feo/excess_amount) без остановки работы — эта ветка больше НЕ
    проверяется здесь как блокирующая, дальше по коду (цикл по цепочке
    предков) для неё СОБИРАЕТСЯ ПРЕДУПРЕЖДЕНИЕ (возвращается вызывающему списком,
    см. return ниже), а не бросается 409. Единственный обязательный, непроходимый
    контроль — суммарный потолок субсидии целиком (PLAN_OVER_SUBSIDY_CEILING).
    Ветка становится ОРИЕНТИРОМ, не жёстким лимитом.

    Видимость перекоса ветки (владелец: «виден как пометка», НЕ должен исчезать
    молча) обеспечена ДВУМЯ независимыми, уже существующими каналами, ни один
    из которых не требует правки этой функции:
      1. Возврат СПИСКОМ warnings из этой функции — вызывающий код (purchases.py/
         purchase_transitions.py) присоединяет его к ответу как поле
         `excess_warnings` (тот же формат/паттерн, что уже применён в
         app.routers.wishes._collect_excess_warnings — «второй механизм не
         изобретать», задача владельца).
      2. Persistent-бейдж `feo_excess`/`feo_excess_hint`/`feo_excess_state` на
         КАЖДОЙ закупке (app.routers.purchases._compute_purchase_feo_excess) —
         считается заново на КАЖДОМ GET (список/карточка) НАПРЯМУЮ из
         compute_feo_plan_tree (excess_over_feo/excess_amount), полностью
         НЕЗАВИСИМО от того, блокирует эта функция или нет — раз
         compute_feo_plan_tree не менялся, канал продолжает работать
         автоматически и после этой правки.

    Раньше (ДО 2026-08-05 не было вообще, ДО 2026-09-03 БЛОКИРОВАЛО): «Если
    где-то превысил план ФЭО, значит где-то надо снимать — должны быть
    заблокированы действия, пока план закупок не загонять обратно в размеры
    ФЭО» — это правило породило жалобу владельца выше (перебор 50 тыс. в одной
    ветке блокировал действие, даже если в соседней ветке свободно 300 тыс. —
    единственный выход был вручную «перераспределять» между категориями,
    точно то, от чего владелец отказался 2026-09-03).

    Контроль факт-над-планом (excess_fact_over_plan) НЕ ЗАТРОНУТ этой правкой
    и остаётся блокирующим как раньше — это про другое (договор дороже плана
    закупки), не про перекос между ветками. Контроль
    excess_plan_over_manual (Σ автозаведённых плановых позиций дороже вручную
    заданного числа той же категории) ТОЖЕ НЕ ЗАТРОНУТ — это конфликт внутри
    ОДНОЙ категории между двумя её собственными числами, чинится своими же
    данными (поднять вручную заданный план или убрать лишние позиции), а не
    перераспределением между ветками ФЭО — другая природа, вне жалобы
    владельца от 2026-09-03.

    Вызывается ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ план (создание закупки,
    увеличение суммы/смена категории ФЭО при PUT, согласование заявки →
    создание закупок) и ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ факт сверх плана
    (переход статуса закупки work_in_progress → contracted, сохранение/
    изменение договорных позиций) — см. вызывающий код в app.routers.purchases /
    app.routers.wishes / app.routers.contract_items.

    НЕ вызывается для переходов статусов вперёд у уже существующих закупок
    (ordered → delivered → paid), уменьшений сумм, удаления позиций, отката
    заявок — это путь ВОЗВРАТА в рамки плана, его блокировать нельзя.

    adding_amount — необязательная сумма добавляемого действия. Для ОБОИХ
    ОСТАВШИХСЯ блокирующих узловых видов превышения (факт>план узла, позиции>
    ручной план узла) используется ТОЛЬКО для текста отказа (сколько ещё
    пытаются добавить сверху уже несогласованного превышения); на решение
    блокировать/не блокировать не влияет — блокирует сам факт СУЩЕСТВУЮЩЕГО
    несогласованного превышения на узле или предке. ИСКЛЮЧЕНИЕ — жёсткий
    потолок субсидии (см. ниже, задача владельца п.3): там adding_amount
    ДЕЙСТВИТЕЛЬНО участвует в решении блокировать, т.к. это правило не про
    «уже случившееся», а про «это конкретное действие не должно случиться».

    Задача владельца п.3 (2026-08-12, «жёсткий потолок»): «общий план по всем
    подкатегориям не должен превышать общую сумму ФЭО — критично, ни при каких
    обстоятельствах». Проверяется ПЕРВЫМ, до узловых проверок ниже, и НЕ
    участвует в согласовании через PlanExcessApproval вообще — ни admin_override,
    ни обход для OWNER_ROLES: если план (с учётом adding_amount) выходит за
    потолок финансирования по ФЭО субсидии (calculate_budget_from_categories,
    тот же источник, что и feo_budget_total у субсидии, см. app.routers.
    subsidies) — действие безусловно отклоняется. ЭТО и есть суммарный контроль,
    которого хотел владелец 2026-09-03 — остаётся непроходимым, эта правка его
    не трогает.

    Возвращает список предупреждений о перекосе ОТДЕЛЬНОЙ ветки/категории
    (план узла > её финансирования по ФЭО, несогласовано) — по одному словарю
    на КАЖДЫЙ узел цепочки предков с таким перекосом (может быть пусто, может
    быть несколько на разных уровнях цепочки сразу). Формат словаря — см.
    внутри цикла ниже (то же содержимое, что раньше уходило в detail 409
    PLAN_EXCESS_OVER_FEO).
    """
    from fastapi import HTTPException

    warnings: list[dict] = []

    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        return warnings

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    if not tree or feo_category_id not in tree:
        return warnings

    # ── Жёсткий потолок субсидии (задача владельца п.3) — см. docstring выше. ──
    from app.routers.subsidies import calculate_budget_from_categories  # local: avoid router import cycle
    ceiling = await calculate_budget_from_categories(db, cat.subsidy_id)
    if ceiling and ceiling > 0:
        total_plan_now = sum(n["display"] for n in tree.values() if n["parent_id"] is None)
        total_plan_after_d = Decimal(str(total_plan_now)) + Decimal(str(adding_amount))
        ceiling_d = Decimal(str(ceiling))
        if total_plan_after_d - ceiling_d > Decimal("0.005"):
            from app.models.subsidy import Subsidy
            subsidy_row = await db.get(Subsidy, cat.subsidy_id)
            subsidy_name = subsidy_row.name if subsidy_row else f"#{cat.subsidy_id}"
            over_d = total_plan_after_d - ceiling_d
            raise HTTPException(
                409,
                {
                    "code": "PLAN_OVER_SUBSIDY_CEILING",
                    "message": (
                        f"Жёсткий потолок ФЭО по субсидии «{subsidy_name}»: всего запланировано "
                        f"{total_plan_after_d:,.2f} ₽, финансирование по ФЭО (потолок) "
                        f"{ceiling_d:,.2f} ₽, превышение {over_d:,.2f} ₽. Это ограничение НЕ "
                        f"согласуется ни при каких обстоятельствах — уменьшите план по какой-либо "
                        f"подкатегории минимум на {over_d:,.2f} ₽."
                    ),
                    "subsidy_id": cat.subsidy_id,
                    "total_plan": float(total_plan_after_d),
                    "ceiling": float(ceiling_d),
                    "over_amount": float(over_d),
                },
            )

    # Цепочка «узел → предки» через parent_id (снизу вверх)
    chain_ids: list[int] = []
    cur_id: Optional[int] = feo_category_id
    seen: set[int] = set()
    while cur_id is not None and cur_id not in seen and cur_id in tree:
        seen.add(cur_id)
        chain_ids.append(cur_id)
        cur_id = tree[cur_id]["parent_id"]

    for cid in chain_ids:
        node = tree[cid]
        extra = (
            f" Запрашиваемое действие добавляет ещё {Decimal(str(adding_amount)):,.2f} ₽ поверх этого."
            if adding_amount else ""
        )

        excess = node.get("excess_amount") or 0.0
        if excess > 0.005 and not node.get("excess_approved"):
            cat_row = await db.get(FeoCategory, cid)
            name = cat_row.name if cat_row else f"#{cid}"
            budget_d = Decimal(str(node.get("budget") or 0.0))
            full_plan_d = Decimal(str(node["plan"] + node["over"]))  # текущая плановая сумма (до сжатия по бюджету)
            excess_d = Decimal(str(excess))
            # Владелец, план zany-fluttering-mountain.md п.4 (2026-08-10): «должна
            # отображаться данная закупка и показать, что из-за неё всё превысило» —
            # находим виновника (см. find_excess_culprit) и называем его в
            # предупреждении, а не только абстрактную сумму превышения. Правка
            # владельца 2026-09-03: раньше здесь был raise HTTPException(409,
            # {"code": "PLAN_EXCESS_OVER_FEO", ...}) — «перебор в одной ветке
            # блокирует, даже если суммарно по ФЭО есть место». Теперь — ТОЛЬКО
            # предупреждение (см. docstring функции выше), 409 не бросается,
            # цикл продолжается (проверяет остальных предков/остальные виды
            # превышения того же узла ниже).
            culprit = await find_excess_culprit(db, cid, node.get("budget"))
            culprit_txt = ""
            culprit_fields: dict = {
                "culprit_purchase_id": None,
                "culprit_purchase_number": None,
                "culprit_item_name": None,
                "culprit_amount_before": None,
            }
            if culprit:
                if culprit["purchase_id"] is not None:
                    cnum = culprit["purchase_number"] or culprit["purchase_id"]
                    who = f"закупка №{cnum} (id {culprit['purchase_id']})"
                else:
                    # Плановое значение самой категории (planned_quantity×planned_amount) —
                    # у него нет конкретной закупки-источника, см. find_excess_culprit.
                    who = "плановая позиция без привязанной закупки"
                # Владелец, Волна 1 п.13 (2026-09-13): текст ДО правки называл эту
                # позицию «виновником», будто из-за неё случилось ВСЁ превышение —
                # на деле она лишь ПЕРВАЯ, после которой нарастающая сумма
                # пересекла границу ФЭО (может быть далеко не единственная и не
                # самая крупная — см. find_excess_culprit.docstring). Формулировка
                # ниже честно разделяет «первая позиция за чертой» и «итоговое
                # превышение» — оба числа берутся из ОДНОГО расчёта
                # (culprit['total_excess'] всегда равно excess_d выше, тест
                # test_feo_excess_culprit_matches_control.py).
                culprit_txt = (
                    f" Первая позиция, после которой сумма вышла за финансирование по ФЭО "
                    f"(а не единственная причина всего превышения) — {who}: до неё по этой "
                    f"категории было выбрано {culprit['amount_before']:,.2f} ₽, она добавила "
                    f"«{culprit['item_name']}» на {culprit['amount_at_crossing']:,.2f} ₽, после неё "
                    f"стало {culprit['cumulative_after']:,.2f} ₽ при финансировании по ФЭО "
                    f"{budget_d:,.2f} ₽. Итоговое превышение по категории (с учётом всех позиций, "
                    f"добавленных как до, так и после неё) — {excess_d:,.2f} ₽."
                )
                culprit_fields.update({
                    "culprit_purchase_id": culprit["purchase_id"],
                    "culprit_purchase_number": culprit["purchase_number"],
                    "culprit_item_name": culprit["item_name"],
                    "culprit_amount_before": culprit["amount_before"],
                })
            warnings.append({
                "code": "PLAN_EXCESS_OVER_FEO",
                "message": (
                    f"Категория ФЭО «{name}»: финансирование по ФЭО {budget_d:,.2f} ₽, "
                    f"текущая плановая сумма {full_plan_d:,.2f} ₽, превышение "
                    f"{excess_d:,.2f} ₽.{culprit_txt}{extra} Действие НЕ заблокировано (суммарно "
                    f"по ФЭО контролируется общий потолок) — при желании можно перенести позиции "
                    f"в другую категорию или согласовать превышение (запрос согласования превышения "
                    f"плана ФЭО по категории «{name}»)."
                ),
                "feo_category_id": cid,
                "feo_category_name": name,
                "excess_amount": float(excess_d),
                "budget": float(budget_d),
                "plan_amount": float(full_plan_d),
                **culprit_fields,
            })

        excess_fact = node.get("excess_fact_over_plan") or 0.0
        if excess_fact > 0.005 and not node.get("excess_fact_approved"):
            cat_row = await db.get(FeoCategory, cid)
            name = cat_row.name if cat_row else f"#{cid}"
            plan_d = Decimal(str(node.get("plan") or 0.0))
            fact_d = Decimal(str(node.get("fact") or 0.0))
            excess_fact_d = Decimal(str(excess_fact))
            raise HTTPException(
                409,
                f"Итог закупки по категории ФЭО «{name}» превышает план: план "
                f"{plan_d:,.2f} ₽, факт (по договору/КП) {fact_d:,.2f} ₽, превышение "
                f"{excess_fact_d:,.2f} ₽.{extra} Переход в «Договор» и увеличение договорных "
                f"позиций заблокированы, пока превышение не согласовано (запрос согласования "
                f"превышения плана по категории «{name}») или сумма договора не снижена до плана."
            )

        # Задача владельца п.2 (2026-08-12): ТРЕТИЙ вид — Σ плановых позиций больше
        # «ручного» плана (manual_plan_entered) — «планируются одни траты, а тут уже
        # превысили, значит не хватит на всё, надо думать, что уменьшать». Наравне с
        # двумя видами выше: блокирует уже СУЩЕСТВУЮЩЕЕ несогласованное превышение
        # (adding_amount — только в тексте, как и у них).
        excess_plan = node.get("excess_plan_over_manual") or 0.0
        if excess_plan > 0.005 and not node.get("excess_plan_approved"):
            cat_row = await db.get(FeoCategory, cid)
            name = cat_row.name if cat_row else f"#{cid}"
            manual_d = Decimal(str(node.get("manual_plan_entered") or 0.0))
            full_d = Decimal(str(node.get("plan_manual") or 0.0))
            excess_plan_d = Decimal(str(excess_plan))
            items = node.get("excess_plan_items") or []
            items_txt = ""
            if items:
                shown = "; ".join(
                    f"«{it['name']}» ({Decimal(str(it['amount'])):,.2f} ₽)" for it in items[:10]
                )
                more = f" и ещё {len(items) - 10} поз." if len(items) > 10 else ""
                items_txt = f" Из-за автоматически заведённых позиций: {shown}{more}."
            raise HTTPException(
                409,
                {
                    "code": "PLAN_ITEMS_OVER_MANUAL_PLAN",
                    "message": (
                        f"Сумма плановых позиций по категории ФЭО «{name}» превышает вручную "
                        f"заведённый план: ручной план {manual_d:,.2f} ₽, сумма всех плановых "
                        f"позиций {full_d:,.2f} ₽, превышение {excess_plan_d:,.2f} ₽.{items_txt}"
                        f"{extra} Уменьшите/уберите лишние автоматически заведённые позиции, либо "
                        f"увеличьте ручной план, либо согласуйте превышение (запрос согласования "
                        f"превышения плана по категории «{name}»)."
                    ),
                    "feo_category_id": cid,
                    "excess_amount": float(excess_plan_d),
                    "manual_plan": float(manual_d),
                    "plan_amount": float(full_d),
                    "items": items,
                },
            )

    return warnings



