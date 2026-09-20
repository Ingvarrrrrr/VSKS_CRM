"""Ядро «свёрнуть категорию ФЭО в плановую позицию» (владелец, 2026-09-20).

КОНТЕКСТ: старый фолбэк импорта ФЭО (services/feo_import_apply.py:1083-1119 —
план, заданный прямо на строке листовой категории) создавал КАТЕГОРИЮ и внутри
неё ОДНУ плановую позицию (FeoPlannedItem) того же имени, вместо того чтобы
завести саму позицию сразу в родительской категории. На бою таких пар
категория+единственная-позиция 240 штук — лишний уровень дерева без смысла.
Это действие убирает категорию, оставляя её единственную плановую позицию на
месте (в родительской категории).

Правило №6 (один показатель — один источник истины): проверки условий
свёртки собраны в ОДНОЙ функции check_collapse_conflict — её же вызывают и
GET /collapse-candidates (чтобы заполнить blocked_reason ТЕМИ ЖЕ текстами,
какими POST откажет), и POST /{cat_id}/collapse-to-item (чтобы бросить 409).
Блокировка по закупкам стадии «Ведётся работа» переиспользует
app.routers.feo_categories._collect_blocking_purchases — тот же текст и тот
же набор статусов, что и у DELETE /feo-categories/{id} (не второй набор
статусов).

Перенос ссылок (Purchase/PurchaseItem/Product/Wish/WishItem.feo_category_id)
переиспользует тот же паттерн bulk UPDATE, что и _purge_feo_categories в
feo_categories.py; перенос самой плановой позиции — существующую
app.services.plan_autoassign.move_planned_item_to_category (та же функция,
что и у PUT /feo-planned-items/{id} и у автопереноса вслед за закупкой/
заявкой) — не заводим вторую копию этой логики.

Правило №5 (модульность): роутер (app/routers/feo_categories_collapse.py)
несёт только HTTP-оркестрацию (гейты доступа, коммит, сборку ответа); вся
проверочная/переносная логика — здесь.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


def category_own_feo_pair(cat: FeoCategory) -> Optional[tuple]:
    """Собственная «сумма ФЭО» категории, заданная ПРЯМО на ней (а не
    посчитанная по детям — у листа без детей авторасчёт по детям и так даёт
    0, поэтому здесь читаем поля напрямую).

    Приоритет: (feo_quantity, feo_amount, feo_unit) — числа «по документу
    ФЭО» (feo_amount там — цена ЗА ЕДИНИЦУ, см. докстринг FeoCategory);
    иначе — (planned_quantity, planned_amount, unit), старый формат
    CRM-плана листа (planned_amount тоже цена за единицу, см.
    _validate_plan_pair в feo_categories.py). Обе пары валидны только когда
    ОБА числа пары заданы и положительны — половина пары не считается «своей
    суммой», просто мусор в одном поле.

    FeoCategory.budget («итоговая сумма строки») сознательно НЕ участвует —
    это отдельный потолок финансирования узла (используется как ceiling в
    compute_feo_plan_tree, не как слагаемое суммы плана), а не число для
    переноса на позицию; аналога budget у FeoPlannedItem нет.

    Возвращает (total_amount, quantity, unit_price, unit) или None.
    """
    if (
        cat.feo_quantity is not None and cat.feo_amount is not None
        and float(cat.feo_quantity) > 0 and float(cat.feo_amount) > 0
    ):
        total = Decimal(str(cat.feo_quantity)) * Decimal(str(cat.feo_amount))
        return (total, cat.feo_quantity, cat.feo_amount, cat.feo_unit)
    if (
        cat.planned_quantity is not None and cat.planned_amount is not None
        and float(cat.planned_quantity) > 0 and float(cat.planned_amount) > 0
    ):
        total = Decimal(str(cat.planned_quantity)) * Decimal(str(cat.planned_amount))
        return (total, cat.planned_quantity, cat.planned_amount, cat.unit)
    return None


async def collapse_children_count(db: AsyncSession, cat_id: int) -> int:
    return (await db.execute(
        select(func.count()).select_from(FeoCategory).where(FeoCategory.parent_id == cat_id)
    )).scalar_one()


async def collapse_active_items(db: AsyncSession, cat_id: int) -> list[FeoPlannedItem]:
    return (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == cat_id)
        .where(FeoPlannedItem.is_active.is_(True))
        .order_by(FeoPlannedItem.id)
    )).scalars().all()


async def check_collapse_conflict(db: AsyncSession, cat: FeoCategory) -> FeoPlannedItem:
    """Все условия свёртки категории в плановую позицию — ЕДИНАЯ проверка
    (Правило №6), переиспользуемая и GET /collapse-candidates (blocked_reason,
    перехватывает HTTPException и берёт e.detail как текст), и
    POST /{cat_id}/collapse-to-item (даёт 409 как есть). Возвращает
    единственную активную плановую позицию категории при успехе.
    """
    if cat.parent_id is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Корневую категорию нельзя свернуть в плановую позицию — у неё "
                "нет родительской категории, куда перенести закупки и позицию."
            ),
        )
    children_count = await collapse_children_count(db, cat.id)
    if children_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"У категории есть подкатегории ({children_count}) — сначала "
                f"сверните или перенесите их, категория с детьми не сворачивается."
            ),
        )
    items = await collapse_active_items(db, cat.id)
    if len(items) == 0:
        raise HTTPException(
            status_code=409,
            detail="У категории нет ни одной активной плановой позиции — сворачивать нечего.",
        )
    if len(items) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"У категории {len(items)} активных плановых позиций — свернуть в "
                f"позицию можно только категорию ровно с одной."
            ),
        )

    # Блокировка закупками «Ведётся работа» и далее — тот же текст/набор
    # статусов, что и у DELETE /feo-categories/{id} (см. её докстринг).
    from app.routers import feo_categories as fc
    blocking = await fc._collect_blocking_purchases([cat.id], db)
    if blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Нельзя свернуть: {len(blocking)} закупок со стадией «Ведётся "
                    f"работа» и далее привязано к этой категории. Закупки на ранних "
                    f"стадиях (желания, план закупок) сворачиванию не мешают."
                ),
                "purchase_ids": [p.id for p in blocking],
            },
        )
    return items[0]


def transfer_feo_money(cat: FeoCategory, item: FeoPlannedItem) -> None:
    """Перенести «свою сумму ФЭО» категории (см. category_own_feo_pair) на
    единственную плановую позицию, если у категории она задана, а у позиции
    своих feo_*-чисел ещё нет. Если у ОБЕИХ задано и суммы не совпадают —
    409 (не молчаливая перезапись чужого числа). Мутирует item на месте,
    ничего не коммитит.
    """
    own = category_own_feo_pair(cat)
    if own is None:
        return
    total, qty, unit_price, unit = own
    item_has_feo = item.feo_amount is not None and float(item.feo_amount) > 0
    if item_has_feo:
        if abs(float(item.feo_amount) - float(total)) > 0.01:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"У категории «{cat.name}» задана сумма ФЭО {total:,.2f} ₽, а у "
                    f"позиции «{item.name}» уже задана своя сумма ФЭО "
                    f"{float(item.feo_amount):,.2f} ₽ — числа не совпадают, перенос "
                    f"отменён, разберитесь вручную, какое из двух верно."
                ),
            )
        return  # уже совпадает — переносить нечего
    item.feo_amount = total
    if qty is not None:
        item.feo_quantity = qty
    item.feo_unit_price = unit_price
    # Владелец: перенесённое число — это и есть «построчная разбивка по ФЭО»
    # для этой позиции (категория, из которой оно приехало, была ровно такой
    # разбивкой — лист с одной позицией и своей суммой по документу ФЭО).
    item.is_feo_breakdown = True


# Модели, ссылающиеся на FeoCategory.feo_category_id напрямую (ondelete=SET
# NULL на каждой) — при свёртке ссылки переезжают на cat.parent_id, а НЕ
# обнуляются (в отличие от _purge_feo_categories при удалении дерева).
_RELINK_TARGETS = ("purchases", "purchase_items", "products", "wishes", "wish_items")


async def bulk_relink_category_refs(db: AsyncSession, cat_id: int, parent_id: int) -> dict:
    """UPDATE feo_category_id: cat_id → parent_id у Purchase/PurchaseItem/
    Product/Wish/WishItem одним bulk-запросом на модель, rowcount на выходе —
    контракт moved_refs POST /{cat_id}/collapse-to-item. Плановые позиции
    (FeoPlannedItem) сюда НЕ входят — их переезд отдельно, через
    app.services.plan_autoassign.move_planned_item_to_category (см.
    relink_remaining_planned_items ниже про НЕактивные позиции той же
    категории)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    counts: dict[str, int] = {}
    for label, model in (
        ("purchases", Purchase),
        ("purchase_items", PurchaseItem),
        ("products", Product),
        ("wishes", Wish),
        ("wish_items", WishItem),
    ):
        result = await db.execute(
            model.__table__.update()
            .where(model.feo_category_id == cat_id)
            .values(feo_category_id=parent_id)
        )
        counts[label] = result.rowcount or 0
    return counts


async def relink_remaining_planned_items(db: AsyncSession, cat_id: int, parent_id: int, skip_item_id: int) -> None:
    """Подчищает НЕактивные FeoPlannedItem, которые могли остаться под
    категорией (свёртка требует ровно ОДНУ активную позицию, но не запрещает
    существование архивных неактивных — is_active=False). FeoCategory.id —
    FK ondelete=CASCADE у feo_planned_items.feo_category_id: если их не
    перенести перед удалением категории, они удалятся каскадом вместе с
    категорией, что может оставить висячие ссылки purchase_items/wish_items
    на них (feo_planned_item_id БЕЗ FK-констрейнта в БД — см. докстринг
    delete_planned_item в feo_planned_items.py). Не входит в moved_refs
    (контракт ответа перечисляет только пять моделей выше) — тихая защита
    целостности, а не видимый пользователю перенос."""
    await db.execute(
        FeoPlannedItem.__table__.update()
        .where(FeoPlannedItem.feo_category_id == cat_id)
        .where(FeoPlannedItem.id != skip_item_id)
        .values(feo_category_id=parent_id)
    )
