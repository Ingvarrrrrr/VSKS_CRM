"""feo_plan_tree.py — дерево «плановой суммы» по дереву ФЭО (compute_feo_plan_tree).

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). Единый источник для _calculate_feo_planned_tree_bulk
(subsidies.py), _create_plan_graph_version (purchases.py), GET /api/feo-categories/
plan-positions и planned-purchase-totals — см. docstring compute_feo_plan_tree
ниже за полной формулой (ПРАВИЛО №6 — не заводить вторую формулу дерева плана).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_fact import (
    fact_consumption_by_category,
    ordered_consumption_by_category,
    plan_consumption_by_category,
    planned_item_consumption,
)
from app.services.purchase_summary import purchase_summaries_by_id


async def compute_feo_plan_tree(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, dict]:
    """Рекурсивная формула «плановой суммы» дерева ФЭО — единый источник для
    _calculate_feo_planned_tree_bulk (subsidies.py, KPI «Запланировано»/«Свободно»
    на дашборде, в списке субсидий и в панели субсидии), _create_plan_graph_version
    (purchases.py, снапшот версии плана закупок), GET /api/feo-categories/plan-positions
    и GET /api/feo-categories/planned-purchase-totals.

    ФОРМУЛА v2 (сессия 2026-08-05, задача владельца «заказ замещает план, пока не
    набрано количество — план не трогаем»). Раньше было display = MAX(plan_manual,
    consumed) + over — эконом на частичном заказе не высвобождался, пока не заказано
    ВСЁ количество целиком. Теперь — явная замена, а не MAX.

    ФОРМУЛА v3 (сессия 2026-08-12, задача владельца «направление со временем может
    наполниться, соответственно должно считаться и оно»). Повод: у категории 3677
    «Окружные» (НЕ лист — направление с 5 подкатегориями) автозаведение создало
    плановую позицию «Бинт марлевый» на 48 441,80 ₽ прямо на самом направлении
    (а не на одной из подкатегорий). compute_feo_plan_tree считал plan_manual/plan
    группы ТОЛЬКО как сумму детей — собственные плановые позиции узла с детьми
    нигде не попадали в дерево, 48 441,80 ₽ «терялись». Решение: узел с детьми
    теперь суммирует ещё и СВОИ активные FeoPlannedItem (той же формулой
    _own_plan_and_forecast, что и лист) — см. plan_manual/plan/qty_plan группы
    ниже. Собственные ПОЛЯ группы (planned_quantity × planned_amount, старый
    формат) как НЕ учитывались, так и не учитываются — см. предупреждение там же.

    Для каждой категории cat_id (и листа, и группы — не только листьев) считается:
      plan_manual — «сколько сами запланировали». Способ расчёта задаётся
        ЯВНЫМ переключателем FeoCategory.plan_source, а НЕ угадывается по тому,
        пустые ли числовые поля (задача владельца, план
        zany-fluttering-mountain.md, сессия 2026-08-13, см. _manual_plan_for
        ниже и ФОРМУЛА «п.2» в блоке «ТРИ НЕЗАВИСИМЫХ вида превышения» ниже):
          лист:  'planned_items' (умолчание) — plan_manual = Σ активных
                 FeoPlannedItem.amount узла (leaf_item_amt — план введён
                 плановыми позициями внутри категории, панель «Добавить
                 плановую»); 'manual_sum' — plan_manual = FeoCategory.
                 manual_plan_amount (ОДНО число, введённое вручную), ПОКА
                 накопленное превышение над ним не согласовано (после
                 согласования — тоже становится Σ позиций, см.
                 excess_plan_over_manual ниже). ⚠️ Поля FeoCategory.
                 planned_quantity/planned_amount (старый формат «кол-во × цена
                 за единицу листа») В РАСЧЁТЕ plan_manual БОЛЬШЕ НЕ УЧАСТВУЮТ
                 ВООБЩЕ — формула «лист: planned_quantity × planned_amount,
                 fallback на Σ FeoPlannedItem.amount при произведении = 0»
                 (документированная здесь ДО 2026-08-13) была УДАЛЕНА
                 коммитом f8d68bc: старая формула ложно срабатывала на
                 категориях без единого введённого владельцем числа (пример —
                 3710 «Расходные материалы для проведения окружных
                 полуфиналов», поля были NULL). planned_quantity листа
                 по-прежнему читается — но ТОЛЬКО как qty (количество) для
                 замещения «заказ вместо плана» в plan/qty_plan ниже, суммы
                 (amt/planned_amount) эта ветка больше не касается; если qty не
                 задано (0) — Σ quantity тех же активных FeoPlannedItem
                 (симметричный fallback по количеству, иначе qty_plan всё
                 равно уйдёт в 0 и замещение не сработает).
        группа: Σ plan_manual прямых детей ПЛЮС собственная часть узла,
                посчитанная ТЕМ ЖЕ переключателем plan_source/manual_plan_amount
                САМОЙ группы (не старыми полями planned_quantity/planned_amount
                — те по-прежнему НЕ учитываются, так же, как feoPlannedTotalFor
                во фронте, иначе формулы разойдутся; на этом поле уже была
                боевая поломка — категория «Микроавтобус» после пропажи
                подкатегории показала цену 10 130 000 за штуку) — задача
                владельца «направление со временем может наполниться,
                соответственно должно считаться и оно» (сессия 2026-08-12,
                см. ФОРМУЛА v3 ниже).
      ordered / ordered_quantity — Σ фактической суммы/количества позиций в
        статусах «Заказано»/«Поставлено»/«Оплачено» (ORDERED_STATUSES,
        см. ordered_consumption_by_category), БЕЗ over_plan=true и БЕЗ
        привязанных к FeoPlannedItem (Ур.5) — этого узла + рекурсивно всех
        потомков. Это то самое «реально заказанное количество/сумма», которое
        решает, замещать план или нет.
      over — Σ сумм позиций с over_plan=true по ВСЕМ PLANNED_STATUSES (как и
        раньше — расход «сверх плана», прибавляется безусловно поверх, не
        участвует в замещении), этого узла + рекурсивно всех потомков.
      plan — собственно «план замещается заказом»:
        лист:   ordered, ЕСЛИ planned_quantity > 0 И ordered_quantity ≥
                planned_quantity (количество набрано целиком) — план
                становится фактической суммой заказа, экономия/переплата
                высвобождается; ИНАЧЕ (заказано частично или количество не
                задано) — plan_manual (весь план резервируется, даже если
                частично уже заказано дешевле/дороже).
        группа: Σ plan прямых детей + «собственный» plan узла — та же функция
                _own_plan_and_forecast, что и у листа, но с qty/amt взятыми
                из собственных активных FeoPlannedItem узла (leaf_item_qty/
                leaf_item_amt по cat_id самой группы), а НЕ из planned_quantity/
                planned_amount группы (те по-прежнему 0, см. выше). ДО задачи
                «направление со временем может наполниться» (2026-08-12)
                собственная часть группы была всегда 0 — own-позиции группы
                вообще нигде не считались (боевой пример — «Бинт марлевый»
                48 441,80 ₽ на категории 3677 «Окружные», направление с 5
                подкатегориями: план был, а в дереве нигде не отображался).
                Теперь own-позиции узла с детьми участвуют в plan наравне с
                позициями листа, тем же правилом замещения «заказ вместо
                плана» (qty > 0 and ordered_qty >= qty).
      display — «плановая сумма» для UI/KPI = plan + over.
      residual — plan − ordered (может уйти в минус — «перерасход» в UI).
      ordered_qty / ordered_sum — алиасы ordered_quantity/ordered (те же значения,
        под именами, ожидаемыми GET /api/feo-categories/plan-tree, сессия 2026-08-05
        задача «формула только на бэкенде» — фронт больше не пересчитывает план сам,
        читает готовые числа с бэкенда и не должен путать имена полей).
      over_quantity — Σ количества позиций с over_plan=true (аналогично over, но
        в штуках/ед.изм.), этого узла + рекурсивно всех потомков.
      consumed / consumed_quantity — Σ суммы/количества ВСЕХ позиций ВО ВСЕХ
        PLANNED_STATUSES (включая ещё не заказанные — plan_schedule/
        work_in_progress/contracted), БЕЗ over_plan=true и БЕЗ привязанных к
        FeoPlannedItem (см. plan_consumption_by_category.consumed) — этого узла +
        рекурсивно всех потомков. Шире, чем ordered/ordered_quantity (которые
        считают только реально РАЗМЕЩЁННЫЕ закупки, ORDERED_STATUSES) — «сколько
        вообще заявлено», а не «сколько реально заказано».
      qty_plan / display_quantity — то же замещение «заказ вместо плана», что и
        plan/display, но для количества (аналог для GET /api/feo-categories/
        plan-tree и «Планового количества» в SubsidiesView.vue): лист — ordered_qty,
        ЕСЛИ planned_quantity > 0 И ordered_qty ≥ planned_quantity, иначе
        planned_quantity; группа — Σ qty_plan прямых детей ПЛЮС собственный
        qty_plan узла (той же формулой замещения, от Σ quantity собственных
        активных FeoPlannedItem группы — planned_quantity ПОЛЯ группы по-прежнему
        не учитывается, см. plan выше).
        display_quantity = qty_plan + over_quantity.
      forecast / forecast_over — прогнозное предупреждение (не блокирует,
        только для UI): avg_ordered_price = ordered / ordered_quantity (если
        ordered_quantity > 0); forecast = ordered + оставшееся_количество ×
        avg_ordered_price; forecast_over = max(0, forecast − plan_manual).
        Для узлов без заказов или без planned_quantity forecast = plan_manual,
        forecast_over = 0 (прогнозировать не на чем). Для групп forecast_over —
        по-прежнему только накопление (rollup) forecast_over детей, БЕЗ
        собственной части узла (own_forecast/own_forecast_over считаются в коде
        для единообразия с plan, но не используются в forecast группы — задача
        владельца охватывала только plan/plan_manual/qty_plan/display, прогнозное
        предупреждение per-направление не заказывалось, поведение не меняем).

    ТРИ НЕЗАВИСИМЫХ вида превышения плана (задача владельца, сессия 2026-08-12) —
    участвуют в assert_no_unapproved_excess наравне друг с другом, один и тот же
    PlanExcessApproval по категории закрывает все три сразу:
      1) excess_over_feo/excess_amount — план дороже финансирования по ФЭО узла
         (budget), см. выше.
      2) excess_fact_over_plan — факт (итог закупки/КП) дороже плана узла, см. выше.
         СУПРЕССИЯ (задача п.1): если у листа ЕСТЬ хотя бы одна активная плановая
         позиция (FeoPlannedItem) и ВСЕ они auto_created=true (заведены автоматически
         из закупки/заявки, не человеком) — excess_fact_over_plan принудительно 0:
         план по определению следует за такой закупкой, ругаться не на что (боевой
         пример — «Приобретение брендированных футболок участников финала»). Если
         хоть одна позиция заведена руками/импортом — правило работает как раньше.
         Для групп собственной логики нет — просто rollup fact/plan детей, как и
         было.
      3) excess_plan_over_manual (задача п.2, ПЕРЕРАБОТАНО 2026-08-13, план
         zany-fluttering-mountain.md) — Σ активных плановых позиций узла
         (leaf_item_amt) больше вручную заданной суммы. Способ расчёта плана
         больше НЕ угадывается по тому, пустые поля или нет (старая формула
         срабатывала на 3710 «Расходные материалы для проведения окружных
         полуфиналов» без единого введённого владельцем числа — poля были NULL,
         разница тождественно равнялась Σ позиций) — задаётся explicit
         переключателем FeoCategory.plan_source:
           'planned_items' (умолчание) — план узла = Σ его активных плановых
             позиций (leaf_item_amt), manual_plan_entered=0, excess_plan_over_manual
             ВСЕГДА 0 (план не может превысить сам себя).
           'manual_sum' — план узла = FeoCategory.manual_plan_amount (ОДНО число,
             без кол-ва/цены за единицу), manual_plan_entered = это число; если
             Σ активных позиций (items_total) больше — поднимается
             excess_plan_over_manual = items_total − manual_plan_entered. ДО
             согласования план узла (plan_manual/plan) остаётся manual_plan_amount
             (превышение не входит); ПОСЛЕ согласования (excess_plan_approved) —
             план узла становится равен items_total (решение владельца: «когда
             позиции переросли ручную сумму и превышение согласовано, планом
             становится Σ позиций», прежнее значение не теряется — см.
             PlanExcessApproval.plan_before/plan_after).
         excess_plan_items — позиции узла, ДОБАВЛЕННЫЕ ПОСЛЕДНИМИ (created_at
         DESC, id DESC), набираемые от свежих к старым, пока накопленная сумма
         не покроет excess_plan_over_manual (решение владельца «виновники —
         последние добавленные»; БЕЗ фильтра auto_created — теперь неважно, кто
         завёл позицию). Каждый элемент — {id, name, amount, purchases: [...]},
         purchases — закупки, привязанные к этой плановой позиции (см.
         planned_item_consumption.linked_purchase_ids), в формате
         app.services.purchase_summary.purchase_summaries_by_id — клик по
         виновнику открывает его закупку(и), список при их нескольких.
         Для группы: собственная часть считается ТЕМ ЖЕ правилом (по
         FeoCategory.plan_source/manual_plan_amount САМОЙ группы и её
         СОБСТВЕННЫМ прямым плановым позициям, leaf_item_amt по id группы, как
         и own_plan/own_qty, см. ФОРМУЛА v3 ниже) и складывается с rollup'ом
         уже клэмпнутых значений детей — та же схема, что у forecast_over.
         ⚠️ Бэкфилл миграции q5r6s7t8u9v0 переводит в 'manual_sum' ТОЛЬКО
         ЛИСТЬЯ (см. её docstring) — у узлов с детьми старые поля planned_quantity/
         planned_amount исторически игнорировались (боевой пример «Микроавтобус»,
         id 905), включение бэкфилла и для них воскресило бы ту же поломку.
         excess_plan_approved/excess_plan_pending — тот же PlanExcessApproval.

    excess_approval_amount/excess_approval_at/excess_approval_by_id/
    excess_approval_by_name (задача п.4) — данные ПОСЛЕДНЕГО approved-запроса
    PlanExcessApproval по категории (сумма превышения на момент запроса, когда
    resolved_at и кто — финализирующий шаг, последний decided_at среди approved
    шагов цепочки), чтобы фронт мог показать «превышение согласовано» ДАЖЕ когда
    узел всё ещё формально в превышении (excess_approved=true, display включает
    превышение полностью) — «если согласовали, так и остаётся».

    ЧЕТВЁРТЫЙ вид — жёсткий потолок субсидии (Σ display корневых узлов не может
    превышать общее финансирование по ФЭО субсидии) — НЕ в узле дерева (это
    свойство субсидии целиком, не категории), проверяется отдельно в самом начале
    assert_no_unapproved_excess и НЕ согласуется вообще (см. её docstring).

    К каждому узлу также приложены subsidy_id/parent_id, чтобы вызывающий код мог
    просуммировать корневые узлы (parent_id IS NULL) для тотала субсидии без
    повторного запроса к FeoCategory.

    Изоляция субсидий обеспечивается plan_consumption_by_category/
    ordered_consumption_by_category (см. их docstring) — результат не зависит
    от состава батча subsidy_ids.
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result
    from app.models.feo_planned_item import FeoPlannedItem

    cat_q = select(
        FeoCategory.id, FeoCategory.subsidy_id, FeoCategory.parent_id,
        FeoCategory.planned_quantity, FeoCategory.planned_amount, FeoCategory.budget,
        FeoCategory.plan_source, FeoCategory.manual_plan_amount,
    ).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    cat_rows = (await db.execute(cat_q)).all()
    if not cat_rows:
        return result

    by_id = {r.id: r for r in cat_rows}
    children_map: dict[int, list[int]] = {}
    has_children: set[int] = set()
    for r in cat_rows:
        if r.parent_id is not None and r.parent_id in by_id:
            has_children.add(r.parent_id)
            children_map.setdefault(r.parent_id, []).append(r.id)

    leaf_ids = [r.id for r in cat_rows if r.id not in has_children]

    # Σ amount/Σ quantity активных FeoPlannedItem (Ур.5) per категория — задача
    # владельца «направление со временем может наполниться, соответственно
    # должно считаться и оно» (сессия 2026-08-12): ДО этой задачи запрос был
    # ограничен leaf_ids, потому что собственные плановые позиции узла с детьми
    # (направления) нигде не суммировались. Теперь считаем по ВСЕМ категориям
    # (list(by_id.keys())), не только по листьям — группа (см. её ветку в _visit
    # ниже) тоже читает свою запись отсюда и прибавляет её к сумме детей.
    # Для листа — тот же fallback, что и раньше: когда planned_quantity/
    # planned_amount листа не заполнены, а план введён позициями (импорт Excel).
    # Симметричный fallback по количеству (Σ quantity) — т.к. план у владельца
    # переезжает с полей категории на плановые позиции внутри неё (модель «всё
    # планирование — записи внутри категории»): без этого qty листа остаётся 0,
    # «плановое количество» в UI показывает ноль, а правило замещения «заказ
    # вместо плана» (qty > 0 and ordered_qty >= qty) никогда не срабатывает,
    # потому что ему не с чем сравнивать.
    leaf_item_amt: dict[int, float] = {}
    leaf_item_qty: dict[int, float] = {}
    if by_id:
        fpi_q = (
            select(
                FeoPlannedItem.feo_category_id,
                func.coalesce(func.sum(FeoPlannedItem.amount), 0).label("amt"),
                func.coalesce(func.sum(FeoPlannedItem.quantity), 0).label("qty"),
            )
            .where(FeoPlannedItem.feo_category_id.in_(list(by_id.keys())))
            .where(FeoPlannedItem.is_active.is_(True))
            .group_by(FeoPlannedItem.feo_category_id)
        )
        for r in (await db.execute(fpi_q)).all():
            leaf_item_amt[r.feo_category_id] = float(r.amt)
            leaf_item_qty[r.feo_category_id] = float(r.qty)

    over_consumption = await plan_consumption_by_category(db, subsidy_ids, exclude_planned_item_linked=True)
    ordered_consumption = await ordered_consumption_by_category(db, subsidy_ids, exclude_planned_item_linked=True)
    fact_consumption = await fact_consumption_by_category(db, subsidy_ids)

    # Задача владельца «план ≠ факт, шаг 2» (сессия 2026-08-12): FeoPlannedItem.auto_created
    # («плановая позиция заведена автоматически из закупки/заявки, а не человеком») — нужен
    # для leaf_all_auto (ниже, в _visit): если ВСЕ активные позиции листа автозаведены,
    # excess_fact_over_plan для этого листа не поднимается (план по определению следует
    # за закупкой — ругаться не на что, боевой пример «Приобретение брендированных
    # футболок участников финала»).
    # leaf_item_flags: {cat_id: (кол-во активных позиций, из них auto_created)} — один
    # batch-запрос на все листья субсидии. (Σ amount НЕавтозаведённых — старое третье
    # значение кортежа — убрана вместе со старой формулой manual_plan_entered, см.
    # ПЕРЕРАБОТАНО 2026-08-13 в docstring выше: план п.2 «слагаемое _manual_items_amt
    # убрать».)
    leaf_item_flags: dict[int, tuple] = {}
    if leaf_ids:
        flags_q = (
            select(
                FeoPlannedItem.feo_category_id,
                func.count(FeoPlannedItem.id).label("cnt"),
                func.coalesce(
                    func.sum(case((FeoPlannedItem.auto_created.is_(True), 1), else_=0)), 0
                ).label("auto_cnt"),
            )
            .where(FeoPlannedItem.feo_category_id.in_(leaf_ids))
            .where(FeoPlannedItem.is_active.is_(True))
            .group_by(FeoPlannedItem.feo_category_id)
        )
        for fr in (await db.execute(flags_q)).all():
            leaf_item_flags[fr.feo_category_id] = (int(fr.cnt), int(fr.auto_cnt))

    # Владелец, план zany-fluttering-mountain.md (2026-08-13): «виновники превышения —
    # позиции, добавленные последними, набираемые от свежих к старым, пока не покроют
    # сумму превышения» — для plan_source='manual_sum' узлов (см. docstring выше).
    # own_items_sorted: {cat_id: [{id, name, amount}, ...]} отсортированы СВЕЖИЕ ПЕРВЫМИ
    # (created_at DESC, id DESC), по ВСЕМ категориям (не только листьям — group's own
    # часть тоже может быть в режиме manual_sum, см. ФОРМУЛА v3). БЕЗ фильтра
    # auto_created — теперь неважно, кто завёл позицию, важно кто последний.
    own_items_sorted: dict[int, list[dict]] = {}
    if by_id:
        items_sorted_q = (
            select(
                FeoPlannedItem.feo_category_id, FeoPlannedItem.id,
                FeoPlannedItem.name, FeoPlannedItem.amount,
            )
            .where(FeoPlannedItem.feo_category_id.in_(list(by_id.keys())))
            .where(FeoPlannedItem.is_active.is_(True))
            .order_by(FeoPlannedItem.feo_category_id, FeoPlannedItem.created_at.desc(), FeoPlannedItem.id.desc())
        )
        for ir in (await db.execute(items_sorted_q)).all():
            own_items_sorted.setdefault(ir.feo_category_id, []).append(
                {"id": ir.id, "name": ir.name, "amount": float(ir.amount or 0)}
            )

    # Для каждого узла в режиме 'manual_sum' с превышением (Σ позиций > manual_plan_amount)
    # — сумма превышения и «виновники» (см. own_items_sorted выше), БЕЗ привязки к
    # закупкам пока (см. ниже, батчем через planned_item_consumption/purchase_summaries_by_id
    # — не изобретаем новый запрос к purchase_items, план явно требует переиспользовать
    # planned_item_consumption.linked_purchase_ids).
    own_manual_excess: dict[int, float] = {}
    own_excess_items_raw: dict[int, list[dict]] = {}
    for _cid, _r in by_id.items():
        if (_r.plan_source or "planned_items") != "manual_sum":
            continue
        _manual_amt = float(_r.manual_plan_amount) if _r.manual_plan_amount is not None else 0.0
        _items_total = leaf_item_amt.get(_cid, 0.0)
        _excess = _items_total - _manual_amt
        if _excess > 0.005:
            own_manual_excess[_cid] = _excess
            _running = 0.0
            _culprits: list[dict] = []
            for _it in own_items_sorted.get(_cid, []):
                if _running >= _excess - 0.005:
                    break
                _culprits.append(_it)
                _running += _it["amount"]
            own_excess_items_raw[_cid] = _culprits

    # Связь «позиция → закупки» уже вычисляется в planned_item_consumption
    # (linked_purchase_ids) — переиспользуем, новых запросов к purchase_items не
    # изобретаем (план zany-fluttering-mountain.md, раздел 4). Карточка закупки —
    # app.services.purchase_summary.purchase_summaries_by_id (тот же формат, что
    # у перехода «заявка → её закупки», см. app.routers.wishes._wish_purchase_summaries_map).
    _culprit_item_ids = [it["id"] for _items in own_excess_items_raw.values() for it in _items]
    _item_consumption = await planned_item_consumption(db, _culprit_item_ids) if _culprit_item_ids else {}
    _purchase_ids_needed: set = set()
    for _cons in _item_consumption.values():
        _purchase_ids_needed.update(_cons.get("linked_purchase_ids") or [])
    _purchase_summaries = await purchase_summaries_by_id(db, _purchase_ids_needed) if _purchase_ids_needed else {}

    # Контракт с фронтом (план zany-fluttering-mountain.md, фиксировано, менять
    # нельзя — параллельный агент уже пишет под эту форму): purchases —
    # РОВНО {id, registry_number, purchase_number, status, status_label, amount,
    # stopped_at}. purchase_summaries_by_id отдаёт более широкий словарь (плюс
    # item_name — переиспользуется и app.routers.wishes для другого формата,
    # см. её docstring) — здесь отсекаем лишнее до контрактной формы.
    _PURCHASE_CONTRACT_FIELDS = (
        "id", "registry_number", "purchase_number", "status", "status_label",
        "amount", "stopped_at",
    )
    own_excess_items: dict[int, list[dict]] = {}
    for _cid, _items in own_excess_items_raw.items():
        _built = []
        for _it in _items:
            _linked = (_item_consumption.get(_it["id"]) or {}).get("linked_purchase_ids") or []
            _purchases = [
                {k: _purchase_summaries[pid][k] for k in _PURCHASE_CONTRACT_FIELDS}
                for pid in _linked if pid in _purchase_summaries
            ]
            _built.append({"id": _it["id"], "name": _it["name"], "amount": _it["amount"], "purchases": _purchases})
        own_excess_items[_cid] = _built

    # Согласование превышения плана над финансированием узла (feo_categories.budget) —
    # задача владельца «должны быть заблокированы действия, пока план закупок не
    # загонять обратно в размеры ФЭО» + «согласование цепочкой». Берём ПОСЛЕДНИЙ
    # (по created_at) запрос plan_excess_approvals на каждый узел — если approved,
    # превышение считается легализованным и полностью входит в display; если
    # pending/rejected/отсутствует — превышение НЕ входит в display (остаётся
    # plan_manual), но видно отдельно в excess_amount/excess_pending для UI-бейджа
    # (см. GET /api/feo-categories/plan-tree, frontend SubsidiesView.vue).
    from app.models.plan_excess_approval import PlanExcessApproval
    latest_approval_by_cat: dict[int, PlanExcessApproval] = {}
    if by_id:
        appr_rows = (await db.execute(
            select(PlanExcessApproval)
            .where(PlanExcessApproval.feo_category_id.in_(list(by_id.keys())))
            .order_by(PlanExcessApproval.feo_category_id, PlanExcessApproval.created_at.desc())
        )).scalars().all()
        for a in appr_rows:
            if a.feo_category_id not in latest_approval_by_cat:
                latest_approval_by_cat[a.feo_category_id] = a

    # Задача владельца п.4 (2026-08-12): «если согласовали превышение — так и
    # остаётся... надо, чтобы висело предупреждение, что согласовали». Для КАЖДОЙ
    # approved-заявки находим финализирующий шаг (кто последним поставил approved,
    # с максимальным decided_at — в sequential/parallel цепочке это и есть тот, чьё
    # решение закрыло запрос) — см. app.routers.plan_excess.decide_plan_excess_step.
    finalizer_by_approval: dict[int, tuple] = {}
    finalizer_names: dict[int, Optional[str]] = {}
    approved_ids = [a.id for a in latest_approval_by_cat.values() if a.status == "approved"]
    if approved_ids:
        from app.models.plan_excess_approval import PlanExcessApprovalStep
        step_rows = (await db.execute(
            select(
                PlanExcessApprovalStep.approval_id,
                PlanExcessApprovalStep.decided_by_user_id,
                PlanExcessApprovalStep.decided_at,
            )
            .where(PlanExcessApprovalStep.approval_id.in_(approved_ids))
            .where(PlanExcessApprovalStep.status == "approved")
            .order_by(PlanExcessApprovalStep.approval_id, PlanExcessApprovalStep.decided_at.desc())
        )).all()
        for sr in step_rows:
            if sr.approval_id not in finalizer_by_approval:
                finalizer_by_approval[sr.approval_id] = (sr.decided_by_user_id, sr.decided_at)
        finalizer_user_ids = {v[0] for v in finalizer_by_approval.values() if v[0]}
        if finalizer_user_ids:
            from app.models.user import User
            user_rows = (await db.execute(
                select(User.id, User.full_name, User.username).where(User.id.in_(finalizer_user_ids))
            )).all()
            finalizer_names = {u.id: (u.full_name or u.username) for u in user_rows}

    def _own_plan_and_forecast(qty: float, amt: float, plan_manual: float, ordered: float, ordered_qty: float):
        """Формула замещения плана заказом для ОДНОГО узла (без учёта детей) —
        общая для листа и «собственной» части группы. qty/amt — planned_quantity/
        planned_amount именно этого узла (для группы — всегда 0, см. вызывающий код)."""
        plan = ordered if (qty > 0 and ordered_qty >= qty) else plan_manual
        if ordered_qty > 0:
            avg_price = ordered / ordered_qty
            remaining_qty = max(0.0, qty - ordered_qty) if qty > 0 else 0.0
            forecast = ordered + remaining_qty * avg_price
            forecast_over = max(0.0, forecast - plan_manual)
        else:
            forecast = plan_manual
            forecast_over = 0.0
        return plan, forecast, forecast_over

    def _manual_plan_for(cid: int, r) -> tuple:
        """Владелец, план zany-fluttering-mountain.md (2026-08-13): переключатель
        способа расчёта плана ОДНОГО узла (без детей) — общая формула для листа и
        «собственной» части группы (own_plan, см. ФОРМУЛА v3). r — строка FeoCategory
        ЭТОГО узла (plan_source/manual_plan_amount).

        Возвращает (manual_plan_entered, plan_manual, excess_plan_over_manual,
        excess_plan_items):
          'planned_items' (умолчание) — manual_plan_entered=0, plan_manual = Σ
            активных плановых позиций узла (leaf_item_amt[cid], уже посчитана по
            ВСЕМ категориям выше), excess_plan_over_manual всегда 0 — план не
            может превысить сам себя.
          'manual_sum' — manual_plan_entered = manual_plan_amount узла; plan_manual
            остаётся этой же суммой, ПОКА накопленное превышение (см.
            own_manual_excess, посчитано пакетно выше) не согласовано; если
            согласовано (latest_approval_by_cat[cid].status=='approved') —
            plan_manual становится Σ позиций (решение владельца: «план стал
            равен сумме позиций»). excess_plan_items — уже готовые виновники с
            привязанными закупками (own_excess_items, посчитано выше).
        """
        items_total = leaf_item_amt.get(cid, 0.0)
        if (r.plan_source or "planned_items") != "manual_sum":
            return 0.0, items_total, 0.0, []
        manual_amt = float(r.manual_plan_amount) if r.manual_plan_amount is not None else 0.0
        excess = own_manual_excess.get(cid, 0.0)
        items = own_excess_items.get(cid, [])
        plan_manual = manual_amt
        appr = latest_approval_by_cat.get(cid)
        if excess > 0.005 and appr is not None and appr.status == "approved":
            plan_manual = items_total
        return manual_amt, plan_manual, excess, items

    def _visit(cat_id: int) -> dict:
        cached = result.get(cat_id)
        if cached is not None:
            return cached
        r = by_id[cat_id]
        over_cons = over_consumption.get(cat_id) or {}
        own_over = over_cons.get("over", 0.0)
        own_over_qty = over_cons.get("over_quantity", 0.0)
        own_consumed = over_cons.get("consumed", 0.0)
        own_consumed_qty = over_cons.get("consumed_quantity", 0.0)
        ord_cons = ordered_consumption.get(cat_id) or {}
        own_ordered = ord_cons.get("ordered", 0.0)
        own_ordered_qty = ord_cons.get("ordered_quantity", 0.0)
        fact_cons = fact_consumption.get(cat_id) or {}
        own_fact = fact_cons.get("fact", 0.0)
        own_fact_qty = fact_cons.get("fact_quantity", 0.0)

        leaf_all_auto = False
        manual_plan_entered = 0.0
        excess_plan_over_manual = 0.0
        excess_plan_items: list = []

        kids = children_map.get(cat_id, [])
        if not kids:
            qty = float(r.planned_quantity) if r.planned_quantity is not None else 0.0
            amt = float(r.planned_amount) if r.planned_amount is not None else 0.0
            manual_plan_entered, plan_manual, excess_plan_over_manual, excess_plan_items = _manual_plan_for(cat_id, r)
            if qty == 0.0:
                # planned_quantity категории не задано (план введён позициями,
                # не полями листа) — без этого fallback'а qty_plan/display_quantity
                # ниже обнуляются, и правило замещения «заказ вместо плана»
                # (qty > 0 and ordered_qty >= qty) не срабатывает, т.к. qty всегда 0.
                qty = leaf_item_qty.get(cat_id, 0.0)
            ordered = own_ordered
            ordered_qty = own_ordered_qty
            over = own_over
            over_qty = own_over_qty
            consumed = own_consumed
            consumed_qty = own_consumed_qty
            fact = own_fact
            fact_qty = own_fact_qty
            plan, forecast, forecast_over = _own_plan_and_forecast(qty, amt, plan_manual, ordered, ordered_qty)
            # qty_plan — тот же принцип замещения, что и plan (money), но для
            # количества: заказанное количество замещает плановое, когда оно набрано
            # полностью, иначе показывается всё плановое количество листа.
            qty_plan = ordered_qty if (qty > 0 and ordered_qty >= qty) else qty

            # Задача владельца п.1 (2026-08-12): leaf_all_auto — истинно, если у листа
            # ЕСТЬ хотя бы одна активная плановая позиция и ВСЕ они auto_created —
            # план целиком заведён автоматически из закупки, ругаться на «факт дороже
            # плана» на таком листе бессмысленно (см. применение ниже, у excess_fact_over_plan).
            _flags = leaf_item_flags.get(cat_id)
            leaf_all_auto = bool(_flags and _flags[0] > 0 and _flags[0] == _flags[1])
        else:
            child_nodes = [_visit(c) for c in kids]
            children_plan = sum(c["plan"] for c in child_nodes)
            children_plan_manual = sum(c["plan_manual"] for c in child_nodes)
            children_ordered = sum(c["ordered"] for c in child_nodes)
            children_ordered_qty = sum(c["ordered_quantity"] for c in child_nodes)
            children_over = sum(c["over"] for c in child_nodes)
            children_over_qty = sum(c["over_quantity"] for c in child_nodes)
            children_consumed = sum(c["consumed"] for c in child_nodes)
            children_consumed_qty = sum(c["consumed_quantity"] for c in child_nodes)
            children_forecast_over = sum(c["forecast_over"] for c in child_nodes)
            children_fact = sum(c["fact"] for c in child_nodes)
            children_fact_qty = sum(c["fact_quantity"] for c in child_nodes)

            # Задача владельца «направление со временем может наполниться,
            # соответственно должно считаться и оно» (сессия 2026-08-12, повод —
            # позиция «Бинт марлевый» 48 441,80 ₽ заведена автозаведением прямо
            # на категории 3677 «Окружные», а это НЕ лист, а направление с 5
            # подкатегориями — сумма терялась нигде). own_qty/own_amt — те же
            # активные FeoPlannedItem, что читает лист (leaf_item_qty/leaf_item_amt,
            # теперь собраны по ВСЕМ категориям, не только листьям), но
            # ПРИВЯЗАННЫЕ ПРЯМО К ЭТОМУ УЗЛУ.
            #
            # Владелец, план zany-fluttering-mountain.md (2026-08-13): «собственная
            # часть» группы теперь считается ТЕМ ЖЕ переключателем plan_source/
            # manual_plan_amount, что и лист (_manual_plan_for(cat_id, r) — r здесь
            # строка САМОЙ группы), а не голой Σ own_amt как раньше. На практике для
            # подавляющего большинства групп это НИЧЕГО не меняет: миграция
            # q5r6s7t8u9v0 сознательно НЕ переводит группы в 'manual_sum' (их старые
            # planned_quantity×planned_amount исторически игнорировались — на этом
            # уже была боевая поломка «Микроавтобус», id 905, цена 10 130 000 за
            # штуку), поэтому r.plan_source группы почти всегда 'planned_items' →
            # own_plan_manual_for_calc == own_amt, как и было. Новый режим 'manual_sum'
            # для группы включается только явным выбором в форме.
            own_qty = leaf_item_qty.get(cat_id, 0.0)
            own_amt = leaf_item_amt.get(cat_id, 0.0)
            own_manual_entered, own_plan_manual_for_calc, own_excess, own_excess_items_ = _manual_plan_for(cat_id, r)
            own_plan, _own_forecast, _own_forecast_over = _own_plan_and_forecast(
                own_qty, own_amt, own_plan_manual_for_calc, own_ordered, own_ordered_qty
            )
            own_qty_plan = own_ordered_qty if (own_qty > 0 and own_ordered_qty >= own_qty) else own_qty

            plan_manual = children_plan_manual + own_plan_manual_for_calc
            ordered = own_ordered + children_ordered
            ordered_qty = own_ordered_qty + children_ordered_qty
            over = own_over + children_over
            over_qty = own_over_qty + children_over_qty
            consumed = own_consumed + children_consumed
            consumed_qty = own_consumed_qty + children_consumed_qty
            fact = own_fact + children_fact
            fact_qty = own_fact_qty + children_fact_qty
            plan = own_plan + children_plan
            forecast_over = children_forecast_over
            forecast = plan_manual + forecast_over
            # qty_plan группы = Σ qty_plan детей + собственный qty_plan узла (та же
            # формула замещения, что и own_plan выше, но для количества).
            children_qty_plan = sum(c["qty_plan"] for c in child_nodes)
            qty_plan = children_qty_plan + own_qty_plan

            # excess_plan_over_manual (задача владельца п.2, ПЕРЕРАБОТАНО 2026-08-13) —
            # rollup уже посчитанных (и уже «зажатых» до >=0) значений детей ПЛЮС
            # собственная часть узла (own_excess/own_excess_items_ — та же формула,
            # что и у листа, см. _manual_plan_for) — та же схема, что у forecast_over
            # выше (клэмп на каждом узле, сумма на родителе).
            manual_plan_entered = sum(c["manual_plan_entered"] for c in child_nodes) + own_manual_entered
            excess_plan_over_manual = sum(c["excess_plan_over_manual"] for c in child_nodes) + own_excess
            excess_plan_items = [it for c in child_nodes for it in c["excess_plan_items"]] + own_excess_items_

        # Согласование превышения (см. комментарий у latest_approval_by_cat выше):
        # full_display — «настоящая» плановая сумма узла (как считалось раньше,
        # ДО задачи владельца «блокировать пока не согласовано превышение»).
        # Если она превышает финансирование по ФЭО (budget) и превышение НЕ
        # согласовано — display откатывается к plan_manual (превышение не входит
        # в план, пока не согласовано или не убрано обратно в рамки).
        budget = float(r.budget) if r.budget is not None else None
        full_display = plan + over
        excess_amount = 0.0
        excess_pending = False
        excess_approved = False
        display = full_display
        appr = latest_approval_by_cat.get(cat_id)
        if budget is not None and full_display - budget > 0.005:
            excess_amount = full_display - budget
            if appr is not None and appr.status == "approved":
                excess_approved = True
                display = full_display
            else:
                display = plan_manual
                excess_pending = bool(appr is not None and appr.status == "pending")

        # Задача владельца «план ≠ факт» (шаг C, сессия 2026-08-06): ВТОРОЕ,
        # независимое превышение — «факт дороже плана» (итог закупки/КП больше,
        # чем было запланировано), а НЕ «план дороже финансирования ФЭО»
        # (excess_amount/excess_over_feo — старая, НЕ изменённая семантика, см.
        # выше). excess_amount оставлен как есть для обратной совместимости
        # существующих потребителей; excess_over_feo — то же число под понятным
        # именем. НЕ влияет на display/full_display — это отдельный сигнал для
        # гейта (assert_no_unapproved_excess) и панелей факт/план, а не для
        # KPI «Запланировано».
        excess_over_feo = excess_amount
        excess_fact_over_plan = (fact - plan) if (fact - plan) > 0.005 else 0.0
        if leaf_all_auto:
            # Задача владельца п.1 (2026-08-12): весь план листа автозаведён из
            # самой же закупки (см. leaf_all_auto выше) — план по определению
            # следует за закупкой, «факт дороже плана» тут ложная тревога.
            excess_fact_over_plan = 0.0
        # Согласование превышения факта над планом — та же PlanExcessApproval-запись
        # на категорию (единый механизм согласования, задача владельца «согласование
        # существующим механизмом»): approved снимает блокировку для ВСЕХ ТРЁХ видов
        # превышения одновременно (см. assert_no_unapproved_excess/plan_excess.py).
        excess_fact_approved = bool(excess_fact_over_plan > 0.005 and appr is not None and appr.status == "approved")
        excess_fact_pending = bool(excess_fact_over_plan > 0.005 and appr is not None and appr.status == "pending")

        # Задача владельца п.2 (2026-08-12): ТРЕТЬЕ независимое превышение — Σ ВСЕХ
        # плановых позиций листа/подветки (plan_manual) больше «ручного» плана
        # (manual_plan_entered, посчитан выше в _visit) — «планируются одни траты,
        # а тут уже превысили, значит не хватит на всё». Тот же PlanExcessApproval
        # закрывает и это (см. assert_no_unapproved_excess).
        excess_plan_approved = bool(excess_plan_over_manual > 0.005 and appr is not None and appr.status == "approved")
        excess_plan_pending = bool(excess_plan_over_manual > 0.005 and appr is not None and appr.status == "pending")

        # Задача владельца п.4 (2026-08-12): «если согласовали превышение — так и
        # остаётся... надо, чтобы висело предупреждение, что согласовали» — данные
        # для такого предупреждения (сумма/дата/автор ПОСЛЕДНЕГО approved-запроса
        # по категории), независимо от того, какой из трёх видов превышения его
        # породил и даже если сейчас узел уже не в превышении (запись не стирается).
        if appr is not None and appr.status == "approved":
            excess_approval_amount = float(appr.excess_amount) if appr.excess_amount is not None else None
            excess_approval_at = appr.resolved_at.isoformat() if appr.resolved_at else None
            _finalizer = finalizer_by_approval.get(appr.id)
            excess_approval_by_id = _finalizer[0] if _finalizer else None
            excess_approval_by_name = finalizer_names.get(_finalizer[0]) if _finalizer and _finalizer[0] else None
            # Владелец, план zany-fluttering-mountain.md (2026-08-13): «план был X →
            # стал Y» на постоянной плашке «превышение согласовано» — те же
            # plan_before/plan_after, что записаны на PlanExcessApproval в момент
            # запроса (см. app.routers.plan_excess.request_plan_excess_approval),
            # NULL для превышений НЕ вида plan_over_manual (см. модель).
            excess_approval_plan_before = float(appr.plan_before) if appr.plan_before is not None else None
            excess_approval_plan_after = float(appr.plan_after) if appr.plan_after is not None else None
        else:
            excess_approval_amount = None
            excess_approval_at = None
            excess_approval_by_id = None
            excess_approval_by_name = None
            excess_approval_plan_before = None
            excess_approval_plan_after = None

        node = {
            "subsidy_id": r.subsidy_id,
            "parent_id": r.parent_id,
            "plan_manual": plan_manual,
            "ordered": ordered,
            "ordered_quantity": ordered_qty,
            "ordered_qty": ordered_qty,
            "ordered_sum": ordered,
            "over": over,
            "over_quantity": over_qty,
            "consumed": consumed,
            "consumed_quantity": consumed_qty,
            "fact": fact,
            "fact_quantity": fact_qty,
            "plan": plan,
            "budget": budget,
            "display": display,
            "excess_amount": excess_amount,
            "excess_pending": excess_pending,
            "excess_approved": excess_approved,
            "excess_over_feo": excess_over_feo,
            "excess_fact_over_plan": excess_fact_over_plan,
            "excess_fact_approved": excess_fact_approved,
            "excess_fact_pending": excess_fact_pending,
            # Задача владельца п.2 (2026-08-12): Σ плановых позиций против «ручного»
            # плана — см. комментарий у excess_plan_approved выше.
            "manual_plan_entered": manual_plan_entered,
            "excess_plan_over_manual": excess_plan_over_manual,
            "excess_plan_approved": excess_plan_approved,
            "excess_plan_pending": excess_plan_pending,
            "excess_plan_items": excess_plan_items,
            # Владелец, план zany-fluttering-mountain.md (2026-08-13): переключатель
            # способа расчёта плана этого узла — фронт показывает режим/поле «сумма»
            # в форме категории (см. app.routers.feo_categories POST/PUT).
            "plan_source": r.plan_source or "planned_items",
            "manual_plan_amount": float(r.manual_plan_amount) if r.manual_plan_amount is not None else None,
            # Задача владельца п.4 (2026-08-12): данные последнего approved-согласования
            # по категории (для предупреждения «превышение согласовано»), см. комментарий выше.
            "excess_approval_amount": excess_approval_amount,
            "excess_approval_at": excess_approval_at,
            "excess_approval_by_id": excess_approval_by_id,
            "excess_approval_by_name": excess_approval_by_name,
            "excess_approval_plan_before": excess_approval_plan_before,
            "excess_approval_plan_after": excess_approval_plan_after,
            "residual": plan - ordered,
            "forecast": forecast,
            "forecast_over": forecast_over,
            "qty_plan": qty_plan,
            "display_quantity": qty_plan + over_qty,
        }
        result[cat_id] = node
        return node

    for cid in by_id:
        _visit(cid)
    return result



