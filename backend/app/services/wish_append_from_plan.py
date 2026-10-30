"""«Добавить забытое из субсидии» — задача владельца (29.10.2026): заявку уже
распределили (канбаном) на несколько закупок, потом вспомнили, что часть
плановых позиций субсидии забыли выбрать. Этот сервис присоединяет новые
позиции К СУЩЕСТВУЮЩЕЙ заявке и заводит для них отдельную закупку-колонку
«… — Добавляем забытое», которую владелец вручную разносит по уже имеющимся
закупкам (см. app/routers/purchase_items_move.py — перенос позиции между
«сёстрами» одной заявки уже существует, вторая реализация переноса здесь не
заводится).

Вызывается из app/routers/wish_append_from_plan.py
(POST /api/wishes/{wish_id}/append-from-plan).

ПРАВИЛО №6 — переиспользует, не копирует:
  - app.services.plan_to_wish.build_items_from_plan — та же проверка остатка
    плана и сборка item_dicts, что у «из плана — в заявку»
    (app/services/plan_to_wish.py::create_wish_from_plan) и у авансового пути
    (app/services/plan_to_purchase.py). Второй расчёт остатка не пишем.
  - app.services.wish_access.ensure_wish_write_access — тот же гейт
    «кто может править заявку» (автор/участник/SaaS), что у PUT /wishes/{id}
    (app/routers/wishes.py::update_wish).
  - app.services.feo_effective_category.effective_item_feo_category_id и
    app.services.payroll_category_guard — те же правила, что у создания
    заявки (app/routers/wishes.py::create_wish).
  - app.services.item_contractor.set_item_contractor,
    app.services.purchase_money_writer.recalc_purchase_money — тот же писатель
    денег/контрагента позиции, что у app/services/wish_multi_sync.py (сборка
    PurchaseItem из WishItem скопирована оттуда почти буквально — это не
    дублирование формулы, а создание новой строки по тому же шаблону полей,
    который там инлайн, а не функция; выносить в общую функцию обе точки
    пока не стали — риск регрессии в wish_multi_sync.py вне объёма задачи).

Суффикс названия колонки — APPEND_FORGOTTEN_SUFFIX, единственный источник на
бэке; фронт держит свою копию строки в useWishPurchaseNav/PlanToRequestDialog
(frontend/src/constants/wishAppendForgotten.ts) только для подсветки той же
закупки в канбане — печать текста остаётся за бэком (Purchase.item_name/
subject пишутся здесь один раз).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish_item import WishItem
from app.services.item_contractor import set_item_contractor
from app.services.plan_to_wish import PlanToWishItemInput, build_items_from_plan

# Единственный источник суффикса названия колонки «Добавляем забытое» на
# бэке — Purchase.item_name/subject всегда оканчиваются на это (см.
# _find_or_create_append_purchase ниже). Фронт для подсветки колонки держит
# свою копию строки (константа в одном месте на фронте, см. докстринг модуля).
APPEND_FORGOTTEN_SUFFIX = "Добавляем забытое"

# Статус новой колонки, если у заявки ЕЩЁ нет ни одной незамороженной (не
# 'split') закупки, откуда можно подсмотреть статус — тот же дефолт, что
# app.services.wish_distribution._distribute_wish_to_purchases(purchase_status
# по умолчанию) ставит при первом распределении заявки на закупки.
_FALLBACK_PURCHASE_STATUS = "plan_schedule"


def _is_append_forgotten_purchase(p: Purchase) -> bool:
    name = (p.item_name or p.subject or "").strip()
    return p.contract_id is None and name.endswith(APPEND_FORGOTTEN_SUFFIX)


async def _find_or_create_append_purchase(wish, db: AsyncSession) -> tuple[Purchase, bool]:
    """Возвращает (закупка-колонка «Добавляем забытое», создана_ли_новая).

    Переиспользует незавершённую (без договора) колонку этой заявки, если она
    уже есть — «не плодить вторую» (задача владельца, п.1). Иначе создаёт
    новую с тем же набором шапочных полей, что
    app.services.wish_distribution._distribute_wish_to_purchases проставляет
    остальным закупкам заявки (контрагент/форма договора/НДС и т.п.) —
    переносится, если задано у заявки, тот же принцип «не перетирать уже
    заданное» не нужен здесь, т.к. закупка свежесозданная.
    """
    existing_rows = (await db.execute(
        select(Purchase).where(Purchase.wish_id == wish.id).order_by(Purchase.id)
    )).scalars().all()

    for p in existing_rows:
        if _is_append_forgotten_purchase(p):
            return p, False

    non_split_statuses = [p.status for p in existing_rows if p.status != "split"]
    status = non_split_statuses[0] if non_split_statuses else _FALLBACK_PURCHASE_STATUS

    base_title = (wish.title or "").strip() or f"Заявка #{wish.id}"
    subject = f"{base_title} — {APPEND_FORGOTTEN_SUFFIX}"

    p = Purchase(
        wish_id=wish.id,
        subsidy_id=wish.subsidy_id,
        item_name=subject,
        subject=subject,
        status=status,
        service_note_to_user_id=wish.assigned_to,
        service_note_text=wish.justification,
        service_note_by=wish.created_by,
        assigned_user_id=getattr(wish, "executor_id", None),
        execution_term=getattr(wish, "execution_deadline", None),
        purchase_method="advance" if getattr(wish, "source", None) == "advance_report" else "single",
        payment_basis_type="advance_report" if getattr(wish, "source", None) == "advance_report" else None,
        vat_mode=(getattr(wish, "vat_mode", None) or "uniform"),
        tz_vat_on_top=bool(getattr(wish, "tz_vat_on_top", False)),
        contractor_id=getattr(wish, "contractor_id", None),
        contract_form=getattr(wish, "contract_form", None),
        tz_not_required=bool(getattr(wish, "tz_not_required", False)),
        planned_quantity=0,
        planned_total_price=0,
        total_nmck=0,
        nmck=0,
    )
    db.add(p)
    await db.flush()
    return p, True


async def _recompute_purchase_feo_header(purchase: Purchase, db: AsyncSession) -> None:
    """feo_category_id/feo_per_item шапки закупки — пересчёт по фактическим
    категориям её позиций (единственная категория → шапка её хранит;
    несколько — режим «своя категория у каждого товара», как у шапки заявки
    с позициями из нескольких категорий, см. plan_to_wish.create_wish_from_plan
    про тот же принцип feo_per_item)."""
    cats = (await db.execute(
        select(PurchaseItem.feo_category_id)
        .where(PurchaseItem.purchase_id == purchase.id)
        .where(PurchaseItem.feo_category_id.isnot(None))
        .distinct()
    )).scalars().all()
    distinct_cats = set(cats)
    purchase.feo_category_id = next(iter(distinct_cats)) if len(distinct_cats) == 1 else None
    purchase.feo_per_item = len(distinct_cats) > 1


async def append_items_from_plan(
    db: AsyncSession,
    current_user,
    wish_id: int,
    items: list[PlanToWishItemInput],
) -> dict:
    """POST /api/wishes/{wish_id}/append-from-plan — см. докстринг модуля."""
    from app.routers.wishes import _load_wish
    from app.services.wish_access import ensure_wish_write_access
    from app.services.feo_effective_category import effective_item_feo_category_id
    from app.services.payroll_category_guard import assert_no_goods_in_payroll, default_wish_item_type
    from app.services.purchase_money_writer import recalc_purchase_money

    wish = await _load_wish(wish_id, db)
    await ensure_wish_write_access(wish, current_user, db)

    if not wish.subsidy_id:
        raise HTTPException(400, "Заявка не привязана к субсидии — добавить позиции из плана нельзя")

    item_dicts, warnings, _categories_used, _subsidy = await build_items_from_plan(
        db, wish.subsidy_id, items,
    )

    _wish_contractor_obj = None
    if getattr(wish, "contractor_id", None):
        from app.models.contractor import Contractor as _Contractor
        _wish_contractor_obj = await db.get(_Contractor, wish.contractor_id)

    purchase, _created_new = await _find_or_create_append_purchase(wish, db)

    created_wish_items: list[WishItem] = []
    for item_data in item_dicts:
        eff_cat_id = effective_item_feo_category_id(
            bool(wish.feo_per_item), wish.feo_category_id, item_data.get("feo_category_id"),
        )
        item_type_for_create = default_wish_item_type(item_data)
        await assert_no_goods_in_payroll(db, eff_cat_id, [{
            "item_name": item_data.get("item_name", ""),
            "item_type": item_type_for_create,
        }])
        wi = WishItem(
            wish_id=wish.id,
            product_id=item_data.get("product_id"),
            item_name=item_data.get("item_name", ""),
            item_type=item_type_for_create,
            quantity=item_data.get("quantity", 1),
            unit=item_data.get("unit", "шт"),
            unit_price=item_data.get("unit_price", 0),
            total_price=item_data.get("total_price", 0),
            country_origin=item_data.get("country_origin", "РФ"),
            feo_category_id=item_data.get("feo_category_id"),
            feo_planned_item_id=item_data.get("feo_planned_item_id"),
            over_plan=item_data.get("over_plan", False),
            # Владелец (14.10.2026): позиция ЗАГРУЖЕНА из Плана закупок —
            # ставится ТОЛЬКО build_items_from_plan (Правило №6), см.
            # app/services/feo_item_lock.py.
            from_plan=True,
        )
        db.add(wi)
        created_wish_items.append(wi)
    await db.flush()

    from app.services.wish_access import _eff_date

    for wi, item_data in zip(created_wish_items, item_dicts):
        pi = PurchaseItem(
            purchase_id=purchase.id,
            product_id=wi.product_id,
            item_name=wi.item_name,
            item_type=wi.item_type,
            quantity=wi.quantity,
            unit=wi.unit,
            unit_price=wi.unit_price,
            total_price=wi.total_price,
            planned_quantity=wi.quantity,
            planned_unit_price=wi.unit_price,
            planned_total=wi.total_price,
            country_origin=wi.country_origin,
            feo_category_id=wi.feo_category_id,
            feo_planned_item_id=wi.feo_planned_item_id,
            over_plan=wi.over_plan,
            needed_date=_eff_date(wish, wi),
            wish_item_id=wi.id,
            vat_rate=getattr(wi, "vat_rate", None),
            from_plan=True,
        )
        set_item_contractor(pi, contractor=_wish_contractor_obj, name=getattr(wish, "contractor_name", None))
        db.add(pi)

    await db.flush()
    await _recompute_purchase_feo_header(purchase, db)
    await recalc_purchase_money(db, purchase)
    await db.commit()

    return {
        "wish_id": wish.id,
        "purchase_id": purchase.id,
        "items_count": len(item_dicts),
        "warnings": warnings,
    }
