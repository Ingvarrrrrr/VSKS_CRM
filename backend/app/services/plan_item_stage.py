"""plan_item_stage.py — раскраска плановых позиций дерева ФЭО по стадии закупки
(владелец, 16.10.2026): «цветом будет отображаться стадия, а заполнение строки
этим цветом — какое количество уже закуплено. Пустая строка — ещё не начинали,
полная — всё закуплено. Когда одна плановая закупалась несколькими закупками —
плановая закрашивается полностью, но из полосок разного цвета, пропорциональных
по высоте; каждая закупка — своей стадией».

Шкала стадий (порядок/подписи/цвета — ЕДИНСТВЕННЫЙ источник
frontend/src/constants/planStageScale.ts, здесь только ключи, см. STAGE_*):
  in_work        — Purchase.status in (plan_schedule, work_in_progress)
  contracted     — Purchase.status == contracted
  ordered        — Purchase.status in (ordered, delivered)
  paid_marked    — оплата закупки ПО ЭТОЙ ПОЗИЦИИ (пропорция
                   app.services.feo_plan_payments._item_ratio/_item_payment_split
                   — ПРАВИЛО №6, та же формула, что и paid_consumption_rows,
                   второй расчёт распределения платежа НЕ заводится) покрывает
                   сумму позиции целиком, но не подтверждена выпиской
  paid_confirmed — то же, подтверждено выпиской (Purchase.payment_amount —
                   Payment.confirmed_by_statement=True, см. докстринг
                   feo_plan_payments.py)
Частичная оплата (меньше суммы позиции целиком) стадию НЕ поднимает — остаётся
стадия по статусу закупки (владелец: «частичная оплата — стадия по статусу
закупки»).

Закупка попадает в сегмент, если Purchase.stopped_at IS NULL и status в
PLANNED_STATUSES (app.routers.purchase_budget — тот же набор статусов, что и
везде в дереве ФЭО/consumption, ПРАВИЛО №6, второй список статусов не заводим) —
статусы 'wishes' (заявка/черновик) и 'cancelled' сюда не попадают.

Две точки входа:
  planned_item_stage_segments   — позиции, привязанные к FeoPlannedItem (Ур.5,
                                   PurchaseItem.feo_planned_item_id).
  category_plan_stage_segments  — план, заведённый прямо на листовой категории
                                   (kind='plan_position'/'feo_article' в
                                   /feo-categories/plan-positions), т.е. позиции
                                   закупки этой категории БЕЗ собственной
                                   FeoPlannedItem (иначе задвоили бы с первой
                                   точкой — та же категория считала бы закупку
                                   и как «план категории», и как «план Ур.5»).

Обе используют один и тот же _build_segments (нормализация доли, сортировка по
стадии) — ПРАВИЛО №6, второй алгоритм сборки сегментов не пишем.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_payments import purchase_item_payment_amounts

STAGE_IN_WORK = "in_work"
STAGE_CONTRACTED = "contracted"
STAGE_ORDERED = "ordered"
STAGE_PAID_MARKED = "paid_marked"
STAGE_PAID_CONFIRMED = "paid_confirmed"

# Статус закупки → стадия шкалы (до проверки оплаты, см. _resolve_stage). Статусы
# не из этого словаря (включая 'wishes'/'cancelled', отфильтрованные выше) не
# участвуют в раскраске вовсе.
_STATUS_STAGE: dict[str, str] = {
    "plan_schedule": STAGE_IN_WORK,
    "work_in_progress": STAGE_IN_WORK,
    "contracted": STAGE_CONTRACTED,
    "ordered": STAGE_ORDERED,
    "delivered": STAGE_ORDERED,
    "paid": STAGE_ORDERED,
}

_PAYMENT_EPS = 0.01

# «Поставлено и дальше» — для признака segments[].delivered (выгрузка ФЭО,
# задача владельца 20.10.2026, не меняет `stage`): закупка, у которой товар
# точно поставлен — статусы 'delivered' и 'paid' (оплата в этой модели
# наступает после поставки, см. _STATUS_STAGE выше — оба статуса уже сливаются
# в STAGE_ORDERED). ПРАВИЛО №6: второй список статусов не заводим — это
# подмножество PLANNED_STATUSES (_active_statuses), а не новая шкала.
_DELIVERED_STATUSES: set = {"delivered", "paid"}


def _active_statuses() -> set:
    # Локальный импорт — избегаем цикла роутер↔сервис (тот же приём, что и в
    # feo_plan_payments.paid_consumption_rows).
    from app.routers.purchase_budget import PLANNED_STATUSES
    return PLANNED_STATUSES


def _resolve_stage(status: Optional[str], item_total: float, paid_marked: float, paid_confirmed: float) -> str:
    """Стадия ОДНОЙ закупки по ОДНОЙ плановой позиции — статус закупки, если
    оплата покрывает сумму позиции целиком (с учётом погрешности округления)."""
    base = _STATUS_STAGE.get(status or "", STAGE_IN_WORK)
    if item_total <= 0:
        return base
    if paid_confirmed >= item_total - _PAYMENT_EPS:
        return STAGE_PAID_CONFIRMED
    if paid_marked >= item_total - _PAYMENT_EPS:
        return STAGE_PAID_MARKED
    return base


def _build_segments(groups: dict[tuple, dict], denom_qty: float, denom_amount: float) -> dict:
    """groups: {(purchase_id, registry_number, stage): {"quantity": float, "amount": float}}
    → {"segments": [...], "overflow": bool}. Доля (share) считается по количеству
    плановой позиции, если оно задано (>0), иначе по сумме — та же логика, что у
    остальных показателей плановой позиции (app.services.feo_plan.*_consumption,
    ПРАВИЛО №6: один и тот же выбор quantity/amount-базы). Σ share > 1 (несколько
    закупок перекрыли план) — нормируем к 1, флаг overflow=True (сырые доли видны
    во вложенных segments[].quantity/amount, нормировку теряет только share)."""
    use_qty = denom_qty is not None and denom_qty > 0
    denom = denom_qty if use_qty else denom_amount
    segments = []
    for (purchase_id, registry_number, stage), agg in groups.items():
        base = agg["quantity"] if use_qty else agg["amount"]
        share = (base / denom) if denom and denom > 0 else 0.0
        segments.append({
            "purchase_id": purchase_id,
            "registry_number": registry_number,
            "stage": stage,
            "share": share,
            "quantity": agg["quantity"],
            "amount": agg["amount"],
            # «Товар поставлен» (выгрузка ФЭО, задача владельца 20.10.2026) —
            # НЕ влияет на `stage` (полосы дерева ФЭО по-прежнему сливают
            # delivered в ordered, см. _resolve_stage) — отдельный признак по
            # статусу закупки «поставлено и дальше» (delivered, paid — тот же
            # порядок статусов, что и PLANNED_STATUSES выше по шкале ordered).
            "delivered": bool(agg.get("delivered")),
        })
    total_share = sum(s["share"] for s in segments)
    overflow = total_share > 1 + 1e-6
    if overflow and total_share > 0:
        for s in segments:
            s["share"] = s["share"] / total_share
    # Сверху самая дальняя стадия (владелец: «сверху самая дальняя стадия, ниже
    # более ранние») — сортируем по убыванию «продвинутости», см. _STAGE_RANK.
    segments.sort(key=lambda s: _STAGE_RANK.get(s["stage"], 0), reverse=True)
    return {"segments": segments, "overflow": overflow}


_STAGE_RANK = {
    STAGE_IN_WORK: 0,
    STAGE_CONTRACTED: 1,
    STAGE_ORDERED: 2,
    STAGE_PAID_MARKED: 3,
    STAGE_PAID_CONFIRMED: 4,
}


async def _fetch_rows(db: AsyncSession, stmt):
    rows = (await db.execute(stmt)).all()
    if not rows:
        return [], {}
    purchase_ids = sorted({r.purchase_id for r in rows})
    payment_map = await purchase_item_payment_amounts(db, purchase_ids)
    return rows, payment_map


async def planned_item_stage_segments(
    db: AsyncSession,
    planned_item_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
) -> dict[int, dict]:
    """{feo_planned_item_id: {"segments": [...], "overflow": bool}} — одна полоса
    на каждую действующую закупку, привязанную позициями
    (PurchaseItem.feo_planned_item_id) к этой плановой позиции."""
    result: dict[int, dict] = {}
    if not planned_item_ids:
        return result

    active = _active_statuses()
    stmt = (
        select(
            PurchaseItem.id.label("purchase_item_id"),
            PurchaseItem.feo_planned_item_id.label("planned_item_id"),
            PurchaseItem.purchase_id.label("purchase_id"),
            PurchaseItem.quantity.label("quantity"),
            PurchaseItem.total_price.label("amount"),
            Purchase.status.label("status"),
            Purchase.registry_number.label("registry_number"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id.in_(planned_item_ids))
        .where(Purchase.status.in_(list(active)))
        .where(Purchase.stopped_at.is_(None))
    )
    if exclude_purchase_id is not None:
        stmt = stmt.where(Purchase.id != exclude_purchase_id)

    rows, payment_map = await _fetch_rows(db, stmt)
    if not rows:
        return result

    fpi_rows = (await db.execute(
        select(FeoPlannedItem.id, FeoPlannedItem.quantity, FeoPlannedItem.amount)
        .where(FeoPlannedItem.id.in_(planned_item_ids))
    )).all()
    denom = {r.id: (float(r.quantity) if r.quantity is not None else 0.0, float(r.amount) if r.amount is not None else 0.0) for r in fpi_rows}

    grouped: dict[int, dict[tuple, dict]] = defaultdict(lambda: defaultdict(lambda: {"quantity": 0.0, "amount": 0.0}))
    stage_cache: dict[int, str] = {}
    for r in rows:
        pm = payment_map.get(r.purchase_item_id, {"paid_marked": 0.0, "paid_confirmed": 0.0, "item_total": float(r.amount or 0)})
        # Стадия считается раз на (planned_item_id, purchase_id) — несколько
        # строк закупки на одну позицию складываются в одну полосу.
        bucket = grouped[r.planned_item_id][(r.purchase_id, r.registry_number, "__pending__")]
        bucket["quantity"] += float(r.quantity or 0)
        bucket["amount"] += float(r.amount or 0)
        bucket.setdefault("_marked", 0.0)
        bucket.setdefault("_confirmed", 0.0)
        bucket["_marked"] += pm["paid_marked"]
        bucket["_confirmed"] += pm["paid_confirmed"]
        bucket.setdefault("_status", r.status)

    for planned_item_id, by_key in grouped.items():
        final_groups: dict[tuple, dict] = {}
        for (purchase_id, registry_number, _placeholder), agg in by_key.items():
            stage = _resolve_stage(agg.get("_status"), agg["amount"], agg["_marked"], agg["_confirmed"])
            final_groups[(purchase_id, registry_number, stage)] = {
                "quantity": agg["quantity"], "amount": agg["amount"],
                "delivered": agg.get("_status") in _DELIVERED_STATUSES,
            }
        dq, da = denom.get(planned_item_id, (0.0, 0.0))
        result[planned_item_id] = _build_segments(final_groups, dq, da)
    return result


async def category_plan_stage_segments(
    db: AsyncSession,
    category_ids: list[int],
    exclude_purchase_id: Optional[int] = None,
) -> dict[int, dict]:
    """{feo_category_id: {"segments": [...], "overflow": bool}} — план, заведённый
    прямо на листовой категории (kind='plan_position'/'feo_article'): позиции
    закупок ЭТОЙ категории (COALESCE(PurchaseItem.feo_category_id,
    Purchase.feo_category_id) — та же проекция категории, что и у
    unlinked_actual_by_category/plan_consumption_by_category, ПРАВИЛО №6), у
    которых НЕТ собственной FeoPlannedItem (иначе их полоса уже посчитана
    planned_item_stage_segments для этой же плановой позиции — задвоение)."""
    from sqlalchemy import func as sqlfunc, or_ as sqlor

    result: dict[int, dict] = {}
    if not category_ids:
        return result

    active = _active_statuses()
    cat_col = sqlfunc.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            PurchaseItem.id.label("purchase_item_id"),
            cat_col.label("category_id"),
            PurchaseItem.purchase_id.label("purchase_id"),
            PurchaseItem.quantity.label("quantity"),
            PurchaseItem.total_price.label("amount"),
            Purchase.status.label("status"),
            Purchase.registry_number.label("registry_number"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == cat_col)
        .where(cat_col.in_(category_ids))
        .where(PurchaseItem.feo_planned_item_id.is_(None))
        .where(Purchase.status.in_(list(active)))
        .where(Purchase.stopped_at.is_(None))
    )
    if exclude_purchase_id is not None:
        stmt = stmt.where(Purchase.id != exclude_purchase_id)

    rows, payment_map = await _fetch_rows(db, stmt)
    if not rows:
        return result

    cat_rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.planned_quantity, FeoCategory.planned_amount)
        .where(FeoCategory.id.in_(category_ids))
    )).all()
    denom = {}
    for r in cat_rows:
        qty = float(r.planned_quantity) if r.planned_quantity is not None else 0.0
        unit_price = float(r.planned_amount) if r.planned_amount is not None else 0.0
        denom[r.id] = (qty, qty * unit_price)

    grouped: dict[int, dict[tuple, dict]] = defaultdict(lambda: defaultdict(lambda: {"quantity": 0.0, "amount": 0.0}))
    for r in rows:
        pm = payment_map.get(r.purchase_item_id, {"paid_marked": 0.0, "paid_confirmed": 0.0, "item_total": float(r.amount or 0)})
        bucket = grouped[r.category_id][(r.purchase_id, r.registry_number, "__pending__")]
        bucket["quantity"] += float(r.quantity or 0)
        bucket["amount"] += float(r.amount or 0)
        bucket.setdefault("_marked", 0.0)
        bucket.setdefault("_confirmed", 0.0)
        bucket["_marked"] += pm["paid_marked"]
        bucket["_confirmed"] += pm["paid_confirmed"]
        bucket.setdefault("_status", r.status)

    for category_id, by_key in grouped.items():
        final_groups: dict[tuple, dict] = {}
        for (purchase_id, registry_number, _placeholder), agg in by_key.items():
            stage = _resolve_stage(agg.get("_status"), agg["amount"], agg["_marked"], agg["_confirmed"])
            final_groups[(purchase_id, registry_number, stage)] = {
                "quantity": agg["quantity"], "amount": agg["amount"],
                "delivered": agg.get("_status") in _DELIVERED_STATUSES,
            }
        dq, da = denom.get(category_id, (0.0, 0.0))
        result[category_id] = _build_segments(final_groups, dq, da)
    return result
