"""«Из плана — сразу в авансовый отчёт» (plan-to-purchase). Сервисный слой для
app/routers/plan_to_wish.py::post_create_purchase_from_plan.

Повод (владелец, 30.09.2026, дословно): «Я подгоняю уже свершившиеся закупки —
это всё авансовые, чеков пока нет, но я знаю, что они были. Надо, чтобы при
создании из плана сразу можно было заводить как авансовый и не требовало
заведения товара в БД». В отличие от «Создать закупку на основе плана» →
заявка (app.services.plan_to_wish.create_wish_from_plan), здесь пользователь
уже точно знает, что купил — заводить промежуточную заявку и потом
переоформлять её в авансовый (app.services.wish_advance_conversion) для этого
сценария лишний шаг.

ПРАВИЛО №6 — второй механизм не заводим:
  - валидация субсидии/категорий, остаток плановой позиции (409 при
    превышении, включая занятость листовой категории целиком) и сборка
    item_dicts — ТОЛЬКО app.services.plan_to_wish.build_items_from_plan (тот
    же источник, что и «в заявку», второй расчёт остатка здесь не заводим);
  - сама закупка + авто-компаньон (Wish source='advance_report',
    status='draft') — ТОЛЬКО app.routers.purchases.create_purchase, вызванная
    напрямую с purchase_method='advance' и wish_id=None (та же ветка, что уже
    использует ручное «Новый авансовый отчёт» — см. её докстринг про
    is_advance/auto_wish) — не копия её тела ни на йоту.

Товар из каталога НЕОБЯЗАТЕЛЕН (в отличие от «в заявку», где владелец в задаче
2 plan_to_wish.py запретил пустой product_id): build_items_from_plan уже берёт
item_name из имени плановой позиции, когда product не выбран — здесь это
используется НАПРЯМУЮ, без специальной ветки. Если товар не выбран,
create_purchase САМ заведёт Product по item_name (см. её тело, блок `if not
d.get("product_id") and d.get("item_name")`) — пользователю не нужно заранее
заводить товар в каталоге вручную.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.plan_to_wish import PlanToWishItemInput, build_items_from_plan


async def create_purchase_from_plan(
    db: AsyncSession,
    current_user,
    subsidy_id: int,
    title: Optional[str],
    items: list[PlanToWishItemInput],
) -> dict:
    """POST /feo-planned-items/plan-to-wish/create-advance — заводит
    Purchase(purchase_method='advance') на остаток плановых позиций, с
    авто-компаньоном (заявка на возмещение, см. докстринг модуля)."""
    from app.routers.purchases import create_purchase
    from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate

    item_dicts, warnings, categories_used, _subsidy = await build_items_from_plan(db, subsidy_id, items)

    feo_category_id = next(iter(categories_used)) if len(categories_used) == 1 else None

    purchase_items = [
        PurchaseItemCreate(
            product_id=d["product_id"],
            item_name=d["item_name"],
            item_type=d["item_type"],
            quantity=d["quantity"],
            unit=d["unit"],
            unit_price=d["unit_price"],
            total_price=d["total_price"],
            feo_category_id=d["feo_category_id"],
            feo_planned_item_id=d["feo_planned_item_id"],
            match_confirmed=True,
        )
        for d in item_dicts
    ]

    # Purchase не хранит «название» как Wish.title — item_name/item_type
    # верхнего уровня остаются legacy-полем ОДНОЙ позиции (используется как
    # displayName в реестре авансовых, см. AdvanceReportsView.vue). Явный
    # title от пользователя побеждает; иначе — имя первой позиции (+ пометка
    # «и ещё N», если позиций больше одной), чтобы список авансовых не
    # показывал закупку без названия.
    if title and title.strip():
        top_item_name = title.strip()[:500]
    elif len(purchase_items) == 1:
        top_item_name = purchase_items[0].item_name
    elif purchase_items:
        top_item_name = f"{purchase_items[0].item_name} и ещё {len(purchase_items) - 1} поз."[:500]
    else:
        top_item_name = None

    data = PurchaseCreate(
        purchase_method="advance",
        purchase_basis="plan_schedule",
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        status="wishes",
        item_type=purchase_items[0].item_type if purchase_items else None,
        item_name=top_item_name,
        items=purchase_items,
    )

    # admin_override/context — явные литералы, не Query()-дефолты роутера
    # (create_purchase вызывается напрямую, в обход FastAPI-DI, тот же приём,
    # что и create_wish_from_plan с app.routers.wishes.create_wish).
    result = await create_purchase(data=data, admin_override=False, context=None, db=db, current_user=current_user)

    result_warnings = [
        (w.get("message") if isinstance(w, dict) else str(w))
        for w in (result.get("excess_warnings") or [])
    ]

    return {
        "purchase_id": result["id"],
        "registry_number": result.get("registry_number"),
        "wish_id": result.get("wish_id"),
        "items_count": len(purchase_items),
        "warnings": [*warnings, *result_warnings],
    }
