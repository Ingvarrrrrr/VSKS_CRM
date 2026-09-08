"""Ссылочные хелперы категорий ФЭО: перевод ссылок при переезде узла
(`_relink_feo_category`) и подсчёт того, что на узле висит (`_feo_category_load`).

Вынесено из app/routers/feo_import.py (Правило №5, разрезание 1088-строчного
роутера) без изменения поведения — чистая логика без FastAPI-декораторов,
поэтому уехала в services/, а не в routers/-соседа. Re-export в
app.routers.feo_import ОБЯЗАТЕЛЕН: feo_import_remap.py/feo_import_report.py
делают `from app.routers.feo_import import _feo_category_load,
_relink_feo_category` ЛОКАЛЬНО (внутри функции, не на уровне модуля) — этот
приём против цикла (feo_import.py импортирует _do_feo_import из
feo_import_engine на уровне модуля) сохраняется независимо от того, где
физически лежит тело функций, лишь бы имена были достижимы через
app.routers.feo_import. Точно так же feo_categories.py ре-экспортирует эти
два имени лениво (`_LAZY_REEXPORTS`, PEP 562 `__getattr__`), указывая на
app.routers.feo_import, — тот путь тоже продолжает работать через re-export.
"""
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.routers import feo_categories as fc


async def _relink_feo_category(old_id: int, new_id: int, db: AsyncSession) -> dict:
    """Перевести все ссылки со старой категории на новую. Не коммитит.
    Возвращает счётчик переехавших строк по каждой таблице."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    counts: dict[str, int] = {}

    def _rowcount(result) -> int:
        rc = result.rowcount
        return rc if rc and rc > 0 else 0

    result = await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchases"] = _rowcount(result)

    result = await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchase_items"] = _rowcount(result)

    result = await db.execute(
        Wish.__table__.update().where(Wish.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wishes"] = _rowcount(result)

    result = await db.execute(
        WishItem.__table__.update().where(WishItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wish_items"] = _rowcount(result)

    result = await db.execute(
        Product.__table__.update().where(Product.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["products"] = _rowcount(result)

    # Плановые позиции — с дедупликацией по имени (регистронезависимо, trim)
    old_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == old_id)
    )).scalars().all()
    new_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == new_id)
    )).scalars().all()
    new_by_name = {(i.name or "").strip().lower(): i for i in new_items}

    planned_items_moved = 0
    for item in old_items:
        key = (item.name or "").strip().lower()
        existing = new_by_name.get(key)
        if existing is not None:
            await db.execute(
                PurchaseItem.__table__.update()
                .where(PurchaseItem.feo_planned_item_id == item.id)
                .values(feo_planned_item_id=existing.id)
            )
            await db.execute(
                FeoPlannedItem.__table__.delete().where(FeoPlannedItem.id == item.id)
            )
        else:
            await db.execute(
                FeoPlannedItem.__table__.update()
                .where(FeoPlannedItem.id == item.id)
                .values(feo_category_id=new_id)
            )
            new_by_name[key] = item
        planned_items_moved += 1
    counts["feo_planned_items"] = planned_items_moved

    return counts


async def _feo_category_load(ids: list[int], db: AsyncSession) -> dict:
    """Что висит на переданных категориях: количества по каждой из ссылающихся
    таблиц + список блокирующих закупок с человекочитаемым статусом.
    Позволяет вызывающему решить, пуст ли узел, и показать пользователю причину.

    own_data (2026-08, боевая причина): раньше "пусто" проверялось ТОЛЬКО по
    внешним ссылкам (закупки/позиции/заявки/товары/плановые позиции). Собственные
    данные категории — план (planned_quantity/planned_amount), финансирование
    (budget) и поля ФЭО (feo_quantity/feo_amount) — не считались ничем, поэтому
    категория с планом на 10 130 000 руб., но без единой ссылки, признавалась
    пустой и удалялась молча. Так дважды пропадала с прода категория
    «(DONGFENG) JUNFENG K33». own_data = сколько из переданных id имеют хоть одно
    из этих полей not NULL и не ноль — вызывающий код обязан учитывать его наравне
    с остальными ссылками при решении "пуст ли узел".
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.routers.purchase_transitions import STATUS_LABELS

    purchases_count = (await db.execute(
        select(func.count(Purchase.id)).where(Purchase.feo_category_id.in_(ids))
    )).scalar_one()
    purchase_items_count = (await db.execute(
        select(func.count(PurchaseItem.id)).where(PurchaseItem.feo_category_id.in_(ids))
    )).scalar_one()
    wishes_count = (await db.execute(
        select(func.count(Wish.id)).where(Wish.feo_category_id.in_(ids))
    )).scalar_one()
    wish_items_count = (await db.execute(
        select(func.count(WishItem.id)).where(WishItem.feo_category_id.in_(ids))
    )).scalar_one()
    products_count = (await db.execute(
        select(func.count(Product.id)).where(Product.feo_category_id.in_(ids))
    )).scalar_one()
    planned_items_count = (await db.execute(
        select(func.count(FeoPlannedItem.id)).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalar_one()
    own_data_count = (await db.execute(
        select(func.count(FeoCategory.id)).where(
            FeoCategory.id.in_(ids),
            or_(
                and_(FeoCategory.budget.isnot(None), FeoCategory.budget != 0),
                and_(FeoCategory.feo_quantity.isnot(None), FeoCategory.feo_quantity != 0),
                and_(FeoCategory.feo_amount.isnot(None), FeoCategory.feo_amount != 0),
                and_(FeoCategory.planned_quantity.isnot(None), FeoCategory.planned_quantity != 0),
                and_(FeoCategory.planned_amount.isnot(None), FeoCategory.planned_amount != 0),
            ),
        )
    )).scalar_one()

    blocking = await fc._collect_blocking_purchases(ids, db)
    purchases_list = [
        {
            "id": p.id,
            "purchase_number": p.purchase_number,
            "subject": p.subject,
            "status": p.status,
            "status_label": STATUS_LABELS.get(p.status, p.status),
        }
        for p in blocking
    ]

    return {
        "purchases": purchases_count,
        "purchase_items": purchase_items_count,
        "wishes": wishes_count,
        "wish_items": wish_items_count,
        "products": products_count,
        "feo_planned_items": planned_items_count,
        "own_data": own_data_count,
        "blocking_purchases": purchases_list,
    }
