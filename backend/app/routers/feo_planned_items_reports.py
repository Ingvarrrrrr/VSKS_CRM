"""Разрезание feo_planned_items.py (Правило №5, сессия 2026-09-08): отчётные/
агрегирующие эндпоинты ФЭО — comparison (план vs факт по категории, со стадиями
ФЭО→План→Закупка→Договор→Приёмка), consumers (расшифровка «кто съел плановую
позицию») и residuals (остатки по всем плановым позициям субсидии). Все пути
статические/литеральные ИЛИ "/{item_id}/<literal>" (минимум на сегмент длиннее
catch-all "/{item_id}" ядра — PUT/DELETE) на префиксе /api/feo-planned-items —
регистрируется рядом с feo_planned_items.router (см. app/routes.py).
"""
from decimal import Decimal, InvalidOperation
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.product import Product
from app.models.contract_item import ContractItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.schemas import FeoComparisonOut, FeoActualItemOut, FeoStageOut, FeoPlannedItemOut
from app.services.acceptance_docs import total_amount as _acceptance_total_amount

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


def _safe_mul(a, b) -> Optional[Decimal]:
    if a is None or b is None:
        return None
    try:
        return Decimal(str(a)) * Decimal(str(b))
    except (InvalidOperation, TypeError):
        return None


def _build_item_stages(
    pi: PurchaseItem,
    ci: Optional[ContractItem],
    cat: Optional[FeoCategory],
    plan_items_map: dict,
    cat_plan_fallback: Optional[dict] = None,
) -> list[FeoStageOut]:
    """Собирает цепочку стадий feo → plan → purchase → contract → accepted для одной
    фактической позиции (см. /comparison). Стадия попадает в массив, только если у
    неё есть хоть какие-то данные. Порядок — строго фиксированный.

    cat_plan_fallback — фолбэк для стадии «План», когда план переехал в записи
    внутри категории (FeoPlannedItem) и у категории cat.planned_quantity/
    planned_amount оба NULL: dict {"quantity", "unit_price", "amount"}, посчитанный
    ОДНИМ запросом на весь /comparison-эндпоинт (см. вызывающий код), а не в цикле
    по позициям — категория здесь всегда одна на запрос.
    """
    stages: list[FeoStageOut] = []

    # 1. ФЭО — из категории (общая для всех позиций этого запроса)
    if cat is not None and (cat.feo_quantity is not None or cat.feo_amount is not None or cat.budget is not None):
        feo_total = _safe_mul(cat.feo_quantity, cat.feo_amount)
        if feo_total is None:
            feo_total = cat.budget
        stages.append(FeoStageOut(
            key="feo", label="ФЭО",
            name=cat.name,
            quantity=cat.feo_quantity,
            unit=cat.feo_unit,
            unit_price=cat.feo_amount,
            total=feo_total,
        ))

    # 2. План — приоритет FeoPlannedItem (если позиция сопоставлена), иначе конечный
    # элемент дерева ФЭО (cat.planned_quantity/planned_amount — planned_amount ЦЕНА ЗА ЕД.)
    fpi = plan_items_map.get(pi.feo_planned_item_id) if pi.feo_planned_item_id else None
    if fpi is not None:
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=fpi.name,
            quantity=fpi.quantity,
            unit=fpi.unit,
            # Владелец (2026-09-02, см. FeoPlannedItem.unit_price): цена за единицу —
            # самостоятельное поле, НЕ amount/quantity. Раньше здесь тем же способом,
            # что и в /plan-positions, фабриковалась цифра из деления — тот же баг,
            # только в другой выдаче (стадия «План» карточки сравнения).
            unit_price=fpi.unit_price,
            total=fpi.amount,
        ))
    elif cat is not None and (cat.planned_quantity is not None or cat.planned_amount is not None):
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=cat.name,
            quantity=cat.planned_quantity,
            unit=cat.unit,
            unit_price=cat.planned_amount,
            total=_safe_mul(cat.planned_quantity, cat.planned_amount),
        ))
    elif cat is not None and cat_plan_fallback is not None:
        # План переехал в записи внутри категории — у мигрированных категорий-листьев
        # cat.planned_quantity/planned_amount оба пусты (NULL), план лежит в активных
        # FeoPlannedItem. Без этого фолбэка стадия «План» не добавляется вовсе, и в
        # цепочке ФЭО→План→Закупка→Договор→Приёмка выпадает целое звено, хотя план есть.
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=cat.name,
            quantity=cat_plan_fallback.get("quantity"),
            unit=cat.unit,
            unit_price=cat_plan_fallback.get("unit_price"),
            total=cat_plan_fallback.get("amount"),
        ))

    # 3. Что выставляли на закупку — всегда есть (purchase_item сюда дошёл, значит есть item_name)
    stages.append(FeoStageOut(
        key="purchase", label="Что выставляли на закупку",
        name=pi.item_name,
        quantity=pi.quantity,
        unit=pi.unit,
        unit_price=pi.unit_price,
        total=pi.total_price,
    ))

    # 4. Номенклатура подрядчика — только если есть договорная строка
    if ci is not None:
        stages.append(FeoStageOut(
            key="contract", label="Номенклатура подрядчика",
            name=ci.name,
            quantity=ci.quantity,
            unit=ci.unit,
            unit_price=ci.unit_price,
            total=ci.total,
        ))

    # 5. Приняли — только если хоть что-то заполнено
    if (
        pi.accepted_name is not None or pi.accepted_quantity is not None or pi.accepted_unit is not None
        or pi.final_unit_price is not None or pi.final_total is not None
    ):
        stages.append(FeoStageOut(
            key="accepted", label="Приняли",
            name=pi.accepted_name,
            quantity=pi.accepted_quantity,
            unit=pi.accepted_unit,
            unit_price=pi.final_unit_price,
            total=pi.final_total,
        ))

    return stages


@router.get("/comparison", response_model=FeoComparisonOut)
async def get_comparison(
    feo_category_id: int = Query(...),
    subsidy_id: Optional[int] = Query(None),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Возвращает плановые позиции и фактические (из закупок) для сравнения.

    Требование владельца (2026-08-05): «Фактическое количество/цена/сумма должны начать
    отображаться после того, как закупка переведена в статус "Заказано", и если потом сменить
    значения на то, что фактически поставлено, после того как будут загружены данные из
    закрывающих документов». Реализовано полем fact_amount/fact_confirmed на каждой позиции —
    см. правила ниже. До «Заказано» (plan_schedule/work_in_progress/contracted) это ещё ПЛАН,
    а не факт, поэтому fact_amount=None.

    exclude_purchase_id/exclude_wish_id (план crystalline-soaring-heron.md, п.1): та же
    исключающая логика, что и в /feo-categories/plan-positions и /feo-planned-items/residuals
    (см. app.services.feo_plan.apply_wish_item_exclusion) — редактируемая сейчас закупка
    или заявка, чья закупка уже отражена в actual, не должна выглядеть задвоенной суммой,
    если вызывающий экран сам добавляет её позиции поверх (форма сконвертированной заявки).
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.services.feo_plan import purchase_item_fact_amount, FACT_CONFIRMED_STATUSES, apply_wish_item_exclusion

    # Плановые позиции — только активные (согласовано с /residuals, is_active=False скрыты).
    # Порядок — sort_order, потом id: владелец просил менять плановые позиции местами
    # внутри категории, и стрелки в панели субсидии пишут именно sort_order. Раньше здесь
    # стояло order_by(id), и панель (она читает ИМЕННО этот эндпоинт) порядок игнорировала:
    # перестановка сохранялась в БД, но на экране ничего не менялось. В соседнем
    # GET /feo-planned-items/ сортировка уже была правильной — расхождение и было багом.
    planned_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .where(FeoPlannedItem.is_active == True)
        .order_by(FeoPlannedItem.sort_order.nulls_last(), FeoPlannedItem.id)
    )).scalars().all()

    # Фактические: purchase_items через COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id) —
    # без coalesce ломается режим «своя категория ФЭО для каждого товара» (Purchase.feo_per_item).
    effective_cat_id = sqlfunc.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            PurchaseItem,
            Purchase,
            ContractItem,
            PurchaseItem.product_id.label("_product_id"),
            Product.photo_data.isnot(None).label("_product_has_photo"),
            Product.photo_url.label("_photo_url"),
            Product.photo_link.label("_photo_link"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(ContractItem, ContractItem.source_item_id == PurchaseItem.id)
        .outerjoin(Product, PurchaseItem.product_id == Product.id)
        .where(effective_cat_id == feo_category_id)
        # Желания — ещё не подтверждённые хотелки; cancelled/split — вне жизненного цикла закупки.
        # Явное перечисление вместо `!= "wishes"`, чтобы cancelled/split не попадали в план/факт.
        .where(Purchase.status.in_(PLANNED_STATUSES))
        # Выравниваем с app.services.feo_plan.py — остановленные закупки не считаются
        # (решение владельца 2026-08-13).
        .where(Purchase.stopped_at.is_(None))
    )
    if subsidy_id is not None:
        stmt = stmt.where(Purchase.subsidy_id == subsidy_id)
    if exclude_purchase_id is not None:
        stmt = stmt.where(PurchaseItem.purchase_id != exclude_purchase_id)
    stmt = apply_wish_item_exclusion(stmt, exclude_wish_id)

    actual_rows = (await db.execute(stmt)).all()

    # Дедуп на случай, если у одной purchase_item окажется несколько ContractItem
    # (в норме source_item_id уникален на позицию; JOIN иначе размножит строку).
    ci_by_pi_id: dict[int, ContractItem] = {}
    _seen_pi_ids: set[int] = set()
    _dedup_rows = []
    for row in actual_rows:
        pi_id = row.PurchaseItem.id
        if row.ContractItem is not None and pi_id not in ci_by_pi_id:
            ci_by_pi_id[pi_id] = row.ContractItem
        if pi_id in _seen_pi_ids:
            continue
        _seen_pi_ids.add(pi_id)
        _dedup_rows.append(row)
    actual_rows = _dedup_rows

    # stages: категория одна на весь запрос (все строки уже отфильтрованы по
    # effective_cat_id == feo_category_id), плановые позиции — по id, встреченным
    # в actual_rows (включая неактивные — planned_rows выше содержит только активные).
    feo_cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == feo_category_id)
    )).scalar_one_or_none()

    # Фолбэк стадии «План» (_build_item_stages): план переехал в записи внутри
    # категории — если planned_quantity/planned_amount категории оба NULL, план
    # лежит в активных FeoPlannedItem. Считаем ОДНИМ запросом-агрегатом на весь
    # эндпоинт (категория тут всегда одна — feo_category_id из query), не в цикле
    # по фактическим позициям ниже.
    cat_plan_fallback: Optional[dict] = None
    if feo_cat is not None and feo_cat.planned_quantity is None and feo_cat.planned_amount is None:
        _fb_row = (await db.execute(
            select(
                sqlfunc.coalesce(sqlfunc.sum(FeoPlannedItem.amount), 0),
                sqlfunc.coalesce(sqlfunc.sum(FeoPlannedItem.quantity), 0),
            )
            .where(FeoPlannedItem.feo_category_id == feo_category_id)
            .where(FeoPlannedItem.is_active == True)
        )).one()
        _fb_amt = Decimal(str(_fb_row[0] or 0))
        _fb_qty = Decimal(str(_fb_row[1] or 0))
        if _fb_amt > 0 or _fb_qty > 0:
            cat_plan_fallback = {
                "quantity": _fb_qty if _fb_qty > 0 else None,
                "amount": _fb_amt if _fb_amt > 0 else None,
                "unit_price": (_fb_amt / _fb_qty) if _fb_qty > 0 else None,
            }

    _plan_item_ids = {row.PurchaseItem.feo_planned_item_id for row in actual_rows if row.PurchaseItem.feo_planned_item_id}
    plan_items_map: dict = {}
    if _plan_item_ids:
        _pi_rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(_plan_item_ids))
        )).scalars().all()
        plan_items_map = {p.id: p for p in _pi_rows}

    # Владелец (2026-08-18): «данные-то есть [в позициях закупок], почему они не
    # подтягиваются?» — плановая позиция без СВОЕГО item_type наследует тип от
    # связанных позиций закупок (см. FeoPlannedItemOut.item_type_effective/
    # item_type_inherited). Один сгруппированный запрос на ВСЕ плановые позиции
    # категории сразу (не в цикле по planned_rows — иначе N+1). Фильтры статуса/
    # stopped_at — те же, что и у actual_rows выше (PLANNED_STATUSES +
    # Purchase.stopped_at.is_(None)), чтобы «тип» не подтягивался из
    # отменённых/остановленных закупок.
    _planned_ids_all = [p.id for p in planned_rows]
    _inherited_type_map: dict[int, Optional[str]] = {}
    if _planned_ids_all:
        _type_rows = (await db.execute(
            select(PurchaseItem.feo_planned_item_id, PurchaseItem.item_type)
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .where(PurchaseItem.feo_planned_item_id.in_(_planned_ids_all))
            .where(Purchase.status.in_(PLANNED_STATUSES))
            .where(Purchase.stopped_at.is_(None))
            .distinct()
        )).all()
        _types_by_planned: dict[int, set] = {}
        for _fpi_id, _itype in _type_rows:
            if not _itype:
                continue
            _types_by_planned.setdefault(_fpi_id, set()).add(_itype)
        for _fpi_id, _types in _types_by_planned.items():
            # Один и тот же непустой тип у всех связанных позиций — наследуем.
            # Разные типы — не выдумываем за пользователя, отдаём None
            # (см. item_type_effective ниже: own или ничего).
            _inherited_type_map[_fpi_id] = next(iter(_types)) if len(_types) == 1 else None

    # Resolve contractor names
    from app.models.contractor import Contractor
    contractor_ids = {row.Purchase.contractor_id for row in actual_rows if row.Purchase.contractor_id}
    contractors = {}
    if contractor_ids:
        c_rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c.name for c in c_rows}

    # Пропорциональное распределение сумм уровня закупки (contract_price / acceptance_doc_amount)
    # между позициями. Считаем по ВСЕМ позициям закупки (не только этой категории) — при
    # feo_per_item одна закупка может охватывать несколько категорий ФЭО одновременно.
    purchase_ids = {row.Purchase.id for row in actual_rows}
    purchase_totals: dict = {}
    if purchase_ids:
        totals_rows = (await db.execute(
            select(
                PurchaseItem.purchase_id,
                sqlfunc.count(PurchaseItem.id),
                sqlfunc.coalesce(sqlfunc.sum(PurchaseItem.total_price), 0),
            )
            .where(PurchaseItem.purchase_id.in_(purchase_ids))
            .group_by(PurchaseItem.purchase_id)
        )).all()
        purchase_totals = {r[0]: (r[1], Decimal(str(r[2] or 0))) for r in totals_rows}

    actual_out = []
    for row in actual_rows:
        pi = row.PurchaseItem
        p = row.Purchase
        _product_id = row._product_id
        _product_has_photo = row._product_has_photo
        _photo_url = row._photo_url
        _photo_link = row._photo_link
        if _product_id is not None and _product_has_photo:
            product_photo = f"/api/products/{_product_id}/photo"
        elif _product_id is not None:
            product_photo = _photo_url or _photo_link or None
        else:
            product_photo = None

        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)  # нет сумм для пропорции — делим поровну
        else:
            ratio = Decimal(1)

        # fact_amount/fact_confirmed/fact_allocated — единая формула, вынесена в
        # app.services.feo_plan.purchase_item_fact_amount, чтобы переиспользовать её
        # и в расчёте плановой суммы (ordered_consumption_by_category), без риска разъехаться.
        fact_amount, fact_allocated = purchase_item_fact_amount(pi, p, ratio, items_count)
        fact_confirmed = p.status in FACT_CONFIRMED_STATUSES
        # (plan_schedule / work_in_progress / contracted — это ещё ПЛАН, fact_amount=None)

        _ci = ci_by_pi_id.get(pi.id)
        _stages = _build_item_stages(pi, _ci, feo_cat, plan_items_map, cat_plan_fallback)

        actual_out.append(FeoActualItemOut(
            purchase_item_id=pi.id,
            item_name=pi.item_name,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total_price=pi.total_price,
            feo_planned_item_id=pi.feo_planned_item_id,
            purchase_id=p.id,
            purchase_number=p.purchase_number,
            registry_number=p.registry_number,
            purchase_status=p.status,
            wish_id=p.wish_id,
            contract_number=p.contract_number,
            contractor_name=contractors.get(p.contractor_id) if p.contractor_id else p.item_name,
            product_photo=product_photo,
            final_unit_price=pi.final_unit_price,
            final_total=pi.final_total,
            acceptance_doc_amount=_acceptance_total_amount(p),
            contract_price=p.contract_price,
            purchase_items_count=items_count,
            fact_amount=fact_amount,
            fact_confirmed=fact_confirmed,
            fact_allocated=fact_allocated,
            over_plan=bool(pi.over_plan),
            accepted_name=pi.accepted_name,
            accepted_quantity=pi.accepted_quantity,
            accepted_unit=pi.accepted_unit,
            stages=_stages,
        ))

    planned_out: list[FeoPlannedItemOut] = []
    for r in planned_rows:
        out = FeoPlannedItemOut.model_validate(r)
        _own_type = r.item_type
        if _own_type:
            out.item_type_effective = _own_type
            out.item_type_inherited = False
        else:
            _inherited = _inherited_type_map.get(r.id)
            out.item_type_effective = _inherited
            out.item_type_inherited = bool(_inherited)
        planned_out.append(out)

    return FeoComparisonOut(
        planned=planned_out,
        actual=actual_out,
    )


_WISH_STATUS_LABELS = {
    "draft": "Черновик",
    "submitted": "На согласовании",
    "approved": "Согласовано",
    "rejected": "Не согласовано",
    "converted": "Передано в исполнение",
}
"""Человекочитаемые подписи статуса заявки — зеркалит WishesView.vue (STATUS_LABELS,
не вынесен в общий backend-модуль, у wishes.py своего словаря нет). Используется
ТОЛЬКО GET /{item_id}/consumers ниже — остальной роутер заявочные статусы не
показывает."""


@router.get("/{item_id}/consumers")
async def get_planned_item_consumers(
    item_id: int,
    exclude_purchase_id: Optional[int] = Query(
        None,
        description="Та же закупка, что исключается при загрузке /feo-categories/plan-positions "
                     "и /feo-planned-items/residuals — чтобы редактируемая сейчас закупка не "
                     "выглядела потребителем самой себя, и сумма «съедено» совпадала с consumed.",
    ),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Расшифровка расхода плановой позиции (владелец, 2026-08-20): «Откуда у 14
    футболок... остаток 4512? Я ничего к ним не привязывал. Я не могу это найти.
    Нигде этого не видно...» — список плановых позиций показывает «план X ·
    выбрано Y · остаток Z» (FeoPlannedItemsSelect.vue), но КТО съел Y — нигде не
    видно. Боевой случай: у одной плановой позиции («Футболка Trisar (цвет
    олива) с нанесением», план 15 793,40 ₽) висели ДВЕ строки заявки №40 — сама
    заявка и её собственная закупка. Этот эндпоинт возвращает каждую позицию
    закупки/заявки, ссылающуюся на item_id (feo_planned_item_id), с суммой,
    статусом (по-русски) и данными для перехода — а не просто цифру.

    Фильтры и суммы — СТРОГО та же логика, что app.services.feo_plan
    .planned_item_consumption (используется /feo-categories/plan-positions и
    /feo-planned-items/residuals для того же числа `consumed`): позиция закупки
    учитывается, только если Purchase.status в PLANNED_STATUSES (значит, ещё не
    отменена/не «желание») И Purchase.stopped_at IS NULL И не исключена
    exclude_purchase_id/exclude_wish_id. Иначе цифра «съедено» здесь разошлась бы
    с той, что уже видна в списке позиций — ровно тот дефект, который чинится.

    Каждая позиция ЗАКУПКИ, ссылающаяся на item_id, попадает в ответ ВСЕГДА (даже
    если сейчас не учитывается в сумме — например, закупка отменена/остановлена);
    поле counts_towards_consumed показывает, входит ли она в consumed. Позиции
    ЗАЯВКИ (wish_items) сами по себе план НЕ резервируют (решение владельца
    2026-08-17 — см. planned_item_consumption), поэтому у них
    counts_towards_consumed всегда false; они показаны для полноты картины
    («заявка ещё не в закупке, но уже помечена этой плановой позицией»).

    Дедуп факт-конвертации (владелец: «заявка и закупка — это одна позиция»,
    см. plan_autoassign._fpi_reference_keys): если у позиции заявки есть
    порождённая ею позиция закупки (PurchaseItem.wish_item_id), которая ТОЖЕ
    ссылается на этот же item_id, — в ответе показывается ТОЛЬКО строка закупки
    (более свежие/актуальные данные), а не обе; иначе одна и та же позиция
    выглядела бы двумя потребителями и сумма/список задваивались бы. Сама связь
    видна через поле wish_id на строке закупки — оно указывает, из какой заявки
    та выросла.
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS as _PURCHASE_STATUS_LABELS
    from app.models.user import User

    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")

    pi_rows = (await db.execute(
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .order_by(PurchaseItem.id)
    )).all()
    wi_rows = (await db.execute(
        select(WishItem, Wish)
        .join(Wish, WishItem.wish_id == Wish.id)
        .where(WishItem.feo_planned_item_id == item_id)
        .order_by(WishItem.id)
    )).all()

    # Автор заявки — батч одним запросом (не полагаемся на Wish.creator lazy="joined"
    # автоподгрузку через plain select(Wish, WishItem), чтобы не зависеть от деталей
    # стратегии загрузки relationship при явном JOIN на два entity).
    creator_ids = {w.created_by for _wi, w in wi_rows if w.created_by is not None}
    creators: dict[int, str] = {}
    if creator_ids:
        u_rows = (await db.execute(
            select(User.id, User.full_name, User.username).where(User.id.in_(creator_ids))
        )).all()
        creators = {u.id: (u.full_name or u.username) for u in u_rows}

    # Та же «одна логическая позиция» (app.services.plan_autoassign._fpi_reference_keys /
    # app.services.feo_plan.apply_wish_item_exclusion) — исключаем строку закупки не
    # только по Purchase.wish_id, но и по PurchaseItem.wish_item_id, если он указывает
    # на WishItem исключаемой заявки, ссылающийся на ЭТУ ЖЕ плановую позицию (уже
    # загружено в wi_rows ниже — второго запроса не требуется).
    _excluded_wish_item_ids = (
        {wi.id for wi, w in wi_rows if w.id == exclude_wish_id} if exclude_wish_id is not None else set()
    )

    def _pi_counts(pi: PurchaseItem, purchase: Purchase) -> bool:
        if purchase.status not in PLANNED_STATUSES:
            return False
        if purchase.stopped_at is not None:
            return False
        if exclude_purchase_id is not None and purchase.id == exclude_purchase_id:
            return False
        if exclude_wish_id is not None and purchase.wish_id == exclude_wish_id:
            return False
        if pi.wish_item_id is not None and pi.wish_item_id in _excluded_wish_item_ids:
            return False
        return True

    converted_wish_item_ids = {pi.wish_item_id for pi, _p in pi_rows if pi.wish_item_id is not None}

    consumers: list[dict] = []
    total_consumed = Decimal("0")

    for pi, p in pi_rows:
        counts = _pi_counts(pi, p)
        amount = Decimal(str(pi.total_price)) if pi.total_price is not None else Decimal("0")
        if counts:
            total_consumed += amount
        consumers.append({
            "type": "purchase",
            "counts_towards_consumed": counts,
            "item_name": pi.item_name,
            "quantity": float(pi.quantity) if pi.quantity is not None else None,
            "unit": pi.unit,
            "amount": float(amount),
            "purchase_id": p.id,
            "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "purchase_subject": p.subject or p.item_name,
            "status": p.status,
            "status_label": _PURCHASE_STATUS_LABELS.get(p.status, p.status),
            "wish_id": p.wish_id,
        })

    for wi, w in wi_rows:
        # Уже представлена строкой закупки выше (см. докстринг: одна логическая
        # позиция) — не дублируем и не считаем сумму дважды.
        if wi.id in converted_wish_item_ids:
            continue
        amount = Decimal(str(wi.total_price)) if wi.total_price is not None else Decimal("0")
        consumers.append({
            "type": "wish",
            # Незаконвертированная заявка план не резервирует (владелец, 2026-08-17) —
            # см. докстринг planned_item_consumption. Показана только для полноты.
            "counts_towards_consumed": False,
            "item_name": wi.item_name,
            "quantity": float(wi.quantity) if wi.quantity is not None else None,
            "unit": wi.unit,
            "amount": float(amount),
            "wish_id": w.id,
            "wish_title": w.title,
            "status": w.status,
            "status_label": _WISH_STATUS_LABELS.get(w.status, w.status),
            "author_name": creators.get(w.created_by) if w.created_by is not None else None,
        })

    planned_amount = float(item.amount) if item.amount is not None else 0.0
    residual = planned_amount - float(total_consumed)

    return {
        "planned_item_id": item.id,
        "planned_item_name": item.name,
        "planned_amount": planned_amount,
        "consumed": float(total_consumed),
        "residual": residual,
        "consumers": consumers,
    }


@router.get("/residuals")
async def get_feo_residuals(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Returns per-FeoPlannedItem residual for a given subsidy.
    Response: list of {feo_item_id, name, category_id, category_name, planned_amount,
                        used_amount, wish_used_amount, residual, linked_purchase_ids,
                        quantity, unit, used_quantity, residual_quantity}

    Optional ?exclude_purchase_id=X — excludes items of that purchase from
    used_amount and linked_purchase_ids. Use when editing an existing purchase
    to avoid double-counting its own rows.

    Optional ?exclude_wish_id=X — excludes purchases spawned by that wish
    from used_amount. Use when editing an existing wish to avoid showing its
    own привязка as already-consumed plan.

    Решение владельца (2026-08-17): незаконвертированные заявки (Wish) в
    остаток НЕ входят вообще — план расходуют только позиции, попавшие в
    план закупок. Поле wish_used_amount осталось в ответе и всегда равно
    0.0 — ради обратной совместимости фронта, который его читает.
    """
    from app.services.feo_plan import planned_item_consumption

    # All active planned items for this subsidy
    items_q = (
        select(FeoPlannedItem, FeoCategory.id.label("cat_id"), FeoCategory.name.label("cat_name"))
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(FeoPlannedItem.is_active == True)
        .order_by(FeoPlannedItem.id)
    )
    rows = (await db.execute(items_q)).all()

    if not rows:
        return []

    item_ids = [r.FeoPlannedItem.id for r in rows]

    # Общая логика расхода плановой позиции — переиспользуется GET /feo-categories/plan-positions,
    # чтобы оба эндпоинта считали одинаково (см. app/services/feo_plan.py).
    cons_map = await planned_item_consumption(db, item_ids, exclude_purchase_id, exclude_wish_id)

    result = []
    for r in rows:
        item = r.FeoPlannedItem
        planned = float(item.amount or 0)
        planned_qty = float(item.quantity or 0)
        c = cons_map.get(item.id, {"used": 0.0, "used_qty": 0.0, "wish_used": 0.0, "linked_purchase_ids": []})
        used = c["used"]
        used_qty = c["used_qty"]
        wish_used = c["wish_used"]
        result.append({
            "feo_item_id": item.id,
            "name": item.name,
            "category_id": item.feo_category_id,
            "category_name": r.cat_name,
            "planned_amount": planned,
            "used_amount": used,
            "wish_used_amount": wish_used,
            "residual": planned - used,
            "linked_purchase_ids": c["linked_purchase_ids"],
            "quantity": planned_qty,
            "unit": item.unit,
            "used_quantity": used_qty,
            "residual_quantity": planned_qty - used_qty,
        })

    return result
