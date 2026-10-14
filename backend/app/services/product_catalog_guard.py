"""Защита общего каталога товаров (Этап В, план item-tz-description.md,
владелец 14.10.2026): «каталог правят только с галочкой «Редактировать
каталог товаров»». ЕДИНСТВЕННАЯ точка проверки этого права (ПРАВИЛО №6) —
все PUT/PATCH/DELETE по товару и все пути импорта, которые дописывают
описание СУЩЕСТВУЮЩЕГО товара, обязаны звать assert_can_edit_catalog /
can_edit_catalog отсюда, вторую формулу не писать.

Почему без org_id: Product.org_id всегда NULL (каталог общий для всего
приложения, память проекта «Переиспользовать, не дублировать», см. докстринг
app/routers/products.py). У действия нет «своей» орги, которую можно было бы
передать в has_org_key(..., org_id=...) — поэтому используется ТА ЖЕ
проверка, которую FastAPI-фабрики require_tab/require_action уже применяют
для любого НЕ привязанного к конкретному бизнес-объекту action-ключа:
app.auth.permissions._has_key_in_any_org (эффективен ключ хотя бы в одной
орге, доступной пользователю — активная + все его user_org_access). Это тот
же механизм, что и require_action("vehicle.edit") и прочие — не второй.
Кастомная (не дефолтная "Действие запрещено") русская формулировка отказа —
по тому же образцу, что app/routers/purchase_paid_confirmations.py::
_assert_can_decide (свой checker вместо Depends(require_action(...)), когда
нужен текст-с-объяснением, память проекта «Объяснять причину блокировки»).
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import _has_key_in_any_org
from app.models.user import User


def prices_differ(old, new) -> bool:
    """Decimal(БД) vs float/Decimal(из запроса) — сравнение "в лоб" даёт
    ложные срабатывания (Decimal('100') != 100.0 типом при равном значении).
    ЕДИНСТВЕННОЕ место этого сравнения (ПРАВИЛО №6) — используется и
    routers/products.py (PUT/PATCH), и routers/products_price.py
    (price-actualization) для решения, менялась ли цена реально."""
    if old is None and new is None:
        return False
    if old is None or new is None:
        return True
    try:
        return Decimal(str(old)) != Decimal(str(new))
    except Exception:
        return old != new

PRODUCTS_EDIT_CATALOG_ACTION = "products.edit_catalog"

CATALOG_EDIT_DENIED_MESSAGE = (
    "Править общий каталог товаров может только сотрудник с правом "
    "«Редактировать каталог товаров». Предложите правку — её рассмотрят."
)


async def can_edit_catalog(user: User, db: AsyncSession) -> bool:
    """True если user вправе править общий каталог товаров (создание НОВОГО
    товара сюда не относится — об этом см. докстринг роутера/плана, здесь
    только правка СУЩЕСТВУЮЩЕГО)."""
    if user.role == "superadmin":
        return True
    return await _has_key_in_any_org(user, db, PRODUCTS_EDIT_CATALOG_ACTION)


async def assert_can_edit_catalog(user: User, db: AsyncSession) -> None:
    if not await can_edit_catalog(user, db):
        raise HTTPException(status_code=403, detail=CATALOG_EDIT_DENIED_MESSAGE)


# --- Часть 1 плана clever-bouncing-lantern.md (владелец 14.10.2026) ---------
# «Без галочки можно заполнить ПУСТОЕ поле каталога (описание, описание
# 44-ФЗ, фото, цену), но не заменить/стереть уже заполненное». Единственное
# место, где решается этот вопрос по полю (ПРАВИЛО №6) — вызывающий код
# (routers/products.py, routers/products_photos.py) только сравнивает
# старое/новое значение и передаёт сюда РЕАЛЬНО изменившиеся поля, вторую
# такую проверку не писать.
FILL_EMPTY_FIELDS = ("description", "description_44fz", "price", "photo")


def is_fill_empty_change(product: "Product", field: str) -> bool:
    """True, если `field` у `product` сейчас пусто — значит, заполнить его
    может и сотрудник без products.edit_catalog. Любое другое изменение этого
    же поля (стереть непустое, заменить непустое на другое непустое) и любое
    изменение поля, не входящего в FILL_EMPTY_FIELDS, по этой функции
    НЕ разрешается — для них остаётся общая проверка (галочка обязательна)."""
    if field in ("description", "description_44fz"):
        return not (getattr(product, field, None) or "").strip()
    if field == "price":
        return product.price is None
    if field == "photo":
        return not product.photo_data
    return False


async def assert_can_apply_product_changes(
    user: User, db: AsyncSession, product: "Product", changed_fields: dict,
) -> None:
    """changed_fields — {имя_поля: новое_значение}, но ТОЛЬКО для полей, где
    вызывающий код уже убедился, что значение реально меняется (не повторная
    отправка формы с тем же значением — PUT присылает её целиком). Без
    products.edit_catalog пропускает, если КАЖДОЕ изменённое поле —
    заполнение пустого (is_fill_empty_change); иначе 403 тем же текстом, что
    и assert_can_edit_catalog."""
    if not changed_fields:
        return
    if await can_edit_catalog(user, db):
        return
    for field in changed_fields:
        if not is_fill_empty_change(product, field):
            raise HTTPException(status_code=403, detail=CATALOG_EDIT_DENIED_MESSAGE)
