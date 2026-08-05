from decimal import Decimal, InvalidOperation
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc, or_ as sqlor
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.product import Product
from app.models.contract_item import ContractItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.schemas import FeoPlannedItemCreate, FeoPlannedItemOut, FeoComparisonOut, FeoActualItemOut, FeoStageOut


def _safe_mul(a, b) -> Optional[Decimal]:
    if a is None or b is None:
        return None
    try:
        return Decimal(str(a)) * Decimal(str(b))
    except (InvalidOperation, TypeError):
        return None


def _safe_div(a, b) -> Optional[Decimal]:
    if a is None or b is None:
        return None
    try:
        b_dec = Decimal(str(b))
        if b_dec == 0:
            return None
        return Decimal(str(a)) / b_dec
    except (InvalidOperation, TypeError):
        return None


def _build_item_stages(
    pi: PurchaseItem,
    ci: Optional[ContractItem],
    cat: Optional[FeoCategory],
    plan_items_map: dict,
) -> list[FeoStageOut]:
    """Собирает цепочку стадий feo → plan → purchase → contract → accepted для одной
    фактической позиции (см. /comparison). Стадия попадает в массив, только если у
    неё есть хоть какие-то данные. Порядок — строго фиксированный.
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
            unit_price=_safe_div(fpi.amount, fpi.quantity),
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


def _apply_payment_fields(item: FeoPlannedItem, data: FeoPlannedItemCreate) -> None:
    """
    W1b: Apply payment schedule fields and enforce the amount consistency rule:
      monthly mode → amount = monthly_amount * months_count (if both provided).
      one_time mode → amount taken as-is from data.
    """
    item.payment_mode = data.payment_mode
    item.planned_date = data.planned_date
    item.monthly_start_date = data.monthly_start_date
    item.months_count = data.months_count
    item.monthly_amount = data.monthly_amount

    if data.payment_mode == "monthly":
        if data.monthly_amount is not None and data.months_count is not None:
            item.amount = Decimal(str(data.monthly_amount)) * data.months_count
        # else: keep whatever amount was already set (data.amount or existing value)
    else:
        # one_time: honour the manually supplied amount
        item.amount = data.amount

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


@router.get("/", response_model=List[FeoPlannedItemOut])
async def list_planned_items(
    feo_category_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .order_by(FeoPlannedItem.id)
    )).scalars().all()
    return rows


@router.post("/", response_model=FeoPlannedItemOut)
async def create_planned_item(
    data: FeoPlannedItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == data.feo_category_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Категория ФЭО не найдена")

    item = FeoPlannedItem(
        feo_category_id=data.feo_category_id,
        name=data.name,
        quantity=data.quantity,
        unit=data.unit,
        notes=data.notes,
        is_active=data.is_active,
    )
    _apply_payment_fields(item, data)
    db.add(item)
    _sid = cat.subsidy_id
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await db.flush()
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/{item_id}", response_model=FeoPlannedItemOut)
async def update_planned_item(
    item_id: int,
    data: FeoPlannedItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")
    _feo_cat_id = item.feo_category_id
    item.name = data.name
    item.quantity = data.quantity
    item.unit = data.unit
    item.notes = data.notes
    item.is_active = data.is_active
    _apply_payment_fields(item, data)
    _sid = (await db.execute(
        select(FeoCategory.subsidy_id).where(FeoCategory.id == _feo_cat_id)
    )).scalar_one_or_none()
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_planned_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")
    _feo_cat_id = item.feo_category_id
    _sid = (await db.execute(
        select(FeoCategory.subsidy_id).where(FeoCategory.id == _feo_cat_id)
    )).scalar_one_or_none()
    await db.delete(item)
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await db.flush()
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
    await db.commit()
    return {"ok": True}


@router.post("/map")
async def map_purchase_item_to_planned(
    purchase_item_id: int,
    planned_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Сопоставить purchase_item с плановой позицией. planned_item_id=null — снять сопоставление."""
    pi = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.id == purchase_item_id)
    )).scalar_one_or_none()
    if not pi:
        raise HTTPException(404, "Позиция закупки не найдена")

    if planned_item_id is not None:
        planned = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == planned_item_id)
        )).scalar_one_or_none()
        if not planned:
            raise HTTPException(404, "Плановая позиция не найдена")

        # Плановая позиция и позиция закупки обязаны быть в ОДНОЙ категории ФЭО,
        # иначе сумма «исчезает» из одной категории плана и не появляется в другой.
        purchase = (await db.execute(
            select(Purchase).where(Purchase.id == pi.purchase_id)
        )).scalar_one_or_none()
        effective_cat_id = pi.feo_category_id if pi.feo_category_id is not None else (
            purchase.feo_category_id if purchase else None
        )
        if effective_cat_id != planned.feo_category_id:
            cat_ids = [c for c in (effective_cat_id, planned.feo_category_id) if c is not None]
            cat_names = {}
            if cat_ids:
                cat_rows = (await db.execute(
                    select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids))
                )).all()
                cat_names = {row.id: row.name for row in cat_rows}
            planned_cat_name = cat_names.get(planned.feo_category_id, "—")
            item_cat_name = cat_names.get(effective_cat_id, "без категории") if effective_cat_id is not None else "без категории"
            raise HTTPException(
                409,
                f"Плановая позиция «{planned.name}» относится к категории ФЭО «{planned_cat_name}», "
                f"а позиция закупки — к «{item_cat_name}». Привязка между разными категориями невозможна.",
            )

    pi.feo_planned_item_id = planned_item_id
    await db.commit()
    return {"ok": True, "purchase_item_id": purchase_item_id, "planned_item_id": planned_item_id}


@router.get("/comparison", response_model=FeoComparisonOut)
async def get_comparison(
    feo_category_id: int = Query(...),
    subsidy_id: Optional[int] = Query(None),
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
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.services.feo_plan import purchase_item_fact_amount, FACT_CONFIRMED_STATUSES

    # Плановые позиции — только активные (согласовано с /residuals, is_active=False скрыты)
    planned_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .where(FeoPlannedItem.is_active == True)
        .order_by(FeoPlannedItem.id)
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
    )
    if subsidy_id is not None:
        stmt = stmt.where(Purchase.subsidy_id == subsidy_id)

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
    _plan_item_ids = {row.PurchaseItem.feo_planned_item_id for row in actual_rows if row.PurchaseItem.feo_planned_item_id}
    plan_items_map: dict = {}
    if _plan_item_ids:
        _pi_rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(_plan_item_ids))
        )).scalars().all()
        plan_items_map = {p.id: p for p in _pi_rows}

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
        _stages = _build_item_stages(pi, _ci, feo_cat, plan_items_map)

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
            contract_number=p.contract_number,
            contractor_name=contractors.get(p.contractor_id) if p.contractor_id else p.item_name,
            product_photo=product_photo,
            final_unit_price=pi.final_unit_price,
            final_total=pi.final_total,
            acceptance_doc_amount=p.acceptance_doc_amount,
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

    return FeoComparisonOut(
        planned=[FeoPlannedItemOut.model_validate(r) for r in planned_rows],
        actual=actual_out,
    )


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

    Optional ?exclude_wish_id=X — excludes purchases/wishes spawned by that wish
    from used_amount / wish_used_amount. Use when editing an existing wish to
    avoid showing its own привязка as already-consumed plan.
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
            "residual": planned - used - wish_used,
            "linked_purchase_ids": c["linked_purchase_ids"],
            "quantity": planned_qty,
            "unit": item.unit,
            "used_quantity": used_qty,
            "residual_quantity": planned_qty - used_qty,
        })

    return result
