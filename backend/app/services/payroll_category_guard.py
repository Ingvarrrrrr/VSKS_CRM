"""Правило владельца (22.10.2026, заявка №209: генераторы из плана «Закупка
оборудования» согласующий перевёл в статью «Заработная плата работников» —
система молча приняла): «Товары и услуги нельзя переносить в статью ФОТ /
заработной платы». Позицию с item_type товар/услуга/работа НЕЛЬЗЯ поставить
в статью ФЭО, которая эффективно ФОТ (FeoCategory.is_payroll=True у самой
статьи ИЛИ у ЛЮБОГО её предка). Позиции с пустым item_type (NULL/'') —
разрешены (так лежат зарплатные выплаты из импорта факта: закупка «ЗП»,
item_type NULL).

ЕДИНСТВЕННОЕ место этого правила (ПРАВИЛО №6) — импортировать эту функцию
везде, где пользователь меняет статью позиции/шапки, тип позиции, или
включает галочку `is_payroll` у статьи. Второй такой проверки по коду не
заводить.

Эффективность ФОТ категории берётся ТОЛЬКО через существующий резолвер
app.services.feo_payroll.payroll_category_ids (единственный обход дерева
«себя или предок», второй обход здесь не пишем). Эффективная категория
позиции (когда нужно учесть режим per_item/категорию шапки) — через
app.services.feo_effective_category.effective_item_feo_category_id,
импортируется, не копируется.
"""
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feo_payroll import payroll_category_ids
from app.services.item_type_split import kind_of, KIND_GOODS, KIND_SERVICES

_MAX_NAMES_IN_MESSAGE = 5


def default_wish_item_type(item_data: dict) -> Optional[str]:
    """ЕДИНСТВЕННОЕ место дефолта «нет типа у позиции заявки → товар»
    (ПРАВИЛО №6, QA S5, 22.10.2026): до этой правки WishItem.item_type нёс
    Column(default="товар") — Python-side default срабатывал и на ЯВНЫЙ
    None (plan_to_wish отдаёт None для позиций без типа в статье ФОТ), так
    что итоговая заявка молча получала item_type='товар' и упиралась в
    payroll_category_guard. default=... на колонке убран (app/models/
    wish_item.py) — дефолт теперь только здесь.

    Правило: если ключ 'item_type' ОТСУТСТВУЕТ в item_data — 'товар' (как
    было); если ключ присутствует со значением None/'' — возвращается как
    есть (None), значение НЕ подменяется. Используется во ВСЕХ точках
    создания WishItem из словаря (routers/wishes.py::create_wish/update_wish
    draft-пересборка) — не копировать `.get('item_type', 'товар')` по месту.

    Копирование заявки (copy_wish) и компаньон авансового отчёта
    (advance_wish_sync.wish_item_kwargs_from_purchase_item) сюда не
    обращаются — они копируют item_type источника (WishItem/PurchaseItem)
    как есть, без дефолта, им эта функция не нужна."""
    if "item_type" in item_data:
        return item_data["item_type"]
    return "товар"


def _item_name(item) -> str:
    if isinstance(item, dict):
        return str(item.get("item_name") or item.get("name") or item.get("id") or "позиция")
    return str(
        getattr(item, "item_name", None)
        or getattr(item, "name", None)
        or getattr(item, "id", None)
        or "позиция"
    )


def _item_type(item) -> Optional[str]:
    if isinstance(item, dict):
        return item.get("item_type")
    return getattr(item, "item_type", None)


def is_goods_or_services(item_type: Optional[str]) -> bool:
    """Товар/услуга/работа — запрещено в ФОТ; пустой тип (NULL/'') —
    разрешён (зарплатные выплаты из импорта факта, см. докстринг модуля).

    ЕДИНСТВЕННАЯ проверка «это товар/услуга/работа» для правила ФОТ
    (ПРАВИЛО №6) — построена на item_type_split.kind_of (та же нормализация,
    что и везде в проекте); второй захардкоженный кортеж ("товар","услуга",
    "работа") не заводить (найдено дублем в feo_import_apply.py — переведён
    на эту функцию)."""
    return kind_of(item_type) in (KIND_GOODS, KIND_SERVICES)


def _is_goods_or_services(item) -> bool:
    return is_goods_or_services(_item_type(item))


def build_payroll_violation_message(category_name: str, item_names: list[str]) -> str:
    """ЕДИНСТВЕННЫЙ текст ошибки правила — не копировать строкой по месту
    вызова (ПРАВИЛО №6)."""
    shown = item_names[:_MAX_NAMES_IN_MESSAGE]
    names_part = ", ".join(f"«{n}»" for n in shown)
    rest = len(item_names) - len(shown)
    if rest > 0:
        names_part += f"… (и ещё {rest})"
    return (
        f"Статья «{category_name}» — ФОТ (зарплата и выплаты персоналу). "
        f"Товары, услуги и работы в неё ставить нельзя: {names_part}. "
        f"Выберите статью товаров или услуг."
    )


async def assert_no_goods_in_payroll(
    db: AsyncSession,
    category_id: Optional[int],
    items: Iterable,
) -> None:
    """422, если `category_id` эффективно ФОТ (себя или предок, через
    payroll_category_ids), а среди `items` (объекты PurchaseItem/WishItem/
    FeoPlannedItem или dict с полями item_name/item_type) есть хотя бы одна
    позиция с типом товар/услуга/работа.

    Ничего не проверяет, если category_id не задан — звонить ПОСЛЕ того,
    как итоговая категория позиции/шапки известна."""
    if category_id is None:
        return

    from sqlalchemy import select
    from app.models.feo_category import FeoCategory

    cat = (
        await db.execute(select(FeoCategory).where(FeoCategory.id == category_id))
    ).scalar_one_or_none()
    if cat is None:
        return

    payroll_ids = await payroll_category_ids(db, [cat.subsidy_id])
    if category_id not in payroll_ids:
        return

    offending = [_item_name(it) for it in items if _is_goods_or_services(it)]
    if not offending:
        return

    raise HTTPException(
        status_code=422,
        detail=build_payroll_violation_message(cat.name, offending),
    )


async def assert_category_not_payroll_for_single_item(
    db: AsyncSession,
    category_id: Optional[int],
    item_type: Optional[str],
    item_name: Optional[str] = None,
) -> None:
    """Удобная обёртка assert_no_goods_in_payroll для ОДНОЙ позиции (случай,
    когда вызывающий код меняет item_type или feo_category_id одной строки
    и не хочет собирать список items вручную)."""
    await assert_no_goods_in_payroll(
        db, category_id, [{"item_name": item_name or "позиция", "item_type": item_type}],
    )


async def assert_category_can_become_payroll(db: AsyncSession, category_id: int) -> None:
    """422, если у статьи `category_id` (или в её поддереве — через
    payroll_category_ids ПОСЛЕ гипотетического включения признака) уже лежат
    товары/услуги/работы — вызывать ПЕРЕД тем, как сохранить
    FeoCategory.is_payroll=True на существующей статье (владелец, 22.10.2026:
    нельзя включать ФОТ на статье, где уже есть товары/услуги — иначе то же
    нарушение образуется в обратную сторону).

    Проверяет ТРИ источника позиций статьи и её поддерева:
    - плановые позиции (FeoPlannedItem) — только is_active=True (деактивированные
      не считаются «лежащими в статье»);
    - позиции закупок (PurchaseItem) — ПО ЭФФЕКТИВНОЙ категории (своя
      feo_category_id, иначе категория шапки закупки при feo_per_item=False —
      тот же резолвер, что и у assert_no_goods_in_payroll/create_purchase,
      app.services.feo_effective_category.effective_item_feo_category_id;
      иначе товар закупки, у которой категория задана ТОЛЬКО на шапке,
      никогда бы не найдётся). Остановленные закупки (Purchase.stopped_at
      задан) не учитываются — они больше не расходуют план;
    - позиции заявок (WishItem) — та же эффективная категория относительно
      шапки заявки (Wish.feo_category_id/feo_per_item); остановленные заявки
      (Wish.stopped_at задан) не учитываются (симметрично закупкам)."""
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.services.feo_effective_category import effective_item_feo_category_id

    cat = (
        await db.execute(select(FeoCategory).where(FeoCategory.id == category_id))
    ).scalar_one_or_none()
    if cat is None:
        return

    rows = (
        await db.execute(
            select(FeoCategory.id, FeoCategory.parent_id).where(FeoCategory.subsidy_id == cat.subsidy_id)
        )
    ).all()
    children_of: dict = {}
    for r in rows:
        children_of.setdefault(r.parent_id, []).append(r.id)

    subtree_ids: set[int] = set()
    stack = [category_id]
    while stack:
        cid = stack.pop()
        if cid in subtree_ids:
            continue
        subtree_ids.add(cid)
        stack.extend(children_of.get(cid, []))

    offending: list[str] = []

    plan_rows = (
        await db.execute(
            select(FeoPlannedItem.name, FeoPlannedItem.item_type).where(
                FeoPlannedItem.feo_category_id.in_(subtree_ids),
                FeoPlannedItem.is_active.is_(True),
            )
        )
    ).all()
    offending.extend(r.name or "позиция плана" for r in plan_rows if is_goods_or_services(r.item_type))

    # Позиции закупок: ЭФФЕКТИВНАЯ категория (своя, иначе шапка закупки при
    # feo_per_item=False) — своя feo_category_id ИЛИ (feo_per_item=False И
    # шапка закупки в поддереве) попадает в subtree_ids. Остановленные
    # закупки (stopped_at) исключены на уровне SQL, не в Python-фильтре.
    purchase_rows = (
        await db.execute(
            select(
                PurchaseItem.item_name, PurchaseItem.item_type,
                PurchaseItem.feo_category_id, Purchase.feo_category_id.label("header_cat_id"),
                Purchase.feo_per_item,
            )
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(Purchase.stopped_at.is_(None), Purchase.subsidy_id == cat.subsidy_id)
        )
    ).all()
    for r in purchase_rows:
        eff_cat_id = effective_item_feo_category_id(
            bool(r.feo_per_item), r.header_cat_id, r.feo_category_id,
        )
        if eff_cat_id in subtree_ids and is_goods_or_services(r.item_type):
            offending.append(r.item_name or "позиция закупки")

    wish_rows = (
        await db.execute(
            select(
                WishItem.item_name, WishItem.item_type,
                WishItem.feo_category_id, Wish.feo_category_id.label("header_cat_id"),
                Wish.feo_per_item,
            )
            .join(Wish, Wish.id == WishItem.wish_id)
            .where(Wish.stopped_at.is_(None), Wish.subsidy_id == cat.subsidy_id)
        )
    ).all()
    for r in wish_rows:
        eff_cat_id = effective_item_feo_category_id(
            bool(r.feo_per_item), r.header_cat_id, r.feo_category_id,
        )
        if eff_cat_id in subtree_ids and is_goods_or_services(r.item_type):
            offending.append(r.item_name or "позиция заявки")

    if not offending:
        return

    raise HTTPException(
        status_code=422,
        detail=build_payroll_violation_message(cat.name, offending),
    )
