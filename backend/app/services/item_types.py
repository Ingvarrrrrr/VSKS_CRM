"""Единый источник типа позиции «товар/услуга/работа» (ПРАВИЛО №6, план
corrections-21-09.md, раздел W2 — решение владельца от 21.09: у плановой
позиции ФЭО обязано быть поле «Тип», автозаполняемое из каталога, и при
осознанном выборе человека тип обязан переноситься обратно в товар каталога).

Вынесено из app/routers/feo_planned_items.py (там normalize_item_type жил
раньше и использовался И для FeoPlannedItem.item_type, И как единственный
нормализатор для импорта ФЭО/сверки item_type_split) — теперь это ЕДИНАЯ
точка для обоих потребителей:
  - FeoPlannedItem.item_type (models/feo_planned_item.py) — тип плановой
    позиции, вводится вручную или через импорт ФЭО;
  - Product.item_kind (models/product.py) — тип товара каталога, тот же
    набор значений (раньше комментарий на колонке ограничивал его до
    «товар»/«услуга» — по факту нигде не валидировался, и «работа» проходит
    так же свободно, как и два других значения).

app.routers.feo_planned_items ПРОДОЛЖАЕТ экспортировать имя
`normalize_item_type` (реэкспорт из этого модуля) — другие файлы, которые
импортируют его оттуда (app/services/feo_import_apply.py,
app/services/item_type_split.py), трогать не нужно.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.feo_planned_item import FeoPlannedItem
from app.services.product_catalog_match import normalize_product_name, _sql_normalized_name_expr

# Единственный источник допустимых значений — FeoPlannedItem.item_type и
# Product.item_kind используют РОВНО этот набор, нигде не дублируется.
ITEM_TYPES: tuple[str, ...] = ("товар", "услуга", "работа")


def normalize_item_type(v: Optional[str]) -> Optional[str]:
    """Признак «Товар/Услуга/Работа» — приводит свободный ввод (в т.ч. импорт
    ФЭО и шаблон импорта каталога) к одному из трёх нижнерегистрных значений
    ITEM_TYPES, как в purchase_items.item_type/wish_items.item_type. Пусто/
    непонятное значение → None (поле необязательное)."""
    if not v:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if s.startswith("тов"):
        return "товар"
    if s.startswith("усл"):
        return "услуга"
    if s.startswith("раб"):
        return "работа"
    return None


async def apply_item_type_to_product(
    db: AsyncSession, product_id: Optional[int], item_type: Optional[str]
) -> bool:
    """Единственная точка записи Product.item_kind из плановой позиции ФЭО
    (владелец, 21.09, раздел W2): «если у товара каталога тип пуст/другой и
    пользователь задал тип — записать в товар каталога». Вызывается из
    create_planned_item/create_planned_items_bulk/update_planned_item
    (app/routers/feo_planned_items.py) при явном sync_product_kind=true —
    НЕ дублируется в каждой точке отдельной формулой (ПРАВИЛО №6).

    item_type ожидается уже нормализованным (см. normalize_item_type выше).
    Ничего не делает и возвращает False, если product_id/item_type не
    заданы, item_type не входит в ITEM_TYPES, товар не найден, либо
    item_kind товара УЖЕ равен переданному значению (нечего менять — не
    трогаем updated_at/прочие поля товара впустую).

    Не коммитит — коммит остаётся за вызывающим эндпоинтом (та же
    транзакция, что и запись самой плановой позиции)."""
    if not product_id or not item_type or item_type not in ITEM_TYPES:
        return False
    product = (
        await db.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        return False
    if product.item_kind == item_type:
        return False
    product.item_kind = item_type
    return True


async def resolve_product_for_planned_item(
    db: AsyncSession, item: FeoPlannedItem
) -> Optional[int]:
    """Плановая позиция ФЭО не хранит product_id (транзитное поле запроса —
    см. докстринг FeoPlannedItemCreate.product_id, backend/app/schemas/feo.py).
    Инлайн-правка типа (useFeoLevel5ItemType.ts) и часть путей диалога правки
    не знают, из какого товара каталога эта позиция когда-то была создана —
    раньше это молча выключало синхронизацию (apply_item_type_to_product
    требует product_id). Здесь — попытка угадать товар БЕЗ гадания: только
    ТОЧНОЕ совпадение нормализованного имени, единая точка нормализации
    каталога (Правило №6) — app.services.product_catalog_match.normalize_product_name
    /_sql_normalized_name_expr, та же формула, что и у find_exact_product.
    НЕ переиспользует find_exact_product напрямую — тот при нескольких дублях
    с одинаковым именем молча выбирает один (pick_preferred, «предпочитает
    запись с ТЗ»); здесь по требованию владельца (21.09, W2) при неоднозначности
    (0 или 2+ совпадений) возвращается None — не трогаем чужой товар вслепую.

    Каталог общий (см. project_products_catalog_shared) — org_id НЕ фильтруется.
    Ничего не пишет и не коммитит — только подбирает id.
    """
    name = getattr(item, "name", None) if item is not None else None
    norm = normalize_product_name(name)
    if not norm:
        return None
    ids = (
        await db.execute(
            select(Product.id).where(_sql_normalized_name_expr() == norm)
        )
    ).scalars().all()
    if len(ids) != 1:
        return None
    return ids[0]
