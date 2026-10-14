"""Единственный писатель истории описаний товара каталога (ПРАВИЛО №6, план
item-tz-description.md, Этап В, владелец 14.10.2026). ВСЕ пути, которые
реально меняют Product.description / Product.description_44fz у
СУЩЕСТВУЮЩЕГО товара (PUT/PATCH в app/routers/products.py, принятие
предложения в app/services/product_description_proposals.py, откат истории)
обязаны идти через set_product_description — вторую функцию записи текста
описания не писать.

Не коммитит сессию — вызывающий код сам решает транзакцию (как и остальные
сервисы на этом слое, см. app/services/price_actualization.py).
"""
from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_description_history import ProductDescriptionHistory
from app.models.user import User

DESCRIPTION_FIELDS = ("description", "description_44fz")

Source = Literal["edit", "proposal", "revert", "fill_empty"]


async def set_product_description(
    db: AsyncSession,
    product: Product,
    field: str,
    value: Optional[str],
    user: Optional[User],
    source: Source,
    proposal_id: Optional[int] = None,
) -> Optional[ProductDescriptionHistory]:
    """Пишет историю и применяет новое значение к товару, ЕСЛИ значение
    реально отличается от текущего (не плодим пустые строки истории на
    сохранение формы без изменений описания). Возвращает созданную запись
    истории или None, если менять было нечего."""
    if field not in DESCRIPTION_FIELDS:
        raise ValueError(f"Неизвестное поле описания: {field}")

    old_value = getattr(product, field)
    normalized_old = (old_value or "").strip() or None
    normalized_new = (value or "").strip() or None
    if normalized_old == normalized_new:
        return None

    history = ProductDescriptionHistory(
        product_id=product.id,
        field=field,
        old_value=old_value,
        new_value=value,
        user_id=getattr(user, "id", None) if user else None,
        changed_at=datetime.utcnow(),
        source=source,
        proposal_id=proposal_id,
    )
    db.add(history)
    setattr(product, field, value)
    product.updated_at = datetime.utcnow()
    if user is not None:
        product.updated_by = getattr(user, "full_name", None) or getattr(user, "username", None)
    await db.flush()
    return history


async def revert_product_description(
    db: AsyncSession, product: Product, history_id: int, user: Optional[User],
) -> ProductDescriptionHistory:
    """Возвращает значение поля описания к old_value указанной записи
    истории — через ту же единственную точку записи (source='revert'), что
    само по себе создаёт НОВУЮ запись истории (история необратима/линейна,
    «вернуть прежнее» не удаляет и не редактирует старые строки)."""
    row = (await db.execute(
        select(ProductDescriptionHistory).where(
            ProductDescriptionHistory.id == history_id,
            ProductDescriptionHistory.product_id == product.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise ValueError("Запись истории не найдена для этого товара")
    created = await set_product_description(
        db, product, row.field, row.old_value, user, source="revert",
    )
    # Откат к значению, совпадающему с текущим, — действие без эффекта, но
    # пользователь явно нажал «вернуть прежнее»: отдаём ему ту же запись как
    # подтверждение, не 400 «ничего не изменилось».
    return created or row
