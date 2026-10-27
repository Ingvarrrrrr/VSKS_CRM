"""Категория/вид каталога для плановых позиций ФЭО (FeoPlannedItem) по ТОЧНОМУ
совпадению названия (задача владельца, 27.10.2026): переключатель «Позиции: По
категориям / Категории + виды» (FeoTreeToolbar.vue, feoItemsGroupBy) группирует
только виртуальные позиции ЗАКУПОК (у них есть product_id товара — см.
app/routers/feo_plan_reads.py, Product.category/product_type через JOIN). У
плановых позиций (FeoPlannedItem — импорт ФЭО и ручные) своего product_id нет —
переключатель на них не действовал.

Решение владельца: плановые позиции часто называются ровно как товар каталога
(выбирались из каталога при создании, диалог добавления копирует имя, но
product_id не хранит — см. FeoPlannedItemCreate.product_id, транзитное поле
запроса). Если нормализованное имя плановой позиции совпадает с нормализованным
именем товара каталога — берём его категорию/вид. НИКАКОГО fuzzy (Правило
проекта «дедуп только точный») — единственная нормализация,
app.services.product_catalog_match.normalize_product_name/_sql_normalized_name_expr
(Правило №6, второй нормализатор здесь не заводим — та же функция, что
resolve_product_for_planned_item в app/services/item_types.py использует для
похожей задачи «угадать товар по точному имени»).

Несколько товаров каталога с одинаковым нормализованным именем, но РАЗНЫМИ
категориями/видами — результат None (неоднозначно, не угадываем). Каталог общий
(org_id не фильтруется — см. память проекта project_products_catalog_shared).
"""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.product_catalog_match import normalize_product_name, _sql_normalized_name_expr

CatalogCategoryMap = dict[str, tuple[Optional[str], Optional[str]]]


async def catalog_categories_by_normalized_name(
    db: AsyncSession, names: Iterable[Optional[str]],
) -> CatalogCategoryMap:
    """Один запрос на весь набор имён (без N+1) — normalize_product_name(name) →
    (категория, вид). Категория/вид пусты (None), если у совпавших товаров
    каталога они расходятся, либо совпадений нет вовсе.

    Product.category у товара практически всегда заполнена (DEFAULT_PRODUCT_CATEGORY,
    not nullable) — расхождение категорий у одноимённых товаров возможно и
    реально встречается на проде (владелец: у 8 из 249 совпавших названий ЗО
    категории разные), product_type нередко NULL у части товаров — такие
    пустые значения не считаются при определении «однозначности».
    """
    norm_names = {normalize_product_name(n) for n in names}
    norm_names.discard("")
    if not norm_names:
        return {}

    rows = (await db.execute(
        select(
            _sql_normalized_name_expr().label("norm_name"),
            Product.category,
            Product.product_type,
        ).where(_sql_normalized_name_expr().in_(norm_names))
    )).all()

    buckets: dict[str, tuple[set, set]] = {}
    for r in rows:
        cats, types = buckets.setdefault(r.norm_name, (set(), set()))
        if r.category:
            cats.add(r.category)
        if r.product_type:
            types.add(r.product_type)

    result: CatalogCategoryMap = {}
    for norm, (cats, types) in buckets.items():
        category = next(iter(cats)) if len(cats) == 1 else None
        product_type = next(iter(types)) if len(types) == 1 else None
        result[norm] = (category, product_type)
    return result


def catalog_category_for_name(name: Optional[str], catalog_map: CatalogCategoryMap) -> tuple[Optional[str], Optional[str]]:
    """Смотрит уже построенную catalog_map (см. функцию выше) по ОДНОМУ имени —
    та же нормализация, второй раз карту не строит."""
    norm = normalize_product_name(name)
    if not norm:
        return (None, None)
    return catalog_map.get(norm, (None, None))
