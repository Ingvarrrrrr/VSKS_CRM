"""committed_amounts.py — «законтрактовано»: ЕДИНАЯ точка правила (владелец,
02.10.2026, план .planning/quick/2026-10-02-money-redistribution/PLAN.md, шаг 1).

ПРАВИЛО №6: сумма — ТОЛЬКО purchase_item_fact_amount (app.services.feo_plan_fact,
единая формула факта), пакетно через fact_amounts_for_rows (тот же загрузчик,
что использует ЭТОТ модуль и который сам переиспользует _purchase_item_totals/
_contract_item_totals/purchase_item_fact_amount — вторую копию ratio-цикла не
заводим). Статусный предикат «законтрактовано» — committed_status_predicate ниже
— единственное место, где он определён; весь остальной код (compute_feo_plan_tree,
find_excess_culprit, purchase_economy.py, dashboard) обязан ЧИТАТЬ отсюда, а не
собирать свой набор статусов.

Термины владельца (см. PLAN.md, раздел «Термины»):
  Законтрактовано — разовый договор (и закупка без типа договора, включая
    авансовый — у него нет своего purchase_contract_type) — с этапа «Договор»
    (contracted/ordered/delivered/paid). Заказ по рамочному договору
    (purchase_contract_type начинается с 'framework') — только с «Заказано»
    (ordered/delivered/paid), т.к. сама рамочная ГОЛОВА — организационная
    запись без суммы к конкретному товару, деньги занимают только размещённые
    внутри нее заказы. Пример владельца: рамочный на 600 000, заказов на
    350 000 → законтрактовано 350 000 (не 600 000 и не 0).
  Остановленные закупки (Purchase.stopped_at IS NOT NULL) не считаются НИКОГДА
    — то же правило, что и везде в feo_plan_fact.py.
  over_plan=true позиции ИСКЛЮЧЕНЫ — трактуются так же, как в
    ordered_consumption_by_category/fact_consumption_by_category: сверх-плановый
    расход прибавляется к плану БЕЗУСЛОВНО отдельной веткой
    (plan_consumption_by_category.over) — «законтрактовано» описывает базовый
    (не сверх-плановый) расход и не должно задваивать эту сумму.

Функции:
  committed_status_predicate(purchase) — SQL-предикат для WHERE.
  is_purchase_committed(purchase) — питоновский эквивалент для кода, уже
    держащего ORM-объект Purchase (без построения SQL).
  committed_consumption_by_category — по категории ФЭО, с разбивкой по типу
    (kind_of, как fact_consumption_by_category/ordered_consumption_by_category),
    с той же изоляцией субсидий, что и feo_plan_fact.py (Purchase.subsidy_id ==
    FeoCategory.subsidy_id).
  committed_by_planned_item — по плановой позиции (feo_planned_item_id): сумма
    и количество (количество составных позиций — MAX на закупку, см.
    planned_item_consumption/composite_group_metrics, ПРАВИЛО №6).
  committed_by_purchase — по закупке (используется purchase_economy.py и
    карточкой «Заключено договоров», dashboard_charts.contracts_map).
"""
from typing import Optional

from sqlalchemy import and_ as sqland, not_ as sqlnot, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_fact import fact_amounts_for_rows
from app.services.plan_need_level import NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE, normalize_need_level
from sqlalchemy import func

# Разовый договор / закупка без типа договора (single, NULL, пусто, авансовый) —
# занято уже с «Договора». Владелец, вариант Б (шаг 6 плана): авансовый после
# последнего согласования сразу «Поставлено, не оплачено» (delivered) — уже
# внутри этого множества, отдельная ветка не нужна.
SINGLE_COMMITTED_STATUSES: set = {"contracted", "ordered", "delivered", "paid"}
# Рамочный договор (purchase_contract_type начинается с 'framework') — занят
# только РАЗМЕЩЁННЫЙ заказ, сам договор денег не отнимает.
FRAMEWORK_COMMITTED_STATUSES: set = {"ordered", "delivered", "paid"}


def is_framework_purchase_expr(purchase=Purchase):
    """SQL-выражение «эта закупка — рамочный договор» (purchase_contract_type
    начинается с 'framework' — framework_cumulative/framework_with_amount).
    NULL-safe: для NULL/пустой строки возвращает False, а не NULL (см.
    committed_status_predicate — без этого OR/AND по трёхзначной SQL-логике
    молча терял бы строки)."""
    return sqland(purchase.purchase_contract_type.isnot(None), purchase.purchase_contract_type.like("framework%"))


def committed_status_predicate(purchase=Purchase):
    """Единственное место правила статусов «законтрактовано» (см. докстринг
    модуля) — SQL boolean-выражение для WHERE. Остановленные закупки сюда НЕ
    включены (Purchase.stopped_at.is_(None) — отдельное условие, добавляется
    вызывающим кодом, как и everywhere в feo_plan_fact.py)."""
    is_fw = is_framework_purchase_expr(purchase)
    return sqlor(
        sqland(is_fw, purchase.status.in_(FRAMEWORK_COMMITTED_STATUSES)),
        sqland(sqlnot(is_fw), purchase.status.in_(SINGLE_COMMITTED_STATUSES)),
    )


def is_purchase_committed(purchase: Purchase) -> bool:
    """Питоновский эквивалент committed_status_predicate — для кода, уже
    держащего ORM-объект Purchase в памяти (не строящего SQL). ОДНО правило —
    см. докстринг модуля, не дублировать набор статусов где-либо ещё."""
    if purchase.stopped_at is not None:
        return False
    is_fw = bool(purchase.purchase_contract_type) and purchase.purchase_contract_type.startswith("framework")
    allowed = FRAMEWORK_COMMITTED_STATUSES if is_fw else SINGLE_COMMITTED_STATUSES
    return purchase.status in allowed


async def committed_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
    include_over_plan: bool = False,
) -> dict[int, dict]:
    """{feo_category_id: {committed, committed_quantity, committed_goods,
    committed_services, committed_unspecified, committed_missing_fact_items}}
    — ТА ЖЕ структура/изоляция субсидий, что и ordered_consumption_by_category
    (feo_plan_fact.py), но порог статуса — committed_status_predicate (см.
    докстринг модуля), а не ORDERED_STATUSES.

    exclude_planned_item_linked=True — исключить ВАЛИДНО привязанные к
    FeoPlannedItem позиции (та же проверка «существует/активна/своя
    категория», что и в ordered_consumption_by_category) — используется
    compute_feo_plan_tree для порога замещения плана НЕпривязанных закупок
    (шаг 2 плана). exclude_planned_item_linked=False (умолчание) — ВСЕ
    законтрактованные позиции узла (линкованные и нет) — используется для
    ИТОГОВОГО поля узла committed/committed_goods/... (узел+поддерево) и для
    агрегатов по субсидии/дашборду.

    include_over_plan=False (умолчание) — over_plan=true позиции исключены,
    как и раньше (нужно ТОЛЬКО порогу замещения плана — над-плановый расход
    не часть «плана», см. докстринг модуля). include_over_plan=True —
    ИСПРАВЛЕНИЕ #2 (ревью 02.10.2026): над-плановые позиции — реальные деньги
    по договору, должны входить в ИТОГОВОЕ «законтрактовано» узла/субсидии
    (committed_consumption_all в feo_plan_tree.py вызывает с True); из
    ЗАМЕЩЕНИЯ плана (exclude_planned_item_linked-ветка, порог количества)
    они по-прежнему исключены — порог замещения продолжает вызываться с
    include_over_plan=False.

    ИСПРАВЛЕНИЕ #1 (ревью 02.10.2026): строка БЕЗ известного факта
    (fact_amounts_for_rows вернула None — договорная сумма ещё не внесена, нет
    ни contract_price, ни ContractItem) НЕ участвует в committed_quantity
    (позиция не признаётся закрытой по количеству — план не замещается
    ложно), но её сумма «уже занята договором» — входит в committed ПО
    ПЛАНОВОЙ ЦЕНЕ (PurchaseItem.planned_total, а если и её нет — total_price:
    деньги зарезервированы по сумме закупки, даже без плановой привязки).
    Такие строки считаются отдельно в committed_missing_fact_items — повод
    для предупреждения на экране («N позиций в договоре без суммы
    договора»)."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    from app.services.item_type_split import kind_of  # локальный импорт — см. предупреждение в feo_plan_fact.py

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    _fpi = aliased(FeoPlannedItem)
    stmt = (
        select(
            PurchaseItem, Purchase, cat_col.label("cat_id"),
            # Задача 2 (владелец, 04.10.2026, need_level-разбивка «не
            # законтрактовано») — те же три поля валидности привязки, что и
            # в exclude_planned_item_linked ниже/в plan_consumption_by_category,
            # нужны тут же, в ЭТОМ ЖЕ проходе по строкам, без второго запроса.
            _fpi.need_level.label("fpi_need_level"),
            _fpi.id.label("fpi_id"),
            _fpi.is_active.label("fpi_is_active"),
            _fpi.feo_category_id.label("fpi_cat_id"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .outerjoin(_fpi, _fpi.id == PurchaseItem.feo_planned_item_id)
        .where(committed_status_predicate(Purchase))
        .where(Purchase.stopped_at.is_(None))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
    )
    if not include_over_plan:
        stmt = stmt.where(PurchaseItem.over_plan.is_(False))
    if exclude_planned_item_linked:
        stmt = stmt.where(
            sqlor(
                PurchaseItem.feo_planned_item_id.is_(None),
                _fpi.id.is_(None),
                _fpi.is_active.is_(False),
                _fpi.feo_category_id != cat_col,
            )
        )

    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    fact_by_item = await fact_amounts_for_rows(db, rows)
    for r in rows:
        pi = r.PurchaseItem
        fact_amount = fact_by_item.get(pi.id)
        d = result.setdefault(r.cat_id, {
            "committed": 0.0, "committed_quantity": 0.0,
            "committed_goods": 0.0, "committed_services": 0.0, "committed_unspecified": 0.0,
            "committed_missing_fact_items": 0,
            "committed_likely": 0.0, "committed_nice_to_have": 0.0,
        })
        # Задача 2 (владелец, 04.10.2026) — need_level ЭТОЙ строки: берётся у
        # привязанной плановой позиции, ТОЛЬКО если привязка валидна (та же
        # проверка существует/активна/своя категория, что и exclude_planned_item_linked
        # выше) — иначе (не привязана, привязана на несуществующую/неактивную/
        # чужую-категории позицию) нет позиции, чей need_level читать, и по
        # решению владельца («заявки без плановой позиции — считать likely»)
        # сумма идёт в 'likely'.
        _valid_link = (
            pi.feo_planned_item_id is not None
            and r.fpi_id is not None
            and bool(r.fpi_is_active)
            and r.fpi_cat_id == r.cat_id
        )
        _level = normalize_need_level(r.fpi_need_level) if _valid_link else NEED_LEVEL_LIKELY
        if fact_amount is None:
            # ИСПРАВЛЕНИЕ #1 — см. докстринг выше: сумма по плановой/факт.
            # цене позиции входит в committed (деньги заняты договором), но
            # количество НЕ засчитывается (позиция не закрыта).
            fallback = pi.planned_total if pi.planned_total is not None else pi.total_price
            amt = float(fallback or 0)
            d["committed"] += amt
            d[f"committed_{kind_of(pi.item_type)}"] += amt
            d[f"committed_{_level}"] += amt
            d["committed_missing_fact_items"] += 1
            continue
        d["committed"] += float(fact_amount)
        d["committed_quantity"] += float(pi.quantity or 0)
        d[f"committed_{kind_of(pi.item_type)}"] += float(fact_amount)
        d[f"committed_{_level}"] += float(fact_amount)
    return result


async def committed_by_planned_item(db: AsyncSession, item_ids: list[int]) -> dict[int, dict]:
    """{feo_planned_item_id: {amount, quantity, missing_fact_items}} —
    законтрактованная сумма/количество позиций закупок, привязанных к
    плановой позиции (PurchaseItem.feo_planned_item_id), статус —
    committed_status_predicate, БЕЗ over_plan=true (та же трактовка, что
    committed_consumption_by_category — над-плановое не часть плана этой
    позиции, замещение им не управляется).

    ИСПРАВЛЕНИЕ #1 (ревью 02.10.2026): строка БЕЗ известного факта (нет ни
    contract_price, ни ContractItem — fact_amounts_for_rows вернула None) НЕ
    участвует в `quantity` (позиция НЕ признаётся закрытой количеством — план
    не замещается ложно), но её сумма входит в `amount` по плановой цене
    (planned_total, фолбэк total_price — деньги уже заняты договором).
    Отдельно считается `missing_fact_items` — количество таких строк
    (предупреждение «N позиций в договоре без суммы договора»).

    Составные плановые позиции (FeoPlannedItem.is_composite=True) — quantity
    берётся MAX строк ОДНОЙ закупки на эту позицию, Σ по закупкам (та же
    формула, что planned_item_consumption._comp_qty_q, feo_plan_fact.py,
    ПРАВИЛО №6 — переиспользуем идею, не копируем SQL дословно, т.к. тут уже
    нужна Python-группировка ради fact_amounts_for_rows). Строки без факта в
    эту MAX/Σ-группировку количества НЕ попадают вовсе (см. исправление #1)."""
    result: dict[int, dict] = {iid: {"amount": 0.0, "quantity": 0.0, "missing_fact_items": 0} for iid in item_ids}
    if not item_ids:
        return result

    stmt = (
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(committed_status_predicate(Purchase))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    fact_by_item = await fact_amounts_for_rows(db, rows)

    composite_ids = set((
        await db.execute(
            select(FeoPlannedItem.id).where(
                FeoPlannedItem.id.in_(item_ids), FeoPlannedItem.is_composite.is_(True),
            )
        )
    ).scalars().all())

    # Группировка количества по (плановая позиция, закупка) — составной позиции
    # нужен MAX количества строк ОДНОЙ закупки, не Σ (см. докстринг выше). Строки
    # без факта (amt is None) сюда НЕ попадают — исправление #1.
    qty_by_item_purchase: dict[tuple, list] = {}
    for r in rows:
        pi, p = r.PurchaseItem, r.Purchase
        amt = fact_by_item.get(pi.id)
        if amt is not None:
            result[pi.feo_planned_item_id]["amount"] += float(amt)
            qty_by_item_purchase.setdefault((pi.feo_planned_item_id, p.id), []).append(float(pi.quantity or 0))
        else:
            fallback = pi.planned_total if pi.planned_total is not None else pi.total_price
            result[pi.feo_planned_item_id]["amount"] += float(fallback or 0)
            result[pi.feo_planned_item_id]["missing_fact_items"] += 1

    for (fpi_id, _pid), qtys in qty_by_item_purchase.items():
        if fpi_id in composite_ids:
            result[fpi_id]["quantity"] += max(qtys) if qtys else 0.0
        else:
            result[fpi_id]["quantity"] += sum(qtys)
    return result


async def committed_by_purchase(db: AsyncSession, purchase_ids, include_over_plan: bool = True) -> dict[int, float]:
    """{purchase_id: Σ amount законтрактованных позиций (committed_status_predicate)}
    — используется карточкой «Заключено договоров» (dashboard_charts.contracts_map,
    рамочный — по заказам, см. PLAN.md шаг 1). ИСПРАВЛЕНИЕ #2 (ревью 02.10.2026):
    include_over_plan=True (умолчание) — над-плановые позиции реальны по
    договору и входят в сумму закупки; include_over_plan=False — старое
    поведение (без них), оставлено параметром на случай, если вызывающему
    нужен именно «базовый план» закупки. ИСПРАВЛЕНИЕ #1: строка без факта —
    сумма по плановой/факт. цене позиции (fallback), не теряется."""
    purchase_ids = list(purchase_ids)
    result: dict[int, float] = {pid: 0.0 for pid in purchase_ids}
    if not purchase_ids:
        return result

    stmt = (
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.id.in_(purchase_ids))
        .where(committed_status_predicate(Purchase))
        .where(Purchase.stopped_at.is_(None))
    )
    if not include_over_plan:
        stmt = stmt.where(PurchaseItem.over_plan.is_(False))
    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    fact_by_item = await fact_amounts_for_rows(db, rows)
    for r in rows:
        pi, p = r.PurchaseItem, r.Purchase
        amt = fact_by_item.get(pi.id)
        if amt is not None:
            result[p.id] += float(amt)
        else:
            fallback = pi.planned_total if pi.planned_total is not None else pi.total_price
            result[p.id] += float(fallback or 0)
    return result


async def planned_item_contributions(db: AsyncSession, category_ids: list[int]) -> dict[int, dict]:
    """{feo_planned_item_id: {"amount": contribution, "feo_category_id", "item_type_effective"}}
    — ЕДИНАЯ (ПРАВИЛО №6), ПОСТРОЧНАЯ точка правила шага 2 плана «Деньги
    субсидии» (владелец, 02.10.2026, «экономия закрытой позиции возвращается в
    Свободно»): по КАЖДОЙ активной FeoPlannedItem категорий category_ids,
    `amount` — её «вклад в план» (contribution), а не голое поле .amount.

    Правило: для FeoPlannedItem с payment_mode='one_time' и quantity > 0 —
    если законтрактованное количество по ней (committed_by_planned_item) ≥ её
    quantity, contribution = её законтрактованная СУММА (экономия/переплата
    высвобождается); иначе — amount целиком (план резервируется, пока
    количество не набрано полностью). Ежемесячные (payment_mode='monthly') и
    позиции БЕЗ quantity (NULL/0) — всегда amount (нечем мерить «набрано ли
    количество» — владелец: «ежемесячные остаются зарезервированными целиком»).

    Переиспользуется И leaf_items_committed_contribution ниже (агрегат по
    категории для compute_feo_plan_tree), И find_excess_culprit
    (feo_plan_excess.py, ПОСТРОЧНО — виновнику нужна сумма КОНКРЕТНОЙ позиции,
    не агрегат) — оба обязаны читать ОДНО и то же число на одну и ту же
    позицию, иначе Σ контрибьюторов разойдётся с планом дерева (см.
    test_find_excess_culprit_uses_same_plan_source_formula)."""
    from app.services.feo_plan_tree import resolve_effective_item_types  # local: avoid import cycle

    result: dict[int, dict] = {}
    if not category_ids:
        return result

    items_q = (
        select(
            FeoPlannedItem.id, FeoPlannedItem.feo_category_id, FeoPlannedItem.item_type,
            FeoPlannedItem.amount, FeoPlannedItem.quantity, FeoPlannedItem.payment_mode,
        )
        .where(FeoPlannedItem.feo_category_id.in_(category_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )
    rows = (await db.execute(items_q)).all()
    if not rows:
        return result

    # Законтрактованное количество/сумма нужны ТОЛЬКО позициям, способным
    # замещаться (one_time, quantity > 0) — не гоняем лишний запрос по всем.
    _substitution_candidate_ids = [
        r.id for r in rows
        if (r.payment_mode or "one_time") == "one_time" and float(r.quantity or 0) > 0
    ]
    committed_map = await committed_by_planned_item(db, _substitution_candidate_ids)
    eff_types = await resolve_effective_item_types(db, rows)

    for r in rows:
        contribution = float(r.amount or 0)
        if (r.payment_mode or "one_time") == "one_time" and float(r.quantity or 0) > 0:
            _committed = committed_map.get(r.id) or {"amount": 0.0, "quantity": 0.0}
            if _committed["quantity"] >= float(r.quantity):
                contribution = _committed["amount"]
        result[r.id] = {
            "amount": contribution,
            "feo_category_id": r.feo_category_id,
            "item_type_effective": eff_types.get(r.id),
        }
    return result


async def leaf_items_committed_contribution(
    db: AsyncSession, category_ids: list[int]
) -> tuple[dict[int, float], dict[int, dict]]:
    """Агрегат по категории поверх planned_item_contributions (см. её докстринг
    — ОДНА точка правила, эта функция только суммирует) — используется
    compute_feo_plan_tree (feo_plan_tree.py, узел 'planned_items'); режим
    'manual_sum' эту функцию НЕ использует — его items_total остаётся голой Σ
    amount, владелец явно просил его не трогать.

    Возвращает (contribution_by_category, contribution_by_category_and_kind):
    второе — ТА ЖЕ contribution, разложенная по kind_of(item_type_effective),
    нужна, чтобы инвариант «plan_goods+services+unspecified == display узла»
    (test_feo_plan_tree_type_split.py) остался в силе и после замещения
    savings по типу."""
    from app.services.item_type_split import KIND_GOODS, KIND_SERVICES, KIND_UNSPECIFIED, kind_of

    contribution_by_category: dict[int, float] = {}
    contribution_by_kind: dict[int, dict] = {}
    per_item = await planned_item_contributions(db, category_ids)
    for _item_id, info in per_item.items():
        cat_id = info["feo_category_id"]
        contribution_by_category[cat_id] = contribution_by_category.get(cat_id, 0.0) + info["amount"]
        _bucket = kind_of(info["item_type_effective"])
        _kd = contribution_by_kind.setdefault(
            cat_id, {KIND_GOODS: 0.0, KIND_SERVICES: 0.0, KIND_UNSPECIFIED: 0.0}
        )
        _kd[_bucket] += info["amount"]
    return contribution_by_category, contribution_by_kind


async def leaf_items_not_committed_by_need_level(
    db: AsyncSession, category_ids: list[int]
) -> dict[int, dict]:
    """{feo_category_id: {"likely": сумма, "nice_to_have": сумма}} — Задача 2
    (владелец, 04.10.2026, план .planning/quick/2026-10-04-sheet-ideas):
    «незаконтрактованный остаток плана» СОБСТВЕННЫХ (без рекурсии по
    поддереву — рекурсию делает вызывающий код compute_feo_plan_tree, тот же
    приём, что и leaf_items_committed_contribution выше) активных FeoPlannedItem
    категории, разбитый по need_level (app.services.plan_need_level).

    ПРАВИЛО №6 — НЕ вторая формула «законтрактовано»/«вклад в план»: остаток
    ОДНОЙ позиции = planned_item_contributions(...)[item]['amount'] (contribution —
    та же величина, что складывается в leaf_item_committed_amt узла, т.е. формирует
    scalar `plan`) МИНУС committed_by_planned_item(...)[item]['amount']
    (законтрактованная сумма именно этой позиции) — БЕЗ клэмпа на 0 для
    отдельной позиции (аддитивно: Σ по ВСЕМ позициям категории равна
    own-части scalar `planned_not_committed` ТОЧНО, когда нет непривязанных/
    сверх-плановых закупок в категории — см. docstring compute_feo_plan_tree,
    раздел not_committed_likely/not_committed_nice).

    Вызывающий код (compute_feo_plan_tree) берёт ЭТУ сумму как own-часть
    'nice_to_have', а 'likely' узла довыводит остатком из уже готового scalar
    `planned_not_committed` (а не второй independent суммой) — так остаток
    «непривязанных закупок»/«заявок без плановой позиции» автоматически
    попадает в 'likely', без отдельной формулы под него (решение владельца
    «заявки без плановой позиции считать likely»)."""
    result: dict[int, dict] = {}
    if not category_ids:
        return result

    items_q = (
        select(FeoPlannedItem.id, FeoPlannedItem.feo_category_id, FeoPlannedItem.need_level)
        .where(FeoPlannedItem.feo_category_id.in_(category_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )
    rows = (await db.execute(items_q)).all()
    if not rows:
        return result

    contrib = await planned_item_contributions(db, category_ids)
    committed_map = await committed_by_planned_item(db, [r.id for r in rows])

    for r in rows:
        info = contrib.get(r.id)
        if info is None:
            continue
        committed_amt = (committed_map.get(r.id) or {}).get("amount", 0.0)
        remainder = info["amount"] - committed_amt
        level = normalize_need_level(r.need_level)
        d = result.setdefault(r.feo_category_id, {NEED_LEVEL_LIKELY: 0.0, NEED_LEVEL_NICE_TO_HAVE: 0.0})
        d[level] += remainder
    return result


async def subsidy_committed_totals(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {committed, committed_goods, committed_services,
    committed_unspecified, committed_missing_fact_items}} — Σ по КОРНЕВЫМ
    узлам compute_feo_plan_tree (тот же приём, что subsidy_type_totals,
    app.services.type_totals, ПРАВИЛО №6 — читаем готовые typed-поля узла,
    не считаем «законтрактовано» субсидии второй формулой).

    Контракт API (PLAN.md шаг 1-2, п. A — GET /api/dashboard/charts
    subsidy_stats и KPI вкладки «Субсидии»): используется вызывающим кодом
    вместе с effective_subsidy_budget/planned_tree (УЖЕ посчитанными там) для
    planned_not_committed = planned_tree − committed и redistributable =
    budget − committed — САМИ эти два поля здесь не считаются (budget
    субсидии — отдельная точка, app.services.subsidy_budget, не дублируем)."""
    result: dict[int, dict] = {
        sid: {
            "committed": 0.0, "committed_goods": 0.0, "committed_services": 0.0,
            "committed_unspecified": 0.0, "committed_missing_fact_items": 0,
            # plan_* — Σ по корневым узлам (та же величина, что subsidy_type_totals
            # отдаёт отдельным вызовом, app.services.type_totals) — ПЕРЕИСПОЛЬЗУЕМ
            # ОДИН проход по дереву, построенный этой функцией, вместо второго
            # вызова compute_feo_plan_tree ради planned_not_committed_by_kind
            # (dashboard_charts.py, контракт API п. A).
            "plan_goods": 0.0, "plan_services": 0.0, "plan_unspecified": 0.0,
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    # committed_missing_fact_items не возвращается узлом дерева (поле
    # committed_consumption_by_category, не прокинутое в node — дерево
    # считает только суммы, а не счётчик предупреждения) — собираем его
    # отдельно, той же функцией с include_over_plan=True (байт-в-байт та же
    # выборка, что строит committed_consumption_all внутри дерева).
    missing_by_cat = await committed_consumption_by_category(db, subsidy_ids, include_over_plan=True)
    for node in tree.values():
        if node.get("parent_id") is not None:
            continue  # только корневые узлы — та же выборка, что planned_tree/feo_budget_total
        sid = node.get("subsidy_id")
        if sid not in result:
            continue
        d = result[sid]
        d["committed"] += node["committed"]
        d["committed_goods"] += node["committed_goods"]
        d["committed_services"] += node["committed_services"]
        d["committed_unspecified"] += node["committed_unspecified"]
        d["plan_goods"] += node["plan_goods"]
        d["plan_services"] += node["plan_services"]
        d["plan_unspecified"] += node["plan_unspecified"]
    # missing_fact_items — Σ по ВСЕМ категориям субсидии (не только корневым,
    # т.к. committed_consumption_by_category индексирована по cat_id листа/
    # группы напрямую, не по дереву) — нужна карта feo_category_id → subsidy_id.
    if missing_by_cat:
        from app.models.feo_category import FeoCategory as _FC
        cat_sid_rows = (await db.execute(
            select(_FC.id, _FC.subsidy_id).where(_FC.id.in_(missing_by_cat.keys()))
        )).all()
        for cat_id, sid in cat_sid_rows:
            if sid in result:
                result[sid]["committed_missing_fact_items"] += missing_by_cat[cat_id]["committed_missing_fact_items"]
    return result
