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
from app.models.subsidy import Subsidy
from app.services.feo_plan_common import _order_substituted_plan
from app.services.feo_plan_fact import fact_amounts_for_rows
from app.services.plan_need_level import (
    NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE, is_reserve_need_level, normalize_need_level,
)
from app.services.purchase_amounts import aggregate_scope_expr
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


def committed_status_predicate(purchase=Purchase, *, subsidy_year_col=None, today=None):
    """Единственное место правила статусов «законтрактовано» (см. докстринг
    модуля) — SQL boolean-выражение для WHERE. Остановленные закупки сюда НЕ
    включены (Purchase.stopped_at.is_(None) — отдельное условие, добавляется
    вызывающим кодом, как и everywhere в feo_plan_fact.py).

    ДОБАВЛЕНО (🟢 правка 2 плана abstract-noodling-pelican.md, 15.10.2026,
    п.B): заказ рамочного договора (status='contracted', parent_purchase_id
    не NULL — app.services.stage_cumulative.reserved_child_predicate()), чей
    месяц (app.services.monthly_future_payments.framework_child_month_expr)
    уже НАСТУПИЛ (≤ первое число текущего месяца) — тоже «занято», хотя сам
    заказ как отдельная закупка ещё не оформлен (status ещё 'contracted', не
    'ordered'). Второго правила «занято» это не заводит — ветка добавляется
    ТОЛЬКО если вызывающий код передал subsidy_year_col (выражение года
    субсидии из уже выполненного JOIN на Subsidy в своём запросе) — без него
    predicate ведёт себя КАК РАНЬШЕ (обратная совместимость для вызовов, где
    JOIN на Subsidy нет и месяц проверить нечем)."""
    is_fw = is_framework_purchase_expr(purchase)
    base = sqlor(
        sqland(is_fw, purchase.status.in_(FRAMEWORK_COMMITTED_STATUSES)),
        sqland(sqlnot(is_fw), purchase.status.in_(SINGLE_COMMITTED_STATUSES)),
    )
    if subsidy_year_col is None:
        return base

    from datetime import date as _date
    from app.services.monthly_future_payments import framework_child_month_expr
    from app.services.stage_cumulative import reserved_child_predicate

    _today = today or _date.today()
    cur_month = _date(_today.year, _today.month, 1)
    started_reserved = sqland(
        reserved_child_predicate(),
        framework_child_month_expr(purchase, subsidy_year_col) <= cur_month,
    )
    return sqlor(base, started_reserved)


def is_purchase_committed(purchase: Purchase, *, framework_order_month=None, today=None) -> bool:
    """Питоновский эквивалент committed_status_predicate — для кода, уже
    держащего ORM-объект Purchase в памяти (не строящего SQL). ОДНО правило —
    см. докстринг модуля, не дублировать набор статусов где-либо ещё.

    `framework_order_month` (🟢 правка 2, 15.10.2026) — ГОТОВЫЙ месяц заказа
    (date, 1-е число), если вызывающий код уже его знает (например, из
    app.services.monthly_future_payments.framework_order_month_rows) — эта
    функция сама в БД не лезет и siblings/Subsidy.year не считает. Без него
    поведение прежнее (заказ 'contracted' без фактического 'ordered' НЕ
    считается занятым)."""
    if purchase.stopped_at is not None:
        return False
    is_fw = bool(purchase.purchase_contract_type) and purchase.purchase_contract_type.startswith("framework")
    if is_fw:
        if purchase.status in FRAMEWORK_COMMITTED_STATUSES:
            return True
        if (
            purchase.status == "contracted"
            and purchase.parent_purchase_id is not None
            and framework_order_month is not None
        ):
            from datetime import date as _date
            _today = today or _date.today()
            cur_month = _date(_today.year, _today.month, 1)
            return framework_order_month <= cur_month
        return False
    return purchase.status in SINGLE_COMMITTED_STATUSES


async def committed_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
    include_over_plan: bool = False,
    payroll_category_ids: set | None = None,
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

    # локальный импорт — см. предупреждение в feo_plan_fact.py
    from app.services.item_type_split import kind_of_by_category_id
    _payroll_ids = payroll_category_ids or set()

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
        # outerjoin (ИСПРАВЛЕНО 15.10.2026, находка координатора на сверке
        # прода — закупка id=941, single/contracted, Purchase.subsidy_id=NULL,
        # но её позиция привязана к плановой позиции субсидии 7): INNER JOIN
        # на Subsidy выбрасывал строку ЦЕЛИКОМ ещё ДО committed_status_predicate
        # — 40 117 ₽ уезжали из «законтрактовано» в «скорее всего». Год
        # субсидии (subsidy_year_col) нужен ТОЛЬКО ветке рамочного заказа
        # внутри committed_status_predicate — при NULL (нет JOIN-строки) эта
        # ветка просто не срабатывает (см. её докстринг), обычное правило
        # статусов (SINGLE/FRAMEWORK_COMMITTED_STATUSES) продолжает работать
        # как раньше.
        .outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .outerjoin(_fpi, _fpi.id == PurchaseItem.feo_planned_item_id)
        # subsidy_year_col=Subsidy.year (🟢 правка 2, 15.10.2026, п.B) — «законтрактовано»
        # дерева ФЭО включает заказ рамочного договора, чей месяц уже начался,
        # даже если сам заказ ещё не оформлен отдельной закупкой (status=
        # 'contracted'). См. докстринг committed_status_predicate.
        .where(committed_status_predicate(Purchase, subsidy_year_col=Subsidy.year))
        .where(Purchase.stopped_at.is_(None))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        # Purchase.subsidy_id может быть NULL (находка 15.10.2026, см. outerjoin
        # выше) — строка всё равно принадлежит категории cat_col, которую она
        # явно указывает на PurchaseItem/Purchase.feo_category_id; при
        # заполненном Purchase.subsidy_id сверка с категорией остаётся
        # ОБЯЗАТЕЛЬНОЙ (защита от чужой субсидии не снимается).
        .where(sqlor(Purchase.subsidy_id == FeoCategory.subsidy_id, Purchase.subsidy_id.is_(None)))
        # Рамочная ГОЛОВА (framework_with_amount/framework_cumulative,
        # parent_purchase_id IS NULL) с реально существующими дочерними
        # заказами — та же исключающая точка, что и в карточках субсидии
        # (aggregate_scope_expr, purchase_amounts.py, решение владельца
        # 05.10.2026, ПРАВИЛО №6 — НЕ второй предикат): её единственная
        # позиция «Лимит договора …» организационная, реальные деньги несут
        # дочерние закупки своей суммой по стадии. Без этого фильтра голова
        # задваивала «законтрактовано»/«в закупках» своей категории (ложный
        # перерасход узла «Не определена», найдено 06.10.2026).
        .where(aggregate_scope_expr())
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
            "committed_goods": 0.0, "committed_services": 0.0,
            "committed_payroll": 0.0, "committed_unspecified": 0.0,
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
        # 🟡 'unforeseen' схлопывается в 'nice_to_have' — d имеет только два
        # ключа committed_likely/committed_nice_to_have (ПРАВИЛО №6, см.
        # is_reserve_need_level).
        _level = (NEED_LEVEL_NICE_TO_HAVE if (_valid_link and is_reserve_need_level(r.fpi_need_level))
                  else NEED_LEVEL_LIKELY)
        if fact_amount is None:
            # ИСПРАВЛЕНИЕ #1 — см. докстринг выше: сумма по плановой/факт.
            # цене позиции входит в committed (деньги заняты договором), но
            # количество НЕ засчитывается (позиция не закрыта).
            fallback = pi.planned_total if pi.planned_total is not None else pi.total_price
            amt = float(fallback or 0)
            d["committed"] += amt
            d[f"committed_{kind_of_by_category_id(pi.item_type, r.cat_id, _payroll_ids)}"] += amt
            d[f"committed_{_level}"] += amt
            d["committed_missing_fact_items"] += 1
            continue
        d["committed"] += float(fact_amount)
        d["committed_quantity"] += float(pi.quantity or 0)
        d[f"committed_{kind_of_by_category_id(pi.item_type, r.cat_id, _payroll_ids)}"] += float(fact_amount)
        d[f"committed_{_level}"] += float(fact_amount)
    return result


async def committed_by_planned_item(
    db: AsyncSession, item_ids: list[int], *, month_aware: bool = False,
) -> dict[int, dict]:
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
    эту MAX/Σ-группировку количества НЕ попадают вовсе (см. исправление #1).

    ИСПРАВЛЕНИЕ #2 (13.10→15.10.2026, перерасход по позиции с планом 0/без
    quantity, субсидия «ФАДМ 2026_3» id 100, позиция 42925): дополнительный
    ключ `has_rows` — хотя бы одна committed-строка закупки привязана к этой
    позиции (независимо от того, попала ли она в `quantity` — строки без
    известного факта туда не попадают, см. исправление #1). Нужен
    planned_item_contributions ниже, чтобы отличить «позиция без committed
    активности вообще» от «позиция с committed, но без quantity» — только по
    `amount != 0`/`quantity` этого не определить (amount может легитимно быть
    0, если факт 0).

    `month_aware=True` (🟢 правка 2 плана abstract-noodling-pelican.md,
    15.10.2026, п.B/C) — JOIN на Subsidy и committed_status_predicate(...,
    subsidy_year_col=Subsidy.year): заказ рамочного договора, чей месяц уже
    начался, тоже committed (см. докстринг committed_status_predicate).
    Используется app.services.redistributable_raw (карточка «Можно
    перераспределить» не должна показывать уже начавшийся месяц ни
    «нужностью», ни «ещё уйдёт помесячно»). По умолчанию False — поведение
    прежнее (для вызовов без интереса к рамочным заказам)."""
    result: dict[int, dict] = {
        iid: {"amount": 0.0, "quantity": 0.0, "missing_fact_items": 0, "has_rows": False} for iid in item_ids
    }
    if not item_ids:
        return result

    stmt = (
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
    )
    if month_aware:
        # outerjoin (ИСПРАВЛЕНО 15.10.2026, та же находка, что у
        # committed_consumption_by_category выше — закупка id=941 без
        # Purchase.subsidy_id): INNER JOIN на Subsidy выбрасывал строку
        # целиком. Здесь нет отдельной сверки Purchase.subsidy_id==...,
        # NULL-год просто не включает ветку рамочного заказа предиката (см.
        # докстринг committed_status_predicate), обычный статусный чек
        # работает как раньше.
        stmt = stmt.outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id).where(
            committed_status_predicate(Purchase, subsidy_year_col=Subsidy.year)
        )
    else:
        stmt = stmt.where(committed_status_predicate(Purchase))
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
        result[pi.feo_planned_item_id]["has_rows"] = True
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


async def planned_item_contributions(
    db: AsyncSession, category_ids: list[int], payroll_category_ids: Optional[set] = None,
) -> dict[int, dict]:
    """{feo_planned_item_id: {"amount": contribution, "feo_category_id", "item_type_effective"}}
    — ЕДИНАЯ (ПРАВИЛО №6), ПОСТРОЧНАЯ точка правила шага 2 плана «Деньги
    субсидии» (владелец, 02.10.2026, «экономия закрытой позиции возвращается в
    Свободно»): по КАЖДОЙ активной FeoPlannedItem категорий category_ids,
    `amount` — её «вклад в план» (contribution), а не голое поле .amount.

    Правило: для FeoPlannedItem с payment_mode='one_time' и quantity > 0 —
    если законтрактованное количество по ней (committed_by_planned_item) ≥ её
    quantity, contribution = её законтрактованная СУММА (экономия/переплата
    высвобождается); иначе — amount целиком (план резервируется, пока
    количество не набрано полностью). Ежемесячные (payment_mode='monthly') —
    всегда amount (владелец: «ежемесячные остаются зарезервированными
    целиком» — у них по смыслу нет «набранного количества», оплата длится).

    ИСПРАВЛЕНИЕ (13.10→15.10.2026, субсидия «ФАДМ 2026_3» id 100, позиция
    42925 «Ремонт автомобиля…», план 0, quantity NULL, закупка delivered
    40 730): одноразовая позиция БЕЗ quantity (NULL/0) — раньше ВСЕГДА
    amount, то есть её committed-закупка не влияла на contribution вовсе,
    а оседала только в own_committed_all узла — который, ПО ДИЗАЙНУ
    plan_floor_addition (feo_plan_common.py), игнорирует ПРИВЯЗАННЫЕ к
    FeoPlannedItem позиции (они «уже учтены own-планом своим путём»). Деньги
    проваливались в щель между двумя механизмами и молча гасились свободным
    планом СОСЕДНИХ позиций той же категории (planned_not_committed). Раз у
    позиции нет quantity, «набрано частично» неприменимо — ЛЮБАЯ привязанная
    committed-закупка (has_rows) целиком замещает её contribution, как если
    бы количество набралось полностью (та же трактовка, что и у quantity>0,
    просто без деления на штуки).

    Переиспользуется И leaf_items_committed_contribution ниже (агрегат по
    категории для compute_feo_plan_tree), И find_excess_culprit
    (feo_plan_excess.py, ПОСТРОЧНО — виновнику нужна сумма КОНКРЕТНОЙ позиции,
    не агрегат) — оба обязаны читать ОДНО и то же число на одну и ту же
    позицию, иначе Σ контрибьюторов разойдётся с планом дерева (см.
    test_find_excess_culprit_uses_same_plan_source_formula).

    `payroll_category_ids` (владелец, 22.10.2026, план humble-stirring-
    emerson.md, шаг 1) — set id категорий ФОТ (себя+предка, app.services.
    feo_payroll.payroll_category_ids), по статьям ФОТ замещение «заказ вместо
    плана» ОТКЛЮЧАЕТСЯ (feo_plan_common._order_substituted_plan(is_payroll=
    True) — ЕДИНАЯ точка, ПРАВИЛО №6). None (не передан явно) — резолвится
    здесь САМА по subsidy_id категорий (один легкий запрос) — безопасный
    дефолт для вызывающих мест, которые об этом правиле не знают, НЕ
    отдельная формула «это ФОТ»."""
    from app.services.feo_plan_tree import resolve_effective_item_types  # local: avoid import cycle

    result: dict[int, dict] = {}
    if not category_ids:
        return result

    if payroll_category_ids is None:
        from app.services.feo_payroll import payroll_category_ids as _resolve_payroll_ids
        _subsidy_rows = (await db.execute(
            select(FeoCategory.subsidy_id).where(FeoCategory.id.in_(category_ids)).distinct()
        )).scalars().all()
        payroll_category_ids = await _resolve_payroll_ids(db, _subsidy_rows)

    items_q = (
        select(
            FeoPlannedItem.id, FeoPlannedItem.feo_category_id, FeoPlannedItem.item_type,
            FeoPlannedItem.amount, FeoPlannedItem.quantity, FeoPlannedItem.payment_mode,
            FeoPlannedItem.name,
        )
        .where(FeoPlannedItem.feo_category_id.in_(category_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )
    rows = (await db.execute(items_q)).all()
    if not rows:
        return result

    # Законтрактованное количество/сумма нужны ТОЛЬКО позициям, способным
    # замещаться (все one_time — и с quantity, и без, см. исправление выше);
    # ежемесячные не запрашиваем — не гоняем лишний запрос по всем.
    _substitution_candidate_ids = [
        r.id for r in rows if (r.payment_mode or "one_time") == "one_time"
    ]
    committed_map = await committed_by_planned_item(db, _substitution_candidate_ids)
    eff_types = await resolve_effective_item_types(db, rows)

    for r in rows:
        raw_amount = float(r.amount or 0)
        contribution = raw_amount
        _is_payroll = r.feo_category_id in payroll_category_ids
        if (r.payment_mode or "one_time") == "one_time" and not _is_payroll:
            own_qty = float(r.quantity or 0)
            _committed = committed_map.get(r.id) or {
                "amount": 0.0, "quantity": 0.0, "has_rows": False,
            }
            if own_qty > 0:
                # ЕДИНАЯ точка (feo_plan_common._order_substituted_plan,
                # ПРАВИЛО №6) — та же формула, что и дерево/find_excess_culprit;
                # is_payroll уже отфильтрован веткой `and not _is_payroll` выше,
                # передавать её сюда вторично не нужно (оставлено False).
                contribution = _order_substituted_plan(
                    own_qty, _committed["amount"], _committed["quantity"], raw_amount,
                )
            elif _committed.get("has_rows"):
                # план 0/без quantity — нечем мерить «частично»: любая
                # привязанная committed-закупка целиком замещает contribution
                # (см. докстринг исправления выше).
                contribution = _committed["amount"]
        result[r.id] = {
            "amount": contribution,
            "feo_category_id": r.feo_category_id,
            "item_type_effective": eff_types.get(r.id),
            # Задача владельца (13.10.2026) — «перерасход/экономия по заказам
            # ПО ПОЗИЦИИ, не по сумме категории» (см. planned_item_order_diffs
            # ниже, ПРАВИЛО №6 — те же raw_amount/contribution, что уже
            # вычислены в этой же функции, вторая формула не пишется).
            "raw_amount": raw_amount,
            "name": r.name,
        }
    return result


async def planned_item_order_diffs(
    db: AsyncSession, category_ids: list[int], payroll_category_ids: Optional[set] = None,
) -> dict[int, dict]:
    """{feo_planned_item_id: {feo_category_id, name, amount (план из файла —
    r.amount), contribution (план после замены «заказ/договор вместо плана»),
    diff (contribution − amount)}} — задача владельца (13.10.2026): «перерасход/
    экономия по заказам считаются ПО ПОЗИЦИИ, а не по сумме категории» (повод —
    категория «Форменная одежда»: перерасход «Повседневного костюма» и
    экономия «Шапки» внутри ОДНОЙ категории гасили друг друга в сетевой сумме
    узла, +276 050,04 вместо +279 650,04 владельца).

    ЕДИНАЯ точка (ПРАВИЛО №6) — поверх planned_item_contributions (эта же
    функция выше, raw_amount/amount уже посчитаны ею, вторая формула
    замещения не пишется): diff>0 — позиция ПОДОРОЖАЛА (заказ/договор дороже
    плана позиции, целиком набравшей количество) — вклад в order_overspend
    узла категории; diff<0 — позиция ПОДЕШЕВЕЛА — вклад в order_economy (как
    положительная величина, -diff). Вызывающий код (compute_feo_plan_tree —
    батчево на ВСЕ категории субсидии, и app.services.feo_order_diff —
    построчно для окна «Перерасход/экономия по заказам») суммирует/фильтрует
    ЭТИ ЖЕ diff, тождество plan_items_raw + order_overspend − order_economy ==
    plan_manual держится потому, что для режима plan_source='planned_items'
    узла Σ contribution его собственных позиций ЕСТЬ его plan_manual (см.
    leaf_items_committed_contribution/_manual_plan_for в feo_plan_tree.py) —
    Σ(raw+diff) = raw_total + Σdiff = items_total + overspend − economy.

    `payroll_category_ids` — передаётся дальше в planned_item_contributions
    (ПРАВИЛО №6, шаг 1 плана humble-stirring-emerson.md): по статьям ФОТ
    contribution==amount всегда (замещение отключено), поэтому diff==0 —
    «перерасход/экономия по заказам» для ФОТ не формируется, что и нужно
    (ФОТ не даёт экономии ни по узлу, ни по позиции)."""
    contributions = await planned_item_contributions(db, category_ids, payroll_category_ids)
    return {
        item_id: {
            "feo_category_id": info["feo_category_id"],
            "name": info["name"],
            "amount": info["raw_amount"],
            "contribution": info["amount"],
            "diff": info["amount"] - info["raw_amount"],
        }
        for item_id, info in contributions.items()
    }


async def leaf_items_committed_contribution(
    db: AsyncSession, category_ids: list[int], payroll_category_ids: set | None = None,
    payroll_block_category_ids: set | None = None,
) -> tuple[dict[int, float], dict[int, dict]]:
    """Агрегат по категории поверх planned_item_contributions (см. её докстринг
    — ОДНА точка правила, эта функция только суммирует) — используется
    compute_feo_plan_tree (feo_plan_tree.py, узел 'planned_items'); режим
    'manual_sum' эту функцию НЕ использует — его items_total остаётся голой Σ
    amount, владелец явно просил его не трогать.

    Возвращает (contribution_by_category, contribution_by_category_and_kind):
    второе — ТА ЖЕ contribution, разложенная по kind_of_by_category_id(
    item_type_effective, cat_id, payroll_category_ids) — payroll-категория
    (своя или по предку, план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 2) перебивает item_type — нужна, чтобы инвариант «plan_goods+
    services+payroll+unspecified == display узла» (test_feo_plan_tree_type_split.py)
    остался в силе и после замещения savings по типу.

    `payroll_category_ids` — ВСЕ payroll-категории (себя+предок), на показ/
    классификацию "это вид payroll" влияет ВСЕГДА, независимо от кнопки
    «Закрыть ФОТ по статье». `payroll_block_category_ids` (план humble-
    stirring-emerson.md, 22.10.2026, шаг 1) — ПОДМНОЖЕСТВО без закрытых
    статей (FeoCategory.payroll_closed=False) — ИМЕННО оно отключает
    замещение «заказ вместо плана» в planned_item_contributions; по
    умолчанию (не передан) = payroll_category_ids целиком (обратная
    совместимость для вызовов, не знающих о кнопке)."""
    from app.services.item_type_split import empty_kind_dict, kind_of_by_category_id
    _payroll_ids = payroll_category_ids or set()
    _payroll_block_ids = payroll_block_category_ids if payroll_block_category_ids is not None else _payroll_ids

    contribution_by_category: dict[int, float] = {}
    contribution_by_kind: dict[int, dict] = {}
    # planned_item_contributions получает ТОЛЬКО _payroll_block_ids (ПРАВИЛО
    # №6) — закрытая статья ФОТ (payroll_closed=True) остаётся payroll-видом
    # ниже (kind_of_by_category_id читает полный _payroll_ids), но замещение
    # для неё снова разрешено (владелец нажал «Закрыть ФОТ по статье»).
    per_item = await planned_item_contributions(db, category_ids, _payroll_block_ids)
    for _item_id, info in per_item.items():
        cat_id = info["feo_category_id"]
        contribution_by_category[cat_id] = contribution_by_category.get(cat_id, 0.0) + info["amount"]
        _bucket = kind_of_by_category_id(info["item_type_effective"], cat_id, _payroll_ids)
        _kd = contribution_by_kind.setdefault(cat_id, empty_kind_dict())
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
        # 🟡 'unforeseen' («Непредвиденные расходы») схлопывается в тот же
        # бакет, что 'nice_to_have' — единое правило резерва (ПРАВИЛО №6,
        # app.services.plan_need_level.is_reserve_need_level), эта функция
        # не заводит собственного списка резервных значений.
        level = NEED_LEVEL_NICE_TO_HAVE if is_reserve_need_level(r.need_level) else NEED_LEVEL_LIKELY
        d = result.setdefault(r.feo_category_id, {NEED_LEVEL_LIKELY: 0.0, NEED_LEVEL_NICE_TO_HAVE: 0.0})
        d[level] += remainder
    return result


async def subsidy_committed_totals(
    db: AsyncSession, subsidy_ids: list[int], *, tree: Optional[dict] = None,
) -> dict[int, dict]:
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
    субсидии — отдельная точка, app.services.subsidy_budget, не дублируем).

    `tree` — опционально уже посчитанный compute_feo_plan_tree(db, subsidy_ids)
    (ускорение 06.10.2026, координатор: GET /dashboard/charts без флага тоже
    грузил subsidy_money_summary.subsidy_money_summary, которая строила
    дерево ПЯТЬ раз за один HTTP-запрос — здесь, в _plan_floor_added_by_subsidy,
    subsidy_type_totals, _calculate_feo_planned_tree_bulk и
    not_committed_raw_by_subsidy; 699 узлов × ~0,8с = больше половины 7,3с
    ответа). Без аргумента — поведение прежнее."""
    result: dict[int, dict] = {
        sid: {
            "committed": 0.0, "committed_goods": 0.0, "committed_services": 0.0,
            "committed_payroll": 0.0, "committed_unspecified": 0.0, "committed_missing_fact_items": 0,
            # plan_* — Σ по корневым узлам (та же величина, что subsidy_type_totals
            # отдаёт отдельным вызовом, app.services.type_totals) — ПЕРЕИСПОЛЬЗУЕМ
            # ОДИН проход по дереву, построенный этой функцией, вместо второго
            # вызова compute_feo_plan_tree ради planned_not_committed_by_kind
            # (dashboard_charts.py, контракт API п. A).
            "plan_goods": 0.0, "plan_services": 0.0, "plan_payroll": 0.0, "plan_unspecified": 0.0,
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    if tree is None:
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
        d["committed_payroll"] += node["committed_payroll"]
        d["committed_unspecified"] += node["committed_unspecified"]
        d["plan_goods"] += node["plan_goods"]
        d["plan_services"] += node["plan_services"]
        d["plan_payroll"] += node["plan_payroll"]
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
