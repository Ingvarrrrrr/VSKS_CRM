"""feo_plan.py — единый расчёт «расхода плана» по дереву ФЭО.

Вынесено из _calculate_feo_planned_tree_bulk (app/routers/subsidies.py) и
GET /api/feo-planned-items/residuals, чтобы формула не расходилась между
эндпоинтами KPI субсидий (subsidies.py) и справочником плановых позиций
(feo_categories.py /plan-positions).

⚠️ Изоляция субсидий (сессия 2026-08-05): позиция закупки учитывается ТОЛЬКО
если Purchase.subsidy_id совпадает с subsidy_id той FeoCategory, к которой
она фактически отнесена (COALESCE(PurchaseItem.feo_category_id,
Purchase.feo_category_id)). Раньше _calculate_feo_planned_tree_bulk проверял
лишь «Purchase.subsidy_id ∈ запрошенный батч subsidy_ids» и «категория ∈
категории запрошенного батча» — НЕЗАВИСИМО друг от друга. Из-за этого закупка
субсидии A с feo_category_id, указывающей в дерево субсидии B (в т.ч. когда
Purchase.subsidy_id вовсе NULL — не совпадает ни с чем), прибавлялась к
«Запланировано» субсидии B, если та просто присутствовала в том же батче.
Результат зависел от состава батча (на проде разъезжалось: батч по всем
субсидиям давал 6 201 370.73, одиночный вызов для subsidy_id=7 — 6 188 648.23,
расхождение 12 722.50 на 3 позициях). Каждая субсидия обязана считать только
свои вкладки — деньги не должны «перепрыгивать» между субсидиями.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_ as sqland, case, func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.purchase_summary import purchase_summaries_by_id

# «Заказано» и дальше — закупка уже реально размещена (в отличие от plan_schedule/
# work_in_progress/contracted, которые ещё черновик плана закупок). FACT_CONFIRMED_STATUSES —
# подтверждено закрывающим актом (delivered/paid), ORDERED_STATUSES — все три вместе.
FACT_CONFIRMED_STATUSES: set = {"delivered", "paid"}
ORDERED_STATUSES: set = {"ordered"} | FACT_CONFIRMED_STATUSES

# Задача владельца «план ≠ факт» (сессия 2026-08-06, план zany-fluttering-mountain.md,
# шаг «A»): факт (цена по итогам КП/торгов) учитывается уже с «Ведётся работа» — как
# только заполнены договорные позиции (ContractItem) или purchases.contract_price,
# ещё ДО подписания договора (превентивный контроль, см. assert_no_unapproved_excess).
# Раньше порог был только "ordered". НЕ путать с purchase_budget.FACT_STATUSES —
# тот управляет другим порогом (панель «план vs факт» показывает факт с «Заказано» —
# владелец описывал это ДО текущей задачи, см. purchase_budget.py комментарий) и его
# трогать не просили.
FACT_PRICED_STATUSES: set = {"work_in_progress", "contracted", "ordered"}
# Все статусы, где purchase_item_fact_amount способен вернуть не-None (используется
# fact_consumption_by_category / ordered_consumption_by_category).
FACT_ELIGIBLE_STATUSES: set = FACT_PRICED_STATUSES | FACT_CONFIRMED_STATUSES
_CENTS = Decimal("0.01")


def apply_wish_item_exclusion(stmt, exclude_wish_id: Optional[int]):
    """Исключает из `stmt` (обязан уже быть заджойнен PurchaseItem+Purchase) строки,
    принадлежащие заявке `exclude_wish_id` — «одна логическая позиция», то же
    прочтение, что и в app.services.plan_autoassign._fpi_reference_keys (задача
    владельца, план crystalline-soaring-heron.md, п.1): позиция закупки,
    порождённая заявкой (PurchaseItem.wish_item_id → WishItem этой заявки), и
    сама закупка заявки (Purchase.wish_id) — ОДНО и то же, обе стороны обязаны
    исключаться синхронно, иначе форма сконвертированной заявки видит расход,
    в который уже включена её собственная закупка, и задваивает его, добавляя
    свои позиции поверх (см. GET /consumers, докстринг про «Футболку Trisar» —
    тот же боевой случай, заявка №40, там дедуп уже был нужен в списке).

    Basic-условие `Purchase.wish_id == exclude_wish_id` покрывает подавляющее
    большинство случаев (закупка целиком порождена этой заявкой), но НЕ
    гарантирован структурой БД как единственный признак — PurchaseItem.wish_item_id
    прямая ссылка на WishItem, независимая от Purchase.wish_id закупки, в которой
    эта строка сейчас физически лежит (например, после разбиения позиции —
    purchases.py:2815 — часть переезжает в НОВУЮ строку той же закупки, но в
    будущем правки могли бы разъединить их дальше). Оба признака объединены
    через AND(NOT A, NOT B) — исключаем, если ЛЮБОЙ из них указывает на эту
    заявку.

    Commit не делает, мутаций не делает — только достраивает WHERE. Безопасно
    вызывать с exclude_wish_id=None (возвращает stmt как есть).
    """
    if exclude_wish_id is None:
        return stmt
    from app.models.wish_item import WishItem

    _wish_item_ids = select(WishItem.id).where(WishItem.wish_id == exclude_wish_id)
    return stmt.where(
        sqland(
            sqlor(Purchase.wish_id != exclude_wish_id, Purchase.wish_id.is_(None)),
            sqlor(PurchaseItem.wish_item_id.not_in(_wish_item_ids), PurchaseItem.wish_item_id.is_(None)),
        )
    )


def purchase_item_fact_amount(
    pi: PurchaseItem,
    purchase: Purchase,
    ratio: Decimal,
    items_count: int,
    contract_item_total: Optional[Decimal] = None,
) -> tuple[Optional[Decimal], bool]:
    """Единая формула «фактической суммы» позиции закупки.

    Источник правды — GET /api/feo-planned-items/comparison (карточка сравнения
    план/факт), вынесено сюда, чтобы её переиспользовал и расчёт плановой суммы
    (ordered_consumption_by_category / fact_consumption_by_category ниже) — суммы
    не должны расходиться между несколькими местами (сессия 2026-08-05/2026-08-06).

    Приоритет источников факта (задача владельца, сессия 2026-08-06):
      1. contract_item_total — ContractItem.total, ТОЧНО сопоставленный этой позиции
         через source_item_id (без пропорции — предпочтительнее, т.к. известна
         именно ЭТА строка договора, а не доля от суммы закупки). Передаётся
         вызывающим кодом (предзапрошен по PurchaseItem.id, см. ordered_consumption_by_category/
         fact_consumption_by_category) — сама функция БД не читает.
      2. final_total — сумма по закрывающим документам, если уже импортирована.
      3. пропорция от purchases.contract_price (work_in_progress/contracted/ordered)
         либо purchases.acceptance_doc_amount (delivered/paid) — по доле позиции
         в сумме всех позиций закупки (ratio).
      Ничего из этого нет → факта ещё нет, fact_amount=None (для delivered/paid —
      исключение, см. ниже, сохранён старый фолбэк на total_price, т.к. эта стадия
      подтверждена актом приёмки и факт обязан существовать).

    Порог статуса (задача владельца «план ≠ факт», 2026-08-06): опущен с «Заказано»
    до «Ведётся работа» (FACT_PRICED_STATUSES = work_in_progress/contracted/ordered) —
    как только заполнены договорные позиции или contract_price, это уже ФАКТ, ещё до
    подписания договора (превентивный контроль превышения). «Поставлено»/«Оплачено» —
    подтверждено актом приёмки (final_total, иначе доля acceptance_doc_amount, иначе
    total_price — старое поведение, не меняется).

    ratio — доля позиции в сумме ВСЕХ позиций закупки (для пропорционального
    распределения суммы уровня закупки между позициями, когда позиций
    несколько — см. вызывающий код). Возвращает (fact_amount, fact_allocated) —
    fact_allocated=True, если сумма получена делением суммы закупки
    пропорционально (а не берётся напрямую).
    """
    if purchase.status in FACT_PRICED_STATUSES:
        if contract_item_total is not None:
            return contract_item_total, False
        if pi.final_total is not None:
            return Decimal(str(pi.final_total)), False
        if purchase.contract_price is not None:
            contract_price = Decimal(str(purchase.contract_price))
            amt = (contract_price * ratio).quantize(_CENTS) if items_count > 1 else contract_price
            return amt, items_count > 1
        # Нет ни строки договора, ни contract_price — факта ещё нет (текущее
        # поведение plan_schedule: возвращаем None, а не total_price).
        return None, False
    if purchase.status in FACT_CONFIRMED_STATUSES:
        if contract_item_total is not None:
            return contract_item_total, False
        if pi.final_total is not None:
            return Decimal(str(pi.final_total)), False
        if purchase.acceptance_doc_amount is not None:
            doc_amount = Decimal(str(purchase.acceptance_doc_amount))
            amt = (doc_amount * ratio).quantize(_CENTS) if items_count > 1 else doc_amount
            return amt, items_count > 1
        return Decimal(str(pi.total_price or 0)), False
    # plan_schedule — это ещё ПЛАН, факта нет.
    return None, False


async def _contract_item_totals(db: AsyncSession, item_ids) -> dict:
    """{purchase_item_id: Σ ContractItem.total} по source_item_id — приоритет №1
    формулы факта (purchase_item_fact_amount). Сумма (не последняя строка), на
    случай если по одной позиции ТЗ создано несколько строк договора."""
    item_ids = list(item_ids)
    if not item_ids:
        return {}
    rows = (await db.execute(
        select(ContractItem.source_item_id, func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.source_item_id.in_(item_ids))
        .group_by(ContractItem.source_item_id)
    )).all()
    return {r[0]: Decimal(str(r[1])) for r in rows if r[1]}


async def _purchase_item_totals(db: AsyncSession, purchase_ids) -> dict:
    """{purchase_id: (items_count, Σ total_price)} — знаменатель для пропорционального
    распределения (ratio) суммы уровня закупки между её позициями."""
    purchase_ids = list(purchase_ids)
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(
            PurchaseItem.purchase_id,
            func.count(PurchaseItem.id),
            func.coalesce(func.sum(PurchaseItem.total_price), 0),
        )
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .group_by(PurchaseItem.purchase_id)
    )).all()
    return {r[0]: (r[1], Decimal(str(r[2] or 0))) for r in rows}


async def plan_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
    exclude_purchase_id: Optional[int] = None,
    exclude_wish_id: Optional[int] = None,
) -> dict[int, dict]:
    """{feo_category_id: {consumed, consumed_quantity, over, over_quantity}}

    Суммы позиций закупок в PLANNED_STATUSES, отнесённых к конечному элементу
    дерева ФЭО (COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id)),
    разложенные по признаку PurchaseItem.over_plan:
      over_plan=false → consumed / consumed_quantity (расходует план элемента)
      over_plan=true  → over / over_quantity (сверх плана, прибавляется поверх)

    Изоляция субсидий: строка учитывается только если Purchase.subsidy_id ==
    FeoCategory.subsidy_id самой категории, к которой она отнесена — закупка
    «чужой» субсидии (или вовсе без subsidy_id) в чужое дерево не попадает,
    даже если запрошено сразу несколько subsidy_ids одним батчем.

    exclude_planned_item_linked=True — исключить позиции с
    PurchaseItem.feo_planned_item_id IS NOT NULL (они уже расходуют план
    конкретной FeoPlannedItem — Ур.5 — и не должны задваиваться с планом
    самого листа; используется _calculate_feo_planned_tree_bulk).

    Остановленные закупки (владелец, 2026-08-13, «остановка заявки»):
    Purchase.stopped_at IS NOT NULL исключаются целиком — «остановленные
    позиции убираются из плана закупок и не считаются» (строки НЕ удаляются,
    только перестают участвовать в суммах).

    exclude_purchase_id/exclude_wish_id (сессия 2026-08-17, баг «план 54 318 ·
    выбрано 54 318 · не хватает 54 318»): исключают строки редактируемой сейчас
    сущности, чтобы её собственные позиции не считались «занявшими» план —
    иначе позиция сравнивается сама с собой: остаток 0, и UI повторно вычитает
    ту же сумму. Точно так же устроен planned_item_consumption в этом же файле.

    ⚠️ exclude_planned_item_linked=True больше НЕ доверяет голому «feo_planned_item_id
    IS NOT NULL» (сессия 2026-08-18, находка на проде — категория 3710 «Расходные
    материалы для проведения окружных полуфиналов», позиция «Огнетушитель
    углекислотный ОУ-2» 54 318 ₽): позиция считается «уже учтённой своей плановой
    строкой» и потому исключаемой из «в закупках» ТОЛЬКО если связанная FeoPlannedItem
    (а) существует, (б) is_active=True И (в) её feo_category_id совпадает с cat_col —
    категорией, к которой ЭТА строка фактически отнесена. Раньше проверялся только
    факт наличия feo_planned_item_id — если плановую позицию деактивировали
    (plan_autoassign.deactivate_if_orphaned) или она осталась в чужой категории
    (позиция закупки переехала, а плановая строка — нет), сумма пропадала из «в
    закупках»/«превышение» ОБЕИХ категорий одновременно: у «своей» плановой строки
    она не всплывала (плановая строка не активна/не в этой категории — не участвует
    в leaf_item_amt/planned_rows), а у категории, где реально лежит позиция закупки,
    её выкидывал именно этот фильтр. Ни рубль не должен исчезать из-за служебного
    флага/рассинхрона категорий — невалидная привязка теперь равнозначна её
    отсутствию для целей ЭТОЙ суммы (сама привязка feo_planned_item_id при этом не
    трогается, только формула consumed/over).
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle
    from app.models.feo_planned_item import FeoPlannedItem
    from sqlalchemy.orm import aliased

    # Задача владельца «план ≠ факт» (шаг B, сессия 2026-08-06): суммируем СНИМОК
    # плана (planned_total/planned_quantity), а не мутирующую total_price/quantity —
    # иначе правка цены ТЗ по итогам закупки (единственный оставшийся путь — заявка)
    # двигала бы план у НЕпривязанных к FeoPlannedItem позиций. Снимок заполняется
    # Шагом 1 (purchases.py/wishes.py) и заморожен с момента ухода из «План закупок»
    # (см. patch_purchase_item); COALESCE — на случай строк без снимка (создано до
    # миграции j1k2l3m4n5o6 и ещё не сохранялось повторно).
    amount_expr = func.coalesce(PurchaseItem.planned_total, PurchaseItem.total_price)
    qty_expr = func.coalesce(PurchaseItem.planned_quantity, PurchaseItem.quantity)
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    _fpi = aliased(FeoPlannedItem)
    stmt = (
        select(
            cat_col.label("cat_id"),
            PurchaseItem.over_plan,
            func.coalesce(func.sum(amount_expr), 0).label("amount"),
            func.coalesce(func.sum(qty_expr), 0).label("qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .outerjoin(_fpi, _fpi.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
        .group_by(cat_col, PurchaseItem.over_plan)
    )
    if exclude_planned_item_linked:
        # Исключаем (считаем «уже учтено своей плановой строкой») ТОЛЬКО строки с
        # валидной привязкой — см. предупреждение в docstring выше. Остаются (т.е.
        # НЕ исключаются, а значит попадают в consumed/over этой суммы): вовсе не
        # привязанные, привязанные на несуществующую/неактивную/чужой-категории
        # плановую строку — ровно то, что раньше тихо пропадало.
        stmt = stmt.where(
            sqlor(
                PurchaseItem.feo_planned_item_id.is_(None),
                _fpi.id.is_(None),
                _fpi.is_active.is_(False),
                _fpi.feo_category_id != cat_col,
            )
        )
    if exclude_purchase_id is not None:
        stmt = stmt.where(PurchaseItem.purchase_id != exclude_purchase_id)
    stmt = apply_wish_item_exclusion(stmt, exclude_wish_id)

    rows = (await db.execute(stmt)).all()
    for r in rows:
        d = result.setdefault(r.cat_id, {
            "consumed": 0.0, "consumed_quantity": 0.0,
            "over": 0.0, "over_quantity": 0.0,
        })
        if r.over_plan:
            d["over"] += float(r.amount)
            d["over_quantity"] += float(r.qty)
        else:
            d["consumed"] += float(r.amount)
            d["consumed_quantity"] += float(r.qty)
    return result


async def ordered_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_planned_item_linked: bool = False,
) -> dict[int, dict]:
    """{feo_category_id: {ordered, ordered_quantity}} — ФАКТИЧЕСКАЯ сумма и
    количество позиций закупок в статусах «Заказано»/«Поставлено»/«Оплачено»
    (ORDERED_STATUSES), отнесённых к конечному элементу дерева ФЭО (COALESCE
    (PurchaseItem.feo_category_id, Purchase.feo_category_id)), по правилам
    purchase_item_fact_amount (единая формула факта, см. её docstring).

    over_plan=true позиции исключены — их сумма прибавляется поверх плана
    безусловно (см. plan_consumption_by_category.over) и в замещение плана
    (ordered_qty ≥ planned_quantity) не участвует.

    Используется compute_feo_plan_tree — новая формула «плановой суммы»
    (сессия 2026-08-05, задача владельца): план = ordered_sum, если
    ordered_qty ≥ planned_quantity элемента, иначе plan_manual (пока не
    набрано всё плановое количество, бюджет зарезервирован целиком).

    exclude_planned_item_linked — см. plan_consumption_by_category, тот же
    смысл: позиции, привязанные к конкретной FeoPlannedItem (Ур.5), не
    задваивают план листа целиком. С 2026-08-18 — та же поправка, что и там:
    исключается только ВАЛИДНАЯ привязка (FeoPlannedItem существует, активна,
    её feo_category_id совпадает с cat_col этой строки); деактивированная или
    привязанная-к-чужой-категории плановая строка для целей ЭТОЙ суммы
    равнозначна отсутствию привязки — иначе сумма пропадает из «в закупках»
    молча (см. подробный докстринг exclude_planned_item_linked в
    plan_consumption_by_category).

    Изоляция субсидий — как в plan_consumption_by_category (Purchase.
    subsidy_id == FeoCategory.subsidy_id категории, к которой отнесена
    позиция).

    Остановленные закупки исключены (Purchase.stopped_at IS NOT NULL) — см.
    docstring plan_consumption_by_category.
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    from app.models.feo_planned_item import FeoPlannedItem
    from sqlalchemy.orm import aliased

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    _fpi = aliased(FeoPlannedItem)
    stmt = (
        select(PurchaseItem, Purchase, cat_col.label("cat_id"))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .outerjoin(_fpi, _fpi.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.status.in_(list(ORDERED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
    )
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

    # Пропорциональное распределение сумм уровня закупки (contract_price/
    # acceptance_doc_amount) между ВСЕМИ позициями закупки — как в /comparison,
    # считаем по всем позициям закупки, не только вошедшим в выборку.
    purchase_ids = {r.Purchase.id for r in rows}
    purchase_totals = await _purchase_item_totals(db, purchase_ids)
    # Приоритет №1 формулы факта (см. purchase_item_fact_amount) — ContractItem.total
    # по source_item_id, предзапрошено одним батчем на все позиции выборки.
    contract_totals = await _contract_item_totals(db, (r.PurchaseItem.id for r in rows))

    for r in rows:
        pi = r.PurchaseItem
        p = r.Purchase
        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)
        fact_amount, _allocated = purchase_item_fact_amount(
            pi, p, ratio, items_count, contract_item_total=contract_totals.get(pi.id)
        )
        if fact_amount is None:
            continue
        d = result.setdefault(r.cat_id, {"ordered": 0.0, "ordered_quantity": 0.0})
        d["ordered"] += float(fact_amount)
        d["ordered_quantity"] += float(pi.quantity or 0)
    return result


async def fact_consumption_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
) -> dict[int, dict]:
    """{feo_category_id: {fact, fact_quantity}} — задача владельца «план ≠ факт»
    (шаг A.2, сессия 2026-08-06): ФАКТ узла дерева ФЭО = Σ фактической суммы/
    количества позиций закупок в FACT_ELIGIBLE_STATUSES (work_in_progress и
    дальше — см. purchase_item_fact_amount), по правилам той же единой формулы.

    Отличие от ordered_consumption_by_category — ДВА:
      1. Порог статуса ниже (с «Ведётся работа», не с «Заказано») — превентивный
         контроль превышения должен видеть цену по итогам КП/торгов ДО подписания
         договора (см. assert_no_unapproved_excess).
      2. Позиции, привязанные к FeoPlannedItem (feo_planned_item_id IS NOT NULL),
         НЕ исключаются (в отличие от exclude_planned_item_linked=True, которым
         compute_feo_plan_tree вызывает ordered/plan_consumption) — иначе именно
         привязанные позиции (обычный сценарий: заявка → план → закупка) никогда
         не показали бы факт, хотя это и есть основной случай владельца (Great
         Wall POER, эталонный сценарий).

    over_plan=true позиции исключены — они не участвуют в сравнении факт/план
    (их расход уже безусловно учтён отдельно в excess_over_feo/over, см.
    plan_consumption_by_category.over и compute_feo_plan_tree).

    Изоляция субсидий — как в plan_consumption_by_category/ordered_consumption_by_category.

    Остановленные закупки исключены (Purchase.stopped_at IS NOT NULL) — см.
    docstring plan_consumption_by_category.
    """
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(PurchaseItem, Purchase, cat_col.label("cat_id"))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(Purchase.status.in_(list(FACT_ELIGIBLE_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
    )

    rows = (await db.execute(stmt)).all()
    if not rows:
        return result

    purchase_ids = {r.Purchase.id for r in rows}
    purchase_totals = await _purchase_item_totals(db, purchase_ids)
    contract_totals = await _contract_item_totals(db, (r.PurchaseItem.id for r in rows))

    for r in rows:
        pi = r.PurchaseItem
        p = r.Purchase
        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)
        fact_amount, _allocated = purchase_item_fact_amount(
            pi, p, ratio, items_count, contract_item_total=contract_totals.get(pi.id)
        )
        if fact_amount is None:
            continue
        d = result.setdefault(r.cat_id, {"fact": 0.0, "fact_quantity": 0.0})
        d["fact"] += float(fact_amount)
        d["fact_quantity"] += float(pi.quantity or 0)
    return result


async def planned_item_consumption(
    db: AsyncSession,
    item_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
    exclude_wish_id: Optional[int] = None,
) -> dict[int, dict]:
    """{feo_planned_item_id: {used, used_qty, wish_used, linked_purchase_ids}}

    Расход конкретной плановой позиции (FeoPlannedItem, Ур.5) через
    PurchaseItem.feo_planned_item_id. Общая часть GET /api/feo-planned-items/residuals
    и GET /api/feo-categories/plan-positions — чтобы оба эндпоинта считали
    расход плановой позиции одинаково и не расходились.

    used/used_qty — SUM по PurchaseItem в PLANNED_STATUSES, привязанным к
    item_ids через feo_planned_item_id.
    linked_purchase_ids — уникальные id закупок, чьи позиции привязаны к
    плановой позиции (тоже только PLANNED_STATUSES).

    Остановленные закупки (Purchase.stopped_at IS NOT NULL) исключены —
    «остановленные позиции убираются из плана закупок и не считаются»
    (владелец, 2026-08-13).

    Решение владельца (2026-08-17): незаконвертированные заявки (Wish) НЕ
    резервируют план — заявок может лежать сколько угодно (хоть на миллион
    при плане 500 тыс.), из плана вычитается ТОЛЬКО то, что уже попало в план
    закупок (позиции закупок, PurchaseItem). При работе с конкретной заявкой
    показывается только она сама, а не сумма всех заявок. Ключ "wish_used"
    сохранён в возвращаемом словаре и всегда равен 0.0 — исключительно ради
    обратной совместимости вызывающего кода, который его читает.
    """
    result: dict[int, dict] = {
        iid: {"used": 0.0, "used_qty": 0.0, "wish_used": 0.0, "linked_purchase_ids": []}
        for iid in item_ids
    }
    if not item_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle

    used_q = (
        select(
            PurchaseItem.feo_planned_item_id,
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("used_qty"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
    )
    if exclude_purchase_id is not None:
        used_q = used_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    used_q = apply_wish_item_exclusion(used_q, exclude_wish_id)
    used_q = used_q.group_by(PurchaseItem.feo_planned_item_id)
    for r in (await db.execute(used_q)).all():
        result[r.feo_planned_item_id]["used"] = float(r.used)
        result[r.feo_planned_item_id]["used_qty"] = float(r.used_qty)

    links_q = (
        select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
    )
    if exclude_purchase_id is not None:
        links_q = links_q.where(PurchaseItem.purchase_id != exclude_purchase_id)
    links_q = apply_wish_item_exclusion(links_q, exclude_wish_id)
    for lr in (await db.execute(links_q)).all():
        lst = result[lr.feo_planned_item_id]["linked_purchase_ids"]
        if lr.purchase_id not in lst:
            lst.append(lr.purchase_id)

    return result


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
      plan_manual — «сколько сами запланировали»:
        лист:  planned_quantity × planned_amount (planned_amount — цена за
               единицу); если произведение = 0, а активные FeoPlannedItem (Ур.5)
               есть — fallback на Σ FeoPlannedItem.amount (план введён по
               позициям, а не по листу целиком). Количество (qty), участвующее
               в этой формуле и далее в plan/qty_plan, — тоже с fallback'ом:
               planned_quantity листа, а если оно не задано (0) — Σ quantity
               тех же активных FeoPlannedItem (симметрично fallback'у по сумме,
               иначе plan_manual посчитается по позициям, а qty_plan всё равно
               уйдёт в 0 и замещение «заказ вместо плана» не сработает);
        группа: Σ plan_manual прямых детей ПЛЮС собственные активные FeoPlannedItem
                узла (Ур.5), заведённые прямо на направлении, а не на листе —
                задача владельца «направление со временем может наполниться,
                соответственно должно считаться и оно» (сессия 2026-08-12,
                см. ФОРМУЛА v3 ниже). Собственные ПОЛЯ группы (planned_quantity×
                planned_amount, старый формат) по-прежнему НЕ учитываются —
                так же, как feoPlannedTotalFor во фронте, иначе формулы
                разойдутся; на этом поле уже была боевая поломка (категория
                «Микроавтобус» после пропажи подкатегории показала цену
                10 130 000 за штуку).
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
      категории, а РУЧНОЙ план: либо planned_quantity×planned_amount самой
      FeoCategory (одно число, без разбивки — плановые позиции тут ни при чём),
      либо, если эти поля не заданы, Σ amount активных FeoPlannedItem (Ур.5,
      «плановые позиции» — как раз панель «Добавить плановую», из примера
      владельца «Great Wall POER · план 2 шт × 4 000 000»). Плюс `over` —
      Σ сумм PurchaseItem с over_plan=true (сознательно сверх плана),
      прибавляется БЕЗУСЛОВНО поверх — вот это уже реальные позиции закупок.

    Поэтому виновник ищется как ПЕРВЫЙ элемент, на котором нарастающая сумма по
    ДВУМ источникам (в порядке их вклада в формулу — сначала «план», потом
    «сверх плана») впервые пересекла budget:
      1) активные FeoPlannedItem узла/его листьев-потомков, по возрастанию
         `created_at` (у FeoPlannedItem ЕСТЬ created_at — реальное время
         появления плановой позиции, самый честный источник «времени попадания
         в план», который вообще есть в модели данных), tie-break — id.
         Каждая плановая позиция резолвится к закупке, которая на неё
         ссылается (PurchaseItem.feo_planned_item_id) — берётся САМАЯ РАННЯЯ
         (min Purchase.id), т.к. обычно именно она породила эту плановую
         позицию автозаведением (_auto_assign_planned_items, wishes.py); если
         ни одна закупка ещё не привязана — виновник этой строки безымянный
         (purchase_id=None, названа сама плановая позиция).
      2) позиции закупок (PurchaseItem) с over_plan=true в PLANNED_STATUSES,
         по возрастанию Purchase.id (у Purchase НЕТ created_at — id это PK
         IDENTITY/serial, монотонно растёт при INSERT, надёжный прокси
         времени), tie-break — id позиции.
    Если категория имеет СОБСТВЕННЫЙ planned_quantity×planned_amount (не 0) —
    Ур.5-фолбэк формулой не используется вовсе (см. compute_feo_plan_tree), и
    разбить это ОДНО число на закупки нельзя: в качестве первого «контрибьютора»
    подставляется синтетическая запись «плановое значение категории» без
    purchase_id — так превышение всё равно объясняется числом, даже если
    конкретной закупки-виновника формально не существует.

    Если превышение набралось несколькими контрибьюторами — виновником назван
    именно тот, кто пересёк границу budget (не последний/крупнейший).

    Возвращает None, если budget не задан или контрибьюторов не нашлось (не
    должно случаться при excess_amount>0, но не падаем — просто нет данных для
    подсветки виновника).
    """
    if budget is None:
        return None
    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        return None

    all_cats = (await db.execute(
        select(
            FeoCategory.id, FeoCategory.parent_id,
            FeoCategory.planned_quantity, FeoCategory.planned_amount,
        ).where(FeoCategory.subsidy_id == cat.subsidy_id)
    )).all()
    by_id = {r.id: r for r in all_cats}
    children_map: dict[int, list[int]] = {}
    for r in all_cats:
        if r.parent_id is not None:
            children_map.setdefault(r.parent_id, []).append(r.id)
    leaf_ids: list[int] = []
    stack = [feo_category_id]
    while stack:
        cur = stack.pop()
        kids = children_map.get(cur, [])
        if kids:
            stack.extend(kids)
        else:
            leaf_ids.append(cur)
    if not leaf_ids:
        return None

    from app.models.feo_planned_item import FeoPlannedItem
    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle

    # ── Источник №1: «план» — собственные qty×amount листа, ИЛИ (fallback)
    # Σ активных FeoPlannedItem ────────────────────────────────────────────
    contributors: list[dict] = []

    fallback_leaf_ids = [
        lid for lid in leaf_ids
        if not (by_id[lid].planned_quantity and by_id[lid].planned_amount
                and float(by_id[lid].planned_quantity) > 0 and float(by_id[lid].planned_amount) > 0)
    ]
    direct_leaf_ids = [lid for lid in leaf_ids if lid not in fallback_leaf_ids]

    for lid in direct_leaf_ids:
        r = by_id[lid]
        amt = Decimal(str(r.planned_quantity)) * Decimal(str(r.planned_amount))
        if amt > 0:
            cat_row = await db.get(FeoCategory, lid)
            contributors.append({
                "amount": amt, "purchase_id": None, "purchase_number": None,
                "item_name": f"плановое значение категории «{cat_row.name if cat_row else lid}»",
                "created_at": None, "sort_key": (0, lid),
            })

    if fallback_leaf_ids:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem.id, FeoPlannedItem.name, FeoPlannedItem.amount, FeoPlannedItem.created_at)
            .where(FeoPlannedItem.feo_category_id.in_(fallback_leaf_ids))
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

    # ── Источник №2: «сверх плана» — PurchaseItem.over_plan=true, прибавляется
    # безусловно ПОВЕРХ плана (см. compute_feo_plan_tree.over) ─────────────
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    amount_expr = func.coalesce(PurchaseItem.planned_total, PurchaseItem.total_price)
    over_rows = (await db.execute(
        select(
            PurchaseItem.id.label("item_id"), PurchaseItem.item_name.label("item_name"),
            amount_expr.label("amount"), Purchase.id.label("purchase_id"),
            Purchase.purchase_number.label("purchase_number"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(cat_col.in_(leaf_ids))
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
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
            }
    return None


async def assert_no_unapproved_excess(
    db: AsyncSession, feo_category_id: int, adding_amount: Decimal = Decimal("0")
) -> None:
    """Бросает HTTPException 409, если узел ФЭО feo_category_id или любой его
    ПРЕДОК имеет несогласованное превышение — ЛИБО плана над финансированием ФЭО
    (excess_over_feo/excess_amount > 0 и НЕ excess_approved), ЛИБО факта над
    планом (excess_fact_over_plan > 0 и НЕ excess_fact_approved — задача
    владельца «план ≠ факт», шаг C, сессия 2026-08-06). См. compute_feo_plan_tree
    и app.models.plan_excess_approval.

    Требование владельца (2026-08-05): «Если где-то превысил план ФЭО, значит
    где-то надо снимать — должны быть заблокированы действия, пока план закупок
    не загонять обратно в размеры ФЭО». Требование владельца (2026-08-06,
    превентивность): контроль факт-над-планом включается уже на «Ведётся
    работа» (см. FACT_PRICED_STATUSES) — переход закупки в «Договор» и
    увеличение договорных позиций блокируются ДО подписания, пока превышение
    итога закупки над планом не согласовано.

    Вызывается ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ план (создание закупки,
    увеличение суммы/смена категории ФЭО при PUT, согласование заявки →
    создание закупок) и ПЕРЕД действиями, УВЕЛИЧИВАЮЩИМИ факт сверх плана
    (переход статуса закупки work_in_progress → contracted, сохранение/
    изменение договорных позиций) — см. вызывающий код в app.routers.purchases /
    app.routers.wishes / app.routers.contract_items.

    НЕ вызывается для переходов статусов вперёд у уже существующих закупок
    (ordered → delivered → paid), уменьшений сумм, удаления позиций, отката
    заявок — это путь ВОЗВРАТА в рамки плана, его блокировать нельзя.

    adding_amount — необязательная сумма добавляемого действия. Для ДВУХ
    существующих видов превышения (план>ФЭО узла, факт>план узла) используется
    ТОЛЬКО для текста отказа (сколько ещё пытаются добавить сверху уже
    несогласованного превышения); на решение блокировать/не блокировать не
    влияет — блокирует сам факт СУЩЕСТВУЮЩЕГО несогласованного превышения на
    узле или предке (см. сценарий владельца: первая закупка, создавшая
    превышение, не блокируется — блокируется каждая СЛЕДУЮЩАЯ, пока
    превышение не согласовано или не убрано). ИСКЛЮЧЕНИЕ — жёсткий потолок
    субсидии (см. ниже, задача владельца п.3): там adding_amount ДЕЙСТВИТЕЛЬНО
    участвует в решении блокировать, т.к. это правило не про «уже случившееся»,
    а про «это конкретное действие не должно случиться».

    Задача владельца п.3 (2026-08-12, «жёсткий потолок»): «общий план по всем
    подкатегориям не должен превышать общую сумму ФЭО — критично, ни при каких
    обстоятельствах». Проверяется ПЕРВЫМ, до узловых проверок ниже, и НЕ
    участвует в согласовании через PlanExcessApproval вообще — ни admin_override,
    ни обход для OWNER_ROLES: если план (с учётом adding_amount) выходит за
    потолок финансирования по ФЭО субсидии (calculate_budget_from_categories,
    тот же источник, что и feo_budget_total у субсидии, см. app.routers.
    subsidies) — действие безусловно отклоняется.
    """
    from fastapi import HTTPException

    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        return

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    if not tree or feo_category_id not in tree:
        return

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
            # находим виновника (см. find_excess_culprit) и называем его в отказе,
            # а не только абстрактную сумму превышения.
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
                culprit_txt = (
                    f" Виновник — {who}: до неё по этой категории было выбрано "
                    f"{culprit['amount_before']:,.2f} ₽, позиция «{culprit['item_name']}» "
                    f"({culprit['amount_at_crossing']:,.2f} ₽) вывела сумму за границу ФЭО "
                    f"{budget_d:,.2f} ₽."
                )
                culprit_fields.update({
                    "culprit_purchase_id": culprit["purchase_id"],
                    "culprit_purchase_number": culprit["purchase_number"],
                    "culprit_item_name": culprit["item_name"],
                    "culprit_amount_before": culprit["amount_before"],
                })
            raise HTTPException(
                409,
                {
                    "code": "PLAN_EXCESS_OVER_FEO",
                    "message": (
                        f"Превышение плана по категории ФЭО «{name}»: финансирование по ФЭО "
                        f"{budget_d:,.2f} ₽, текущая плановая сумма {full_plan_d:,.2f} ₽, превышение "
                        f"{excess_d:,.2f} ₽.{culprit_txt}{extra} Снимите позиции на {excess_d:,.2f} ₽ "
                        f"или согласуйте превышение (запрос согласования превышения плана ФЭО по "
                        f"категории «{name}»)."
                    ),
                    "feo_category_id": cid,
                    "excess_amount": float(excess_d),
                    "budget": float(budget_d),
                    "plan_amount": float(full_plan_d),
                    **culprit_fields,
                },
            )

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


def _fmt_qty(d: Decimal) -> str:
    """Количество без хвостовых нулей (2, не 2.0000; 2.5, не 2.5000)."""
    s = f"{d:,.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _fmt_money(d: Decimal) -> str:
    return f"{d:,.2f} ₽"


async def assert_tz_not_over_plan(
    db: AsyncSession,
    *,
    feo_planned_item_id: Optional[int],
    feo_category_id: Optional[int],
    quantity,
    unit_price,
    total_price,
    item_name: str = "",
    sibling_quantity=0,
    sibling_total=0,
) -> None:
    """Бросает HTTPException 409, если ТЗ позиции (кол-во / цена за единицу / сумма)
    превышает привязанную плановую позицию — владелец (2026-08-07, план
    zany-fluttering-mountain.md, шаг 5): «ТЗ может быть НИЖЕ плана, но НЕ ВЫШЕ —
    ни по количеству, ни по цене за единицу, ни по сумме».

    Источник плана — РОВНО один из двух (не смешиваются между собой):
      1. feo_planned_item_id задан → FeoPlannedItem.quantity / .amount (amount —
         ВСЯ плановая сумма позиции, не цена за единицу; цена за единицу =
         amount / quantity, только если quantity > 0).
      2. Иначе, если задан feo_category_id → FeoCategory.planned_quantity /
         .planned_amount листа (planned_amount там УЖЕ цена за единицу, см.
         модель); плановая сумма = planned_quantity × planned_amount.
         Фолбэк (план переехал в записи внутри категории): если ОБА поля
         категории пусты (NULL) — берём активные FeoPlannedItem этой категории:
         plan_total = Σ amount (только положительные суммы), plan_qty =
         Σ quantity (если сумма количеств > 0), plan_unit_price = plan_total /
         plan_qty при plan_qty > 0. Без этого фолбэка гейт «ТЗ не дороже и не
         больше плана» тихо отключается для мигрированных категорий-листьев —
         см. compute_feo_plan_tree (тот же приём, та же семантика).

    Количество проверяется ОТДЕЛЬНО и обязательно от суммы — сценарий владельца
    «план 2 самолёта за 30 млн» не разрешает купить 3 штуки даже за те же 30 млн
    (3 шт по более низкой цене может пройти по сумме, но не по количеству).

    Никакого допуска: сравнение строго `>` в Decimal, без эпсилона («баланс
    копейка в копейку» — владелец). Входные quantity/unit_price/total_price
    приводятся к Decimal(str(...)) на входе (вызывающий код может передать
    float/None).

    Нет плановых данных (ни по FeoPlannedItem, ни по FeoCategory) → no-op —
    позиции без плана этим правилом не ограничиваются.

    Сообщение 409 перечисляет ВСЕ нарушенные величины разом (позиция может
    одновременно превышать и количество, и сумму — напр. «3 шт × 4 000 000»
    при плане «2 шт × 4 000 000»), с планом/фактом/разницей по каждой и общей
    подсказкой «что делать».

    sibling_quantity/sibling_total (владелец, задача от 2026-08-17, прод-инцидент
    закупка РЕЕ-2026-00887, +5 761 ₽): эта функция изначально проверяла КАЖДУЮ
    строку ТЗ по отдельности против ПОЛНОГО плана её плановой позиции — если в
    одной операции ДВЕ строки ссылались на ОДНУ и ту же плановую позицию, каждая
    проходила поодиночке, а суммарно план превышался. Параметры добавляют к
    проверяемым количеству и сумме остальные строки ТОЙ ЖЕ операции (закупки/
    заявки), уже привязанные к той же плановой позиции — накопление в пределах
    ОДНОЙ операции, межзакупочный расход сознательно НЕ учитывается (на проде
    таких случаев не было, а проверка через операции несёт риск ложных отказов).
    К цене за единицу (unit_price/price_d) siblings НЕ прибавляются — цена за
    единицу не накапливается, это свойство конкретной строки, а не объёма.
    Дефолт 0 — поведение без siblings не меняется. См. также обёртку
    assert_tz_batch_not_over_plan ниже, которая считает siblings по списку строк.
    """
    from fastapi import HTTPException
    from app.models.feo_planned_item import FeoPlannedItem

    planned_qty: Optional[Decimal] = None
    planned_unit_price: Optional[Decimal] = None
    planned_total: Optional[Decimal] = None

    if feo_planned_item_id:
        fpi = await db.get(FeoPlannedItem, feo_planned_item_id)
        if fpi is not None:
            if fpi.quantity is not None:
                planned_qty = Decimal(str(fpi.quantity))
            if fpi.amount is not None:
                planned_total = Decimal(str(fpi.amount))
                if planned_qty is not None and planned_qty > 0:
                    planned_unit_price = planned_total / planned_qty
    elif feo_category_id:
        cat = await db.get(FeoCategory, feo_category_id)
        if cat is not None:
            if cat.planned_quantity is not None:
                planned_qty = Decimal(str(cat.planned_quantity))
            if cat.planned_amount is not None:
                planned_unit_price = Decimal(str(cat.planned_amount))
            if planned_qty is not None and planned_unit_price is not None:
                planned_total = planned_qty * planned_unit_price
            elif planned_qty is None and planned_unit_price is None:
                # План переехал в записи внутри категории (FeoPlannedItem) — у
                # мигрированных категорий-листьев planned_quantity/planned_amount
                # самой категории — NULL, план лежит в активных FeoPlannedItem.
                # Без этого фолбэка planned_qty/planned_unit_price/planned_total
                # остаются None, ниже срабатывает no-op, и позиция закупки,
                # привязанная к КАТЕГОРИИ напрямую (без конкретной плановой
                # позиции), перестаёт ограничиваться вообще — 409 не сработает
                # никогда. Один запрос с агрегатами, без загрузки всех строк —
                # см. образец в compute_feo_plan_tree (feo_plan.py).
                fpi_agg_q = (
                    select(
                        func.coalesce(
                            func.sum(case((FeoPlannedItem.amount > 0, FeoPlannedItem.amount), else_=0)),
                            0,
                        ).label("amt"),
                        func.coalesce(func.sum(FeoPlannedItem.quantity), 0).label("qty"),
                    )
                    .where(FeoPlannedItem.feo_category_id == feo_category_id)
                    .where(FeoPlannedItem.is_active.is_(True))
                )
                agg_row = (await db.execute(fpi_agg_q)).one()
                fb_amt = Decimal(str(agg_row.amt or 0))
                fb_qty = Decimal(str(agg_row.qty or 0))
                if fb_amt > 0:
                    planned_total = fb_amt
                if fb_qty > 0:
                    planned_qty = fb_qty
                if planned_qty is not None and planned_qty > 0 and planned_total is not None:
                    planned_unit_price = planned_total / planned_qty

    if planned_qty is None and planned_unit_price is None and planned_total is None:
        return  # плановые данные не заданы — правило не применяется

    own_qty_d = Decimal(str(quantity)) if quantity is not None else Decimal("0")
    price_d = Decimal(str(unit_price)) if unit_price is not None else Decimal("0")
    own_total_d = Decimal(str(total_price)) if total_price is not None else (own_qty_d * price_d)

    sib_qty_d = Decimal(str(sibling_quantity)) if sibling_quantity is not None else Decimal("0")
    sib_total_d = Decimal(str(sibling_total)) if sibling_total is not None else Decimal("0")

    qty_d = own_qty_d + sib_qty_d
    total_d = own_total_d + sib_total_d
    has_siblings = sib_qty_d != 0 or sib_total_d != 0

    violations: list[str] = []
    if planned_qty is not None and qty_d > planned_qty:
        diff = qty_d - planned_qty
        violations.append(
            f"количество: план {_fmt_qty(planned_qty)}, в ТЗ {_fmt_qty(qty_d)} "
            f"(больше на {_fmt_qty(diff)})"
        )
    if planned_unit_price is not None and price_d > planned_unit_price:
        diff = price_d - planned_unit_price
        violations.append(
            f"цена за единицу: план {_fmt_money(planned_unit_price)}, в ТЗ {_fmt_money(price_d)} "
            f"(больше на {_fmt_money(diff)})"
        )
    if planned_total is not None and total_d > planned_total:
        diff = total_d - planned_total
        violations.append(
            f"сумма: план {_fmt_money(planned_total)}, в ТЗ {_fmt_money(total_d)} "
            f"(больше на {_fmt_money(diff)})"
        )

    if not violations:
        return

    name = item_name.strip() if item_name else "позиция"
    siblings_note = (
        " (учтены все строки этой операции, привязанные к той же плановой позиции)"
        if has_siblings else ""
    )
    raise HTTPException(
        409,
        f"ТЗ позиции «{name}»{siblings_note} превышает план: " + "; ".join(violations) + ". "
        "Измените плановую позицию в Плане закупок (потребует согласования, если "
        "выходит за ФЭО) или уменьшите ТЗ."
    )


async def assert_tz_batch_not_over_plan(
    db: AsyncSession,
    rows: list,
    *,
    fallback_category_id: Optional[int] = None,
) -> None:
    """Гейт «ТЗ не выше плана» (assert_tz_not_over_plan) для СПИСКА строк одной
    операции (закупка/заявка) целиком — владелец, 2026-08-17, прод-инцидент
    закупка РЕЕ-2026-00887 (+5 761 ₽): assert_tz_not_over_plan проверяла КАЖДУЮ
    строку по отдельности против ПОЛНОГО плана её плановой позиции — если в
    одной операции ДВЕ строки ссылались на ОДНУ и ту же плановую позицию, каждая
    поодиночке проходила (например «план 21 шт / 15 750 ₽»: строка А = 21 шт /
    15 750 ₽ — ровно план, строка Б = 4 шт / 3 000 ₽ — тоже ≤ плана), а вместе
    план превышали (25 шт / 18 750 ₽ против 21 шт / 15 750 ₽). Эта обёртка
    группирует строки по feo_planned_item_id и проверяет план ОДИН раз на
    группу, передавая сумму количества/суммы группы.

    Граница области (важно, НЕ расширять): накопление применяется ТОЛЬКО к
    строкам с заполненным feo_planned_item_id. Строки с feo_planned_item_id
    пустым проверяются против плана КАТЕГОРИИ по отдельности, как раньше —
    накопление там дублировало бы assert_no_unapproved_excess (у которого есть
    свой путь согласования). Межзакупочный расход (та же плановая позиция в
    ДРУГОЙ операции) сознательно НЕ учитывается — на проде таких случаев ноль,
    а проверка через операции несёт риск ложных отказов.

    Строки с over_plan=True пропускаются полностью — не проверяются и не
    учитываются в сумме группы (та же семантика, что и в поштучных вызовах
    во всех местах, откуда раньше вызывалась assert_tz_not_over_plan напрямую).

    unit_price группы = МАКСИМАЛЬНАЯ цена за единицу среди строк группы —
    правило «цена за единицу не выше плановой» обязано сработать на самой
    дорогой строке; для группы из одной строки это её собственная цена, т.е.
    поведение идентично прежнему поштучному вызову.

    Порядок обхода — сначала строки без плановой позиции (в порядке появления
    в rows), затем группы (в порядке первого появления feo_planned_item_id в
    rows) — детерминированный при одинаковом входе, чтобы сообщение об ошибке
    не «прыгало» между одинаковыми запросами. Полное совпадение с исходным
    построчным порядком невозможно в принципе: сумму группы нельзя посчитать,
    не увидев все её строки, поэтому группы проверяются отдельным проходом
    после сборки.

    Разложение суммы группы на «свою»/«братьев» (2026-08-17, фикс текста
    ошибки): ДО этого вызов передавал в assert_tz_not_over_plan уже готовую
    сумму группы целиком через quantity/total_price, БЕЗ sibling_quantity/
    sibling_total — из-за этого внутри has_siblings всегда получался False
    (siblings были нулевыми), и пояснение «учтены все строки...» в тексте 409
    никогда не появлялось, хотя число уже было накоплено по группе — владелец
    видел «в ТЗ 26 шт» и не понимал, откуда взялась цифра, если в его строке
    было только 21. Теперь количество/сумма ПЕРВОЙ строки группы передаются
    как «свои» (quantity/total_price), а Σ остальных строк группы — как
    sibling_quantity/sibling_total. Итоговые проверяемые величины (qty_d =
    own + sib, total_d = own + sib внутри assert_tz_not_over_plan) численно
    ИДЕНТИЧНЫ прежним — меняется только то, что has_siblings становится True
    для групп из 2+ строк и в сообщение попадает пояснение. Для группы из
    ОДНОЙ строки siblings = 0 — поведение полностью совпадает с прежним.
    """
    groups: dict[int, list] = {}
    individuals: list = []
    for row in rows:
        if getattr(row, "over_plan", False):
            continue
        fpi_id = getattr(row, "feo_planned_item_id", None)
        if fpi_id:
            groups.setdefault(fpi_id, []).append(row)
        else:
            individuals.append(row)

    for row in individuals:
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=None,
            feo_category_id=getattr(row, "feo_category_id", None) or fallback_category_id,
            quantity=row.quantity,
            unit_price=row.unit_price,
            total_price=row.total_price,
            item_name=row.item_name,
        )

    for fpi_id, group_rows in groups.items():
        first = group_rows[0]
        siblings = group_rows[1:]

        max_price = Decimal("0")
        for r in group_rows:
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            if r_price > max_price:
                max_price = r_price

        own_qty = Decimal(str(first.quantity)) if first.quantity is not None else Decimal("0")
        own_price = Decimal(str(first.unit_price)) if first.unit_price is not None else Decimal("0")
        own_total = Decimal(str(first.total_price)) if first.total_price is not None else (own_qty * own_price)

        sib_qty = Decimal("0")
        sib_total = Decimal("0")
        for r in siblings:
            r_qty = Decimal(str(r.quantity)) if r.quantity is not None else Decimal("0")
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            r_total = Decimal(str(r.total_price)) if r.total_price is not None else (r_qty * r_price)
            sib_qty += r_qty
            sib_total += r_total

        name = (first.item_name or "").strip() or "позиция"
        if len(group_rows) > 1:
            name = f"{name} и ещё {len(group_rows) - 1} поз."
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=fpi_id,
            feo_category_id=(getattr(first, "feo_category_id", None) or fallback_category_id),
            quantity=own_qty,
            unit_price=max_price,
            total_price=own_total,
            item_name=name,
            sibling_quantity=sib_qty,
            sibling_total=sib_total,
        )


async def feo_plan_subsidy_totals(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Σ display корневых узлов (parent_id IS NULL) дерева ФЭО per субсидия —
    единственное число KPI «Запланировано» (used by _calculate_feo_planned_tree_bulk
    в subsidies.py и total_plan_combined в _create_plan_graph_version в
    purchases.py). Тонкая обёртка над compute_feo_plan_tree — см. её docstring
    за формулой.
    """
    result = {sid: 0.0 for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    tree = await compute_feo_plan_tree(db, subsidy_ids)
    for node in tree.values():
        if node["parent_id"] is None:
            result[node["subsidy_id"]] = result.get(node["subsidy_id"], 0.0) + node["display"]
    return result


def build_category_path(cat, cat_by_id: dict) -> str:
    """Путь категории «Направление › Подкатегория › Лист» (сверху вниз).

    cat_by_id — {id: FeoCategory} для всех категорий той же субсидии
    (нужен для подъёма по parent_id без доп. запросов к БД).
    """
    if cat is None:
        return ""
    names = [cat.name]
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        names.append(cur.name)
    return " › ".join(reversed(names))


def build_ancestor_ids(cat, cat_by_id: dict) -> list:
    """id всех предков категории, от корня до непосредственного родителя (сверху вниз).

    Не включает саму `cat`. cat_by_id — {id: FeoCategory} той же субсидии (см.
    build_category_path). Нужен фронту (GET /feo-categories/plan-positions), чтобы
    находить плановые позиции вложенных конечных категорий по id родителя, выбранного
    в дереве, БЕЗ обхода обрезанного фронтового дерева (frontend/useFeoLeaves
    filterFundedNodes вырезает конечные узлы без собственного budget — см. баг «В этой
    категории нет плановых позиций», сессия 2026-08-05).
    """
    if cat is None:
        return []
    ids = []
    cur = cat
    while cur.parent_id is not None and cur.parent_id in cat_by_id:
        cur = cat_by_id[cur.parent_id]
        ids.append(cur.id)
    return list(reversed(ids))
