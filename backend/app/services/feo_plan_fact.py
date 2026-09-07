"""feo_plan_fact.py — «факт» закупки/позиции и расход плана по категории/позиции.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). purchase_item_fact_amount — единый источник
«фактической суммы» позиции закупки (ПРАВИЛО №6): используется и здесь
(ordered_consumption_by_category/fact_consumption_by_category), и напрямую
в app.services.purchase_amounts_audit — НЕ копировать формулу, переиспользовать
эту функцию.

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

from sqlalchemy import and_ as sqland, func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.acceptance_docs import total_amount as _acceptance_total_amount

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
        # ПРАВИЛО №6 (2026-09-07, группа D4): источник истины — JSONB
        # acceptance_docs (см. app.services.acceptance_docs.total_amount).
        _doc_amount = _acceptance_total_amount(purchase)
        if _doc_amount is not None:
            amt = (_doc_amount * ratio).quantize(_CENTS) if items_count > 1 else _doc_amount
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


async def unlinked_actual_by_category(
    db: AsyncSession,
    subsidy_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
    exclude_wish_id: Optional[int] = None,
) -> dict[int, float]:
    """{feo_category_id: Σ total_price} — НЕПРИВЯЗАННЫЕ фактические позиции закупок.

    Задача владельца (сессия 2026-08-31, план ≠ факт продолжение): «Непривязанная
    к плану позиция тоже вычитается из суммы ФЭО... То, что она не привязана к
    плану — это отдельная история, но в категории ФЭО она уже находится» +
    «считать надо всё-таки с плана закупок (черновиков может быть миллион). То,
    что внесли в план закупок, могли забыть привязать — на это необходимо
    указывать». Значит «занято по статье» = плановые позиции (kind='plan_position'/
    'feo_article'/'planned_item', см. GET /api/feo-categories/plan-positions) +
    эта сумма — позиции закупок категории, у которых feo_planned_item_id IS NULL
    (не привязаны ни к одной плановой позиции), в PLANNED_STATUSES (от «План
    закупок» и дальше — черновики НЕ считаются), Purchase.stopped_at IS NULL
    (остановленные не считаются — то же правило, что и в plan_consumption_by_category),
    БЕЗ over_plan=true (сверх-плановые уже учитываются отдельно в excess_over_feo/
    over, здесь их считать было бы задвоением другого рода).

    Категория — COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id),
    та же привязка, что и везде в этом модуле. Изоляция субсидий — как в
    plan_consumption_by_category (Purchase.subsidy_id == FeoCategory.subsidy_id
    категории, к которой отнесена позиция).

    exclude_purchase_id/exclude_wish_id — та же исключающая логика (см.
    apply_wish_item_exclusion): редактируемая сейчас закупка/заявка не должна
    выглядеть «непривязанной сама к себе» — иначе её собственная позиция
    задваивается (она сама и есть непривязанная).
    """
    result: dict[int, float] = {}
    if not subsidy_ids:
        return result

    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle

    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            cat_col.label("cat_id"),
            func.coalesce(func.sum(PurchaseItem.total_price), 0).label("amount"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(Purchase.status.in_(list(PLANNED_STATUSES)))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.feo_planned_item_id.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(Purchase.subsidy_id == FeoCategory.subsidy_id)
        .group_by(cat_col)
    )
    if exclude_purchase_id is not None:
        stmt = stmt.where(PurchaseItem.purchase_id != exclude_purchase_id)
    stmt = apply_wish_item_exclusion(stmt, exclude_wish_id)

    rows = (await db.execute(stmt)).all()
    for r in rows:
        result[r.cat_id] = float(r.amount)
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



